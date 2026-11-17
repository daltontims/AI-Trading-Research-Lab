# AI Trading Research Lab

An autonomous research laboratory that generates, tests, and rigorously filters
trading hypotheses across stocks, ETFs, futures, forex, crypto and options.

**Simulation only.** No live trading, brokerage connections, fund transfers or
data purchases happen without the owner's explicit permission.

## Status

**Phase 4 — First research batch: complete.** 21 pre-registered hypotheses → 1 validated strategy (H4-17, SPY RSI pullback), 20 rejected. See [reports/phase4_summary.md](reports/phase4_summary.md) and [reports/phase4_vault.md](reports/phase4_vault.md). Next: Phase 5 (automated discovery) and the dashboard. Forex data download still pending.

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

**Validated** (passed development, validation and the one-time final vault test; NOT yet paper-traded):

| ID | Strategy | Market | Timeframe | Vault period | Vault net return | Vault Sharpe (buy & hold) | Vault max DD (buy & hold) | Confidence |
|---|---|---|---|---|---|---|---|---|
| [H4-17](reports/strategies/H4-17.md) | Buy 2-day RSI < 10 dips above the 200-day average; sell when RSI > 70 | SPY | Daily | 2022-07 → 2026-11 | +35.6% | 1.19 (1.09) | −8.2% (−18.2%) | Moderate |

**Candidates:** none open.

**Rejected at the final test:** H4-02 BTC 50-day trend filter (vault −1.0%; buy & hold −26.8%) — see
[reports/phase4_vault.md](reports/phase4_vault.md). All rejected ideas: [research/graveyard/README.md](research/graveyard/README.md).

"Validated" means the result survived every statistical test on data it was never fitted to. It is still
historical evidence, not a guarantee; the next step would be paper trading (needs your permission).
