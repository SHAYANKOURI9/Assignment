import hashlib
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Source, RawItem
from .serializers import SourceSerializer, RawItemSerializer, IngestUploadSerializer
from brain.llm import read_screenshot, available as llm_available


class SourceListView(generics.ListAPIView):
    queryset = Source.objects.all()
    serializer_class = SourceSerializer


class RawItemListView(generics.ListAPIView):
    serializer_class = RawItemSerializer

    def get_queryset(self):
        qs = RawItem.objects.select_related("source")
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        return qs


@api_view(["POST"])
def ingest_manual(request):
    """Accept a manually typed or screenshot-extracted item."""
    serializer = IngestUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        source = Source.objects.get(slug=data["source_slug"])
    except Source.DoesNotExist:
        return Response({"error": "Unknown source slug."}, status=status.HTTP_400_BAD_REQUEST)

    content_hash = hashlib.sha256(
        (data["headline"] + data["body"]).encode()
    ).hexdigest()

    if RawItem.objects.filter(content_hash=content_hash).exists():
        return Response({"error": "Exact duplicate — already in the pile."}, status=status.HTTP_409_CONFLICT)

    item = RawItem.objects.create(
        source=source,
        external_id=f"manual-{content_hash[:12]}",
        headline=data["headline"],
        body=data["body"],
        url=data.get("url", ""),
        published_at=data.get("published_at"),
        received_at=timezone.now(),
        ingest_method=RawItem.IngestMethod.MANUAL,
        content_hash=content_hash,
    )
    return Response(RawItemSerializer(item).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def ingest_screenshot(request):
    """Upload a screenshot; extract text via LLM if key is set, else return empty."""
    image = request.FILES.get("image")
    if not image:
        return Response({"error": "No image provided."}, status=status.HTTP_400_BAD_REQUEST)

    image_bytes = image.read()
    media_type = image.content_type or "image/png"

    extracted = read_screenshot(image_bytes, media_type)
    return Response({
        "headline": extracted["headline"],
        "body": extracted["body"],
        "llm_available": llm_available(),
    })
