# Handoff notes (read first when resuming)

## Project rules (from the owner)
- Simulation only. Never place live trades, connect brokerage accounts, transfer
  funds, buy data, or change account settings without explicit permission.
- Ask only for: major architecture changes, paid services, account creation/access,
  financial commitments, live trading. Make routine research decisions autonomously.
- Owner has limited programming/trading experience: explain decisions plainly.
- Hypothetical account size: $5,000 (also study other sizes).
- Follow docs/RESEARCH_PROTOCOL.md strictly. Log every hypothesis and trial,
  including failures. Keep "candidates" separate from "validated".

## Where things are
- Architecture: docs/ARCHITECTURE.md · Protocol: docs/RESEARCH_PROTOCOL.md · Engine: docs/ENGINE.md · Validation: docs/VALIDATION.md
- Progress: docs/ROADMAP.md · Decisions: docs/DECISIONS.md
- Registry schema: src/lab/registry/schema.sql
- Market data lives in `data/` (gitignored) and must be re-downloadable via ingestors.

## Environment
- Python 3.12+, managed with `uv` (`uv sync`, `uv run pytest`).
- Cloud containers are ephemeral: commit docs, code, and registry exports.

## Data quick start
- Environment `ai-trading-research-lab` (cloud) allows the data hosts; see docs/DATA.md.
- `uv sync --extra dev && uv run lab ingest all && uv run lab quality && uv run pytest`
- Downloads are resumable; ~370 MB for crypto + ETFs.

## Current state
- Phase 0 complete (2026-11-08).
- Phase 1 complete except forex download: Dukascopy returns HTTP 429 to this cloud
  network (DECISIONS D-007). Retry `uv run lab ingest all --only dukascopy` later.
- Phase 2 complete (2026-11-08): engine, costs, metrics, look-ahead detectors, registry
  integration, 84 tests. See docs/ENGINE.md (incl. limitations) and
  reports/phase2_engine_validation.md.
- Phase 3 complete (2026-11-17): validation toolkit + promotion pipeline (docs/VALIDATION.md,
  reports/phase3_calibration.md). Evaluate ideas with `lab.validation.evaluate.evaluate` or
  `lab evaluate`; it records everything and writes reports/strategies/<hypothesis>.md.
- Phase 4 complete (2026-11-17): 21 hypotheses (scripts/phase4_batch.py, research/hypotheses/),
  2 candidates H4-17 (SPY RSI2) and H4-02 (BTC 50d trend), 19 rejected. reports/phase4_summary.md.
- Next: model cash interest (D-020), then vault test for H4-17 and H4-02, then Phase 5 discovery engine.

## Validation conventions (do not break)
- Validation split: one look per hypothesis (enforced). Changed rules = new hypothesis.
- Deflated Sharpe counts ALL trials in the hypothesis family: keep families meaningful.
- Synthetic test data must come from `lab.validation.synthetic.path_bars` (path-consistent bars).

## Engine conventions (do not break)
- Research runs go through `lab.research.run_experiment` (records everything, checks look-ahead).
- Signals at bar t fill at the next bar's open; stop beats target in the same bar; no leverage
  by default; vault only via stage="vault" once per hypothesis.
- Registry: research/registry.sqlite (gitignored) + research/registry/*.jsonl (committed,
  append-only; the DB is rebuilt from it on a fresh machine). Run `Registry().export()` after
  research and commit the JSONL files.
