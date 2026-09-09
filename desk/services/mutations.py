"""Service layer for all desk mutations.

Every public function here:
  1. Enforces role permissions (raises PermissionDenied regardless of caller)
  2. Writes an AuditEvent
  3. Never does a bare .save() on Story/BriefRevision/Publication directly

This means the rules hold for management commands, admin actions, and tests,
not just the HTTP layer.
"""

from __future__ import annotations

from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.utils.text import slugify

from desk.models import Story, StoryItem, BriefRevision, Publication, Merge, AuditEvent
from ingest.models import RawItem


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _audit(actor, verb: str, target, payload: dict | None = None):
    AuditEvent.objects.create(
        actor=actor,
        verb=verb,
        target_type=type(target).__name__,
        target_id=getattr(target, "pk", None),
        payload=payload or {},
    )


def _require_role(user, *roles):
    if user.role not in roles:
        raise PermissionDenied(
            f"Role {user.role!r} cannot perform this action. Required: {roles}"
        )


def _next_version(story: Story) -> int:
    last = story.revisions.order_by("-version").first()
    return (last.version + 1) if last else 1


def _make_slug(subject: str, story_id: int) -> str:
    base = slugify(subject)[:160] or f"story-{story_id}"
    slug = base
    n = 1
    while Story.objects.filter(slug=slug).exclude(pk=story_id).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def claim(story: Story, user) -> Story:
    """Reporter claims a NEW story to work on."""
    _require_role(user, "REPORTER")
    if story.status != Story.Status.NEW:
        raise ValueError(f"Cannot claim a story in status {story.status!r}.")
    story.status = Story.Status.DRAFT
    story.assigned_to = user
    story.claimed_at = timezone.now()
    story.save(update_fields=["status", "assigned_to", "claimed_at"])
    _audit(user, "claim", story)
    return story


def revise(story: Story, user, headline: str, body: str, subject: str = "",
           change_note: str = "", kind: str | None = None) -> BriefRevision:
    """Insert a new BriefRevision. Reporters and editors may both revise."""
    _require_role(user, "REPORTER", "EDITOR")
    if story.status == Story.Status.SPIKED:
        raise ValueError("Cannot revise a spiked story.")

    if kind is None:
        kind = (BriefRevision.Kind.REPORTER_EDIT
                if user.is_reporter else BriefRevision.Kind.EDITOR_EDIT)

    revision = BriefRevision.objects.create(
        story=story,
        version=_next_version(story),
        headline=headline,
        body=body,
        subject=subject or story.subject,
        author=user,
        kind=kind,
        change_note=change_note,
    )
    if subject and subject != story.subject:
        story.subject = subject
        story.slug = _make_slug(subject, story.pk)
        story.save(update_fields=["subject", "slug"])
    _audit(user, "revise", story, {"version": revision.version, "kind": kind})
    return revision


def submit(story: Story, user) -> Story:
    """Reporter submits a DRAFT for editor review."""
    _require_role(user, "REPORTER")
    if story.status != Story.Status.DRAFT:
        raise ValueError(f"Cannot submit a story in status {story.status!r}.")
    if not story.revisions.exists():
        raise ValueError("Cannot submit a story with no revisions.")
    story.status = Story.Status.IN_REVIEW
    story.submitted_at = timezone.now()
    story.save(update_fields=["status", "submitted_at"])
    _audit(user, "submit", story)
    return story


def publish(story: Story, user) -> Publication:
    """Editor publishes the latest revision. Reporters cannot call this."""
    _require_role(user, "EDITOR")  # raises PermissionDenied for any other role
    if story.status not in (Story.Status.IN_REVIEW, Story.Status.DRAFT):
        raise ValueError(f"Cannot publish a story in status {story.status!r}.")

    latest = story.revisions.order_by("-version").first()
    if not latest:
        raise ValueError("No revision to publish.")

    prev_pubs = story.publications.filter(status=Publication.PublicationStatus.LIVE)
    version_no = prev_pubs.count() + 1

    pub = Publication.objects.create(
        story=story,
        revision=latest,
        published_by=user,
        version_no=version_no,
    )

    now = timezone.now()
    story.status = Story.Status.PUBLISHED
    update_fields = ["status"]
    if not story.first_published_at:
        story.first_published_at = now
        update_fields.append("first_published_at")
    if not story.slug:
        story.slug = _make_slug(story.subject or f"story-{story.pk}", story.pk)
        update_fields.append("slug")
    story.save(update_fields=update_fields)

    # Mark all raw items as CLUSTERED
    story.story_items.filter(detached_at__isnull=True).select_related("item").update()
    RawItem.objects.filter(
        story_items__story=story, story_items__detached_at__isnull=True
    ).update(state=RawItem.State.CLUSTERED)

    _audit(user, "publish", story, {"publication_id": pub.pk, "version_no": version_no})
    return pub


def correct(story: Story, user, headline: str, body: str, change_note: str) -> Publication:
    """Post-publish correction: new revision + new Publication (CORRECTED)."""
    _require_role(user, "EDITOR")
    if story.status != Story.Status.PUBLISHED:
        raise ValueError("Can only correct a published story.")

    revision = BriefRevision.objects.create(
        story=story,
        version=_next_version(story),
        headline=headline,
        body=body,
        subject=story.subject,
        author=user,
        kind=BriefRevision.Kind.CORRECTION,
        change_note=change_note,
    )

    # Mark previous live publication as CORRECTED
    story.publications.filter(
        status=Publication.PublicationStatus.LIVE
    ).update(status=Publication.PublicationStatus.CORRECTED)

    pub = Publication.objects.create(
        story=story,
        revision=revision,
        published_by=user,
        version_no=story.publications.count() + 1,
        status=Publication.PublicationStatus.LIVE,
    )
    _audit(user, "correct", story, {"version": revision.version, "change_note": change_note})
    return pub


def merge(from_story: Story, into_story: Story, user, reason: str = "") -> Merge:
    """Merge two stories. Loser → SUPERSEDED (still reachable). Winner gets new revision."""
    _require_role(user, "EDITOR")
    if from_story.pk == into_story.pk:
        raise ValueError("Cannot merge a story into itself.")

    was_published = from_story.status == Story.Status.PUBLISHED

    # Move all items from loser to winner (skip duplicates)
    for si in from_story.story_items.filter(detached_at__isnull=True):
        StoryItem.objects.get_or_create(
            story=into_story,
            item=si.item,
            defaults={"similarity_score": si.similarity_score, "attached_by": user},
        )

    # Supersede loser's live publications
    from_story.publications.filter(
        status=Publication.PublicationStatus.LIVE
    ).update(status=Publication.PublicationStatus.SUPERSEDED)

    from_story.status = Story.Status.SPIKED
    from_story.canonical_story = into_story
    from_story.save(update_fields=["status", "canonical_story"])

    merge_record = Merge.objects.create(
        from_story=from_story,
        into_story=into_story,
        actor=user,
        reason=reason,
        was_published_at_merge=was_published,
    )

    # Add a MERGE_NOTE revision to the winner
    latest = into_story.revisions.order_by("-version").first()
    BriefRevision.objects.create(
        story=into_story,
        version=_next_version(into_story),
        headline=latest.headline if latest else into_story.subject,
        body=latest.body if latest else "",
        subject=into_story.subject,
        author=user,
        kind=BriefRevision.Kind.MERGE_NOTE,
        change_note=f"Merged story #{from_story.pk} into this story. {reason}".strip(),
    )

    # If winner was published, issue a new Publication (v2)
    if into_story.status == Story.Status.PUBLISHED:
        latest_rev = into_story.revisions.order_by("-version").first()
        into_story.publications.filter(
            status=Publication.PublicationStatus.LIVE
        ).update(status=Publication.PublicationStatus.CORRECTED)
        Publication.objects.create(
            story=into_story,
            revision=latest_rev,
            published_by=user,
            version_no=into_story.publications.count() + 1,
            status=Publication.PublicationStatus.LIVE,
        )

    _audit(user, "merge", into_story, {
        "from_story_id": from_story.pk,
        "was_published": was_published,
        "reason": reason,
    })
    return merge_record


def spike(story: Story, user) -> Story:
    """Spike a story (reporter or editor)."""
    _require_role(user, "REPORTER", "EDITOR")
    if story.status == Story.Status.PUBLISHED:
        raise ValueError("Cannot spike a published story. Use merge or correct instead.")
    story.status = Story.Status.SPIKED
    story.save(update_fields=["status"])
    RawItem.objects.filter(
        story_items__story=story, story_items__detached_at__isnull=True
    ).update(state=RawItem.State.SPIKED)
    _audit(user, "spike", story)
    return story


def detach_item(story: Story, raw_item: RawItem, user) -> None:
    """Remove a raw item from a story."""
    _require_role(user, "REPORTER", "EDITOR")
    try:
        si = StoryItem.objects.get(story=story, item=raw_item, detached_at__isnull=True)
    except StoryItem.DoesNotExist:
        raise ValueError("Item is not attached to this story.")
    si.detached_at = timezone.now()
    si.save(update_fields=["detached_at"])
    _audit(user, "detach_item", story, {"item_id": raw_item.pk})
