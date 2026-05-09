"""Weighted decision module v0.5 — full confluence per 15 trading books.

Layers (każdy modyfikuje weighted_long / weighted_short):

  1. Edge-weighted source votes        Tharp, Chan — measured edge
  2. Composite as 12th voter           Schwager confluence, Murphy intermarket
  3. Liquidity bias                    Williams orderflow, Wyckoff absorption
  4. GEX walls modifier                Lefèvre tape, Williams (gamma flip damping)
  5. MTF coherence                     Elder (alignment / opposition adjusts conviction)
  6. WFA stability filter              Pardo (recent edge must hold)
  7. Adaptive threshold                Kaufman (HIGH conviction lower bar)

Sources z silnie negatywnym E (< fade_threshold) są nadal fade'owane —
ich kierunek jest ODWRÓCONY przed wagowaniem.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from master.core import wfa
from master.data.feature_store import FeatureStore


# Domyślne progi (skalibrowane po 74,556 sygnałach EA)
DEFAULT_SINCE_MINUTES = 15
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MIN_SAMPLES = 50
DEFAULT_FADE_THRESHOLD = -0.2
DEFAULT_DECISION_THRESHOLD = 0.3

# Wagi confluence (co dodaje każda warstwa)
COMPOSITE_CONVICTION_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}
LIQUIDITY_WEIGHTS = {
    "ABSORPTION_BID": 0.15,    # bullish — bulls eating supply at bid
    "ABSORPTION_ASK": -0.15,   # bearish — bears eating demand at ask
    "ICEBERG_BID": 0.10,       # hidden buying
    "ICEBERG_ASK": -0.10,      # hidden selling
    "BIG_ORDER_BID": 0.08,
    "BIG_ORDER_ASK": -0.08,
}
GEX_WALL_DAMPING = 0.7         # przy ścianie tnij conviction o 30%
GEX_WALL_PIPS_THRESHOLD = 5.0  # 5 pips = blisko

MTF_ALIGNED_BOOST = 1.15       # +15% gdy MTF alignuje
MTF_OPPOSING_PENALTY = 0.85    # -15% gdy MTF się sprzeciwia

# WFA — recent edge musi być w granicach 50% historical
WFA_DELTA_THRESHOLD = 0.5
WFA_RECENT_DAYS = 7

# Adaptive threshold (Kaufman)
CONVICTION_THRESHOLD_ADJ = {
    "HIGH":   -0.1,    # 0.3 → 0.2 (łatwiej wejść)
    "MEDIUM":  0.0,    # 0.3
    "LOW":    +0.1,    # 0.3 → 0.4 (trudniej)
}


@dataclass
class WeightedDecision:
    """Wynik ważonej decyzji ze wszystkimi layerami confluence."""

    direction: str                              # LONG / SHORT / FLAT
    weighted_score: float                       # net edge w R-multiples
    weighted_long: float
    weighted_short: float
    contributing: dict[str, float] = field(default_factory=dict)
    fade_count: int = 0
    raw_count: int = 0
    n_sources_with_edge: int = 0
    flat_skipped: int = 0

    # v0.5 — confluence layers
    composite_contribution: float = 0.0
    liquidity_modifier: float = 0.0
    gex_warning: str = ""
    mtf_alignment: str = "UNKNOWN"        # ALIGNED / OPPOSING / NEUTRAL / UNKNOWN
    decision_threshold_used: float = DEFAULT_DECISION_THRESHOLD
    sources_unstable: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def compute_weighted_decision(
    fs: FeatureStore,
    since_minutes: int = DEFAULT_SINCE_MINUTES,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    fade_threshold: float = DEFAULT_FADE_THRESHOLD,
    decision_threshold: float = DEFAULT_DECISION_THRESHOLD,
) -> WeightedDecision:
    """Pełna ważona decyzja z 7 layerami confluence."""

    notes: list[str] = []

    # ─── Layer 1: Edge-weighted source votes (Tharp, Chan) ───
    recent = fs.read_recent_signals(since_minutes=since_minutes, limit=5000)
    sources = fs.get_top_sources(lookback_days=lookback_days, min_samples=min_samples)
    edge_per_source = {s.source: s for s in sources}

    weighted_long = 0.0
    weighted_short = 0.0
    contributing: dict[str, float] = {}
    seen: set[str] = set()
    fade_count = 0
    flat_skipped = 0

    for sig in recent:
        if sig.source in seen:
            continue
        if sig.direction == "FLAT" or sig.confidence <= 0.0:
            flat_skipped += 1
            continue
        seen.add(sig.source)
        if sig.source not in edge_per_source:
            continue

        edge_r = edge_per_source[sig.source].expectancy_r

        if edge_r < fade_threshold:
            fade_count += 1
            effective_edge = abs(edge_r)
            if sig.direction == "LONG":
                effective_dir = "SHORT"
            elif sig.direction == "SHORT":
                effective_dir = "LONG"
            else:
                effective_dir = "FLAT"
        else:
            effective_edge = max(edge_r, 0.05)
            effective_dir = sig.direction

        confidence = max(sig.confidence, 0.1)
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

    # ─── Layer 6: WFA stability filter (Pardo) — ZANIM użyjemy edge'u ───
    # Sprawdź czy aktywne source mają stabilny edge w 7-day vs 30-day window.
    # Jeśli np. XGB +0.491R w 30d ale tylko +0.05R w 7d → fade go (recent decay).
    sources_unstable: list[str] = []
    for src_name in list(contributing.keys()):
        if src_name == "composite_meta":
            continue
        try:
            stab = wfa.check_recent_edge_stability(
                fs, src_name,
                full_days=lookback_days,
                recent_days=WFA_RECENT_DAYS,
                delta_threshold=WFA_DELTA_THRESHOLD,
            )
            if not stab.stable and stab.recent_window_n >= 20:
                sources_unstable.append(src_name)
                # Wycofaj wkład — usuń z weighted
                old = contributing[src_name]
                if old > 0:
                    weighted_long -= old
                elif old < 0:
                    weighted_short -= abs(old)
                contributing[src_name] = 0.0
                notes.append(
                    f"WFA: {src_name} unstable "
                    f"(full {stab.full_window_r:+.2f}R → recent {stab.recent_window_r:+.2f}R) — withdrawn"
                )
        except Exception:
            pass  # WFA failure nie powinno blokować decyzji

    # ─── Layer 2: Composite as 12th voter (Schwager confluence) ───
    composite = fs.read_composite()
    composite_contribution = 0.0
    if composite:
        conv_w = COMPOSITE_CONVICTION_WEIGHT.get(composite.conviction, 0.3)
        if composite.direction == "BULL":
            composite_contribution = abs(composite.score) * conv_w
            weighted_long += composite_contribution
            contributing["composite_meta"] = composite_contribution
        elif composite.direction == "BEAR":
            composite_contribution = -abs(composite.score) * conv_w
            weighted_short += abs(composite_contribution)
            contributing["composite_meta"] = composite_contribution
        # NEUT — zero kontrybucji

    # ─── Layer 3: Liquidity bias (Williams orderflow) ───
    liquidity_modifier = 0.0
    ice_events = fs.read_ice_events(since_minutes=30)
    if ice_events:
        for ev in ice_events:
            key = f"{ev.event_type}_{ev.side}" if ev.event_type in ("ICEBERG", "BIG_ORDER") \
                  else ev.event_type
            base = LIQUIDITY_WEIGHTS.get(key, 0.0)
            mod = base * ev.confidence
            liquidity_modifier += mod
        # Dystrybuuj jako virtual contribution
        if liquidity_modifier > 0:
            weighted_long += liquidity_modifier
            contributing["liquidity_meta"] = liquidity_modifier
            notes.append(f"liquidity bullish ({len(ice_events)} events, +{liquidity_modifier:.2f}R)")
        elif liquidity_modifier < 0:
            weighted_short += abs(liquidity_modifier)
            contributing["liquidity_meta"] = liquidity_modifier
            notes.append(f"liquidity bearish ({len(ice_events)} events, {liquidity_modifier:.2f}R)")

    # ─── Layer 4: GEX walls modifier (Lefèvre, Williams gamma flip) ───
    gex_warning = ""
    options = fs.read_options_state()
    current_spot = recent[0].spot if recent else None
    if options and options.flip_level and current_spot:
        # Distance to gamma flip w pips (FX: 1 pip = 0.0001)
        dist_pips = abs(current_spot - options.flip_level) / 0.0001
        if dist_pips < GEX_WALL_PIPS_THRESHOLD:
            gex_warning = (
                f"spot {current_spot:.4f} blisko flip {options.flip_level:.4f} "
                f"({dist_pips:.1f} pips) — damping"
            )
            # Tnij conviction — przy gamma flip ruch częściej zawraca
            weighted_long *= GEX_WALL_DAMPING
            weighted_short *= GEX_WALL_DAMPING
            notes.append(gex_warning)

    # ─── Layer 5: MTF coherence (Elder) ───
    # Sprawdź MTF_30m, MTF_60m: ich GŁOSY (już po fade) muszą się zgadzać z preliminary direction
    preliminary_delta = weighted_long - weighted_short
    if preliminary_delta > 0.05:
        prelim_dir = "LONG"
    elif preliminary_delta < -0.05:
        prelim_dir = "SHORT"
    else:
        prelim_dir = "FLAT"

    mtf_alignment = "UNKNOWN"
    mtf_votes: list[float] = []
    for src_name in ("MTF_30m", "MTF_60m", "MTF_15m", "MTF_240m", "MTF_5m"):
        if src_name in contributing:
            v = contributing[src_name]
            if v != 0.0:
                mtf_votes.append(v)

    if mtf_votes and prelim_dir != "FLAT":
        mtf_avg = sum(mtf_votes) / len(mtf_votes)
        if (prelim_dir == "LONG" and mtf_avg > 0.05) or \
           (prelim_dir == "SHORT" and mtf_avg < -0.05):
            mtf_alignment = "ALIGNED"
            if prelim_dir == "LONG":
                weighted_long *= MTF_ALIGNED_BOOST
            else:
                weighted_short *= MTF_ALIGNED_BOOST
            notes.append(f"MTF aligned ({len(mtf_votes)} TFs avg {mtf_avg:+.2f}R) — boost")
        elif (prelim_dir == "LONG" and mtf_avg < -0.05) or \
             (prelim_dir == "SHORT" and mtf_avg > 0.05):
            mtf_alignment = "OPPOSING"
            weighted_long *= MTF_OPPOSING_PENALTY
            weighted_short *= MTF_OPPOSING_PENALTY
            notes.append(f"MTF opposing ({len(mtf_votes)} TFs avg {mtf_avg:+.2f}R) — penalty")
        else:
            mtf_alignment = "NEUTRAL"

    # ─── Layer 7: Adaptive threshold (Kaufman) ───
    threshold = decision_threshold
    if composite:
        adj = CONVICTION_THRESHOLD_ADJ.get(composite.conviction, 0.0)
        threshold = max(0.1, decision_threshold + adj)
        if adj != 0.0:
            notes.append(
                f"adaptive threshold: composite {composite.conviction} → {threshold:.2f}R"
            )

    # ─── Final decision ───
    delta = weighted_long - weighted_short
    if delta > threshold:
        direction = "LONG"
        weighted_score = delta
    elif delta < -threshold:
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
        composite_contribution=composite_contribution,
        liquidity_modifier=liquidity_modifier,
        gex_warning=gex_warning,
        mtf_alignment=mtf_alignment,
        decision_threshold_used=threshold,
        sources_unstable=sources_unstable,
        notes=notes,
    )
