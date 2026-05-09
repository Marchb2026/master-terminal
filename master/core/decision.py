"""Weighted decision logic — kalibrowane wagowanie sygnałów.

Każdy source głosuje proporcjonalnie do swojego historical edge (expectancy_r).
Sources z silnie negatywnym E (poniżej fade_threshold) mają KIERUNEK ODWRÓCONY —
gdy mówią LONG, statystycznie powinno iść SHORT, więc liczymy ich głos jako SHORT.

To zastępuje klasyczną confluence ("policz głosy") edge-aware confluence
("zważ głosy po jakości źródła").
"""
from __future__ import annotations

from dataclasses import dataclass, field

from master.data.feature_store import FeatureStore


# Domyślne progi (skalibrowane po runie na 74,556 sygnałach EA)
DEFAULT_SINCE_MINUTES = 15
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_MIN_SAMPLES = 50
DEFAULT_FADE_THRESHOLD = -0.2     # source z E < -0.2R = fade
DEFAULT_DECISION_THRESHOLD = 0.3   # min |delta| żeby wybrać kierunek


@dataclass
class WeightedDecision:
    """Wynik decyzji ważonej."""

    direction: str                              # LONG / SHORT / FLAT
    weighted_score: float                       # net edge w R-multiples
    weighted_long: float
    weighted_short: float
    contributing: dict[str, float] = field(default_factory=dict)
    fade_count: int = 0
    raw_count: int = 0
    n_sources_with_edge: int = 0
    flat_skipped: int = 0


def compute_weighted_decision(
    fs: FeatureStore,
    since_minutes: int = DEFAULT_SINCE_MINUTES,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    fade_threshold: float = DEFAULT_FADE_THRESHOLD,
    decision_threshold: float = DEFAULT_DECISION_THRESHOLD,
) -> WeightedDecision:
    """Liczy weighted decision dla aktualnego stanu rynku.

    Algorytm:
      1. Pobierz aktualne sygnały (ostatnie since_minutes), pomiń FLAT/zero-conf
      2. Pobierz historical edge per source (rolling lookback_days)
      3. Dla każdego unikalnego source weź NAJNOWSZY realny sygnał
      4. Jeśli source.edge < fade_threshold → odwróć kierunek sygnału (FADE)
      5. Contribution = abs(edge) × confidence, dodaj do weighted_long/short
      6. delta = weighted_long - weighted_short, jeśli |delta| > threshold → kierunek
    """
    # 1. Recent signals — wysoki limit na wypadek dużej liczby placeholderów
    recent = fs.read_recent_signals(since_minutes=since_minutes, limit=5000)

    # 2. Edge per source
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
        if sig.source in seen:
            continue

        # SKIP "no signal" placeholders
        if sig.direction == "FLAT" or sig.confidence <= 0.0:
            flat_skipped += 1
            continue

        seen.add(sig.source)

        if sig.source not in edge_per_source:
            continue

        edge_r = edge_per_source[sig.source].expectancy_r

        # FADE logic
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
