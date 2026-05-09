"""Master Terminal — weighted decision CLI tool.

Cienki wrapper nad `master.core.decision.compute_weighted_decision`.
Pokazuje weighted decision w czytelnej formie do diagnostyki.

Run:
    python scripts/decision.py
    python scripts/decision.py --since 720 --lookback 14
"""
from __future__ import annotations

import argparse
import sys

from master.config import CONFIG
from master.core.decision import (
    DEFAULT_DECISION_THRESHOLD,
    DEFAULT_FADE_THRESHOLD,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_SINCE_MINUTES,
    WeightedDecision,
    compute_weighted_decision,
)
from master.data.feature_store import FeatureStore


def render_verdict(d: WeightedDecision) -> str:
    """Master-style verdict z weighted decision."""
    if d.weighted_score >= 1.0:
        return f"STRONG {d.direction} — A-grade setup"
    if d.weighted_score >= 0.5:
        return f"{d.direction} — B-grade setup"
    if d.weighted_score >= 0.3:
        return f"weak {d.direction} — watch only"
    return "STAND DOWN — no clear edge"


def main() -> int:
    parser = argparse.ArgumentParser(description="Master Terminal weighted decision")
    parser.add_argument("--since", type=int, default=DEFAULT_SINCE_MINUTES,
                        help="lookback window for current signals (minutes)")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help="lookback window for edge calculation (days)")
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    parser.add_argument("--fade", type=float, default=DEFAULT_FADE_THRESHOLD,
                        help="threshold below which source is faded (default -0.2)")
    args = parser.parse_args()

    fs = FeatureStore(CONFIG)

    composite = fs.read_composite()
    decision = compute_weighted_decision(
        fs,
        since_minutes=args.since,
        lookback_days=args.lookback,
        min_samples=args.min_samples,
        fade_threshold=args.fade,
    )
    liq = fs.has_recent_liquidity_event(since_minutes=30)
    fresh = fs.check_freshness()

    print("=" * 72)
    print(f"MASTER TERMINAL — WEIGHTED DECISION  (instrument: {CONFIG.instrument})")
    print("=" * 72)

    print()
    print(f"Window: ostatnie {args.since}min sygnałów, edge z {args.lookback} dni")
    print(f"Świeżość danych: {fresh.reason}")

    print()
    print("Composite (forecast m1-m12 meta-aggregator):")
    if composite:
        print(f"  direction: {composite.direction:6s}  conviction: {composite.conviction}")
        print(f"  score: {composite.score:+.3f}  votes: {composite.votes}")
    else:
        print("  unavailable")

    print()
    print(f"Weighted Decision  (sygnałów raw: {decision.raw_count}, "
          f"FLAT/zero-conf pominięto: {decision.flat_skipped}, "
          f"realnych source: {decision.n_sources_with_edge}, "
          f"fade'owanych: {decision.fade_count}):")
    print(f"  direction:       {decision.direction}")
    print(f"  weighted_score:  {decision.weighted_score:+.3f}R")
    print(f"  weighted_long:   {decision.weighted_long:+.3f}R")
    print(f"  weighted_short:  {decision.weighted_short:+.3f}R")

    print()
    print("Per-source contributions (sortowane po sile):")
    if decision.contributing:
        sorted_contrib = sorted(decision.contributing.items(),
                               key=lambda x: abs(x[1]), reverse=True)
        for src, contrib in sorted_contrib:
            arrow = "↑ LONG " if contrib > 0 else "↓ SHORT" if contrib < 0 else "  FLAT "
            print(f"  {arrow}  {src:25s}  {contrib:+.3f}R")
    else:
        print("  brak (żaden source nie zgłosił sygnału w oknie)")

    print()
    print("Liquidity event (last 30min):")
    if liq:
        print(f"  {liq.event_type} @ {liq.level_price:.4f}  side={liq.side}  "
              f"qty={liq.qty}  conf={liq.confidence:.2f}")
    else:
        print("  none")

    print()
    print("=" * 72)
    print(f"VERDICT: {render_verdict(decision)}")

    if composite and decision.direction != "FLAT":
        comp_dir = composite.direction
        master_dir = decision.direction
        aligned = (
            (master_dir == "LONG" and comp_dir == "BULL") or
            (master_dir == "SHORT" and comp_dir == "BEAR")
        )
        if not aligned and comp_dir != "NEUT":
            print(f"WARNING: Master = {master_dir}, ale composite = {comp_dir} — sprzeczność")

    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())
