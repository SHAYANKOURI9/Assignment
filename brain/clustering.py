"""Grouping same-event items into stories.

Single-link agglomerative clustering with two guards a naive implementation lacks:

1. A candidate must clear the threshold against its best match *and* keep the mean link
   to the whole cluster above a floor. Plain single-link chains A~B~C together whenever
   B sits between two unrelated items.
2. A hard veto against any existing member blocks the join outright, so a veto is
   transitive. Two crashes on the same highway cannot end up in one story via a third
   item that resembles both.

Items are processed in `received_at` order, so a run over the same input always produces
the same clusters — which matters when the output is a story a person then edits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .scoring import (
    AUTO_CLUSTER_THRESHOLD,
    COHESION_FLOOR,
    SUGGEST_THRESHOLD,
    Corpus,
    ItemFeatures,
    PairScore,
    score_pair,
)


@dataclass
class Cluster:
    """One candidate story: the items, and why they were put together."""

    members: list[ItemFeatures] = field(default_factory=list)
    links: list[PairScore] = field(default_factory=list)

    @property
    def keys(self) -> list[str]:
        return [item.key for item in self.members]

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def confidence(self) -> float:
        """Weakest link in the cluster — the honest number to show a reporter."""
        if not self.links:
            return 1.0
        return min(link.score for link in self.links)

    def seed(self) -> ItemFeatures:
        """Whose wording the machine draft starts from.

        Highest trust tier first (a wire outranks a company release outranks a blog),
        then the earliest filed. A press release is a party to the story; a wire report
        is trying to describe it.
        """
        return sorted(self.members, key=lambda item: (item.trust_tier, item.timestamp))[0]

    def ordered(self) -> list[ItemFeatures]:
        return sorted(self.members, key=lambda item: (item.trust_tier, item.timestamp))


@dataclass
class Suggestion:
    """A pair the system is not confident enough to act on by itself.

    This is the deliberate answer to "sometimes two things that looked separate turn out
    to be the same event": rather than guess, surface the pair with its reasoning and
    let an editor decide. Also what a post-publication merge starts from.

    `confident` marks the pairs that scored high enough to have been auto-clustered but
    couldn't be, because each item was already committed to a different story. Those go to
    the top of an editor's merge queue; the grey-band ones below are genuine coin-flips.
    """

    left: str
    right: str
    score: float
    reason: str
    confident: bool = False
    left_cluster: int | None = None
    right_cluster: int | None = None


@dataclass
class ClusterResult:
    clusters: list[Cluster]
    suggestions: list[Suggestion]
    pairs: dict[tuple[str, str], PairScore]

    def cluster_of(self, key: str) -> Cluster | None:
        for cluster in self.clusters:
            if key in cluster.keys:
                return cluster
        return None

    def pair(self, left: str, right: str) -> PairScore | None:
        return self.pairs.get(_pair_key(left, right))


def cluster_items(
    items: list[ItemFeatures],
    threshold: float = AUTO_CLUSTER_THRESHOLD,
    suggest_threshold: float = SUGGEST_THRESHOLD,
    cohesion_floor: float = COHESION_FLOOR,
) -> ClusterResult:
    """Group items into candidate stories and collect borderline pairs for review."""
    ordered = sorted(items, key=lambda item: (item.received_at, item.key))
    Corpus(ordered)  # computes IDF and fills each item's L2-normalized vector

    pairs: dict[tuple[str, str], PairScore] = {}
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            pairs[_pair_key(left.key, right.key)] = score_pair(left, right)

    clusters: list[Cluster] = []
    for item in ordered:
        best_cluster: Cluster | None = None
        best_score = 0.0
        for cluster in clusters:
            verdict = _evaluate_join(item, cluster, pairs, threshold, cohesion_floor)
            if verdict is not None and verdict > best_score:
                best_cluster, best_score = cluster, verdict
        if best_cluster is None:
            clusters.append(Cluster(members=[item]))
            continue
        for member in best_cluster.members:
            best_cluster.links.append(pairs[_pair_key(item.key, member.key)])
        best_cluster.members.append(item)

    return ClusterResult(
        clusters=clusters,
        suggestions=_collect_suggestions(clusters, pairs, threshold, suggest_threshold),
        pairs=pairs,
    )


def _evaluate_join(
    item: ItemFeatures,
    cluster: Cluster,
    pairs: dict[tuple[str, str], PairScore],
    threshold: float,
    cohesion_floor: float,
) -> float | None:
    """Score for joining this cluster, or None if it must not join."""
    scores: list[float] = []
    for member in cluster.members:
        pair = pairs[_pair_key(item.key, member.key)]
        if pair.veto:
            return None  # a veto against any member blocks the whole cluster
        scores.append(pair.score)

    best = max(scores)
    if best < threshold:
        return None
    if sum(scores) / len(scores) < cohesion_floor:
        return None  # resembles one member but not the group — the chaining case
    return best


def _collect_suggestions(
    clusters: list[Cluster],
    pairs: dict[tuple[str, str], PairScore],
    threshold: float,
    suggest_threshold: float,
) -> list[Suggestion]:
    """Cross-cluster pairs worth a human's attention, best first, one per cluster pair.

    Note what is *not* filtered out: a pair scoring above the auto-cluster threshold that
    nonetheless ended up in two different clusters. Those are the strongest merge
    candidates in the batch, not the weakest. It happens when an item matched two clusters
    and could only join its best one, or when the cohesion floor blocked the join — and
    the late wire item that ties a published story to another published story is exactly
    that shape. Dropping them was silently discarding the most important suggestions.
    """
    index_of: dict[str, int] = {
        key: position for position, cluster in enumerate(clusters) for key in cluster.keys
    }
    best_per_cluster_pair: dict[tuple[int, int], Suggestion] = {}

    for pair in pairs.values():
        if pair.veto or pair.score < suggest_threshold:
            continue
        left_cluster, right_cluster = index_of[pair.left], index_of[pair.right]
        if left_cluster == right_cluster:
            continue
        cluster_key = (min(left_cluster, right_cluster), max(left_cluster, right_cluster))
        existing = best_per_cluster_pair.get(cluster_key)
        if existing is None or pair.score > existing.score:
            best_per_cluster_pair[cluster_key] = Suggestion(
                left=pair.left,
                right=pair.right,
                score=pair.score,
                reason=pair.explain(),
                confident=pair.score >= threshold,
                left_cluster=left_cluster,
                right_cluster=right_cluster,
            )

    return sorted(best_per_cluster_pair.values(), key=lambda s: -s.score)


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)
