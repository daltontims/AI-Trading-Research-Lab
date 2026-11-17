# AI Trading Research Lab

An autonomous research laboratory that generates, tests, and rigorously filters
trading hypotheses across stocks, ETFs, futures, forex, crypto and options.

**Simulation only.** No live trading, brokerage connections, fund transfers or
data purchases happen without the owner's explicit permission.

## Status

**Phase 3 — Statistical validation: complete.** Promotion pipeline (Deflated Sharpe, PBO, SPA, walk-forward, robustness) calibrated: 0 false discoveries on 160 null datasets. Next: Phase 4 (first research batch). Forex data download still pending.

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture, tools, data sources, costs, risks, first actions |
| [docs/RESEARCH_PROTOCOL.md](docs/RESEARCH_PROTOCOL.md) | Statistical rules every strategy must pass |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Development phases and progress |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decision log |
| [docs/DATA.md](docs/DATA.md) | Data sources, lake layout, caveats |
| [docs/ENGINE.md](docs/ENGINE.md) | Backtesting engine: execution rules, costs, risk, limitations |
| [reports/phase2_engine_validation.md](reports/phase2_engine_validation.md) | Engine validation on BTC, ETH, SPY |
| [docs/VALIDATION.md](docs/VALIDATION.md) | How results are judged: tests, gates, confidence |
| [reports/phase3_calibration.md](reports/phase3_calibration.md) | Proof the pipeline rejects luck |
| [reports/data_quality.md](reports/data_quality.md) | Latest automated data-quality report |
| [CLAUDE.md](CLAUDE.md) | Handoff notes for resuming work |

## Leaderboard

No research strategies tested yet (only engine diagnostics). Validated strategies and promising candidates will be
listed separately in `reports/` once research begins.
