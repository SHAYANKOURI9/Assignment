import datetime as _dt
from django.utils import timezone
from datetime import timedelta, timezone as dt_timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from desk.models import Story, BriefRevision, AuditEvent
from ingest.models import RawItem


def _dwell_seconds(story):
    if story.first_item_received_at and story.first_published_at:
        return (story.first_published_at - story.first_item_received_at).total_seconds()
    return None


def _stage_seconds(start, end):
    if start and end:
        return (end - start).total_seconds()
    return None


@api_view(["GET"])
def dashboard(request):
    """
    Desk-head dashboard.
    ?date=YYYY-MM-DD  (defaults to yesterday UTC)
    """
    date_str = request.query_params.get("date")
    if date_str:
        try:
            d = _dt.date.fromisoformat(date_str)
            day_start = _dt.datetime(d.year, d.month, d.day, tzinfo=dt_timezone.utc)
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)
    else:
        now = timezone.now()
        day_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    day_end = day_start + timedelta(days=1)

    published = Story.objects.filter(
        status=Story.Status.PUBLISHED,
        first_published_at__gte=day_start,
        first_published_at__lt=day_end,
    ).select_related("assigned_to").prefetch_related("revisions", "publications__revision")

    count = published.count()

    by_subject = {}
    dwell_list = []
    stage_ingest_claim = []
    stage_claim_submit = []
    stage_submit_publish = []
    slowest = None
    slowest_dwell = -1

    for story in published:
        subj = story.subject[:60] or "Untitled"
        by_subject[subj] = by_subject.get(subj, 0) + 1

        d = _dwell_seconds(story)
        if d is not None:
            dwell_list.append(d)
            if d > slowest_dwell:
                slowest_dwell = d
                slowest = {"id": story.pk, "subject": story.subject, "dwell_minutes": round(d / 60)}

        s1 = _stage_seconds(story.first_item_received_at, story.claimed_at)
        s2 = _stage_seconds(story.claimed_at, story.submitted_at)
        s3 = _stage_seconds(story.submitted_at, story.first_published_at)
        if s1 is not None:
            stage_ingest_claim.append(s1)
        if s2 is not None:
            stage_claim_submit.append(s2)
        if s3 is not None:
            stage_submit_publish.append(s3)

    def _median(lst):
        if not lst:
            return None
        s = sorted(lst)
        return round(s[len(s) // 2] / 60)

    def _p90(lst):
        if not lst:
            return None
        s = sorted(lst)
        idx = int(len(s) * 0.9)
        return round(s[min(idx, len(s) - 1)] / 60)

    rewrite_rates = []
    for story in published:
        machine = story.revisions.filter(kind=BriefRevision.Kind.MACHINE_DRAFT).first()
        pub = story.publications.filter(
            status__in=["LIVE", "CORRECTED"]
        ).order_by("published_at").first()
        if machine and pub:
            m_words = set(machine.body.split())
            p_words = set(pub.revision.body.split())
            if m_words:
                changed = len(m_words.symmetric_difference(p_words)) / max(len(m_words), len(p_words))
                rewrite_rates.append(round(changed * 100))

    total_items_in = RawItem.objects.filter(
        received_at__gte=day_start, received_at__lt=day_end
    ).count()

    return Response({
        "date": day_start.date().isoformat(),
        "published_count": count,
        "by_subject": by_subject,
        "dwell": {
            "median_minutes": _median(dwell_list),
            "p90_minutes": _p90(dwell_list),
            "slowest": slowest,
        },
        "stages": {
            "ingest_to_claim_median_min": _median(stage_ingest_claim),
            "claim_to_submit_median_min": _median(stage_claim_submit),
            "submit_to_publish_median_min": _median(stage_submit_publish),
        },
        "rewrite_rate_pct": round(sum(rewrite_rates) / len(rewrite_rates)) if rewrite_rates else None,
        "dedup": {
            "items_in": total_items_in,
            "briefs_out": count,
            "saved": max(total_items_in - count, 0),
        },
    })
