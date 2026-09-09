"""Run the clusterer over the seed corpus and print what it decided, and why.

    python -m brain.explain                 # summary: clusters, suggestions, accuracy
    python -m brain.explain --dist          # same-event vs different-event score spread
    python -m brain.explain --pairs         # every scored pair above the noise floor
    python -m brain.explain --case metro-purple-line-fault

Needs nothing installed — stock Python, no Django. Useful while tuning the weights, and
useful to a reviewer who wants to see the reasoning without running the app.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .clustering import cluster_items
from .scoring import AUTO_CLUSTER_THRESHOLD, SUGGEST_THRESHOLD, build_features

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


def load_corpus(now: datetime | None = None):
    """Read the seed files and resolve relative hour offsets into real timestamps."""
    now = now or datetime.now(timezone.utc)
    sources = {
        entry["slug"]: entry
        for entry in json.loads((SEED_DIR / "sources.json").read_text())["sources"]
    }
    raw = json.loads((SEED_DIR / "raw_items.json").read_text())["items"]

    features = []
    truth: dict[str, str | None] = {}
    for item in raw:
        source = sources[item["source"]]
        features.append(
            build_features(
                key=item["external_id"],
                headline=item["headline"],
                body=item["body"],
                received_at=now + timedelta(hours=item["received_offset_hours"]),
                published_at=now + timedelta(hours=item["published_offset_hours"]),
                trust_tier=source["trust_tier"],
                source_name=source["name"],
                source_kind=source["kind"],
            )
        )
        truth[item["external_id"]] = item.get("expected_event")
    return features, truth, raw


def summarize(features, truth) -> int:
    result = cluster_items(features)
    by_key = {item.key: item for item in features}

    print(f"\n{len(features)} raw items -> {len(result.clusters)} candidate stories")
    print(f"thresholds: auto >= {AUTO_CLUSTER_THRESHOLD}, review >= {SUGGEST_THRESHOLD}\n")

    multi = [c for c in result.clusters if c.size > 1]
    print(f"-- {len(multi)} grouped, {len(result.clusters) - len(multi)} single-item --\n")
    for cluster in sorted(result.clusters, key=lambda c: -c.size):
        if cluster.size == 1:
            continue
        events = {truth[key] for key in cluster.keys}
        flag = "OK " if len(events) == 1 else "BAD"
        print(f"{flag} [{cluster.size}] conf {cluster.confidence:.2f}  {cluster.seed().headline[:66]}")
        for item in cluster.ordered():
            print(f"       - {item.key:<14} t{item.trust_tier}  {truth[item.key]}")
        print()

    if result.suggestions:
        print(f"-- {len(result.suggestions)} pairs flagged for human review --\n")
        for suggestion in result.suggestions:
            # Guarded against None on both sides: two noise items are not "the same
            # event" just because neither belongs to one.
            same = truth[suggestion.left] is not None and (
                truth[suggestion.left] == truth[suggestion.right]
            )
            verdict = "(really same)" if same else "(really different)"
            rank = "would auto-merge" if suggestion.confident else "grey band"
            print(f"  {suggestion.score:.2f}  {verdict}  [{rank}]")
            print(f"        {by_key[suggestion.left].headline[:72]}")
            print(f"        {by_key[suggestion.right].headline[:72]}")
            print(f"        {suggestion.reason}\n")

    return _score_against_truth(result, truth)


def _score_against_truth(result, truth) -> int:
    """Compare against the ground-truth event labels in the seed file.

    `expected_event` exists only for this check and for the test suite. The application
    never reads it — it would be cheating if it did.

    Three buckets, not two. A same-event pair the system flagged for human review is not
    a failure: the grey band is a designed behaviour, and the post-publication merge case
    depends on it. Only a pair nobody was ever going to be shown was actually missed.

    Deferral is judged between *clusters*, not between items. Suggestions are deliberately
    one-per-cluster-pair — showing an editor the same two stories four times over, once per
    constituent item, is not a feature — so the item's strongest link is the one that
    surfaces. Asking whether each individual pair appears in the list called two of the
    metro social post's three links "missed" while the third was on screen, which describes
    the reporting rather than the software.
    """
    keys = [item.key for cluster in result.clusters for item in cluster.members]
    assigned = {key: index for index, cluster in enumerate(result.clusters) for key in cluster.keys}
    linked_clusters = {
        _pair(suggestion.left_cluster, suggestion.right_cluster)
        for suggestion in result.suggestions
    }

    missed: list[tuple[str, str]] = []
    deferred: list[tuple[str, str]] = []
    wrong: list[tuple[str, str]] = []
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            same_truth = truth[left] is not None and truth[left] == truth[right]
            same_cluster = assigned[left] == assigned[right]
            if same_truth and not same_cluster:
                in_review = _pair(assigned[left], assigned[right]) in linked_clusters
                (deferred if in_review else missed).append((left, right))
            elif same_cluster and not same_truth:
                wrong.append((left, right))

    print("-- accuracy against the seed file's ground truth --")
    _print_bucket("wrong groupings (different events, merged)", wrong, result)
    _print_bucket("missed groupings (same event, never surfaced)", missed, result)
    _print_bucket("deferred to a human (same event, flagged for review)", deferred, result)
    print()
    return 0 if not wrong and not missed else 1


def _print_bucket(label: str, pairs: list[tuple[str, str]], result) -> None:
    print(f"   {label}: {len(pairs)}")
    for left, right in pairs:
        pair = result.pair(left, right)
        print(f"       {left} ~ {right}  score {pair.score:.3f}  {pair.explain()}")


def _pair(left, right) -> tuple:
    return (left, right) if left <= right else (right, left)


def show_case(features, truth, event: str) -> int:
    """Every pair involving one ground-truth event, with each signal broken out."""
    result = cluster_items(features)
    by_key = {item.key: item for item in features}
    members = [key for key, value in truth.items() if value == event]
    if not members:
        print(f"no items tagged {event!r}", file=sys.stderr)
        return 2

    print(f"\n{event}: {len(members)} items\n")
    for key in members:
        print(f"  {key:<14} {by_key[key].headline[:70]}")
        item = by_key[key]
        print(f"       dateline={item.dateline}  entities={len(item.entities)}"
              f"  quantities={ {k: sorted(v) for k, v in item.quantities.items()} }")
    print()

    print(f"  {'pair':<32} {'total':>6} {'text':>6} {'names':>6} {'figs':>6} {'time':>6}  verdict")
    for index, left in enumerate(members):
        for right in members[index + 1 :]:
            _print_pair(result, left, right)
    print("\n  strongest links to items outside this event:")
    scored = []
    for key in members:
        for other in by_key:
            if other in members:
                continue
            pair = result.pair(key, other)
            if pair:
                scored.append((pair.score, key, other))
    for _, left, right in sorted(scored, reverse=True)[:6]:
        _print_pair(result, left, right)
    print()
    return 0


def _print_pair(result, left: str, right: str) -> None:
    pair = result.pair(left, right)
    label = f"{left} ~ {right}"
    print(
        f"  {label:<32} {pair.score:>6.3f} {pair.tfidf:>6.3f} {pair.entity:>6.3f}"
        f" {pair.quantity:>6.3f} {pair.time:>6.3f}  {pair.band}"
        + (f" ({pair.veto})" if pair.veto else "")
    )


def show_pairs(features, truth, floor: float) -> int:
    result = cluster_items(features)
    rows = sorted(result.pairs.values(), key=lambda p: -p.score)
    print(f"\nall pairs scoring >= {floor}\n")
    print(f"  {'pair':<32} {'total':>6} {'text':>6} {'names':>6} {'figs':>6} {'time':>6}  truth")
    for pair in rows:
        if pair.score < floor:
            break
        same = truth[pair.left] is not None and truth[pair.left] == truth[pair.right]
        label = f"{pair.left} ~ {pair.right}"
        print(
            f"  {label:<32} {pair.score:>6.3f} {pair.tfidf:>6.3f} {pair.entity:>6.3f}"
            f" {pair.quantity:>6.3f} {pair.time:>6.3f}  "
            f"{'SAME' if same else 'diff'} {pair.band}"
            + (f" ({pair.veto})" if pair.veto else "")
        )
    print()
    return 0


def show_distribution(features, truth) -> int:
    """Where the same-event and different-event pairs actually sit, so the thresholds
    can be read off the data instead of guessed.

    The two populations are wildly unbalanced — 1,770 pairs, of which ~30 are genuinely
    the same event — so what matters is not an average but the *gap*: the lowest-scoring
    true pair against the highest-scoring false one, once vetoes have done their work.
    """
    result = cluster_items(features)
    by_key = {item.key: item for item in features}

    same: list = []
    different: list = []
    for pair in result.pairs.values():
        if truth[pair.left] is None or truth[pair.right] is None:
            different.append(pair)  # noise items belong with no one
        elif truth[pair.left] == truth[pair.right]:
            same.append(pair)
        else:
            different.append(pair)

    live_different = [p for p in different if not p.veto]
    print(f"\n{len(same)} truly-same pairs, {len(different)} truly-different"
          f" ({len(different) - len(live_different)} of those vetoed outright)\n")

    print("-- every truly-same pair, weakest first --")
    print(f"  {'pair':<32} {'total':>6} {'text':>6} {'names':>6} {'figs':>6} {'time':>6}  band")
    for pair in sorted(same, key=lambda p: p.score):
        _print_pair(result, pair.left, pair.right)

    print("\n-- highest-scoring truly-different pairs that no veto stopped --")
    print(f"  {'pair':<32} {'total':>6} {'text':>6} {'names':>6} {'figs':>6} {'time':>6}  band")
    for pair in sorted(live_different, key=lambda p: -p.score)[:12]:
        _print_pair(result, pair.left, pair.right)
        print(f"       {by_key[pair.left].headline[:70]}")
        print(f"       {by_key[pair.right].headline[:70]}")

    ceiling = max((p.score for p in live_different), default=0.0)
    print(f"\n  highest un-vetoed false pair: {ceiling:.3f}")
    above = sorted(p.score for p in same if p.score > ceiling)
    print(f"  {len(above)} of {len(same)} true pairs score above it"
          f"{f' (weakest {above[0]:.3f})' if above else ''}")
    print(f"  any threshold in ({ceiling:.3f}, {above[0]:.3f}) separates them cleanly\n"
          if above else "  no clean separating threshold exists\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", action="store_true", help="list every scored pair")
    parser.add_argument("--floor", type=float, default=0.35, help="score floor for --pairs")
    parser.add_argument("--dist", action="store_true", help="same vs different score spread")
    parser.add_argument("--case", help="ground-truth event slug to inspect in detail")
    args = parser.parse_args()

    features, truth, _ = load_corpus()
    if args.case:
        return show_case(features, truth, args.case)
    if args.dist:
        return show_distribution(features, truth)
    if args.pairs:
        return show_pairs(features, truth, args.floor)
    return summarize(features, truth)


if __name__ == "__main__":
    raise SystemExit(main())
