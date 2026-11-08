# Phase 2 — Engine Validation Report

*Generated 2026-11-08 08:42 UTC by `scripts/phase2_validation.py`.*

**These are engine diagnostics using textbook rules on the development split only. They are not research findings and none of these strategies is a candidate.** Every run below is recorded in the research registry (family `engine_demo`, stage `diagnostic`).

## 1. Sample backtests (after all costs)

| Run | Net return | CAGR | Sharpe | Sortino | Max DD | Trades | Win rate | PF | Expectancy $ | Exposure | Costs/gross |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SPY 50/200-day moving-average trend (long only, no stop) (`E-20261108-0001`) | 869.60% | 9.55% | 0.81 | 1.16 | -18.35% | 12 | 83.3% | 24.11 | 3,623.34 | 71% | 1% |
| Buy & hold SPY | 639.99% | 8.36% | 0.59 | – | -47.02% | – | – | – | – | 100% | – |
| BTC 1h 55-bar breakout, perpetual, long/short (`E-20261108-0002`) | -59.90% | -16.70% | -0.88 | -1.54 | -62.12% | 786 | 27.7% | 0.82 | -3.81 | 27% | 228% |
| Buy & hold BTCUSDT | 1041.22% | 62.74% | 1.06 | – | -77.20% | – | – | – | – | 100% | – |
| ETH 15m Bollinger mean reversion, perpetual, long/short (`E-20261108-0003`) | -99.85% | -72.94% | -9.11 | -9.04 | -99.86% | 4648 | 45.4% | 0.54 | -1.07 | 18% | n/a |
| Buy & hold ETHUSDT | 1635.34% | 76.98% | 1.10 | – | -81.46% | – | – | – | – | 100% | – |

## 2. Cost stress tests

Each strategy re-run with spread, slippage, fees and borrow multiplied. A strategy whose result flips sign between ×1 and ×2 is *fragile*.

| Run | Costs | Net return | Sharpe | PF | Max DD |
|---|---|---|---|---|---|
| SPY 50/200-day moving-average trend (long only, no stop) | ×1.0 | 869.60% | 0.81 | 24.11 | -18.35% |
| SPY 50/200-day moving-average trend (long only, no stop) | ×1.5 | 866.32% | 0.81 | 23.77 | -18.39% |
| SPY 50/200-day moving-average trend (long only, no stop) | ×2.0 | 860.59% | 0.81 | 23.49 | -18.42% |
| SPY 50/200-day moving-average trend (long only, no stop) | ×3.0 | 853.61% | 0.81 | 23.06 | -18.49% |
| BTC 1h 55-bar breakout, perpetual, long/short | ×1.0 | -59.90% | -0.88 | 0.82 | -62.12% |
| BTC 1h 55-bar breakout, perpetual, long/short | ×1.5 | -80.69% | -1.66 | 0.71 | -80.89% |
| BTC 1h 55-bar breakout, perpetual, long/short | ×2.0 | -91.48% | -2.55 | 0.61 | -91.50% |
| BTC 1h 55-bar breakout, perpetual, long/short | ×3.0 | -98.12% | -4.08 | 0.47 | -98.12% |
| ETH 15m Bollinger mean reversion, perpetual, long/short | ×1.0 | -99.85% | -9.11 | 0.54 | -99.86% |
| ETH 15m Bollinger mean reversion, perpetual, long/short | ×1.5 | -99.90% | -10.54 | 0.40 | -99.90% |
| ETH 15m Bollinger mean reversion, perpetual, long/short | ×2.0 | -99.90% | -10.81 | 0.29 | -99.90% |
| ETH 15m Bollinger mean reversion, perpetual, long/short | ×3.0 | -99.90% | -10.03 | 0.13 | -99.90% |

## 3. Details

### SPY 50/200-day moving-average trend (long only, no stop)

- Data: 1993-01-29 → 2017-12-29, 6,277 bars (1d), split `development`; run time 2.4s for 4 cost levels.
- Cost profile: `equity_us` — fee 0.0 bps/side, half-spread 0.3 bps, slippage 1.0 bps + 0.02×bar range.
- Costs paid: fees $7, spread+slippage $186, carry (funding/borrow/dividends) $6,860; gross P&L before costs $36,813.
- Avg win $4,536.15, avg loss $-940.71, payoff 4.82, expectancy n/a R, avg holding 12,968.0 h, max consecutive wins/losses 9/1, turnover 1.0×/yr, Calmar 0.52.
- Exit reasons: signal 11, end_of_data 1
- Regimes (trend / volatility of the traded instrument, lagged): trend=down: +61.2% over 1639 d; trend=unknown: +0.0% over 100 d; trend=up: +501.4% over 4538 d; volatility=high: +434.4% over 3321 d; volatility=low: +81.4% over 2934 d; volatility=unknown: +0.0% over 22 d
- Warnings: Daily bars: entries/exits assume market-on-open fills; intraday path of stops is approximated from daily high/low (stop assumed to win when stop and target share a bar). Only 12 trades: statistically meaningless.

- Engine causality check on real data: PASSED

### BTC 1h 55-bar breakout, perpetual, long/short

- Data: 2019-01-01 → 2023-12-31, 43,765 bars (1h), split `development`; run time 0.8s for 4 cost levels.
- Cost profile: `crypto_perp` — fee 5.0 bps/side, half-spread 0.5 bps, slippage 1.0 bps + 0.05×bar range.
- Costs paid: fees $1,629, spread+slippage $3,387, carry (funding/borrow/dividends) $-177; gross P&L before costs $2,198.
- Avg win $64.11, avg loss $-29.88, payoff 2.15, expectancy -0.11 R, avg holding 15.0 h, max consecutive wins/losses 5/11, turnover 188.3×/yr, Calmar -0.27.
- Exit reasons: trailing_stop 485, stop 301
- Regimes (trend / volatility of the traded instrument, lagged): trend=down: -33.0% over 709 d; trend=unknown: -7.3% over 100 d; trend=up: -35.4% over 1017 d; volatility=high: -57.7% over 808 d; volatility=low: -0.5% over 996 d; volatility=unknown: -4.7% over 22 d
- Warnings: No bid/ask data: spreads are assumed constants from configs, not observed.

- Engine causality check on real data: PASSED

### ETH 15m Bollinger mean reversion, perpetual, long/short

- Data: 2019-01-01 → 2023-12-31, 175,027 bars (15m), split `development`; run time 1.1s for 4 cost levels.
- Cost profile: `crypto_perp` — fee 5.0 bps/side, half-spread 1.0 bps, slippage 1.0 bps + 0.05×bar range.
- Costs paid: fees $1,867, spread+slippage $2,561, carry (funding/borrow/dividends) $1; gross P&L before costs $-567.
- Avg win $2.72, avg loss $-4.23, payoff 0.64, expectancy -0.30 R, avg holding 1.7 h, max consecutive wins/losses 9/14, turnover 953.1×/yr, Calmar -0.73.
- Exit reasons: stop 2364, signal 2284
- Regimes (trend / volatility of the traded instrument, lagged): trend=down: -92.8% over 649 d; trend=unknown: -30.3% over 100 d; trend=up: -97.1% over 1077 d; volatility=high: -90.6% over 804 d; volatility=low: -98.4% over 1000 d; volatility=unknown: -3.7% over 22 d
- Warnings: No bid/ask data: spreads are assumed constants from configs, not observed.

- Engine causality check on real data: PASSED

## 4. Account size sensitivity (SPY 50/200, whole shares)

| Starting balance | Net return | Max DD | Trades |
|---|---|---|---|
| $1,000 | 839.56% | -18.22% | 12 |
| $5,000 | 869.60% | -18.35% | 12 |
| $25,000 | 876.23% | -18.39% | 12 |
| $100,000 | 896.96% | -18.39% | 12 |

Small accounts hold more idle cash because only whole shares are bought.

## 5. Random-entry calibration on real data (BTC 1-minute, development split)

30 seeds per venue; entries with 0.2% probability per minute, stop and target at 2×ATR, max 60 minutes holding, 0.5% risk per trade.

| Venue profile | Mean net return | Median | Profitable seeds | Mean trades | Mean Sharpe |
|---|---|---|---|---|---|
| `crypto_perp` | -99.5% | -99.5% | 0/30 | 5,194 | -12.23 |
| `crypto_spot` | -99.9% | -99.9% | 0/30 | 3,504 | -13.40 |
| `crypto_perp, costs ×0` | 1.6% | -0.7% | 13/30 | 5,194 | 0.06 |

With realistic costs every seed should lose: costs are paid on every trade and random entries have no edge. The stronger test is the **zero-cost** row: random long/short entries should average close to zero if the engine has no built-in bias. Observed t-statistic of the mean: **0.59** (consistent with zero).

## 6. Speed

One BTC 1-minute backtest over 2,625,351 bars (signals + simulation + metrics + registry write): median 1.17 s. Signals are computed once per strategy and reused across cost levels.

## 7. Registry

Total trials recorded so far: **106**.
