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
