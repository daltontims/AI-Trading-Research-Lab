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
