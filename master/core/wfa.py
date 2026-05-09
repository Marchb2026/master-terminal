"""Walk-Forward Analysis — Pardo's robustness check.

Pytanie: czy historical edge per source utrzymuje się w niedawnej przeszłości?
Jeśli XGB miał +0.491R w 30d window ale tylko +0.05R w ostatnim 7d,
jego edge wycieka i nie powinniśmy mu już ufać.

Pardo (Evaluation and Optimization of Trading Strategies):
- Backtest na 3+ niezależnych windowach
- Out-of-sample validation
- Edge musi być stabilny — pojedyncze runy nie liczą się

Master używa uproszczonej wersji: rolling-window stability.
Recent edge musi być w granicach delta_threshold od full-window edge.
"""
from __future__ import annotations

from dataclasses import dataclass

from master.data.feature_store import FeatureStore


@dataclass
class EdgeStability:
    """Wynik check_recent_edge_stability dla pojedynczego source."""

    source: str
    full_window_r: float          # E w pełnym window (np. 30d)
    full_window_n: int
    recent_window_r: float        # E w recent window (np. 7d)
    recent_window_n: int
    delta: float                  # recent_window_r - full_window_r
    relative_drop: float          # |delta| / max(|full|, 0.1)
    stable: bool                  # czy w granicach tolerancji
    reason: str = ""


def check_recent_edge_stability(
    fs: FeatureStore,
    source: str,
    full_days: int = 30,
    recent_days: int = 7,
    delta_threshold: float = 0.5,    # 50% drop = unstable
    min_recent_n: int = 20,
) -> EdgeStability:
    """Sprawdza stabilność edge'u dla source w rolling window.

    Args:
        fs: FeatureStore (do queries)
        source: nazwa source (XGB, vote_SCORE, etc.)
        full_days: window do reference edge
        recent_days: niedawny window do porównania
        delta_threshold: max relative drop (0.5 = 50%)
        min_recent_n: min sample size w recent — poniżej zwraca stable=True

    Returns:
        EdgeStability — stable=True jeśli recent edge zgodny z full,
        False jeśli wyciek edge'u przekracza delta_threshold.
    """
    full = fs.get_source_expectancy(source, lookback_days=full_days)
    recent = fs.get_source_expectancy(source, lookback_days=recent_days)

    # Brak danych: stable=True (nie blokuj decyzji)
    if not full or not recent:
        return EdgeStability(
            source=source,
            full_window_r=full.expectancy_r if full else 0.0,
            full_window_n=full.n_resolved if full else 0,
            recent_window_r=recent.expectancy_r if recent else 0.0,
            recent_window_n=recent.n_resolved if recent else 0,
            delta=0.0,
            relative_drop=0.0,
            stable=True,
            reason="insufficient data",
        )

    # Recent ma za mało próbek: nie blokuj
    if recent.n_resolved < min_recent_n:
        return EdgeStability(
            source=source,
            full_window_r=full.expectancy_r,
            full_window_n=full.n_resolved,
            recent_window_r=recent.expectancy_r,
            recent_window_n=recent.n_resolved,
            delta=recent.expectancy_r - full.expectancy_r,
            relative_drop=0.0,
            stable=True,
            reason=f"recent n={recent.n_resolved} < min {min_recent_n}",
        )

    delta = recent.expectancy_r - full.expectancy_r
    base = max(abs(full.expectancy_r), 0.1)
    relative_drop = abs(delta) / base

    # Edge SIGNIFICANTLY worse w recent? Unstable.
    # Two ways to be unstable:
    #  (a) recent edge spadł o więcej niż threshold (drop)
    #  (b) recent zmienił znak vs full (sign flip)
    sign_flip = (full.expectancy_r > 0.1 and recent.expectancy_r < -0.1) or \
                (full.expectancy_r < -0.1 and recent.expectancy_r > 0.1)

    if sign_flip:
        stable = False
        reason = f"sign flip ({full.expectancy_r:+.2f}R → {recent.expectancy_r:+.2f}R)"
    elif relative_drop > delta_threshold and abs(delta) > 0.15:
        # Drop >50% AND absolute change >0.15R (żeby 0.05→0.02 nie liczyło)
        stable = False
        reason = f"drop {relative_drop:.0%} (>{delta_threshold:.0%})"
    else:
        stable = True
        reason = f"stable (delta {delta:+.2f}R, drop {relative_drop:.0%})"

    return EdgeStability(
        source=source,
        full_window_r=full.expectancy_r,
        full_window_n=full.n_resolved,
        recent_window_r=recent.expectancy_r,
        recent_window_n=recent.n_resolved,
        delta=delta,
        relative_drop=relative_drop,
        stable=stable,
        reason=reason,
    )


def check_top_sources_stability(
    fs: FeatureStore,
    full_days: int = 30,
    recent_days: int = 7,
    min_samples: int = 50,
) -> dict[str, EdgeStability]:
    """Sprawdza stabilność top source'ów. Używane do diagnostyki / dashboard."""
    sources = fs.get_top_sources(lookback_days=full_days, min_samples=min_samples)
    return {
        s.source: check_recent_edge_stability(
            fs, s.source, full_days=full_days, recent_days=recent_days
        )
        for s in sources
    }
