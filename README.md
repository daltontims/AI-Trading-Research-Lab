# AI Trading Research Lab

An autonomous research laboratory that generates, tests, and rigorously filters
trading hypotheses across stocks, ETFs, futures, forex, crypto and options.

**Simulation only.** No live trading, brokerage connections, fund transfers or
data purchases happen without the owner's explicit permission.

## Status

**Phase 1 — Data layer: complete** (forex download pending). Crypto 1-minute data (2019+), crypto funding rates, 14 ETFs and 5 macro series downloaded and quality-checked. Next: Phase 2 (backtesting engine and cost models).

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture, tools, data sources, costs, risks, first actions |
| [docs/RESEARCH_PROTOCOL.md](docs/RESEARCH_PROTOCOL.md) | Statistical rules every strategy must pass |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Development phases and progress |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decision log |
| [docs/DATA.md](docs/DATA.md) | Data sources, lake layout, caveats |
| [reports/data_quality.md](reports/data_quality.md) | Latest automated data-quality report |
| [CLAUDE.md](CLAUDE.md) | Handoff notes for resuming work |

## Leaderboard

No strategies tested yet. Validated strategies and promising candidates will be
listed separately in `reports/` once research begins.
