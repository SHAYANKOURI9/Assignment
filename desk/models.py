from django.db import models
from django.conf import settings
from ingest.models import RawItem


class Story(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        DRAFT = "DRAFT", "Draft"
        IN_REVIEW = "IN_REVIEW", "In Review"
        PUBLISHED = "PUBLISHED", "Published"
        SPIKED = "SPIKED", "Spiked"

    class ClusteredBy(models.TextChoices):
        AUTO = "AUTO", "Auto"
        LLM = "LLM", "LLM"
        HUMAN = "HUMAN", "Human"

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    subject = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="assigned_stories"
    )
    canonical_story = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_into_me"
    )
    clustered_by = models.CharField(max_length=6, choices=ClusteredBy.choices, default=ClusteredBy.AUTO)
    cluster_confidence = models.FloatField(null=True, blank=True)

    # Timestamp chain for dwell metrics
    first_item_received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    first_published_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.subject or f"Story #{self.pk}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "stories"


class StoryItem(models.Model):
    """Story ↔ RawItem join — explicit so every attach/detach is auditable."""
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="story_items")
    item = models.ForeignKey(RawItem, on_delete=models.PROTECT, related_name="story_items")
    similarity_score = models.FloatField(null=True, blank=True)
    attached_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="attached_items"
    )
    attached_at = models.DateTimeField(auto_now_add=True)
    detached_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("story", "item")]
        ordering = ["attached_at"]


class BriefRevision(models.Model):
    """Append-only. Never UPDATE or DELETE a row — insert the next version."""

    class Kind(models.TextChoices):
        MACHINE_DRAFT = "MACHINE_DRAFT", "Machine Draft"
        REPORTER_EDIT = "REPORTER_EDIT", "Reporter Edit"
        EDITOR_EDIT = "EDITOR_EDIT", "Editor Edit"
        CORRECTION = "CORRECTION", "Correction"
        MERGE_NOTE = "MERGE_NOTE", "Merge Note"

    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    headline = models.CharField(max_length=500)
    body = models.TextField()
    subject = models.CharField(max_length=200, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="revisions"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    change_note = models.CharField(max_length=500, blank=True)
    model = models.CharField(max_length=100, blank=True)   # for MACHINE_DRAFT
    prompt_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("story", "version")]
        ordering = ["version"]

    def save(self, *args, **kwargs):
        # Guard: never allow updating an existing revision
        if self.pk:
            raise ValueError("BriefRevision rows are immutable. Insert a new version.")
        super().save(*args, **kwargs)


class Publication(models.Model):
    """Immutable public record. No unpublish. Corrections are new rows."""

    class PublicationStatus(models.TextChoices):
        LIVE = "LIVE", "Live"
        SUPERSEDED = "SUPERSEDED", "Superseded"
        CORRECTED = "CORRECTED", "Corrected"

    story = models.ForeignKey(Story, on_delete=models.PROTECT, related_name="publications")
    revision = models.ForeignKey(BriefRevision, on_delete=models.PROTECT, related_name="publications")
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="publications"
    )
    published_at = models.DateTimeField(auto_now_add=True)
    version_no = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=12, choices=PublicationStatus.choices, default=PublicationStatus.LIVE
    )

    class Meta:
        ordering = ["-published_at"]

    def save(self, *args, **kwargs):
        if self.pk:
            # Only allow status updates (SUPERSEDED / CORRECTED), nothing else
            orig = Publication.objects.get(pk=self.pk)
            if (orig.story_id != self.story_id or orig.revision_id != self.revision_id
                    or orig.published_by_id != self.published_by_id):
                raise ValueError("Publication rows are immutable except for status.")
        super().save(*args, **kwargs)


class Merge(models.Model):
    from_story = models.ForeignKey(Story, on_delete=models.PROTECT, related_name="merged_from")
    into_story = models.ForeignKey(Story, on_delete=models.PROTECT, related_name="merged_into")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    was_published_at_merge = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEvent(models.Model):
    """Append-only log. Every service call writes one."""
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_events"
    )
    verb = models.CharField(max_length=50, db_index=True)
    target_type = models.CharField(max_length=50)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
