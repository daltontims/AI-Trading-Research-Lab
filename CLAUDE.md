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
- Architecture: docs/ARCHITECTURE.md · Protocol: docs/RESEARCH_PROTOCOL.md
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
- Next: Phase 2 engine & cost models (start with crypto 1m and ETF daily data).
