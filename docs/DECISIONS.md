# Decision Log

Short records of important decisions: what, why, and alternatives considered.

## D-001 — Python as the only language (2026-11-08)
Best research ecosystem; readable; performance via Polars/NumPy/Numba/DuckDB and
NautilusTrader's Rust core. Rejected: C#/LEAN (heavier, cloud lock-in), C++ (slow
to develop).

## D-002 — Two-tier backtesting (2026-11-08)
Own vectorized engine for fast screening (thousands of runs, fully controlled
assumptions); NautilusTrader for high-fidelity event-driven tests and paper
trading. Rejected: Backtrader (unmaintained), Zipline (equity-only), relying on
vectorbt free edition (slower update cadence).

## D-003 — Parquet + DuckDB data lake; SQLite registry (2026-11-08)
No database server, no cost, fast. Market data is not committed to git; it must
be re-downloadable by scripts. The registry is exported to text files in
`research/` so it survives ephemeral environments.

## D-004 — Free data first; options deferred (2026-11-08)
Crypto (Binance archive) and FX (Dukascopy) offer free tick-level data with
bid/ask information, making them the first scalping laboratories. Options data
is costly; deferred pending a budget decision.

## D-005 — Strict promotion protocol (2026-11-08)
See RESEARCH_PROTOCOL.md. Pre-registration, trial counting, holdout vault,
deflated Sharpe, PBO, calibration against random strategies.

## D-006 — Dedicated cloud environment with data-host allowlist (2026-11-08)
Created the personal environment `ai-trading-research-lab` allowing data.binance.vision,
datafeed.dukascopy.com, Yahoo Finance, stooq.com and fred.stlouisfed.org (the default
environment blocked all market-data hosts). Stooq (browser challenge) and FRED (refuses
this network) still do not work, so macro series come from Yahoo (^VIX, ^VIX3M, ^TNX, ^IRX, DX-Y.NYB).

## D-007 — Forex via Dukascopy daily candles; download currently blocked (2026-11-08)
Hourly tick files need ~600 requests per pair-month and each takes ~10 s through this
network, so the default mode uses daily 1-minute bid/ask candle files (24× fewer requests).
Tick mode stays available for short scalping windows. After an initial burst of parallel
requests, Dukascopy answers HTTP 429 ("Too Many Requests") to this cloud network and had not
lifted it after 40+ minutes. The ingestor is now throttled to 1 request/s, one at a time.
Options if the block persists: run `uv run lab ingest dukascopy EURUSD GBPUSD USDJPY` from a
home computer and upload, or use another free FX source. Forex research waits until then;
crypto and ETF research go first.

## D-008 — Data date conventions (2026-11-08)
Bars are stamped at their start, in UTC. Yahoo daily bars map to the trading date; ICE-style
evening session-start stamps (dollar index) are moved to the next day. Yield series are
flagged `price_kind: yield` and checked with absolute changes (zero rates are valid).

## D-009 — Engine design: compiled bar loop instead of an external framework (2026-11-08)
Strategies produce vectorised signal arrays; a Numba-compiled loop handles fills, costs and
portfolio accounting. This gives ~1 s per 2.6M-bar backtest (needed for thousands of variations)
and full control over execution assumptions. NautilusTrader remains planned for tick-level
validation and paper trading (Phase 7–8). Pessimistic conventions: next-bar-open fills, stop wins
when stop and target share a bar, targets never fill better than their price, trailing stops use
completed bars only.

## D-010 — Crypto cost baseline is a global exchange's lowest tier (2026-11-08)
Default `crypto_spot` = 10 bps taker, `crypto_perp` = 5 bps taker + real funding. US-accessible
exchanges' lowest tiers cost far more (≈40 bps taker; profile `crypto_spot_us_retail`), and US
residents generally cannot use offshore perpetual futures. Any crypto candidate must therefore also
be evaluated under `crypto_spot_us_retail` and ×2–×3 cost stress before it is taken seriously.
**Owner input needed later:** which venues/jurisdiction apply, so the default can be set accordingly.

## D-011 — No leverage by default; futures require explicit opt-in (2026-11-08)
Gross exposure ≤ 1× equity and longs paid in cash. A micro E-mini contract (~$25k notional) is
therefore untradeable with $5k unless `max_gross_exposure` is raised, which is recorded in the
experiment config.

## D-012 — Registry reset before the official Phase 2 run (2026-11-08)
A first draft of the Phase 2 validation run (engine demos only, no research hypotheses) was
discarded and re-run after changing the SPY demo to the classic no-stop version and adding the
zero-cost calibration. From this point the registry is append-only: no records are deleted.

## D-013 — Dukascopy candle format verified; download still blocked (2026-11-08)
Three real daily candle files decoded correctly (EURUSD ≈1.104 on 2024-01-02). Dukascopy briefly
allowed requests again but returned HTTP 429 after three files. Forex stays pending (see D-007).
