"""Clustering service: run brain/ over untriaged items and create/update Stories."""

from __future__ import annotations

from datetime import timedelta
from django.utils import timezone
from django.utils.text import slugify

from brain import build_features, cluster_items
from brain.llm import draft_brief, available as llm_available
from desk.models import Story, StoryItem, BriefRevision, AuditEvent
from ingest.models import RawItem


def run_clustering(items: list[RawItem] | None = None) -> dict:
    """Cluster untriaged items and create Story + BriefRevision rows.

    Returns a summary dict for the management command / API response.
    """
    if items is None:
        items = list(
            RawItem.objects.filter(state=RawItem.State.UNTRIAGED)
            .select_related("source")
            .order_by("received_at")
        )

    if not items:
        return {"stories_created": 0, "items_clustered": 0, "suggestions": []}

    features = [
        build_features(
            key=str(item.pk),
            headline=item.headline,
            body=item.body,
            received_at=item.received_at,
            published_at=item.published_at,
            trust_tier=item.source.trust_tier,
            source_name=item.source.name,
            source_kind=item.source.kind,
        )
        for item in items
    ]

    item_by_pk = {str(item.pk): item for item in items}
    result = cluster_items(features)

    stories_created = 0
    items_clustered = 0

    for cluster in result.clusters:
        raw_items = [item_by_pk[key] for key in cluster.keys]
        seed_feature = cluster.seed()
        seed_item = item_by_pk[seed_feature.key]

        story = Story.objects.create(
            status=Story.Status.NEW,
            subject=seed_item.headline[:200],
            cluster_confidence=cluster.confidence,
            clustered_by=Story.ClusteredBy.AUTO,
            first_item_received_at=min(i.received_at for i in raw_items),
        )
        story.slug = _make_slug(story.subject, story.pk)
        story.save(update_fields=["slug"])

        pair_map = {(p.left, p.right): p for p in result.pairs.values()}

        for raw_item in raw_items:
            score = None
            if len(raw_items) > 1:
                key = str(raw_item.pk)
                seed_key = seed_feature.key
                pair = pair_map.get((min(key, seed_key), max(key, seed_key)))
                score = pair.score if pair else None

            StoryItem.objects.create(
                story=story,
                item=raw_item,
                similarity_score=score,
            )
            raw_item.state = RawItem.State.CLUSTERED
            raw_item.save(update_fields=["state"])
            items_clustered += 1

        # Draft the brief
        brief_body = draft_brief(cluster)
        BriefRevision.objects.create(
            story=story,
            version=1,
            headline=seed_item.headline,
            body=brief_body,
            subject=story.subject,
            author=None,
            kind=BriefRevision.Kind.MACHINE_DRAFT,
            model="claude-3-5-haiku-20241022" if llm_available() else "deterministic",
            prompt_version="1",
        )
        stories_created += 1

    AuditEvent.objects.create(
        actor=None,
        verb="cluster_run",
        target_type="RawItem",
        target_id=None,
        payload={
            "items_processed": len(items),
            "stories_created": stories_created,
            "suggestions": len(result.suggestions),
        },
    )

    return {
        "stories_created": stories_created,
        "items_clustered": items_clustered,
        "suggestions": [
            {
                "left": s.left,
                "right": s.right,
                "score": s.score,
                "reason": s.reason,
                "confident": s.confident,
            }
            for s in result.suggestions
        ],
    }


def _make_slug(subject: str, story_id: int) -> str:
    base = slugify(subject)[:160] or f"story-{story_id}"
    slug = base
    n = 1
    while Story.objects.filter(slug=slug).exclude(pk=story_id).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug
