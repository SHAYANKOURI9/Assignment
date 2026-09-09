from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Story, BriefRevision, Publication, AuditEvent
from .serializers import (
    StoryListSerializer, StoryDetailSerializer,
    BriefRevisionSerializer, PublicationSerializer, AuditEventSerializer,
)
from .services.mutations import claim, revise, submit, publish, correct, merge, spike, detach_item
from .services.clustering import run_clustering
from ingest.models import RawItem


@api_view(["GET"])
def story_list(request):
    qs = Story.objects.select_related("assigned_to").prefetch_related("revisions")
    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return Response(StoryListSerializer(qs, many=True).data)


@api_view(["GET"])
def story_detail(request, pk):
    story = get_object_or_404(
        Story.objects.prefetch_related(
            "revisions__author",
            "story_items__item__source",
            "publications__revision",
            "publications__published_by",
        ),
        pk=pk,
    )
    return Response(StoryDetailSerializer(story).data)


@api_view(["POST"])
def story_claim(request, pk):
    story = get_object_or_404(Story, pk=pk)
    updated = claim(story, request.user)
    return Response(StoryListSerializer(updated).data)


@api_view(["POST"])
def story_revise(request, pk):
    story = get_object_or_404(Story, pk=pk)
    headline = request.data.get("headline", "")
    body = request.data.get("body", "")
    subject = request.data.get("subject", "")
    change_note = request.data.get("change_note", "")
    if not headline or not body:
        return Response({"error": "headline and body are required."}, status=status.HTTP_400_BAD_REQUEST)
    revision = revise(story, request.user, headline, body, subject, change_note)
    return Response(BriefRevisionSerializer(revision).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def story_submit(request, pk):
    story = get_object_or_404(Story, pk=pk)
    updated = submit(story, request.user)
    return Response(StoryListSerializer(updated).data)


@api_view(["POST"])
def story_publish(request, pk):
    story = get_object_or_404(Story, pk=pk)
    pub = publish(story, request.user)
    return Response(PublicationSerializer(pub).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def story_correct(request, pk):
    story = get_object_or_404(Story, pk=pk)
    headline = request.data.get("headline", "")
    body = request.data.get("body", "")
    change_note = request.data.get("change_note", "")
    if not headline or not body or not change_note:
        return Response(
            {"error": "headline, body, and change_note are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    pub = correct(story, request.user, headline, body, change_note)
    return Response(PublicationSerializer(pub).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def story_merge(request, pk):
    from_story = get_object_or_404(Story, pk=pk)
    into_pk = request.data.get("into_story_id")
    reason = request.data.get("reason", "")
    if not into_pk:
        return Response({"error": "into_story_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    into_story = get_object_or_404(Story, pk=into_pk)
    merge(from_story, into_story, request.user, reason)
    return Response(StoryDetailSerializer(into_story).data)


@api_view(["POST"])
def story_spike(request, pk):
    story = get_object_or_404(Story, pk=pk)
    updated = spike(story, request.user)
    return Response(StoryListSerializer(updated).data)


@api_view(["POST"])
def story_detach_item(request, pk):
    story = get_object_or_404(Story, pk=pk)
    item_id = request.data.get("item_id")
    if not item_id:
        return Response({"error": "item_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    raw_item = get_object_or_404(RawItem, pk=item_id)
    detach_item(story, raw_item, request.user)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
def run_cluster(request):
    """Trigger clustering over all UNTRIAGED items."""
    result = run_clustering()
    return Response(result)


@api_view(["GET"])
def published_detail(request, slug):
    """Public brief page — no auth required."""
    story = get_object_or_404(
        Story.objects.prefetch_related(
            "publications__revision",
            "publications__published_by",
            "story_items__item__source",
        ),
        slug=slug,
        status=Story.Status.PUBLISHED,
    )
    return Response(StoryDetailSerializer(story).data)


@api_view(["GET"])
def audit_log(request):
    qs = AuditEvent.objects.select_related("actor").order_by("-created_at")[:200]
    return Response(AuditEventSerializer(qs, many=True).data)
