from rest_framework import serializers
from .models import Source, RawItem


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = ["id", "slug", "name", "kind", "handle", "trust_tier"]


class RawItemSerializer(serializers.ModelSerializer):
    source = SourceSerializer(read_only=True)
    source_id = serializers.PrimaryKeyRelatedField(
        queryset=Source.objects.all(), source="source", write_only=True
    )

    class Meta:
        model = RawItem
        fields = [
            "id", "source", "source_id", "external_id", "headline", "body",
            "url", "published_at", "received_at", "ingest_method",
            "extraction_notes", "state", "created_at",
        ]
        read_only_fields = ["id", "created_at", "state"]


class IngestUploadSerializer(serializers.Serializer):
    """For manual/image ingest from the frontend."""
    headline = serializers.CharField(max_length=500)
    body = serializers.CharField()
    source_slug = serializers.SlugField()
    url = serializers.URLField(required=False, allow_blank=True)
    published_at = serializers.DateTimeField(required=False, allow_null=True)
    image = serializers.ImageField(required=False)
