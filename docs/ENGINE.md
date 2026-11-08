# Backtesting Engine

How simulated trades are executed and accounted for, what protects against look-ahead
bias, and — importantly — what the engine does **not** model.

## Quick start

```bash
uv run lab backtest sma_cross SPY --timeframe 1d --sizing pct_equity --param stop_atr=0
uv run lab backtest donchian_breakout BTCUSDT --timeframe 1h --profile crypto_perp --funding --stress
uv run python scripts/phase2_validation.py     # full engine validation report
uv run pytest                                  # 84 tests incl. accounting, look-ahead, calibration
```

In code, research runs go through `lab.research.run_experiment`, which records every run
(including failures) in the registry. `lab.engine.backtest.run_backtest` is the unrecorded
building block used by tests.

## Architecture

| Module | Role |
|---|---|
| `engine/data.py` | Loads instruments from the lake for a research split, resamples, aligns them on a common time grid. Missing bars stay missing. |
| `engine/strategy.py` | Strategy interface: per-instrument signal arrays (entries, exits, stop/target/trailing distances, priority). |
| `engine/core.py` | Compiled (Numba) bar-by-bar portfolio simulator — the single source of truth for fills and accounting. |
| `engine/backtest.py` | Configs (`RiskConfig`, `ExecutionConfig`), runs the simulator, computes metrics, benchmark, regimes, warnings. |
| `engine/metrics.py` | Performance metrics with known-answer tests. |
| `engine/lookahead.py` | Look-ahead detectors usable on any strategy. |
| `costs/` + `configs/costs.yaml` | Per-market cost profiles. |
| `features/indicators.py`, `features/regimes.py` | Causal indicators and lagged regime labels. |
| `registry/db.py`, `research.py` | Research database and recorded experiment runner. |

Strategies compute signals with vectorised NumPy/Polars code once; the simulator loop is
compiled. A 2.6-million-bar BTC 1-minute backtest takes ≈1.2 s end to end.

## Execution model

Inside each bar, for every instrument that has a bar:

1. **Open** — dividends booked; pending exits, then pending entries (highest `priority` first) fill
   at the **open**. Orders come from signals of an earlier bar (`delay_bars` ≥ 1, enforced).
2. **Intrabar** — stop, trailing stop and profit target checked against the bar's high/low.
3. **Close** — funding, borrow and financing charged; trailing extremes updated; equity marked to
   market; risk limits checked; new signals become orders for a later bar.

| Situation | Rule |
|---|---|
| Signal on bar *t* | Fills at the open of the next bar on which the instrument trades. Never at bar *t*'s close. |
| Missing bars | Skipped. Orders wait for the next real bar; positions are valued at the last close. |
| Gap through a stop | Filled at the (worse) open price. |
| Stop and target both inside one bar | **Stop assumed first** (pessimistic). |
| Profit target | Resting limit: price must trade *through* the target by the half-spread; filled at the target, never better, even on a favourable gap. |
| Trailing stop | Level based on the best price of *completed* bars only; the current bar's high cannot raise the stop that same bar. |
| Entry bar | Stops and targets are active from the entry bar onward. |
| Reversal (long → short signal) | Close and re-open on the same next-bar open. |
| End of data | Open positions liquidated at the last close, with costs. |

### Execution prices and costs

```
market order price = reference × (1 ± (half_spread + slippage_bps + slippage_range_frac × prior bar range))
fee                = notional × fee_bps (+ sell_fee_bps on sells) + qty × fee_per_unit, at least min_fee
```

- **Spread**: from bid/ask data when available (forex), otherwise the instrument's assumed half-spread.
- **Slippage**: fixed component plus a volatility component based on the *signal* bar's range (known at
  decision time).
- **Funding** (crypto perpetuals): real historical funding rates; longs pay positive rates.
- **Borrow** (shorts) and **financing**: annual rates accrued per bar held.
- **Dividends**: credited to longs, debited to shorts on ex-dates (equities).
- **Liquidity**: orders capped at `max_participation` × the signal bar's volume (1% by default).
- **Size limits**: lot size, minimum order value, per-position cap, gross exposure cap, cash.

Cost profiles (`configs/costs.yaml`): `crypto_spot` (10 bps taker), `crypto_perp` (5 bps taker,
funding, shorting), `crypto_spot_us_retail` (40 bps), `equity_us` (commission-free, SEC fee, 0.5%
borrow), `fx_retail` (data spreads + markup), `futures_us` ($1.25/contract). Every strategy should be
stress-tested at ×1.5, ×2 and ×3 costs (`cost_sensitivity`, `lab backtest --stress`).

## Position sizing and risk (`RiskConfig`)

| Setting | Default | Meaning |
|---|---|---|
| `initial_cash` | 5,000 | Starting balance |
| `sizing` | `risk` | `risk`: lose `risk_per_trade` of equity if the stop is hit (requires a stop); `pct_equity`; `fixed_notional` |
| `risk_per_trade` | 1% | |
| `max_position_pct` | 100% | Cap on one position's value / equity |
| `max_gross_exposure` | 1.0 | Sum of position values / equity. **1.0 = no leverage**; longs must be paid in cash |
| `max_open_positions` | 10 | |
| `max_daily_loss` | off | Flatten at the next open and block entries for the rest of the UTC day |
| `max_drawdown` | off | Flatten and halt permanently |
| `max_bars_held` | off | Time exit |

Quantities are sized from the signal bar's close and re-capped at the fill price.
Leverage is never assumed: futures (e.g. one micro E-mini ≈ $25k notional) cannot be traded
with $5k unless `max_gross_exposure` is raised explicitly, which is recorded in the experiment.

## Look-ahead protections

1. Engine: orders fill no earlier than the next bar's open (`delay_bars >= 1`), slippage uses the
   prior bar, trailing stops use completed bars, regime labels are lagged one day.
2. Indicators use trailing windows only; `shift()` refuses negative lags; higher-timeframe values
   are only visible after the higher bar has closed (`align_higher_timeframe`).
3. `lookahead.check_strategy`: signals recomputed on truncated data must match — catches
   strategies that peek (tested against deliberately cheating strategies).
4. `lookahead.check_engine`: scrambling all data after bar *k* must not change equity before *k*.
5. `run_experiment` runs check 3 automatically and refuses strategies that fail.
6. Vault data: refused unless `stage="vault"`, once per hypothesis, logged in `vault_access`.

## Metrics

Net return, CAGR (undefined for < 1 week), Sharpe, Sortino, Calmar, max drawdown and its duration,
win rate, average win/loss, payoff ratio, profit factor, expectancy ($ and R), exposure, average gross
exposure, annual turnover, trade count (long/short), average holding time and bars, max consecutive
wins/losses, fees / spread+slippage / carry totals, costs as a share of gross profit, monthly returns,
performance by trend and volatility regime, and an equal-weight buy-and-hold benchmark with beta and
correlation. Definitions are in `engine/metrics.py`; Sharpe/Sortino use daily returns, annualised with
the observed number of days per year (≈365 crypto, ≈252 equities), risk-free rate 0.

## Validation status

See `reports/phase2_engine_validation.md`. Summary: 84 automated tests pass (exact accounting,
stops/targets/trails, gaps, missing data, costs, funding, borrow, dividends, sizing, risk limits,
look-ahead detection, metric known answers, registry). Random entries lose on 60/60 real-data runs after
costs, and average ≈0 without costs (no engine bias).

## Limitations (read before trusting any result)

- **Bar-level simulation.** The order of events inside a bar is unknown; the engine uses pessimistic
  rules, but intrabar paths, queue position, partial fills and latency are not modelled.
  **Scalping strategies cannot be validated on 1-minute bars**; results carry a fidelity warning and
  need tick/quote data (Phase 7, NautilusTrader).
- **No bid/ask for crypto and equities**: spreads are assumed constants. Real spreads widen in fast
  markets exactly when many strategies trade.
- **Daily equity bars**: fills assume market-on-open at the daily open price.
- **One position per instrument** (no pyramiding / scaling in); entries while positioned are ignored.
- **Cash earns no interest** and margin interest is not modelled (no leverage by default).
- **USD-quoted instruments only** (USDJPY etc. need currency conversion — not yet implemented). USDT is
  treated as equal to USD.
- **Perpetual futures are simulated on spot prices** plus historical funding; basis between perp and
  spot is ignored.
- **Funding on coarse bars** is charged if the position is held at that bar's close, an approximation
  for bars longer than the funding interval.
- **Borrow availability** is assumed (easy-to-borrow ETFs); recalls and hard-to-borrow fees are not modelled.
- **Taxes** are not modelled.
- **Futures**: no roll logic or data yet; margin is approximated by allowing gross exposure > 1.
