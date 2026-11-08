# Roadmap

Checkboxes are updated as work completes. See ARCHITECTURE.md §D for context.

## Phase 0 — Foundation ✅
- [x] Architecture proposal (docs/ARCHITECTURE.md)
- [x] Research protocol (docs/RESEARCH_PROTOCOL.md)
- [x] Repository skeleton, pyproject, registry schema
- [x] Handoff notes (CLAUDE.md) and decision log

## Phase 1 — Data layer
- [ ] Unified schemas: bars, trades, quotes (Parquet, UTC timestamps)
- [ ] Instrument registry (`configs/instruments.yaml`)
- [ ] Ingestor: Binance public archive (BTCUSDT, ETHUSDT 1m bars, trades, funding)
- [ ] Ingestor: Dukascopy ticks (EURUSD, USDJPY, GBPUSD)
- [ ] Ingestor: daily ETFs (SPY, QQQ, IWM, sector ETFs, TLT, GLD)
- [ ] Ingestor: FRED macro series, VIX
- [ ] Data-quality checks (gaps, outliers, duplicates, stale prices) + report
- [ ] Fixed data splits per market (`configs/splits.yaml`)

## Phase 2 — Engine & costs
- [ ] Vectorized backtester (next-bar execution enforced)
- [ ] Cost models per asset class
- [ ] Metrics suite (protocol §3)
- [ ] Known-answer tests and look-ahead detection tests

## Phase 3 — Validation toolkit
- [ ] Walk-forward and purged/embargoed CV
- [ ] Deflated Sharpe, PBO (CSCV), SPA/Reality Check, BH-FDR
- [ ] Bootstrap / Monte Carlo
- [ ] Robustness suite (param stability, 2× costs, regimes, cross-market)
- [ ] Calibration run on random strategies

## Phase 4 — Registry & first research
- [ ] SQLite registry + CLI + git export of hypothesis cards
- [ ] ~20 hand-designed hypotheses across crypto, FX, ETFs

## Phase 5 — Discovery engine
- [ ] Feature library + hypothesis templates/grammar
- [ ] Automated event-study screening
- [ ] Scheduled research runs, global trial accounting
- [ ] Optional LLM hypothesis proposer (needs budget approval)

## Phase 6 — Dashboard & reports
- [ ] Streamlit dashboard: leaderboard, candidates vs validated, graveyard
- [ ] Auto-generated Markdown reports in `reports/`

## Phase 7 — High-fidelity simulation
- [ ] NautilusTrader integration; tick-level scalping tests with latency

## Phase 8 — Paper trading (requires permission)
## Phase 9 — Expansion (options, paid data where justified, portfolios)
