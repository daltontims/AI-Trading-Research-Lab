# Phase 4 — First Research Batch

*Generated 2026-11-17 05:11 UTC by `scripts/phase4_batch.py`. 21 pre-registered hypotheses (research/hypotheses/), development split (crypto 2019–2023, ETFs 1993–2017); validation opened only for ideas passing every development gate. Vault untouched.*

**Outcome: 2 candidate(s), 0 screened, 19 rejected.** A *candidate* is promising, not validated: it still needs the vault test, tick-level checks where relevant, and paper trading. Nothing here is a proven edge.

## Leaderboard

| ID | Hypothesis | Verdict | Dev net return | Dev Sharpe | Max DD | Trades | PF | Buy & hold | Deflated Sharpe | Batch FDR q | Validation return | Main reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [H4-02](strategies/H4-02.md) | BTC daily trend filter (long/flat) | **CANDIDATE** | 1542.2% | 1.41 | -61.9% | 40 | 2.13 | 1011.0% | 0.98 | 0.03 | 61.0% | all gates passed |
| [H4-17](strategies/H4-17.md) | SPY 2-day RSI pullback | **CANDIDATE** | 239.3% | 0.76 | -15.3% | 175 | 3.10 | 640.0% | 1.00 | 0.00 | 14.5% | all gates passed |
| [H4-13](strategies/H4-13.md) | BTC daily time-series momentum (long/short) | **REJECTED** | 963.3% | 1.07 | -60.1% | 126 | 1.59 | 1012.1% | 0.89 | 0.09 | not opened | deflated_sharpe: 0.890 |
| [H4-03](strategies/H4-03.md) | ETH daily trend filter (long/flat) | **REJECTED** | 948.7% | 1.06 | -60.8% | 51 | 1.74 | 1536.5% | 0.75 | 0.09 | not opened | deflated_sharpe: 0.750 |
| [H4-14](strategies/H4-14.md) | SPY trend filter (long/flat) | **REJECTED** | 506.5% | 0.68 | -22.0% | 73 | 3.66 | 640.0% | 0.99 | 0.00 | not opened | pbo: 0.236 |
| [H4-16](strategies/H4-16.md) | Dual momentum SPY/TLT/GLD | **REJECTED** | 223.8% | 0.50 | -24.0% | 43 | 3.11 | 314.9% | 0.93 | 0.04 | not opened | deflated_sharpe: 0.926 |
| [H4-06](strategies/H4-06.md) | BTC funding-rate contrarian carry | **REJECTED** | 80.0% | 0.49 | -75.1% | 6 | 148.57 | 1041.2% | 0.52 | 0.57 | not opened | min_trades: 6 |
| [H4-19](strategies/H4-19.md) | SPY with VIX term-structure filter | **REJECTED** | 119.1% | 0.48 | -27.2% | 120 | 1.83 | 640.0% | 0.91 | 0.06 | not opened | deflated_sharpe: 0.908 |
| [H4-15](strategies/H4-15.md) | Sector ETF momentum rotation | **REJECTED** | 139.4% | 0.41 | -47.2% | 110 | 2.84 | 212.9% | 0.76 | 0.09 | not opened | deflated_sharpe: 0.764 |
| [H4-20](strategies/H4-20.md) | Buy SPY after VIX spikes | **REJECTED** | 123.7% | 0.36 | -28.7% | 96 | 1.63 | 640.0% | 0.78 | 0.12 | not opened | deflated_sharpe: 0.782 |
| [H4-21](strategies/H4-21.md) | SPY low-volatility regime | **REJECTED** | 102.2% | 0.35 | -37.6% | 238 | 1.36 | 640.0% | 0.76 | 0.10 | not opened | deflated_sharpe: 0.756 |
| [H4-04](strategies/H4-04.md) | BTC+ETH 4-hour channel breakout (long/short) | **REJECTED** | -1.4% | 0.06 | -33.3% | 307 | 0.99 | 1339.3% | 0.18 | 0.99 | not opened | net_profit_after_costs: -0.014 |
| [H4-18](strategies/H4-18.md) | SPY turn-of-the-month | **REJECTED** | 0.7% | 0.04 | -27.2% | 134 | 1.01 | 640.0% | 0.19 | 0.95 | not opened | profitable_at_2x_costs: -0.095 |
| [H4-09](strategies/H4-09.md) | BTC daily volatility breakout (intraday) | **REJECTED** | -49.7% | -0.18 | -66.5% | 743 | 0.92 | 1041.2% | 0.08 | 1.00 | not opened | net_profit_after_costs: -0.497 |
| [H4-12](strategies/H4-12.md) | ETH/BTC ratio mean reversion (pairs) | **REJECTED** | -45.8% | -0.27 | -67.5% | 90 | 0.83 | 1339.3% | 0.05 | 1.00 | not opened | net_profit_after_costs: -0.458 |
| [H4-08](strategies/H4-08.md) | BTC weekend drift (long) | **REJECTED** | -41.7% | -0.29 | -63.2% | 261 | 0.84 | 1040.1% | 0.12 | 1.00 | not opened | net_profit_after_costs: -0.417 |
| [H4-01](strategies/H4-01.md) | BTC hourly time-series momentum | **REJECTED** | -95.8% | -0.63 | -96.2% | 1984 | 0.84 | 1041.2% | 0.00 | 1.00 | not opened | net_profit_after_costs: -0.958 |
| [H4-05](strategies/H4-05.md) | BTC hourly overreaction reversal | **REJECTED** | -81.2% | -1.46 | -81.2% | 367 | 0.51 | 1041.2% | 0.00 | 1.00 | not opened | net_profit_after_costs: -0.812 |
| [H4-10](strategies/H4-10.md) | BTC 15-minute volume-shock continuation | **REJECTED** | -57.4% | -1.49 | -62.2% | 461 | 0.63 | 1042.1% | 0.00 | 1.00 | not opened | net_profit_after_costs: -0.574 |
| [H4-07](strategies/H4-07.md) | BTC time-of-day session effect | **REJECTED** | -99.1% | -2.05 | -99.2% | 1823 | 0.76 | 1040.1% | 0.00 | 1.00 | not opened | net_profit_after_costs: -0.991 |
| [H4-11](strategies/H4-11.md) | ETH follows BTC (lead-lag) | **REJECTED** | -97.3% | -3.50 | -97.3% | 812 | 0.39 | 1334.9% | 0.00 | 1.00 | not opened | net_profit_after_costs: -0.973 |

*Batch FDR q*: Benjamini–Hochberg adjusted SPA p-values across this batch — the chance that a result this good is a false discovery given that all of these ideas were tested.

## What failed most often

- `deflated_sharpe`: 18 hypotheses
- `spa`: 12 hypotheses
- `walk_forward_positive_windows`: 12 hypotheses
- `years_positive`: 12 hypotheses
- `parameter_plateau`: 11 hypotheses
- `profitable_at_2x_costs`: 10 hypotheses
- `profitable_without_best_year`: 10 hypotheses
- `net_profit_after_costs`: 9 hypotheses
- `profit_factor`: 9 hypotheses
- `walk_forward_oos_sharpe`: 9 hypotheses
- `pbo`: 3 hypotheses
- `min_trades`: 1 hypotheses

## Notes per hypothesis

- **H4-02 BTC daily trend filter (long/flat)** — CANDIDATE; best `{"n": 50}` of 4; walk-forward OOS Sharpe 1.17, 71.4% windows positive; PBO 0.11; avg holding 588.0 h; at US-retail crypto costs: 1181.5%
- **H4-17 SPY 2-day RSI pullback** — CANDIDATE; best `{"exit_rsi": 70.0, "trend_n": 200, "entry_rsi": 10.0}` of 3; walk-forward OOS Sharpe 0.67, 59.6% windows positive; PBO –; avg holding 151.8 h
- **H4-13 BTC daily time-series momentum (long/short)** — REJECTED; best `{"lookback": 30}` of 4; walk-forward OOS Sharpe 0.61, 71.4% windows positive; PBO 0.41; avg holding 341.7 h. Failed: deflated_sharpe: 0.890; pbo: 0.405
- **H4-03 ETH daily trend filter (long/flat)** — REJECTED; best `{"n": 50}` of 4; walk-forward OOS Sharpe 1.09, 57.1% windows positive; PBO 0.79; avg holding 483.3 h. Failed: deflated_sharpe: 0.750; pbo: 0.794
- **H4-14 SPY trend filter (long/flat)** — REJECTED; best `{"n": 250}` of 5; walk-forward OOS Sharpe 0.60, 57.4% windows positive; PBO 0.24; avg holding 2131.1 h. Failed: pbo: 0.236
- **H4-16 Dual momentum SPY/TLT/GLD** — REJECTED; best `{"lookback": 126}` of 3; walk-forward OOS Sharpe 0.37, 38.3% windows positive; PBO –; avg holding 2171.2 h. Failed: deflated_sharpe: 0.926; walk_forward_positive_windows: 0.383; years_positive: 0.360
- **H4-06 BTC funding-rate contrarian carry** — REJECTED; best `{"exit_threshold": 0.0001, "threshold": 0.001}` of 3; walk-forward OOS Sharpe 0.27, 28.6% windows positive; PBO –; avg holding 1002.7 h. Failed: min_trades: 6; deflated_sharpe: 0.520; spa: 0.296; walk_forward_positive_windows: 0.286
- **H4-19 SPY with VIX term-structure filter** — REJECTED; best `{"ratio": 0.95}` of 3; walk-forward OOS Sharpe 0.26, 25.5% windows positive; PBO –; avg holding 597.2 h. Failed: deflated_sharpe: 0.908; walk_forward_positive_windows: 0.255; years_positive: 0.320
- **H4-15 Sector ETF momentum rotation** — REJECTED; best `{"skip": 21, "top": 3, "lookback": 126}` of 3; walk-forward OOS Sharpe 0.27, 55.6% windows positive; PBO –; avg holding 2648.3 h. Failed: deflated_sharpe: 0.764
- **H4-20 Buy SPY after VIX spikes** — REJECTED; best `{"n": 10, "spike": 1.2}` of 3; walk-forward OOS Sharpe 0.17, 51.1% windows positive; PBO –; avg holding 349.8 h. Failed: deflated_sharpe: 0.782; spa: 0.056
- **H4-21 SPY low-volatility regime** — REJECTED; best `{"median_n": 252, "vol_n": 10}` of 3; walk-forward OOS Sharpe 0.41, 70.2% windows positive; PBO –; avg holding 447.4 h. Failed: deflated_sharpe: 0.756; parameter_plateau: 0.463
- **H4-04 BTC+ETH 4-hour channel breakout (long/short)** — REJECTED; best `{"trail_atr": 3.0, "n": 100}` of 3; walk-forward OOS Sharpe -0.47, 28.6% windows positive; PBO –; avg holding 48.9 h. Failed: net_profit_after_costs: -0.014; profit_factor: 0.993; profitable_at_2x_costs: -0.531; deflated_sharpe: 0.176
- **H4-18 SPY turn-of-the-month** — REJECTED; best `{"days_after": 4}` of 3; walk-forward OOS Sharpe -0.01, 23.4% windows positive; PBO –; avg holding 179.1 h. Failed: profitable_at_2x_costs: -0.095; deflated_sharpe: 0.191; spa: 0.544; walk_forward_oos_sharpe: -0.011
- **H4-09 BTC daily volatility breakout (intraday)** — REJECTED; best `{"k": 0.7}` of 3; walk-forward OOS Sharpe -0.66, 0.0% windows positive; PBO –; avg holding 11.2 h. Failed: net_profit_after_costs: -0.497; profit_factor: 0.918; profitable_at_2x_costs: -0.947; deflated_sharpe: 0.077
- **H4-12 ETH/BTC ratio mean reversion (pairs)** — REJECTED; best `{"entry_z": 2.0, "exit_z": 0.5, "n": 240}` of 3; walk-forward OOS Sharpe -0.10, 42.9% windows positive; PBO –; avg holding 444.8 h. Failed: net_profit_after_costs: -0.458; profit_factor: 0.827; profitable_at_2x_costs: -0.575; deflated_sharpe: 0.054
- **H4-08 BTC weekend drift (long)** — REJECTED; best `{"side": "long"}` of 1; walk-forward OOS Sharpe 0.05, 57.1% windows positive; PBO –; avg holding 48.0 h. Failed: net_profit_after_costs: -0.417; profit_factor: 0.844; profitable_at_2x_costs: -0.749; deflated_sharpe: 0.124
- **H4-01 BTC hourly time-series momentum** — REJECTED; best `{"lookback": 96}` of 5; walk-forward OOS Sharpe -0.75, 28.6% windows positive; PBO 0.02; avg holding 22.0 h. Failed: net_profit_after_costs: -0.958; profit_factor: 0.835; profitable_at_2x_costs: -0.999; deflated_sharpe: 0.000
- **H4-05 BTC hourly overreaction reversal** — REJECTED; best `{"k": 4.0}` of 3; walk-forward OOS Sharpe -1.06, 28.6% windows positive; PBO –; avg holding 5.7 h. Failed: net_profit_after_costs: -0.812; profit_factor: 0.508; profitable_at_2x_costs: -0.961; deflated_sharpe: 0.000
- **H4-10 BTC 15-minute volume-shock continuation** — REJECTED; best `{"ret_z": 2.0, "vol_z": 4.0}` of 3; walk-forward OOS Sharpe -1.57, 0.0% windows positive; PBO –; avg holding 1.0 h. Failed: net_profit_after_costs: -0.574; profit_factor: 0.626; profitable_at_2x_costs: -0.884; deflated_sharpe: 0.000
- **H4-07 BTC time-of-day session effect** — REJECTED; best `{"session": "us"}` of 3; walk-forward OOS Sharpe -2.42, 14.3% windows positive; PBO –; avg holding 8.0 h. Failed: net_profit_after_costs: -0.991; profit_factor: 0.760; profitable_at_2x_costs: -0.999; deflated_sharpe: 0.000
- **H4-11 ETH follows BTC (lead-lag)** — REJECTED; best `{"z": 3.0}` of 3; walk-forward OOS Sharpe -3.72, 0.0% windows positive; PBO –; avg holding 1.0 h. Failed: net_profit_after_costs: -0.973; profit_factor: 0.394; profitable_at_2x_costs: -0.999; deflated_sharpe: 0.000

Registry trials so far: 4542.
