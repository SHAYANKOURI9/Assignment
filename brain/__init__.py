"""Clustering and brief drafting, with no dependency on Django or on numpy/scikit-learn.

Kept importable on its own for two reasons. It can be run and tested directly against
`seed/raw_items.json` with nothing installed (`python -m brain.explain`), and it forces
the same-event logic to stay free of ORM entanglement.

The deterministic path here always works. `brain.llm` optionally upgrades three specific
steps when ANTHROPIC_API_KEY is set — brief drafting, adjudicating borderline duplicate
pairs, and reading a screenshot — and degrades to this code when it is not.
"""

from .clustering import Cluster, ClusterResult, Suggestion, cluster_items
from .scoring import (
    AUTO_CLUSTER_THRESHOLD,
    SUGGEST_THRESHOLD,
    Corpus,
    ItemFeatures,
    PairScore,
    build_features,
    score_pair,
)

__all__ = [
    "AUTO_CLUSTER_THRESHOLD",
    "SUGGEST_THRESHOLD",
    "Cluster",
    "ClusterResult",
    "Corpus",
    "ItemFeatures",
    "PairScore",
    "Suggestion",
    "build_features",
    "cluster_items",
    "score_pair",
]
