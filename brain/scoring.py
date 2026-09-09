"""Pairwise same-event scoring.

The question this module answers is not "how similar is this text?" but "is this the
same event?" — and those come apart badly on newsroom copy. Two Phase 3 press releases
from two different companies share nearly every word of their vocabulary. A wire report
and a commuter's social post about the same shutdown share almost none.

So the score is a blend of four signals with different failure modes, plus a small set
of hard vetoes for the cases where a high text score is simply wrong.

Two things in here were arrived at by measuring rather than by reasoning, and both
contradicted what I expected — `python -m brain.explain --dist` is how they were caught:

* **Cosine similarity was removed.** It tracked the IDF-overlap measure below to within
  a few points on every symmetric pair, and was strictly worse on asymmetric ones (0.29
  against 0.48 for a 30-word social post beside a 77-word wire report). It earned nothing.
* **Weighting the headline and first paragraph separately was removed.** The theory was
  that news copy front-loads, so same-event copy should agree hardest at the top. The
  opposite held: it lowered every true pair and *raised* the two press releases that must
  not merge, because headlines are where house style diverges most while press-release
  headlines are near-identical boilerplate.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime

from . import text as T

# --- Weights -----------------------------------------------------------------
#
# Text carries the most weight because it is the only signal always present. Names come
# next: sharing "Vizhinjam" and "Arvent Holdings" is far more telling than sharing
# "payments" and "port". Figures and time are corroborating rather than deciding.

WEIGHT_TEXT = 0.45
WEIGHT_ENTITY = 0.25
WEIGHT_QUANTITY = 0.15
WEIGHT_TIME = 0.15

# How much shared rare-name weight counts as a convincing amount, expressed in names so
# it scales with the batch rather than being a magic number. Deliberately an absolute
# quantity and not a fraction of the shorter item's names: a post that mentions one place
# and shares it is *consistent* with a story, which is not the same as corroborating it.
# Dividing by the shorter list scored a commuter's "stuck at Indiranagar" 1.00 against
# both the metro wire copy and a what's-on listing that also happened to say Indiranagar.
ENTITY_SATURATION_NAMES = 3.0

# Same-event copy on a news desk lands within a day of itself. 36 hours puts a
# next-morning follow-up at ~0.37 rather than zero.
TIME_DECAY_HOURS = 36.0

# --- Confidence bands --------------------------------------------------------
#
# The grey band is the point of this design. A desk would rather see "possible
# duplicate, review" than have the software silently merge two stories or silently
# leave a triplicate on the list. Everything between these two numbers becomes a
# suggestion for a human, with the contributing signals shown.

AUTO_CLUSTER_THRESHOLD = 0.62
SUGGEST_THRESHOLD = 0.45

# A candidate must also keep the *average* link to every existing member above this,
# not just beat the threshold against its single best match. Without it, single-link
# clustering chains A~B~C together when B happens to sit between two unrelated items.
COHESION_FLOOR = 0.42

# Two items that each name several proper nouns and share none of them are very probably
# about different things, however alike the prose. Applied as a multiplier rather than a
# veto: strong evidence, not proof.
ENTITY_PENALTY = 0.55
ENTITY_RELIABLE_MIN_ENTITIES = 3
# A 30-word social post's entity set describes the writing, not the event. Requiring some
# prose length before trusting it stops "CLASS 12 DATE SHEET OUT — Feb 17" being penalised
# for not saying "February" the way the board's own notice does.
ENTITY_RELIABLE_MIN_TOKENS = 60

MAX_TIME_GAP_HOURS = 72.0

# Which kinds of source dateline from the event, and which from their own front desk.
WIRE_KINDS = frozenset({"WIRE"})


@dataclass
class ItemFeatures:
    """Everything the scorer needs from one raw item, computed once.

    The `*_idf` fields are filled in by `Corpus`, because rarity is a property of the
    batch rather than of the item. They are stored here rather than looked up through a
    corpus reference so that `score_pair` stays a pure function of two items.
    """

    key: str
    headline: str
    received_at: datetime
    published_at: datetime | None = None
    trust_tier: int = 3
    source_name: str = ""
    source_kind: str = "BLOG"

    grams: frozenset[str] = frozenset()
    token_count: int = 0
    entities: set[str] = field(default_factory=set)
    entity_toks: set[str] = field(default_factory=set)
    quantities: dict[str, set[float]] = field(default_factory=dict)
    dateline: str | None = None
    clean_body: str = ""
    lede: str = ""

    # Filled in by Corpus
    term_idf: dict[str, float] = field(default_factory=dict)
    idf_mass: float = 0.0
    entity_idf: dict[str, float] = field(default_factory=dict)
    entity_saturation: float = 1.0

    @property
    def timestamp(self) -> datetime:
        """Prefer the source's own clock; fall back to when we received it."""
        return self.published_at or self.received_at

    @property
    def entity_reliable(self) -> bool:
        """Whether an *absence* of shared names in this item means anything.

        Terse or lowercase social posts yield few, or junk, capitalized runs. That is a
        property of the writing, not evidence about the event, so it must not be allowed
        to push a score down.
        """
        return (
            len(self.entities) >= ENTITY_RELIABLE_MIN_ENTITIES
            and self.token_count >= ENTITY_RELIABLE_MIN_TOKENS
        )

    @property
    def dateline_is_event_location(self) -> bool:
        """A wire datelines from where the event happened.

        A press release datelines from where the *issuer* sits — Vayu Air files from
        Gurugram about new flights out of Bhubaneswar. Comparing the two kinds of
        dateline compares two different things, so the veto has to know which it holds.
        """
        return self.source_kind in WIRE_KINDS


def build_features(
    key: str,
    headline: str,
    body: str,
    received_at: datetime,
    published_at: datetime | None = None,
    trust_tier: int = 3,
    source_name: str = "",
    source_kind: str = "BLOG",
) -> ItemFeatures:
    clean = T.strip_boilerplate(body)
    paragraphs = [p.strip() for p in clean.split("\n") if p.strip()]

    # A full stop between headline and body so the two cannot bleed into one sentence.
    # Without it, a headline ending "...since 8.15" followed by a body opening "purple
    # line dead again" was read as a death toll of fifteen.
    combined = f"{headline.rstrip(' .:-')}.\n{clean}"

    tokens = T.tokenize(combined)
    entities = T.extract_entities(combined)
    return ItemFeatures(
        key=key,
        headline=headline,
        received_at=received_at,
        published_at=published_at,
        trust_tier=trust_tier,
        source_name=source_name,
        source_kind=source_kind,
        grams=frozenset(T.ngrams(tokens)),
        token_count=len(tokens),
        entities=entities,
        entity_toks=T.entity_tokens(entities),
        quantities=T.extract_quantities(combined),
        dateline=T.extract_dateline(clean),
        clean_body=clean,
        lede=paragraphs[0] if paragraphs else "",
    )


class Corpus:
    """Works out which words and names are rare in one batch of items, and tells each
    item what it is holding.

    The batch is the right reference class: on a day when nine items mention the monetary
    policy committee, that phrase should stop being distinctive.

    One deliberate departure from textbook TF-IDF: words appearing in only *one* item are
    dropped from the word table entirely. At this corpus size they are also the
    highest-IDF words, so keeping them was actively harmful — a reporter's own turns of
    phrase, unshareable by definition, made up two thirds of every item's weight and
    buried the agreement that mattered. Two reports of the same metro failure agreeing on
    Byappanahalli, 60,000 commuters and 12.40 pm scored 0.30; dropping the singletons put
    the same pair at 0.81.
    """

    MIN_DOCUMENT_FREQUENCY = 2

    def __init__(self, items: list[ItemFeatures]) -> None:
        self.items = items
        self.idf = self._idf((item.grams for item in items), len(items), self.MIN_DOCUMENT_FREQUENCY)
        # Names get their own table. "Halasuru" turns up in three items, all of them about
        # the same metro failure; "Committee" and "Corporation" turn up in a dozen
        # unrelated ones. Counting those two kinds of agreement equally is what left a
        # commuter's blog post at 0.44 against the wire copy beside it.
        #
        # No singleton floor here, unlike the word table. A name only one item uses still
        # belongs in that item's own weight: an item full of proper nouns nobody else
        # mentions really is thin evidence for any pairing.
        self.entity_idf = self._idf((item.entity_toks for item in items), len(items), 1)
        self.entity_saturation = ENTITY_SATURATION_NAMES * self._typical_name_weight()

        for item in items:
            item.term_idf = {g: self.idf[g] for g in item.grams if g in self.idf}
            item.idf_mass = sum(item.term_idf.values())
            item.entity_idf = {
                t: self.entity_idf[t] for t in item.entity_toks if t in self.entity_idf
            }
            item.entity_saturation = self.entity_saturation

    @staticmethod
    def _idf(term_sets, n: int, min_df: int) -> dict[str, float]:
        n = max(n, 1)
        document_frequency: dict[str, int] = {}
        for terms in term_sets:
            for term in terms:
                document_frequency[term] = document_frequency.get(term, 0) + 1
        # Smoothed IDF, floored at zero so a term present in every item contributes nothing.
        return {
            term: max(math.log((n + 1) / (df + 1)), 0.0)
            for term, df in document_frequency.items()
            if df >= min_df
        }

    def _typical_name_weight(self) -> float:
        """Median name weight, so the saturation point is expressed in names rather than
        in a magic constant that would drift as the batch size changes."""
        if not self.entity_idf:
            return 1.0
        return max(statistics.median(self.entity_idf.values()), 0.1)


def idf_overlap(left: ItemFeatures, right: ItemFeatures) -> float:
    """Share of the more concise item's distinctive vocabulary that both items use.

    Dividing by the smaller item's weight rather than by the union is what lets a 40-word
    social post be compared to a 400-word wire report at all.
    """
    denominator = min(left.idf_mass, right.idf_mass)
    if denominator <= 0:
        return 0.0
    smaller, larger = (
        (left.term_idf, right.term_idf)
        if len(left.term_idf) <= len(right.term_idf)
        else (right.term_idf, left.term_idf)
    )
    shared = sum(weight for term, weight in smaller.items() if term in larger)
    return min(shared / denominator, 1.0)


def entity_agreement(left: ItemFeatures, right: ItemFeatures) -> float:
    """How much rare-name agreement there is, saturating once it is convincing."""
    smaller, larger = (
        (left.entity_idf, right.entity_idf)
        if len(left.entity_idf) <= len(right.entity_idf)
        else (right.entity_idf, left.entity_idf)
    )
    shared = sum(weight for token, weight in smaller.items() if token in larger)
    return min(shared / left.entity_saturation, 1.0)


def time_proximity(left: ItemFeatures, right: ItemFeatures) -> float:
    return math.exp(-hours_apart(left, right) / TIME_DECAY_HOURS)


def hours_apart(left: ItemFeatures, right: ItemFeatures) -> float:
    return abs((left.timestamp - right.timestamp).total_seconds()) / 3600.0


def find_veto(left: ItemFeatures, right: ItemFeatures) -> str | None:
    """A reason these cannot be the same event, whatever the text says.

    Each of these is here because a real pair in the corpus needs it:

    * conflicting quantities — two crashes on NH-48 the same day, four dead and three
    * disjoint datelines — Palanpur and Sirohi; Hyderabad and Pune
    * time gap — a fare proposal and a cable fault, same corporation, three days apart
    """
    conflict = T.quantities_conflict(left.quantities, right.quantities)
    if conflict:
        return conflict

    dateline_conflict = _dateline_conflict(left, right)
    if dateline_conflict:
        return dateline_conflict

    gap = hours_apart(left, right)
    if gap > MAX_TIME_GAP_HOURS:
        return f"filed {gap:.0f} hours apart"

    return None


def _dateline_conflict(left: ItemFeatures, right: ItemFeatures) -> str | None:
    if not (left.dateline and right.dateline):
        return None
    # Only compare datelines that mean the same thing: both event locations (wire against
    # wire) or both issuer locations (release against release). Across kinds a mismatch is
    # expected and says nothing — which is why a Vayu Air release datelined Gurugram no
    # longer blocks the wire report datelined New Delhi about the same route announcement.
    if left.dateline_is_event_location != right.dateline_is_event_location:
        return None
    # Substring check so "new delhi" and "delhi" are not treated as different places.
    if left.dateline in right.dateline or right.dateline in left.dateline:
        return None
    return f"different datelines ({left.dateline} vs {right.dateline})"


@dataclass
class PairScore:
    left: str
    right: str
    score: float
    tfidf: float
    entity: float
    quantity: float
    time: float
    veto: str | None = None
    entity_penalty_applied: bool = False

    @property
    def band(self) -> str:
        if self.veto:
            return "separate"
        if self.score >= AUTO_CLUSTER_THRESHOLD:
            return "same"
        if self.score >= SUGGEST_THRESHOLD:
            return "review"
        return "separate"

    def explain(self) -> str:
        """Human-readable reasoning, shown in the UI next to a suggestion.

        A reporter who is told "possible duplicate" and nothing else will either trust
        it blindly or ignore it. Showing which signals fired makes the call reviewable.
        """
        if self.veto:
            return f"Kept separate: {self.veto}."
        parts = [f"wording {self.tfidf:.0%}"]
        if self.entity:
            parts.append(f"shared names {self.entity:.0%}")
        if self.quantity:
            parts.append(f"matching figures {self.quantity:.0%}")
        parts.append(f"filed {self.time:.0%} close in time")
        reason = ", ".join(parts)
        if self.entity_penalty_applied:
            reason += "; downweighted — no proper nouns in common"
        return reason


def score_pair(left: ItemFeatures, right: ItemFeatures) -> PairScore:
    """Blend the four signals, skipping any that neither item can supply."""
    text = idf_overlap(left, right)
    time = time_proximity(left, right)
    entity = entity_agreement(left, right)

    # Figures corroborate; they do not refute. Two accounts of one event routinely quote
    # different numbers from it — the wire counts 60,000 commuters, the blog counts forty
    # minutes on a platform — and the case where they genuinely contradict each other is
    # already a hard veto. So a shared figure lifts the score, and an unshared one is
    # treated as silence rather than as an argument against.
    quantity = (
        _quantity_overlap(left, right)
        if _quantities_comparable(left) and _quantities_comparable(right)
        else 0.0
    )

    # Renormalize over the signals actually present. A social post carrying no proper
    # nouns and no figures should be judged on the evidence it has, not penalized for
    # evidence it cannot carry — otherwise every terse post is a non-match by construction.
    terms: list[tuple[float, float]] = [(WEIGHT_TEXT, text), (WEIGHT_TIME, time)]
    if entity > 0.0:
        terms.append((WEIGHT_ENTITY, entity))
    if quantity > 0.0:
        terms.append((WEIGHT_QUANTITY, quantity))

    total_weight = sum(weight for weight, _ in terms)
    score = sum(weight * value for weight, value in terms) / total_weight

    penalty_applied = False
    if left.entity_reliable and right.entity_reliable and not (left.entity_toks & right.entity_toks):
        score *= ENTITY_PENALTY
        penalty_applied = True

    return PairScore(
        left=left.key,
        right=right.key,
        score=round(score, 4),
        tfidf=round(text, 4),
        entity=round(entity, 4),
        quantity=round(quantity, 4),
        time=round(time, 4),
        veto=find_veto(left, right),
        entity_penalty_applied=penalty_applied,
    )


def _quantities_comparable(item: ItemFeatures) -> bool:
    return any(
        item.quantities.get(unit) for unit in ("money", "dead", "injured", "figure", "percent")
    )


def _quantity_overlap(left: ItemFeatures, right: ItemFeatures) -> float:
    """Best per-unit overlap across the units both items report.

    Averaged across units rather than pooled, so an item quoting eight figures does not
    swamp one quoting two.
    """
    scores: list[float] = []
    for unit in ("money", "dead", "injured", "figure", "percent"):
        a, b = left.quantities.get(unit), right.quantities.get(unit)
        if not a or not b:
            continue
        if unit == "money":
            matches = sum(1 for x in a if any(T._close(x, y) for y in b))
            scores.append(matches / min(len(a), len(b)))
        else:
            scores.append(T.overlap_coefficient(a, b))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
