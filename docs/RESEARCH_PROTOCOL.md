# Research Protocol

*The rules every hypothesis and strategy must follow. These rules exist to stop
us fooling ourselves. They are changed only through an entry in DECISIONS.md.*

## 1. Pre-registration

- Every hypothesis is written to the registry **before** it is tested: the
  question, the market(s), the event/condition, the expected direction, the
  rules, the parameter ranges allowed, and the test it must pass.
- Changing rules after seeing results creates a **new hypothesis** linked to
  its parent. The parent's trials still count.
- Every backtest run — including failed, aborted and diagnostic runs — is
  logged as a *trial*.

## 2. Data partitioning (per market)

```
|◄──────────── DEVELOPMENT (≈70%) ────────────►|◄─ VALIDATION ─►|◄ VAULT ►|
|  training / walk-forward folds               |   (≈15–20%)    | (most   |
|                                              |                | recent  |
|                                              |                | ≈10–15%)|
```

- **Development:** exploration, event studies, screening, walk-forward.
- **Validation (out-of-sample):** used only for candidates that passed
  development. Each look is logged.
- **Vault (holdout):** most recent data. Opened **once per strategy**, only at
  the promotion decision. Results are final; no re-tuning afterwards.
- Split boundaries are fixed in `configs/splits.yaml` and versioned.
- Cross-validation folds are **purged and embargoed** so overlapping trade
  horizons cannot leak information between training and test.

## 3. Mandatory metrics (always after costs)

Number of trades · win rate · average win / average loss (risk-reward) ·
profit factor · expectancy per trade (in $ and in R) · net return · CAGR ·
maximum drawdown and duration · Sharpe · Sortino · Calmar · exposure ·
turnover · cost as % of gross profit · worst day/week · skew and tail ratio ·
performance by year and by regime (trend/range, high/low volatility).

## 4. Cost and execution realism

- Every market has a cost model: commission/fees, half-spread, slippage, and
  where relevant funding/borrow/rollover.
- Signals execute on the **next** bar/tick after the decision, never the same one.
- Scalping/intraday: bid/ask-aware fills, latency of 100–300 ms assumed for a
  retail setup, no fills at prices the market did not trade through,
  conservative limit-order fill assumptions.
- Every candidate is re-run at **2× costs**. If it dies at 2× costs, it is
  flagged *fragile*.
- Position size must be small relative to typical volume (liquidity check).

## 5. Statistical tests

- **Minimum sample:** ≥ 100 trades in development for intraday/scalping,
  ≥ 30 for swing (flagged *low sample* below 100).
- **Deflated Sharpe Ratio** (Bailey & López de Prado) using the total number
  of trials for that hypothesis family: must exceed 0.95.
- **Probability of Backtest Overfitting** (CSCV): must be < 0.2 when
  parameters were searched.
- **Reality Check / SPA** across the strategies tested in a batch.
- **Benjamini–Hochberg** false-discovery control across hypotheses at the
  event-study stage.
- **Bootstrap / Monte Carlo:** block bootstrap of returns and trade-order
  resampling to get confidence intervals for drawdown and returns.

## 6. Robustness

- **Parameter stability:** performance must hold across a neighbourhood of
  parameter values (a plateau, not a spike).
- **Walk-forward:** rolling re-fit; out-of-sample segments must be positive in
  aggregate and in most segments.
- **Regime breakdown:** not dependent on a single year or a single regime.
- **Cross-market replication:** where it makes sense, the effect should appear
  in related instruments (e.g. ES and NQ; EUR/USD and GBP/USD).
- **Parameter budget:** ≤ 4 tunable parameters, bounded search with a fixed
  trial budget recorded in the registry.

## 7. Promotion stages

| Stage | Meaning | Gate |
|---|---|---|
| `IDEA` | Registered, untested | — |
| `REJECTED` | Failed a gate; kept in graveyard with reason | — |
| `EFFECT` | Event study shows a statistically meaningful effect | BH-adjusted p < 0.05 on development data |
| `SCREENED` | Profitable after costs on development data | Sections 3–4 |
| `CANDIDATE` ("promising") | Passes walk-forward, validation, robustness | Sections 5–6 |
| `VALIDATED` | Passes the vault test and event-driven simulation | Vault opened once, positive after costs, consistent with validation |
| `PAPER` | Running in paper trading (with permission) | — |
| `PAPER_PASSED` | ≥ 3 months paper, results within expected range | — |

The dashboard always shows `CANDIDATE` and `VALIDATED` separately. Nothing
below `VALIDATED` is described as an edge.

## 8. Calibration

Before trusting the pipeline, and after any major change, it is run on
**random strategies** and on **shuffled data**. The pass rate must match the
nominal false-positive rate. If random strategies get promoted, the pipeline
is broken and research stops until it is fixed.

## 9. Confidence ratings

Each strategy report includes a confidence rating — *Very low / Low / Moderate
/ High* — with a short justification (sample size, number of trials,
robustness, economic rationale, cost sensitivity). "High" requires
`PAPER_PASSED`.
