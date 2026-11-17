# Validation Toolkit

How the lab decides whether a backtest result is likely a real edge or luck. This implements
docs/RESEARCH_PROTOCOL.md; thresholds live in `configs/protocol.yaml`.

## The core problem, in plain words

If you try enough strategies, some will look excellent purely by chance — exactly like some
people flipping coins will get ten heads in a row. The more variations tried, the better the
best one looks, even when none of them work. Every tool below is a different way of asking:
*is this result better than what luck alone would produce, given how many things we tried?*

## Quick start

```bash
uv run lab evaluate ts_momentum BTCUSDT --timeframe 1h --profile crypto_perp --funding \
    --space '{"lookback": [6, 12, 24, 48]}' --sizing pct_equity \
    --title "BTC hourly momentum" --question "Do positive 6-48h returns predict continuation?"
uv run python scripts/phase3_calibration.py   # proves the pipeline rejects luck
```

The command pre-registers the hypothesis, runs the pipeline, records everything and writes a
strategy card to `reports/strategies/<hypothesis>.md`.

## The pipeline (`lab.validation.evaluate`)

| Stage | What runs | Must pass to continue |
|---|---|---|
| 1. Screen (development data) | Every parameter combination is backtested after costs; the best by Sharpe is chosen. Every combination counts as a trial. | Enough trades (100 intraday / 30 swing), net profit, profit factor > 1, **still profitable at 2× costs** |
| 2. Statistics (development data) | Deflated Sharpe, PBO, SPA, walk-forward, parameter plateau, yearly consistency | All gates below |
| 3. Validation look | Chosen parameters on the validation split — **once per hypothesis**, only if stages 1–2 pass | Profit, PF > 1, probability Sharpe > 0 ≥ 80%, enough trades |

Result: **REJECTED** (with the failed gates), **SCREENED** (passed stage 1–2, validation not
opened) or **CANDIDATE** ("promising"). A candidate is *not* validated: the vault test,
tick-level checks for short-term strategies, and paper trading come later.

### Statistical gates

| Gate | Plain meaning | Threshold |
|---|---|---|
| **Deflated Sharpe** | Probability the Sharpe beats the best of N luck-only strategies, where N = all trials ever run in this hypothesis family, adjusted for skewed/fat-tailed returns | ≥ 0.95 |
| **PBO** (probability of backtest overfitting) | Split history into 16 blocks; in every half/half combination, does the in-sample winner stay above median out-of-sample? | ≤ 0.20 |
| **SPA** (Hansen) | Bootstrap test that the best of all configurations tried beats zero, accounting for having tried them all | p ≤ 0.05 |
| **Walk-forward** | Repeatedly choose parameters on the past (≈1.5 years), trade the next ≈6 months, stitch the results | Out-of-sample Sharpe > 0 and ≥ 50% of windows profitable |
| **Parameter plateau** | Neighbouring parameter values should work almost as well (a plateau, not a spike) | Median neighbour Sharpe ≥ 50% of best; ≥ 66% of neighbours positive |
| **Year consistency** | Not dependent on one lucky year | ≥ 50% of years profitable, and profitable with the best year removed |

### Diagnostics (reported on every strategy card, not gated)

Bootstrap 95% interval for the annual Sharpe and for max drawdown (stationary bootstrap, keeps
volatility clustering); trade-order Monte Carlo (range of final equity and drawdowns from the
same trades in a different order, probability of losing half the account); one extra bar of
execution delay; 2× costs; regime breakdown; cross-market replication (optional); walk-forward
efficiency (out-of-sample Sharpe ÷ in-sample Sharpe).

## Building blocks

| Module | Contents |
|---|---|
| `validation/stats.py` | Probabilistic & Deflated Sharpe, expected max Sharpe of N trials, minimum track record, stationary bootstrap, trade Monte Carlo, White Reality Check, Hansen SPA, Benjamini–Hochberg (+ adjusted p-values), Newey–West t-stat |
| `validation/cv.py` | Walk-forward (rolling/anchored, embargo), purged & embargoed k-fold, CSCV/PBO |
| `validation/evaluate.py` | The pipeline, gates, confidence ratings, strategy cards |

All are tested against known answers and Monte Carlo properties (`tests/test_validation_stats.py`):
e.g. the best of 50 random strategies passes naive significance > 60% of the time but the Deflated
Sharpe < 10%; SPA rejects at ≈ the nominal rate under the null and finds a planted winner; PBO
averages 0.5 on noise and ≈0 for a genuinely skilled configuration.

## Rules that protect the data

- The validation split is opened **once per hypothesis**; a second attempt raises an error.
  Changed rules must be registered as a new hypothesis (linked by `parent_id`), and its trials
  add to the family's count, making the Deflated Sharpe stricter.
- The vault is never used by this pipeline.
- Calibration uses only the development split of real data.

## Confidence ratings

`none` (rejected) · `very_low` (screened) · `low` (candidate with caveats, e.g. under 300 trades or a
gate not applicable) · `moderate` (candidate, all gates passed, ≥ 300 trades). `high` is reserved
for strategies that later pass paper trading.

## Limitations

- Walk-forward and PBO reuse each configuration's continuous backtest sliced into windows; positions
  open across a window boundary carry their P&L into the next window (small effect for short holds).
- Daily returns are the unit of analysis; strategies trading a few times a year produce few
  informative observations and will usually fail (by design).
- The Deflated Sharpe uses the variance of Sharpe ratios across the current parameter grid; highly
  correlated variations overstate the effective number of trials (conservative).
- Single-dataset PBO estimates are noisy (calibration: 10–90% range 0.25–0.75 on pure noise), so PBO
  is one gate among several, never the sole criterion.
- Passing every gate on historical data is still not proof: regimes change and edges decay.
