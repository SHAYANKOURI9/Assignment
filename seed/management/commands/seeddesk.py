"""python manage.py seeddesk [--reset]

Idempotent seed: loads sources.json + raw_items.json, creates three demo users,
runs the clusterer, then walks a few stories through the full workflow so the
analytics dashboard is non-empty on first load.
"""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

SEED_DIR = Path(__file__).resolve().parent.parent.parent.parent / "seed"
User = get_user_model()


class Command(BaseCommand):
    help = "Seed the database with demo sources, raw items, users, and stories."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Wipe all desk data first.")

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        self._seed_users()
        self._seed_sources()
        self._seed_raw_items()
        self._run_clustering()
        self._walk_stories()
        self.stdout.write(self.style.SUCCESS("Seed complete."))

    # ------------------------------------------------------------------

    def _reset(self):
        from desk.models import Story, StoryItem, BriefRevision, Publication, Merge, AuditEvent
        from ingest.models import RawItem, Source
        self.stdout.write("Resetting desk data…")
        AuditEvent.objects.all().delete()
        Merge.objects.all().delete()
        Publication.objects.all().delete()
        BriefRevision.objects.all().delete()
        StoryItem.objects.all().delete()
        Story.objects.all().delete()
        RawItem.objects.all().delete()
        Source.objects.all().delete()

    def _seed_users(self):
        demos = [
            ("reporter", "Reporter Demo", "REPORTER"),
            ("editor", "Editor Demo", "EDITOR"),
            ("deskhead", "Desk Head Demo", "DESK_HEAD"),
        ]
        for username, display, role in demos:
            first, last = display.split(" ", 1)
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "role": role},
            )
            user.set_password("demo")
            user.role = role
            user.save()

    def _seed_sources(self):
        from ingest.models import Source
        data = json.loads((SEED_DIR / "sources.json").read_text())
        for s in data["sources"]:
            Source.objects.get_or_create(
                slug=s["slug"],
                defaults={
                    "name": s["name"],
                    "kind": s["kind"],
                    "handle": s.get("handle", ""),
                    "trust_tier": s["trust_tier"],
                    "homepage": s.get("homepage", ""),
                },
            )
        self.stdout.write(f"  Sources: {Source.objects.count()}")

    def _seed_raw_items(self):
        from ingest.models import RawItem, Source
        data = json.loads((SEED_DIR / "raw_items.json").read_text())
        now = timezone.now()
        created = 0
        for item in data["items"]:
            source = Source.objects.get(slug=item["source"])
            received_at = now + timedelta(hours=item["received_offset_hours"])
            published_at = now + timedelta(hours=item["published_offset_hours"])
            content_hash = hashlib.sha256(
                (item["headline"] + item["body"]).encode()
            ).hexdigest()
            _, was_created = RawItem.objects.get_or_create(
                external_id=item["external_id"],
                defaults={
                    "source": source,
                    "headline": item["headline"],
                    "body": item["body"],
                    "url": item.get("url", ""),
                    "published_at": published_at,
                    "received_at": received_at,
                    "ingest_method": "FILE",
                    "content_hash": content_hash,
                },
            )
            if was_created:
                created += 1
        self.stdout.write(f"  Raw items created: {created}")

    def _run_clustering(self):
        from desk.services.clustering import run_clustering
        result = run_clustering()
        self.stdout.write(
            f"  Clustering: {result['stories_created']} stories, "
            f"{result['items_clustered']} items, "
            f"{len(result['suggestions'])} suggestions"
        )

    def _walk_stories(self):
        """Walk a handful of stories through the workflow so analytics isn't empty."""
        from desk.models import Story
        from desk.services.mutations import claim, revise, submit, publish

        reporter = User.objects.get(username="reporter")
        editor = User.objects.get(username="editor")

        # Pick the 5 largest clusters to walk through
        stories = list(
            Story.objects.filter(status=Story.Status.NEW)
            .prefetch_related("story_items", "revisions")
            .order_by("-cluster_confidence")[:5]
        )

        for story in stories:
            try:
                claim(story, reporter)
                latest_rev = story.revisions.order_by("-version").first()
                revise(
                    story, reporter,
                    headline=latest_rev.headline if latest_rev else story.subject,
                    body=latest_rev.body if latest_rev else "Reporter draft.",
                    change_note="Reporter pass",
                )
                submit(story, reporter)
                publish(story, editor)
                self.stdout.write(f"  Published: {story.subject[:60]}")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  Skipped {story.pk}: {exc}"))
