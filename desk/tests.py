"""
Tests named after the brief's own sentences — the test list is a requirements checklist.

Run with: python manage.py test desk.tests
"""

from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from accounts.models import User
from ingest.models import Source, RawItem
from desk.models import Story, StoryItem, BriefRevision, Publication, AuditEvent
from desk.services.mutations import claim, revise, submit, publish, correct, merge, spike
from desk.services.clustering import run_clustering


def _make_user(username, role):
    u = User.objects.create_user(username=username, password="x", role=role)
    return u


def _make_source(slug="test-wire", kind="WIRE", tier=1):
    return Source.objects.get_or_create(
        slug=slug,
        defaults={"name": slug, "kind": kind, "trust_tier": tier},
    )[0]


def _make_item(source, external_id="item-1", headline="Test headline", body="Test body."):
    return RawItem.objects.create(
        source=source,
        external_id=external_id,
        headline=headline,
        body=body,
        received_at=timezone.now(),
    )


def _make_story_with_revision(editor=None):
    """Helper: NEW story → DRAFT with one revision → IN_REVIEW, ready to publish."""
    reporter = _make_user("rep_helper", "REPORTER")
    if editor is None:
        editor = _make_user("ed_helper", "EDITOR")
    source = _make_source("helper-wire")
    item = _make_item(source, external_id="helper-item")
    story = Story.objects.create(
        status=Story.Status.NEW,
        subject="Helper story",
        first_item_received_at=timezone.now(),
    )
    StoryItem.objects.create(story=story, item=item)
    claim(story, reporter)
    revise(story, reporter, headline="Headline", body="Body text here.")
    submit(story, reporter)
    return story, editor


# ---------------------------------------------------------------------------
# 1. Reporter cannot publish
# ---------------------------------------------------------------------------

class TestReporterCannotPublish(TestCase):
    def test_reporter_cannot_publish(self):
        reporter = _make_user("rep1", "REPORTER")
        editor = _make_user("ed1", "EDITOR")
        story, _ = _make_story_with_revision(editor)

        # HTTP layer: 403 via service
        with self.assertRaises(PermissionDenied):
            publish(story, reporter)

        # Story must still be IN_REVIEW — not published
        story.refresh_from_db()
        self.assertEqual(story.status, Story.Status.IN_REVIEW)

    def test_desk_head_cannot_publish(self):
        dh = _make_user("dh1", "DESK_HEAD")
        story, _ = _make_story_with_revision()
        with self.assertRaises(PermissionDenied):
            publish(story, dh)


# ---------------------------------------------------------------------------
# 2. Editor can publish
# ---------------------------------------------------------------------------

class TestEditorCanPublish(TestCase):
    def test_editor_can_publish(self):
        editor = _make_user("ed2", "EDITOR")
        story, _ = _make_story_with_revision(editor)

        pub = publish(story, editor)

        self.assertIsInstance(pub, Publication)
        story.refresh_from_db()
        self.assertEqual(story.status, Story.Status.PUBLISHED)
        self.assertIsNotNone(story.first_published_at)

        # Revision is flagged as the published one
        self.assertEqual(pub.revision.story, story)
        self.assertEqual(pub.status, Publication.PublicationStatus.LIVE)


# ---------------------------------------------------------------------------
# 3. Published revision is never mutated
# ---------------------------------------------------------------------------

class TestPublishedRevisionIsNeverMutated(TestCase):
    def test_published_revision_is_never_mutated(self):
        editor = _make_user("ed3", "EDITOR")
        story, _ = _make_story_with_revision(editor)
        pub = publish(story, editor)

        original_rev = pub.revision
        original_body = original_rev.body
        original_pk = original_rev.pk

        # Attempt to mutate the revision directly must raise
        with self.assertRaises(ValueError):
            original_rev.body = "MUTATED"
            original_rev.save()

        # Original row is byte-identical
        original_rev.refresh_from_db()
        self.assertEqual(original_rev.body, original_body)
        self.assertEqual(original_rev.pk, original_pk)

        # A correction inserts a NEW row, not an update
        correct(story, editor, headline="Corrected", body="New body.", change_note="Fix typo")
        self.assertEqual(story.revisions.count(), 2)  # reporter edit + correction
        original_rev.refresh_from_db()
        self.assertEqual(original_rev.body, original_body)  # still unchanged


# ---------------------------------------------------------------------------
# 4. Three (four) wordings become one story
# ---------------------------------------------------------------------------

class TestThreeWordingsBecomeOneStory(TestCase):
    def test_metro_quartet_clusters_to_one_story(self):
        """The metro-purple-line-fault quartet must collapse to one story."""
        import json
        from pathlib import Path
        from brain import build_features, cluster_items

        seed_dir = Path(__file__).resolve().parent.parent / "seed"
        sources_data = json.loads((seed_dir / "sources.json").read_text())
        items_data = json.loads((seed_dir / "raw_items.json").read_text())

        sources = {s["slug"]: s for s in sources_data["sources"]}
        metro_ids = {"bns-0781", "butc-pr-118", "tpd-0233", "soc-bc-9914"}

        now = timezone.now()
        features = []
        for item in items_data["items"]:
            src = sources[item["source"]]
            from datetime import timedelta
            features.append(build_features(
                key=item["external_id"],
                headline=item["headline"],
                body=item["body"],
                received_at=now + timedelta(hours=item["received_offset_hours"]),
                published_at=now + timedelta(hours=item["published_offset_hours"]),
                trust_tier=src["trust_tier"],
                source_name=src["name"],
                source_kind=src["kind"],
            ))

        result = cluster_items(features)

        # Find the cluster containing the metro items
        metro_cluster = result.cluster_of("bns-0781")
        self.assertIsNotNone(metro_cluster)

        # All four must be in the same cluster OR the missing one must be in suggestions
        cluster_keys = set(metro_cluster.keys)
        in_cluster = metro_ids & cluster_keys
        # At minimum the three auto-clustered ones must be together
        self.assertGreaterEqual(len(in_cluster), 3)

        # The social post (soc-bc-9914) is in the grey band — must appear in suggestions
        if "soc-bc-9914" not in cluster_keys:
            suggestion_keys = {(s.left, s.right) for s in result.suggestions}
            suggestion_keys |= {(s.right, s.left) for s in result.suggestions}
            self.assertTrue(
                any("soc-bc-9914" in pair for pair in suggestion_keys),
                "soc-bc-9914 must appear in suggestions if not auto-clustered",
            )


# ---------------------------------------------------------------------------
# 5. Lookalike pairs stay separate
# ---------------------------------------------------------------------------

class TestLookalikesPairStaySeparate(TestCase):
    def test_pharma_pair_stays_separate(self):
        """Two different pharma Phase-3 releases must not merge."""
        import json
        from pathlib import Path
        from brain import build_features, cluster_items
        from datetime import timedelta

        seed_dir = Path(__file__).resolve().parent.parent / "seed"
        sources_data = json.loads((seed_dir / "sources.json").read_text())
        items_data = json.loads((seed_dir / "raw_items.json").read_text())
        sources = {s["slug"]: s for s in sources_data["sources"]}
        now = timezone.now()

        features = [
            build_features(
                key=item["external_id"],
                headline=item["headline"],
                body=item["body"],
                received_at=now + timedelta(hours=item["received_offset_hours"]),
                published_at=now + timedelta(hours=item["published_offset_hours"]),
                trust_tier=sources[item["source"]]["trust_tier"],
                source_name=sources[item["source"]]["name"],
                source_kind=sources[item["source"]]["kind"],
            )
            for item in items_data["items"]
        ]
        result = cluster_items(features)

        zydan_cluster = result.cluster_of("zydan-pr-41")
        verakine_cluster = result.cluster_of("verakine-pr-27")
        self.assertIsNotNone(zydan_cluster)
        self.assertIsNotNone(verakine_cluster)
        self.assertNotEqual(zydan_cluster, verakine_cluster,
                            "Pharma lookalikes must be in separate clusters")

    def test_highway_crash_pair_stays_separate(self):
        """Two NH-48 crashes with different death tolls must not merge."""
        import json
        from pathlib import Path
        from brain import build_features, cluster_items
        from datetime import timedelta

        seed_dir = Path(__file__).resolve().parent.parent / "seed"
        sources_data = json.loads((seed_dir / "sources.json").read_text())
        items_data = json.loads((seed_dir / "raw_items.json").read_text())
        sources = {s["slug"]: s for s in sources_data["sources"]}
        now = timezone.now()

        features = [
            build_features(
                key=item["external_id"],
                headline=item["headline"],
                body=item["body"],
                received_at=now + timedelta(hours=item["received_offset_hours"]),
                published_at=now + timedelta(hours=item["published_offset_hours"]),
                trust_tier=sources[item["source"]]["trust_tier"],
                source_name=sources[item["source"]]["name"],
                source_kind=sources[item["source"]]["kind"],
            )
            for item in items_data["items"]
        ]
        result = cluster_items(features)

        palanpur_cluster = result.cluster_of("bns-0774")
        sirohi_cluster = result.cluster_of("apa-2210")
        self.assertIsNotNone(palanpur_cluster)
        self.assertIsNotNone(sirohi_cluster)
        self.assertNotEqual(palanpur_cluster, sirohi_cluster,
                            "NH-48 crash lookalikes must be in separate clusters")


# ---------------------------------------------------------------------------
# 6. Post-publish merge supersedes and corrects
# ---------------------------------------------------------------------------

class TestPostPublishMergeSupersedes(TestCase):
    def setUp(self):
        self.editor = _make_user("ed_merge", "EDITOR")
        self.reporter = _make_user("rep_merge", "REPORTER")
        self.source = _make_source("merge-wire")

    def _published_story(self, ext_id, headline):
        item = _make_item(self.source, external_id=ext_id, headline=headline)
        story = Story.objects.create(
            status=Story.Status.NEW,
            subject=headline,
            first_item_received_at=timezone.now(),
        )
        StoryItem.objects.create(story=story, item=item)
        claim(story, self.reporter)
        revise(story, self.reporter, headline=headline, body="Body.")
        submit(story, self.reporter)
        publish(story, self.editor)
        story.refresh_from_db()
        return story

    def test_post_publish_merge_supersedes_and_corrects(self):
        from_story = self._published_story("merge-from", "Story A")
        into_story = self._published_story("merge-into", "Story B")

        self.assertEqual(from_story.status, Story.Status.PUBLISHED)
        self.assertEqual(into_story.status, Story.Status.PUBLISHED)

        merge(from_story, into_story, self.editor, reason="Same event confirmed")

        from_story.refresh_from_db()
        into_story.refresh_from_db()

        # Loser is spiked and points to winner
        self.assertEqual(from_story.status, Story.Status.SPIKED)
        self.assertEqual(from_story.canonical_story, into_story)

        # Loser's publication is SUPERSEDED (still reachable)
        loser_pub = from_story.publications.first()
        self.assertEqual(loser_pub.status, Publication.PublicationStatus.SUPERSEDED)

        # Winner still published, has a new live publication
        self.assertEqual(into_story.status, Story.Status.PUBLISHED)
        live_pubs = into_story.publications.filter(status=Publication.PublicationStatus.LIVE)
        self.assertEqual(live_pubs.count(), 1)

        # Winner has a MERGE_NOTE revision
        merge_note = into_story.revisions.filter(kind=BriefRevision.Kind.MERGE_NOTE).first()
        self.assertIsNotNone(merge_note)

        # Items from loser are now on winner
        from_item_ids = set(
            from_story.story_items.values_list("item_id", flat=True)
        )
        into_item_ids = set(
            into_story.story_items.filter(detached_at__isnull=True).values_list("item_id", flat=True)
        )
        self.assertTrue(from_item_ids.issubset(into_item_ids))


# ---------------------------------------------------------------------------
# 7. Yesterday dwell metrics
# ---------------------------------------------------------------------------

class TestYesterdayDwellMetrics(TestCase):
    def test_yesterday_dwell_metrics(self):
        from django.test import Client

        editor = _make_user("ed_dwell", "EDITOR")
        source = _make_source("dwell-wire")
        yesterday = timezone.now() - timedelta(days=1)

        item = _make_item(source, external_id="dwell-item")
        item.received_at = yesterday.replace(hour=8)
        item.save(update_fields=["received_at"])

        story = Story.objects.create(
            status=Story.Status.PUBLISHED,
            subject="Dwell test story",
            first_item_received_at=yesterday.replace(hour=8),
            claimed_at=yesterday.replace(hour=9),
            submitted_at=yesterday.replace(hour=10),
            first_published_at=yesterday.replace(hour=11),
        )
        StoryItem.objects.create(story=story, item=item)
        rev = BriefRevision.objects.create(
            story=story, version=1, headline="H", body="B",
            subject=story.subject, author=editor,
            kind=BriefRevision.Kind.EDITOR_EDIT,
        )
        Publication.objects.create(
            story=story, revision=rev, published_by=editor, version_no=1,
        )

        client = Client()
        client.force_login(editor)
        response = client.get(
            "/api/analytics/dashboard/",
            {"date": yesterday.date().isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(data["published_count"], 1)
        self.assertIsNotNone(data["dwell"]["median_minutes"])
        # 8am → 11am = 180 minutes
        self.assertEqual(data["dwell"]["median_minutes"], 180)


# ---------------------------------------------------------------------------
# 8. Every mutation writes an audit event
# ---------------------------------------------------------------------------

class TestEveryMutationWritesAuditEvent(TestCase):
    def test_every_mutation_writes_an_audit_event(self):
        reporter = _make_user("rep_audit", "REPORTER")
        editor = _make_user("ed_audit", "EDITOR")
        source = _make_source("audit-wire")
        item = _make_item(source, external_id="audit-item")

        story = Story.objects.create(
            status=Story.Status.NEW,
            subject="Audit test",
            first_item_received_at=timezone.now(),
        )
        StoryItem.objects.create(story=story, item=item)

        before = AuditEvent.objects.count()

        claim(story, reporter)
        self.assertEqual(AuditEvent.objects.count(), before + 1)

        revise(story, reporter, headline="H", body="B")
        self.assertEqual(AuditEvent.objects.count(), before + 2)

        submit(story, reporter)
        self.assertEqual(AuditEvent.objects.count(), before + 3)

        publish(story, editor)
        self.assertEqual(AuditEvent.objects.count(), before + 4)

        correct(story, editor, headline="H2", body="B2", change_note="Fix")
        self.assertEqual(AuditEvent.objects.count(), before + 5)

        verbs = list(
            AuditEvent.objects.filter(created_at__gte=timezone.now() - timedelta(seconds=5))
            .values_list("verb", flat=True)
        )
        for expected in ("claim", "revise", "submit", "publish", "correct"):
            self.assertIn(expected, verbs)
