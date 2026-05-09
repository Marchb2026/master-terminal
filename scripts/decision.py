"""Master Terminal — weighted decision based on source edge analysis.

Insight z 74,556 sygnałów (XGB: E=+0.491R, vote_MICRO: E=-1.339R) — różne
source mają DRAMATYCZNIE różny edge. Klasyczna confluence (zlicz głosy)
jest tu szkodliwa, bo 5 źródeł o ujemnym E krzyczących LONG to mocny
argument PRZECIWKO longowi.

Ten skrypt:
1. Pobiera aktualne sygnały z signals_unified.db (ostatnie X min)
2. Pobiera historical expectancy per source (rolling window 30 dni)
3. Waży każdy aktualny sygnał przez jego edge
4. Source z E < fade_threshold ma kierunek odwrócony (fade)
5. Liczy weighted_long vs weighted_short, decyduje
6. Sprawdza composite + liquidity events jako sanity
7. Pokazuje finalny verdict: STRONG/B/watch/STAND DOWN

Run:
    python scripts/decision.py
    python scripts/decision.py --since 60 --lookback 14   # ostatnia godzina, edge z 14 dni
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from master.config import CONFIG
from master.data.feature_store import FeatureStore


# Domyślne progi (dostosowane do tego co zobaczyliśmy w sanity check)
DEFAULT_SINCE_MINUTES = 15
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MIN_SAMPLES = 50
DEFAULT_FADE_THRESHOLD = -0.2     # source z E < -0.2R = fade
DEFAULT_DECISION_THRESHOLD = 0.3   # min |delta| żeby pokazać kierunek


@dataclass
class WeightedDecision:
    direction: str                              # LONG / SHORT / FLAT
    weighted_score: float                       # net edge w R-multiples
    weighted_long: float
    weighted_short: float
    contributing: dict[str, float] = field(default_factory=dict)  # source -> ±contrib
    fade_count: int = 0
    raw_count: int = 0
    n_sources_with_edge: int = 0
    flat_skipped: int = 0     # ile FLAT/zero-conf placeholderów pominięto


def compute_weighted_decision(
    fs: FeatureStore,
    since_minutes: int = DEFAULT_SINCE_MINUTES,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    fade_threshold: float = DEFAULT_FADE_THRESHOLD,
    decision_threshold: float = DEFAULT_DECISION_THRESHOLD,
) -> WeightedDecision:
    """Liczy weighted decision dla aktualnego stanu rynku."""

    # 1. Najnowsze sygnały (bez filtra confidence — bierzemy wszystko, filtr robimy poniżej)
    # Wysoki limit żeby objąć wszystkie source mimo FLAT placeholderów EA.
    recent = fs.read_recent_signals(since_minutes=since_minutes, limit=5000)

    # 2. Edge per source (rolling window)
    sources = fs.get_top_sources(
        lookback_days=lookback_days,
        min_samples=min_samples,
    )
    edge_per_source = {s.source: s for s in sources}

    # 3. Wagowanie
    weighted_long = 0.0
    weighted_short = 0.0
    contributing: dict[str, float] = {}
    seen: set[str] = set()
    fade_count = 0
    flat_skipped = 0

    for sig in recent:
        # Każdy source głosuje raz (bierzemy najnowszy realny sygnał)
        if sig.source in seen:
            continue

        # SKIP "no signal" placeholders — EA zapisuje co kilka sekund rekordy
        # z direction=FLAT i confidence=0 jako proof-of-life. To nie są decyzje
        # tradingowe, tylko status updates. Idziemy dalej do najnowszego realnego.
        if sig.direction == "FLAT" or sig.confidence <= 0.0:
            flat_skipped += 1
            continue

        seen.add(sig.source)

        # Brak danych historycznych = ignorujemy
        if sig.source not in edge_per_source:
            continue

        edge_r = edge_per_source[sig.source].expectancy_r

        # Fade logic
        if edge_r < fade_threshold:
            # Silnie negatywny E → odwracamy kierunek
            fade_count += 1
            effective_edge = abs(edge_r)
            if sig.direction == "LONG":
                effective_dir = "SHORT"
            elif sig.direction == "SHORT":
                effective_dir = "LONG"
            else:
                effective_dir = "FLAT"
        else:
            # Bierzemy face-value, min weight 0.05R żeby flat-y się zliczały
            effective_edge = max(edge_r, 0.05)
            effective_dir = sig.direction

        # Confidence z sygnału (0.0-1.0) skaluje wagę
        confidence = max(sig.confidence, 0.1)  # min 0.1 żeby nie zerować
        contribution = effective_edge * confidence

        signed = (
            contribution if effective_dir == "LONG"
            else -contribution if effective_dir == "SHORT"
            else 0.0
        )
        contributing[sig.source] = signed

        if effective_dir == "LONG":
            weighted_long += contribution
        elif effective_dir == "SHORT":
            weighted_short += contribution

    # 4. Decyzja
    delta = weighted_long - weighted_short
    if delta > decision_threshold:
        direction = "LONG"
        weighted_score = delta
    elif delta < -decision_threshold:
        direction = "SHORT"
        weighted_score = abs(delta)
    else:
        direction = "FLAT"
        weighted_score = abs(delta)

    return WeightedDecision(
        direction=direction,
        weighted_score=weighted_score,
        weighted_long=weighted_long,
        weighted_short=weighted_short,
        contributing=contributing,
        fade_count=fade_count,
        raw_count=len(recent),
        n_sources_with_edge=len(seen),
        flat_skipped=flat_skipped,
    )


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

    # Composite (sanity check)
    composite = fs.read_composite()

    # Weighted decision
    decision = compute_weighted_decision(
        fs,
        since_minutes=args.since,
        lookback_days=args.lookback,
        min_samples=args.min_samples,
        fade_threshold=args.fade,
    )

    # Liquidity event
    liq = fs.has_recent_liquidity_event(since_minutes=30)

    # Freshness
    fresh = fs.check_freshness()

    # Render
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

    # Final verdict
    print()
    print("=" * 72)
    print(f"VERDICT: {render_verdict(decision)}")

    # Composite alignment check
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
