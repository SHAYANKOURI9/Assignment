"""Optional LLM upgrades for three specific steps in the pipeline.

Activated when ANTHROPIC_API_KEY is set in the environment; degrades silently to the
deterministic fallbacks in `brain.clustering` and `brain.scoring` when it is not.

Three entry points:

* `draft_brief(cluster)`      — write a short editor brief from the seed item's wording
* `adjudicate_pair(pair, left, right)` — decide a borderline duplicate pair
* `read_screenshot(image_bytes)` — extract headline + body text from a screenshot

All three return plain Python values so callers need no knowledge of the Anthropic SDK.
"""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .clustering import Cluster
    from .scoring import ItemFeatures, PairScore

_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_MODEL = "claude-3-5-haiku-20241022"
_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        try:
            import anthropic  # type: ignore
            _CLIENT = anthropic.Anthropic(api_key=_API_KEY)
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is not installed. "
                "Run `pip install anthropic` or unset ANTHROPIC_API_KEY to use the "
                "deterministic fallback."
            ) from exc
    return _CLIENT


def available() -> bool:
    """Whether the LLM path is active."""
    return bool(_API_KEY)


# ---------------------------------------------------------------------------
# Brief drafting
# ---------------------------------------------------------------------------

def draft_brief(cluster: "Cluster") -> str:
    """One-paragraph editor brief for a cluster, starting from the seed item.

    Falls back to a plain summary built from the seed headline when the API is
    unavailable, so callers can always call this unconditionally.
    """
    if not available():
        return _fallback_brief(cluster)

    seed = cluster.seed()
    others = [m for m in cluster.ordered() if m.key != seed.key]
    other_headlines = "\n".join(f"- {m.headline}" for m in others)

    prompt = (
        f"You are a wire editor writing a one-paragraph brief (3–5 sentences) for a "
        f"story cluster. Start from the primary source below and incorporate any "
        f"additional detail from the supporting items. Write in plain prose, no bullet "
        f"points, no headline.\n\n"
        f"PRIMARY ({seed.source_name}):\n{seed.headline}\n\n{seed.clean_body}\n\n"
        + (f"SUPPORTING HEADLINES:\n{other_headlines}\n\n" if other_headlines else "")
        + "Brief:"
    )

    message = _client().messages.create(
        model=_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _fallback_brief(cluster: "Cluster") -> str:
    seed = cluster.seed()
    size = cluster.size
    sources = ", ".join(m.source_name for m in cluster.ordered())
    return (
        f"{seed.headline}. "
        f"Covered by {size} source{'s' if size != 1 else ''}: {sources}."
    )


# ---------------------------------------------------------------------------
# Borderline pair adjudication
# ---------------------------------------------------------------------------

def adjudicate_pair(
    pair: "PairScore",
    left: "ItemFeatures",
    right: "ItemFeatures",
) -> tuple[bool, str]:
    """Decide whether a borderline pair is the same event.

    Returns (same_event: bool, reason: str).  Falls back to the score band when
    the API is unavailable.
    """
    if not available():
        return _fallback_adjudicate(pair)

    prompt = (
        "You are a news editor deciding whether two items describe the same real-world "
        "event. Answer with exactly one word on the first line — SAME or DIFFERENT — "
        "then a single sentence of reasoning.\n\n"
        f"ITEM A ({left.source_name}):\n{left.headline}\n{left.lede}\n\n"
        f"ITEM B ({right.source_name}):\n{right.headline}\n{right.lede}\n\n"
        f"Similarity signals: {pair.explain()}\n\n"
        "Verdict:"
    )

    message = _client().messages.create(
        model=_MODEL,
        max_tokens=80,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    lines = text.splitlines()
    same = lines[0].strip().upper().startswith("SAME")
    reason = lines[1].strip() if len(lines) > 1 else text
    return same, reason


def _fallback_adjudicate(pair: "PairScore") -> tuple[bool, str]:
    from .scoring import AUTO_CLUSTER_THRESHOLD
    same = pair.score >= AUTO_CLUSTER_THRESHOLD and not pair.veto
    return same, pair.explain()


# ---------------------------------------------------------------------------
# Screenshot reading
# ---------------------------------------------------------------------------

def read_screenshot(image_bytes: bytes, media_type: str = "image/png") -> dict[str, str]:
    """Extract headline and body text from a screenshot of a news item.

    Returns a dict with keys ``headline`` and ``body``.  Falls back to empty
    strings when the API is unavailable (the caller must handle that case).
    """
    if not available():
        return {"headline": "", "body": ""}

    b64 = base64.standard_b64encode(image_bytes).decode()
    message = _client().messages.create(
        model=_MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract the news article text from this screenshot. "
                            "Reply with exactly two sections separated by a blank line:\n"
                            "HEADLINE: <the headline>\n\n"
                            "<the body text, preserving paragraph breaks>"
                        ),
                    },
                ],
            }
        ],
    )
    raw = message.content[0].text.strip()
    headline = ""
    body = raw
    if raw.upper().startswith("HEADLINE:"):
        first_line, _, rest = raw.partition("\n")
        headline = first_line[len("HEADLINE:"):].strip()
        body = rest.strip()
    return {"headline": headline, "body": body}
