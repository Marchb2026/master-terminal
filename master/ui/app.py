"""Master Terminal — minimalny ekran w Dash.

Jeden widok, cztery stany (STAND_DOWN/WATCH/READY/ENGAGED/EXIT).
Bez tabów. Refresh raz na cfg.ui_refresh_seconds (domyślnie 60s).

Reguła: jeśli coś nie wpływa na werdykt — nie pokazuj.
"""
from __future__ import annotations

import logging

from master.config import MasterConfig
from master.core.pipeline import run_pipeline
from master.core.verdict import VerdictState

log = logging.getLogger(__name__)


def _state_color(state: VerdictState) -> str:
    return {
        VerdictState.STAND_DOWN: "#666666",
        VerdictState.WATCH: "#d4a64a",
        VerdictState.READY: "#3a8a3a",
        VerdictState.ENGAGED: "#2a6cb0",
        VerdictState.EXIT: "#b03a3a",
    }.get(state, "#888")


def run(cfg: MasterConfig) -> int:
    """Uruchamia minimalne UI w Dash."""
    try:
        from dash import Dash, dcc, html
    except ImportError:
        log.error("Dash not installed. pip install dash plotly")
        return 1

    app = Dash(__name__, title="Master Terminal")

    app.layout = html.Div(
        style={
            "fontFamily": "monospace",
            "backgroundColor": "#0d1117",
            "color": "#e0e0e0",
            "minHeight": "100vh",
            "padding": "40px",
        },
        children=[
            html.H1("MASTER TERMINAL", style={"letterSpacing": "0.2em"}),
            html.Div(id="verdict-block"),
            dcc.Interval(
                id="refresh",
                interval=cfg.ui_refresh_seconds * 1000,
                n_intervals=0,
            ),
        ],
    )

    @app.callback(
        [
            ("verdict-block", "children"),
        ],
        [("refresh", "n_intervals")],
    )
    def update_verdict(_n):
        v = run_pipeline(cfg)
        body_lines = []
        body_lines.append(html.Pre(v.render_text(), style={"fontSize": "16px"}))
        return [body_lines]

    log.info("Starting Master UI on port %d", cfg.ui_port)
    app.run(host="127.0.0.1", port=cfg.ui_port, debug=False)
    return 0
