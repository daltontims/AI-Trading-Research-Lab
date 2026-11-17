# Phase 4 — Candidate Review

Extra scrutiny for hypotheses that passed every gate. Cross-market runs use the exact same rules and parameters on the development split and are recorded as robustness trials.

## H4-02 — BTC daily trend filter (long/flat)

Rules: `TrendFilter` with `{"n": 50}`; BTCUSDT 1d.

| | Development | Validation |
|---|---|---|
| Strategy net return | 1542.2% | 61.0% |
| Buy & hold | 1011.0% | 142.0% |
| Strategy Sharpe / buy & hold Sharpe | 1.41 / 1.06 | 1.05 / 1.41 |
| Strategy max DD / buy & hold max DD | -61.9% / -76.6% | -28.9% / -28.1% |
| Exposure (time in market) | 53.7% | 56.1% |
| Trades | 40 | 14 |

- Deflated Sharpe at evaluation: 0.977 (5 family trials); recomputed with all 16 trials now in family `crypto-daily-trend`: **0.959**.
- Trade-order Monte Carlo: 95th-percentile drawdown -62.3%, probability of halving the account 6.3%.
- At US-retail crypto costs (≈40 bps/side): 1181.5% on development data.

Cross-market replication (same rules, development split):

| Market | Net return | Sharpe | Max DD | Trades | Buy & hold |
|---|---|---|---|---|---|
| ETHUSDT | 948.7% | 1.06 | -60.8% | 51 | 1536.5% |
| SOLUSDT | 8351.5% | 1.83 | -73.7% | 32 | 2975.8% |

Replicated (profitable with positive Sharpe) on **2/2** other markets.

## H4-17 — SPY 2-day RSI pullback

Rules: `RsiReversion` with `{"exit_rsi": 70.0, "trend_n": 200, "entry_rsi": 10.0}`; SPY 1d.

| | Development | Validation |
|---|---|---|
| Strategy net return | 239.3% | 14.5% |
| Buy & hold | 640.0% | 49.7% |
| Strategy Sharpe / buy & hold Sharpe | 0.76 / 0.59 | 0.51 / 0.54 |
| Strategy max DD / buy & hold max DD | -15.3% / -47.0% | -8.3% / -32.7% |
| Exposure (time in market) | 12.4% | 9.8% |
| Trades | 175 | 25 |

- Deflated Sharpe at evaluation: 0.997 (4 family trials); recomputed with all 12 trials now in family `H4-17`: **0.999**.
- Trade-order Monte Carlo: 95th-percentile drawdown -15.0%, probability of halving the account 0.0%.

Cross-market replication (same rules, development split):

| Market | Net return | Sharpe | Max DD | Trades | Buy & hold |
|---|---|---|---|---|---|
| QQQ | 166.7% | 0.62 | -15.0% | 137 | 222.4% |
| IWM | 110.6% | 0.58 | -20.0% | 122 | 274.4% |
| DIA | 55.0% | 0.41 | -13.1% | 135 | 282.7% |
| XLK | 54.1% | 0.33 | -16.7% | 118 | 120.3% |
| XLF | 111.1% | 0.59 | -11.3% | 117 | 85.5% |
| XLI | 92.5% | 0.53 | -19.0% | 134 | 280.0% |

Replicated (profitable with positive Sharpe) on **6/6** other markets.

