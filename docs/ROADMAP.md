# Roadmap

Checkboxes are updated as work completes. See ARCHITECTURE.md §D for context.

## Phase 0 — Foundation ✅
- [x] Architecture proposal (docs/ARCHITECTURE.md)
- [x] Research protocol (docs/RESEARCH_PROTOCOL.md)
- [x] Repository skeleton, pyproject, registry schema
- [x] Handoff notes (CLAUDE.md) and decision log

## Phase 1 — Data layer ✅ (forex download pending)
- [x] Unified schemas: bars, quote bars, ticks, funding (Parquet, UTC bar-start timestamps)
- [x] Instrument registry (`configs/instruments.yaml`)
- [x] Ingestor: Binance public archive (BTC/ETH/SOL 1m bars 2019+, funding 2020+) — downloaded
- [ ] Binance trade-level data (aggTrades) for scalping — Phase 7
- [x] Ingestor: Dukascopy (1m bid/ask candles + tick mode), tested offline
- [ ] **Download Dukascopy EURUSD/GBPUSD/USDJPY** — blocked: Dukascopy returns HTTP 429 to this cloud network (see DECISIONS D-007)
- [x] Ingestor: Yahoo daily ETFs (14 symbols) — downloaded
- [x] Macro: VIX, VIX3M, 10y & 13w yields, dollar index via Yahoo (FRED unreachable here)
- [x] Data-quality checks + `reports/data_quality.md`
- [x] Fixed data splits per market with locked vault (`configs/splits.yaml`)

## Phase 2 — Engine & costs ✅
- [x] Compiled bar-by-bar portfolio engine: long/short, stops, targets, trailing stops, time exits,
      multiple positions, priority, sizing (risk / % equity / fixed), cash & exposure limits,
      daily-loss and max-drawdown limits (docs/ENGINE.md)
- [x] Next-bar execution enforced; pessimistic intrabar rules; gaps and missing bars handled
- [x] Cost profiles per market: fees, spread, slippage, funding, borrow, dividends, liquidity caps
- [x] Metrics suite incl. benchmark, monthly and regime breakdowns
- [x] Look-ahead detectors (signal causality + engine causality), run automatically on experiments
- [x] Research registry integration: every run recorded incl. failures; vault lock; JSONL export
- [x] 84 tests: known-answer accounting, look-ahead, calibration, registry
- [x] Sample backtests on BTC, ETH, SPY + cost stress + account sizes + random calibration
      (reports/phase2_engine_validation.md)
- [ ] Cash interest, FX conversion, futures roll — when needed

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
