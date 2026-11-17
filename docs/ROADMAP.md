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

## Phase 3 — Validation toolkit ✅
- [x] Walk-forward (rolling/anchored, embargo) and purged/embargoed k-fold
- [x] Deflated & Probabilistic Sharpe, PBO (CSCV), White Reality Check, Hansen SPA, BH-FDR,
      Newey–West t-stat, minimum track record
- [x] Stationary bootstrap (Sharpe, drawdown), trade-order Monte Carlo
- [x] Robustness: 2× costs, parameter plateau, yearly consistency, extra delay, cross-market
- [x] Promotion pipeline with gates (configs/protocol.yaml), registry records, strategy cards,
      one validation look per hypothesis (docs/VALIDATION.md)
- [x] Calibration on null and planted-edge data (reports/phase3_calibration.md)
- [x] Found and fixed a stop-fill optimism + flawed synthetic generator (D-015, D-016)

## Phase 4 — Registry & first research ✅
- [x] SQLite registry + CLI + git export of hypothesis cards
- [x] 21 hand-designed hypotheses (crypto, ETFs), pre-registered before testing
- [x] Context (VIX) and portfolio (rotation, pairs, lead-lag) strategy types; calendar features
- [x] Results: 2 candidates (H4-17, H4-02), 19 rejected (reports/phase4_summary.md)
- [x] Model interest on idle cash (T-bill − 0.5%)
- [x] Vault test: H4-17 VALIDATED, H4-02 REJECTED (reports/phase4_vault.md)
- [ ] FX hypotheses (blocked: no FX data)

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
