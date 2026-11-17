# Phase 4 — Summary and Conclusions

*21 pre-registered hypotheses (committed before any test: commit 4658498), evaluated by the Phase 3
pipeline on development data, with a single validation look for those passing every gate. Details:
[phase4_research_batch.md](phase4_research_batch.md) (leaderboard),
[phase4_candidate_review.md](phase4_candidate_review.md) (extra scrutiny), strategy cards in
[strategies/](strategies/), failures in [../research/graveyard/](../research/graveyard/README.md).*

## Final outcome (after the vault test, reports/phase4_vault.md)

- **H4-17 SPY RSI(2) pullback — VALIDATED.** Vault 2022-07 → 2026-11: +35.6% (7.2%/yr), Sharpe 1.19 vs
  1.09 buy & hold, max drawdown −8% vs −18%, 40 trades, 75% winners, still +31% at 2× costs.
- **H4-02 BTC 50-day trend filter — REJECTED at the vault** (−1.0% while BTC fell 27%: good protection,
  no edge).

## Results at a glance (before the vault test)

| Group | Count | Notes |
|---|---|---|
| **Candidates** (promising, NOT validated) | 2 | H4-17 SPY RSI(2) pullback; H4-02 BTC 50-day trend filter |
| Rejected: profitable but failed luck/robustness gates | 8 | SPY trend filter (PBO 0.24), BTC daily momentum, ETH trend, dual momentum, VIX term structure, sector momentum, VIX spike, low-vol regime |
| Rejected: lost money after costs | 10 | every hourly / 15-minute crypto idea, pairs, weekend, turn-of-month (at 2× costs) |
| Rejected: too few trades | 1 | funding contrarian (6 trades — thresholds rarely reached) |

## Candidates

### H4-17 — SPY 2-day RSI pullback (stronger)
Buy SPY at the next open when the 2-day RSI closes below 10 while SPY is above its 200-day average;
sell at the next open after RSI closes above 70.
- Development (1993–2017): +239% after costs, Sharpe 0.76 vs 0.59 buy & hold, max drawdown −15% vs −47%,
  175 trades, 77% winners, profit factor 3.1, profitable in 20 of 25 years.
- Validation (2018–mid 2022, one look): +14.5%, Sharpe 0.51 vs 0.54 buy & hold, max DD −8% vs −33%.
- Same rules worked on **6/6 other ETFs** (QQQ, IWM, DIA, XLK, XLF, XLI).
- **Weaknesses:** in the market only ~12% of the time, so total return is far below buy & hold (the engine
  pays no interest on idle cash, which understates it); widely published rule (since ~2008) that may have
  weakened — validation Sharpe is lower than development; daily bars assume market-on-open fills.
- **Confidence: low.** Real, broad statistical evidence, but modest validation sample (25 trades).

### H4-02 — BTC 50-day trend filter, long/flat (weaker)
Hold BTC when its daily close is above the 50-day average, otherwise hold cash.
- Development (2019–2023): +1,542% vs +1,011% buy & hold, Sharpe 1.41 vs 1.06, max DD −62% vs −77%; 40 trades.
- Validation (2024–mid 2025): +61% vs +142% buy & hold; Sharpe 1.05 vs 1.41 — **worse than simply holding**.
- Replicates directionally on ETH and SOL (profitable), but the ETH version of the hypothesis (H4-03) was
  rejected by the luck gates; recomputed Deflated Sharpe with all family trials is 0.959 (threshold 0.95).
- Survives US-retail crypto costs (+1,182% in development).
- **Weaknesses:** only 54 trades in total; drawdowns of ~60% remain; its value is mainly avoiding bear
  markets (2022), which may not repeat; it lagged buy & hold in the validation bull market.
- **Confidence: low.**

## What we learned

1. **Short-horizon crypto trading is dominated by costs.** All seven hourly/15-minute crypto ideas lost
   money after realistic costs; several had positive gross edges that costs erased. Scalping-style research
   needs much cheaper execution assumptions than retail access provides — or tick data showing genuinely
   larger edges.
2. **Slow, well-known effects survive best**: trend filters and short-term index pullbacks. These are
   also the most published, so their future edge is uncertain.
3. **The gates matter.** Eight ideas made money in development but were stopped for being indistinguishable
   from luck or fragile. Without the gates, all eight would have looked attractive.

## Next steps

1. Done: cash interest modelled (D-020) and vault tests run with settings fixed in advance (D-021).
2. Paper trading of H4-17 would be the next validation stage — requires the owner's permission and a
   free paper account (e.g. Alpaca paper trading).
3. Phase 5: automated hypothesis generation, building on the families that showed signal (trend and
   pullback effects across many ETFs and coins), with the trial counts growing accordingly.
