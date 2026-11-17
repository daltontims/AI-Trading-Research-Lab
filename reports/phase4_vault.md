# Phase 4 — Vault (final) test

*Run 2026-11-17 05:25 UTC. Settings fixed beforehand in docs/DECISIONS.md D-021. Each candidate's frozen rules were run once on data never used before (the vault). The outcome is final.*

## H4-17 — SPY 2-day RSI pullback: **VALIDATED**

Vault period 2022-07-01 → 2026-11-06 (`E-20261117-0756`).

| Metric | Development | Validation | **Vault** |
|---|---|---|---|
| Net return | 239.3% | 14.5% | **35.6%** |
| CAGR | 5.0% | 3.1% | 7.2% |
| Sharpe | 0.76 | 0.51 | 1.19 |
| Max drawdown | -15.3% | -8.3% | -8.2% |
| Trades | 175 | 25 | 40 |
| Win rate | 76.6% | 72.0% | 75.0% |
| Profit factor | 3.10 | 1.99 | 2.10 |
| Buy & hold return | 640.0% | 49.7% | 100.7% |
| Buy & hold Sharpe | 0.59 | 0.54 | 1.09 |
| Buy & hold max DD | -47.0% | -32.7% | -18.2% |

- Probability vault Sharpe > 0 (PSR): 0.99; at 2× costs: 31.1%.
- Interest on idle cash: $788.
- Development re-run with cash interest (diagnostic): 429.2% (was 239.3% without), CAGR 6.9%, Sharpe 1.02, interest earned $4,895.

## H4-02 — BTC daily trend filter (long/flat): **REJECTED**

Vault period 2025-07-01 → 2026-10-31 (`E-20261117-0757`).

| Metric | Development | Validation | **Vault** |
|---|---|---|---|
| Net return | 1542.2% | 61.0% | **-1.0%** |
| CAGR | 75.0% | 37.4% | -0.7% |
| Sharpe | 1.41 | 1.05 | 0.09 |
| Max drawdown | -61.9% | -28.9% | -24.9% |
| Trades | 40 | 14 | 15 |
| Win rate | 27.5% | 28.6% | 13.3% |
| Profit factor | 2.13 | 2.51 | 0.97 |
| Buy & hold return | 1011.0% | 142.0% | -26.8% |
| Buy & hold Sharpe | 1.06 | 1.41 | -0.35 |
| Buy & hold max DD | -76.6% | -28.1% | -53.0% |

- Probability vault Sharpe > 0 (PSR): 0.54; at 2× costs: -9.9%.
- No interest on idle cash (crypto).
- Failed: vault_net_profit: -0.010 (needs 0)
- Failed: vault_profit_factor: 0.966 (needs 1.000)
- Failed: vault_psr: 0.540 (needs 0.800)

