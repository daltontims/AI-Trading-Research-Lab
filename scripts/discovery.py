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
    ap.add_argument("--mode", choices=["per_instrument", "pooled"], default="per_instrument",
                    help="event-study screen: each instrument alone, or each market group pooled by date")
    ap.add_argument("--plan", default="core_daily", choices=list(batch.PLANS),
                    help="which markets, bar sizes and entry kinds the batch covers")
    ap.add_argument("--parent", default=None, help="earlier batch with the same rules (links each idea to its parent)")
    a = ap.parse_args()
    if a.register:
        hs = batch.register(a.batch, Registry(), plan=a.plan, mode=a.mode, parent=a.parent)
        print(f"registered {len(hs)} hypotheses for {a.batch}")
    else:
        batch.run(a.batch, plan=a.plan, workers=a.workers, mode=a.mode, parent=a.parent)
