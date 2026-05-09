"""Master Terminal — weighted decision CLI tool v0.5.

Pokazuje wszystkie 7 layerów confluence:
  1. Source-edge votes  2. Composite voter  3. Liquidity bias
  4. GEX walls  5. MTF coherence  6. WFA stability  7. Adaptive threshold

Run:
    python scripts/decision.py
    python scripts/decision.py --since 720
    python scripts/decision.py --wfa   # show WFA table for top sources
"""
from __future__ import annotations

import argparse
import sys

from master.config import CONFIG
from master.core import wfa
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
    if d.weighted_score >= 1.0:
        return f"STRONG {d.direction} — A-grade setup"
    if d.weighted_score >= 0.5:
        return f"{d.direction} — B-grade setup"
    if d.weighted_score >= 0.3:
        return f"weak {d.direction} — watch only"
    return "STAND DOWN — no clear edge"


def main() -> int:
    parser = argparse.ArgumentParser(description="Master Terminal weighted decision")
    parser.add_argument("--since", type=int, default=DEFAULT_SINCE_MINUTES)
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    parser.add_argument("--fade", type=float, default=DEFAULT_FADE_THRESHOLD)
    parser.add_argument("--wfa", action="store_true",
                        help="show WFA stability table for top sources only")
    args = parser.parse_args()

    fs = FeatureStore(CONFIG)

    # WFA-only mode
    if args.wfa:
        print("=" * 72)
        print("WFA STABILITY — recent 7d vs full 30d edge")
        print("=" * 72)
        print()
        stab = wfa.check_top_sources_stability(
            fs, full_days=args.lookback, recent_days=7, min_samples=args.min_samples
        )
        if not stab:
            print("brak source z wystarczającą historią")
            return 0
        print(f"  {'source':25s}  {'full E':>9s}  {'recent E':>9s}  "
              f"{'Δ':>7s}  {'drop':>6s}  status")
        print("  " + "─" * 70)
        for src, s in sorted(stab.items(), key=lambda kv: kv[1].full_window_r, reverse=True):
            status = "✓ stable" if s.stable else "✗ UNSTABLE"
            print(f"  {src:25s}  {s.full_window_r:+8.3f}R  "
                  f"{s.recent_window_r:+8.3f}R  {s.delta:+7.3f}  "
                  f"{s.relative_drop:>5.0%}   {status}")
            if not s.stable:
                print(f"    └ {s.reason}")
        return 0

    # Standard mode
    composite = fs.read_composite()
    decision = compute_weighted_decision(
        fs,
        since_minutes=args.since,
        lookback_days=args.lookback,
        min_samples=args.min_samples,
        fade_threshold=args.fade,
    )
    liq = fs.has_recent_liquidity_event(since_minutes=30)
    options = fs.read_options_state()
    fresh = fs.check_freshness()

    print("=" * 72)
    print(f"MASTER TERMINAL — WEIGHTED DECISION v0.5  (instrument: {CONFIG.instrument})")
    print("=" * 72)

    print()
    print(f"Window: ostatnie {args.since}min sygnałów, edge z {args.lookback} dni")
    print(f"Świeżość danych: {fresh.reason}")

    print()
    print("─── Layer 2: Composite (forecast m1-m12 meta) ───")
    if composite:
        print(f"  direction: {composite.direction:6s}  conviction: {composite.conviction}  "
              f"score: {composite.score:+.3f}")
        print(f"  contribution: {decision.composite_contribution:+.3f}R")
    else:
        print("  unavailable")

    print()
    print(f"─── Layer 1: Source-edge votes ───")
    print(f"  sygnałów raw: {decision.raw_count}, "
          f"FLAT/zero-conf pominięto: {decision.flat_skipped}, "
          f"realnych source: {decision.n_sources_with_edge}, "
          f"fade'owanych: {decision.fade_count}")
    if decision.contributing:
        sorted_contrib = sorted(
            ((k, v) for k, v in decision.contributing.items() if v != 0.0),
            key=lambda x: abs(x[1]), reverse=True
        )
        for src, contrib in sorted_contrib:
            arrow = "↑ LONG " if contrib > 0 else "↓ SHORT" if contrib < 0 else "  FLAT "
            tag = ""
            if src == "composite_meta":
                tag = " [composite]"
            elif src == "liquidity_meta":
                tag = " [liquidity]"
            elif src in decision.sources_unstable:
                tag = " [WFA-flagged]"
            print(f"  {arrow}  {src:25s}  {contrib:+.3f}R{tag}")

    print()
    print("─── Layer 3: Liquidity bias (ICE events 30min) ───")
    if liq:
        print(f"  {liq.event_type} @ {liq.level_price:.4f}  side={liq.side}  "
              f"qty={liq.qty}  conf={liq.confidence:.2f}")
        print(f"  modifier total: {decision.liquidity_modifier:+.3f}R")
    else:
        print("  none")

    print()
    print("─── Layer 4: GEX walls ───")
    if options and options.flip_level:
        print(f"  flip_level: {options.flip_level:.4f}  "
              f"gex: {options.gex:+.0f} ({options.gex_direction})")
        if decision.gex_warning:
            print(f"  ⚠️  {decision.gex_warning}")
    else:
        print("  unavailable")

    print()
    print(f"─── Layer 5: MTF coherence ───")
    print(f"  alignment: {decision.mtf_alignment}")

    print()
    print(f"─── Layer 6: WFA stability ───")
    if decision.sources_unstable:
        print(f"  unstable (recent edge wycieka): {', '.join(decision.sources_unstable)}")
    else:
        print(f"  all top sources stable")

    print()
    print(f"─── Layer 7: Adaptive threshold ───")
    print(f"  decision threshold: {decision.decision_threshold_used:.2f}R "
          f"(default {DEFAULT_DECISION_THRESHOLD:.2f}R)")

    print()
    print("=" * 72)
    print(f"FINAL Weighted Decision:")
    print(f"  direction:       {decision.direction}")
    print(f"  weighted_score:  {decision.weighted_score:+.3f}R")
    print(f"  weighted_long:   {decision.weighted_long:+.3f}R")
    print(f"  weighted_short:  {decision.weighted_short:+.3f}R")

    if decision.notes:
        print()
        print("Notatki pipeline:")
        for n in decision.notes:
            print(f"  • {n}")

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
