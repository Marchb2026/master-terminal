"""Master Terminal — entrypoint.

Uruchomienie:
    python -m master.main           # CLI verdict (stdout)
    python -m master.main --ui      # UI na porcie z config.UI_PORT
"""
from __future__ import annotations

import argparse
import logging
import sys

from master.config import CONFIG, ensure_dirs


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def run_once() -> int:
    """Wywołuje pełen pipeline raz i drukuje werdykt na stdout."""
    log = logging.getLogger("master.main")
    log.info("Master Terminal · instrument=%s", CONFIG.instrument)

    # Importy lokalne — żeby `python -m master.main --help` było szybkie
    from master.core.pipeline import run_pipeline

    verdict = run_pipeline(CONFIG)
    print(verdict.render_text())
    return 0


def run_ui() -> int:
    """Uruchamia jednostronicowe UI."""
    log = logging.getLogger("master.main")
    log.info("Master Terminal UI · port=%d", CONFIG.ui_port)
    from master.ui.app import run as ui_run
    return ui_run(CONFIG)


def main() -> int:
    parser = argparse.ArgumentParser(prog="master", description="Master Terminal")
    parser.add_argument("--ui", action="store_true", help="uruchom UI zamiast CLI")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    ensure_dirs()

    return run_ui() if args.ui else run_once()


if __name__ == "__main__":
    sys.exit(main())
