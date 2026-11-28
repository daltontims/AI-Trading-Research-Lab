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

## D-014 — Phase 3 validation pipeline (2026-11-17)
`lab.validation.evaluate` implements the protocol: development screen (trades, profit, 2× costs),
statistical gates (Deflated Sharpe vs. all trials in the hypothesis family, PBO, Hansen SPA,
walk-forward, parameter plateau, yearly consistency), then a single validation look. Thresholds
are in `configs/protocol.yaml`. Outcomes: REJECTED / SCREENED / CANDIDATE. The vault is not used.

## D-015 — Stop-order overshoot added to the execution model (2026-11-17)
Stops crossed inside a bar now fill beyond the stop by 20% of the bar's excursion past it
(`stop_overshoot_frac`). This is treated as execution realism, not a fee: cost multipliers below 1
(including zero-cost tests) do not remove it; stress multipliers above 1 increase it. Phase 2 results
that involved intrabar stops were slightly optimistic and have been re-run.

## D-016 — Flawed synthetic data generator found and replaced (2026-11-17)
The first Phase 3 calibration showed breakout strategies "profiting" on pure random walks
(46 of 60 false candidates). Cause: synthetic bars had large open-to-close moves but tiny
independent wicks, so stops were crossed only by jumps and filled at the stop level — prices the
path skipped. Diagnosis: with signals only the bias vanished; with path-consistent bars it shrank
with finer paths (t = 3.1 at 30 steps/bar, 0.2 at 200). Fixes: path-based generator
(`lab.validation.synthetic`), stop overshoot (D-015), regression test. The invalid calibration
hypotheses (`H-CAL-*`) remain in the registry for the record; the valid run uses `H-CAL2-*`.
Lesson: every synthetic dataset must be physically consistent, and the engine must be calibrated
on null data for every exit type it supports.

## D-017 — One validation look per hypothesis (2026-11-17)
The pipeline refuses a second validation run for the same hypothesis. A modified idea must be
registered as a new hypothesis (linked via parent_id), and its trials add to the family count.

## D-018 — Stop overshoot is a deliberate, measured cost on real data (2026-11-17)
On real BTC 1-minute data, random entries without the overshoot average zero at zero cost
(t = 0.59: no stop-fill bias on fine-grained real paths); with it they lose ≈20% over five years at
0.5% risk per trade. The overshoot is therefore conservative on liquid real data. Kept at 20%
because short-term crypto stops do slip in fast markets; revisit with tick data (Phase 7).

## D-019 — Trade-order Monte Carlo uses per-trade returns (2026-11-17)
The first version resampled dollar P&L, which is wrong for compounding strategies (a large late
trade replayed early could exceed the account; one card showed a −772% drawdown). It now compounds
per-trade returns on equity. Diagnostic only — no verdict changed; all cards were corrected.

## D-020 — Vault tests postponed until idle cash earns interest (2026-11-17)
Vault results are final. Low-exposure candidates (H4-17 is in the market ~12% of the time) are
materially affected by the 0% interest assumption on cash, so cash interest (T-bill yield) will be
modelled before the vault is opened for H4-17 and H4-02.

## D-021 — Vault test settings, fixed before opening (2026-11-17)
Rules and parameters are frozen from the development search (no changes):
- H4-17: `RsiReversion` entry_rsi=10, exit_rsi=70, trend_n=200 on SPY daily; `equity_us` costs;
  100% of equity per trade; **cash interest on** (13-week T-bill − 0.5%), as US brokers pay interest
  on idle cash. Vault period: 2022-07-01 → latest data.
- H4-02: `TrendFilter` n=50 on BTCUSDT daily; `crypto_spot` costs; 100% of equity; **no cash
  interest** (idle USDT on an exchange earns nothing by default). Vault period: 2025-07-01 → latest data.
Gates (configs/protocol.yaml `vault`): net profit > 0, profit factor > 1, PSR ≥ 0.80, trades ≥ 25% of
the development minimum (≥ 7.5 for swing). 2× cost stress reported, not gated. Outcome is final.
A development re-run of H4-17 with cash interest is recorded as a diagnostic (no new validation look).

## D-022 — Paper trading started; daily run scheduled (2026-11-17)
First paper order submitted 2026-11-17 01:29 New York time: H4-17 buy 6 SPY market-on-open (signal
date 2026-11-16: RSI(2) 9.95 < 10, close 739.95 above its 200-day average 732.16). H4-17 moved
VALIDATED → PAPER automatically on its first submitted order. The daily cycle runs as a weekday
scheduled task at 08:40 New York time in the `ai-trading-research-lab` cloud environment: it checks
out the paper-trading branch, runs `lab paper run --submit`, and commits the journal and registry
back to that branch. The 3-month paper evaluation (PAPER → PAPER_PASSED) is due after 2027-02-17.

## D-023 — Partly filled entries are completed at the next open (2026-11-19)
The first paper entry (H4-17, buy 6 SPY market-on-open) filled only 3 shares at 738.41; Alpaca expired
the rest. The runner held 3 shares because it never resizes an open position, so the trade ran at half
the size the backtest assumes. Owner approved the fix: each submitted plan now records the size it
meant to hold (`target_qty`); while the strategy stays in, the next run buys the shortfall at the open
(here: buy 3 at the 2026-11-20 open, if H4-17 is still long). Fills record `ordered_qty` and `partial`
so the partial-fill rate can be checked against the cost model in the 3-month review. The top-up's
price differs from the original entry; the review measures returns per share, so this changes dollar
size, not the comparison.


## D-024 — Top-ups use a plain market order; backup run at 09:05 New York (2026-11-28)
After D-023, all three top-up orders for H4-17 (buy 3 SPY, market-on-open "opg") expired with nothing
filled (Nov 20, 23, 24), and the first entry filled only 3 of 6. The broker gives no reason; Alpaca's
paper simulation of the opening auction looks unreliable for us. Owner approved: top-ups (and only
top-ups) are now sent as market orders with time_in_force "day", queued before the open and filled at
the first trade after 09:30. New entries and exits still use the opening auction, as the backtest
assumes. The top-up's fill price is journaled like any fill, so the 3-month review can measure the
difference. Owner also approved a backup scheduled run at 09:05 New York time that repeats the daily
run if the 08:40 one did not happen (the Nov 25 wake-up arrived a day late). Re-runs are idempotent.

## D-025 — Phase 5 discovery engine: generated ideas, event-study screen, parallel full tests (2026-11-28)
Owner asked for much more automated, higher-throughput research ("both, factory first"). Ideas are now
generated from entry × trend filter × exit templates on 17 daily markets (714 per batch, ≤ 2 tuned
parameters each), pre-registered and committed before testing. Stage IDEA → EFFECT is an event study
(next-open to h-bar return vs. normal, overlapping events thinned, one-sided t-test) with
Benjamini–Hochberg at 5% across all tests in the batch, as protocol §5 requires. Only EFFECT ideas get the
full Phase 3 pipeline, run in parallel. Each rule combination is a family across markets, and the Deflated
Sharpe uses the family's full planned trial count (new `family_trials_floor`), so results do not depend on
run order and replicating a rule on more markets raises the bar. Crypto uses US-retail costs (D-010).
Registry: WAL mode, 300 s busy timeout, experiment-id retry for parallel writers. Calibrated on random walks
(tests/test_discovery.py). Details: docs/DISCOVERY.md.

## D-026 — Batch D5-01 found nothing; D5-02 re-tests the same ideas with a pooled screen (2026-11-28)
D5-01 (per-instrument event studies, BH across 1,071 tests): 0 of 714 ideas passed; best q = 0.09 (SPY after 4
down days). Yet 146 tests had p < 0.05 where ~54 are expected by chance, concentrated in buy-the-dip rules on
US equity ETFs: a collective effect too weak to show on any single market after the correction. Decision: keep
D5-01 as final and logged, and register D5-02 with the same 714 ideas (each linked to its D5-01 parent) but a
pooled screen per market group, averaging events per date so correlated ETFs count once (126 tests). Survivors
still face the full per-market pipeline, with the Deflated Sharpe counting the whole family.

## D-027 — Discovery winners are promoted and paper traded automatically (2026-11-28)
Owner approved multi-strategy paper trading so that new winners go onto the paper account automatically.
After every discovery batch, `lab.discovery.promote` runs each new CANDIDATE once on the vault (final,
never repeated). A VALIDATED strategy is added to configs/deployment.yaml and the $5,000 is split equally
between all deployed strategies (allocations sum to 1: no leverage). Safety rules enforced by the runner on
every run: one strategy per symbol (the broker holds one position per symbol), allocations ≤ 1 in total,
US equity ETFs only (crypto paper trading needs 24/7 handling and different symbols: not supported yet, such
winners are recorded but not deployed). When allocations shrink, a strategy's partly filled entry is only
topped up to what its new allocation buys. Every promotion outcome is logged in
research/discovery/promotions.jsonl. The promotion commit must be pushed: the daily run trades whatever
configs/deployment.yaml says on the branch.
