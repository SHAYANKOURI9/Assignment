from rest_framework import serializers
from .models import Story, StoryItem, BriefRevision, Publication, Merge, AuditEvent
from ingest.serializers import RawItemSerializer
from accounts.serializers import UserSerializer


class BriefRevisionSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = BriefRevision
        fields = ["id", "version", "headline", "body", "subject", "author",
                  "kind", "change_note", "model", "created_at"]


class StoryItemSerializer(serializers.ModelSerializer):
    item = RawItemSerializer(read_only=True)

    class Meta:
        model = StoryItem
        fields = ["id", "item", "similarity_score", "attached_at", "detached_at"]


class PublicationSerializer(serializers.ModelSerializer):
    revision = BriefRevisionSerializer(read_only=True)
    published_by = UserSerializer(read_only=True)

    class Meta:
        model = Publication
        fields = ["id", "revision", "published_by", "published_at", "version_no", "status"]


class StoryListSerializer(serializers.ModelSerializer):
    assigned_to = UserSerializer(read_only=True)
    latest_headline = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = ["id", "slug", "status", "subject", "assigned_to", "cluster_confidence",
                  "clustered_by", "latest_headline", "item_count",
                  "first_item_received_at", "created_at", "claimed_at",
                  "submitted_at", "first_published_at"]

    def get_latest_headline(self, obj):
        rev = obj.revisions.order_by("-version").first()
        return rev.headline if rev else obj.subject

    def get_item_count(self, obj):
        return obj.story_items.filter(detached_at__isnull=True).count()


class StoryDetailSerializer(StoryListSerializer):
    revisions = BriefRevisionSerializer(many=True, read_only=True)
    story_items = StoryItemSerializer(many=True, read_only=True)
    publications = PublicationSerializer(many=True, read_only=True)

    class Meta(StoryListSerializer.Meta):
        fields = StoryListSerializer.Meta.fields + ["revisions", "story_items", "publications"]


class MergeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merge
        fields = ["id", "from_story", "into_story", "actor", "reason",
                  "was_published_at_merge", "created_at"]


class AuditEventSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)

    class Meta:
        model = AuditEvent
        fields = ["id", "actor", "verb", "target_type", "target_id", "payload", "created_at"]
