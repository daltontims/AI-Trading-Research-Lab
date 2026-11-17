# AI Trading Research Lab

An autonomous research laboratory that generates, tests, and rigorously filters
trading hypotheses across stocks, ETFs, futures, forex, crypto and options.

**Simulation only.** No live trading, brokerage connections, fund transfers or
data purchases happen without the owner's explicit permission.

## Status

**Phase 4 — First research batch: complete.** 21 pre-registered hypotheses tested: 2 candidates, 19 rejected (see [reports/phase4_summary.md](reports/phase4_summary.md)). Next: cash-interest modelling, then the final (vault) test for the candidates. Forex data download still pending.

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

**Validated strategies: none.** Nothing has passed the final (vault) test or paper trading yet.

**Candidates** (passed development and validation gates — promising, not proven):

| ID | Strategy | Market | Timeframe | Validation net return | Validation Sharpe (buy & hold) | Confidence |
|---|---|---|---|---|---|---|
| [H4-17](reports/strategies/H4-17.md) | 2-day RSI pullback in an uptrend | SPY (replicates on 6/6 ETFs) | Daily | +14.5% | 0.51 (0.54) | Low |
| [H4-02](reports/strategies/H4-02.md) | 50-day trend filter, long/flat | BTC | Daily | +61.0% | 1.05 (1.41) | Low |

Rejected ideas and reasons: [research/graveyard/README.md](research/graveyard/README.md).
