"""Run a discovery batch (Phase 5). See docs/DISCOVERY.md.

    uv run python scripts/discovery.py D5-01 --register   # pre-register only; commit before running
    uv run python scripts/discovery.py D5-01              # run (resumable)
    uv run python scripts/discovery.py D5-01 --workers 4
"""

from __future__ import annotations

import argparse

from lab.discovery import batch
from lab.registry.db import Registry

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--register", action="store_true", help="pre-register only")
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()
    if a.register:
        hs = batch.register(a.batch, Registry())
        print(f"registered {len(hs)} hypotheses for {a.batch}")
    else:
        batch.run(a.batch, workers=a.workers)
