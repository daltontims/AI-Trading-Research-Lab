# Phase 3 — Pipeline Calibration

*Generated 2026-11-17 04:49 UTC by `scripts/phase3_calibration.py`.*

Does the promotion pipeline (docs/VALIDATION.md) reject luck and detect real effects? Each row runs the **full pipeline** — parameter search, cost screen, Deflated Sharpe, PBO, SPA, walk-forward, parameter plateau, year consistency and one validation look — on datasets where the truth is known.

Synthetic bars are built from a continuous price path (`lab.validation.synthetic`). An earlier run used a flawed generator and is kept in the registry as `H-CAL-*` but is **invalid** (DECISIONS D-016).

| Test | Setting | Truth | Datasets | Became CANDIDATE | Rate | Passed cost screen |
|---|---|---|---|---|---|---|
| A | Null: random walk, momentum grid (6 lookbacks) | 0 expected | 60 | 0 | 0.0% | 0 |
| A | Null: random walk, breakout grid (3×3) | 0 expected | 60 | 0 | 0.0% | 15 |
| B | Null: best of 12 random-entry strategies, real BTC 1h, no costs | 0 expected | 20 | 0 | 0.0% | 20 |
| C | Null: BTC 1h with shuffled return order, momentum grid, no costs | 0 expected | 20 | 0 | 0.0% | 20 |
| D | Power: planted momentum φ=0.03 | high expected | 20 | 0 | 0.0% | 1 |
| D | Power: planted momentum φ=0.06 | high expected | 20 | 0 | 0.0% | 1 |
| D | Power: planted momentum φ=0.1 | high expected | 20 | 1 | 5.0% | 1 |
| D | Power: planted momentum φ=0.15 | high expected | 20 | 20 | 100.0% | 20 |

**False-positive rate across all null tests: 0/160 = 0.0%** (the protocol requires this to be at or below the nominal 5%).

## How to read this

- *Null* rows contain no real edge by construction, so every CANDIDATE there is a false discovery.
- *Power* rows contain a real momentum effect of strength φ (autocorrelation of hourly returns). Weak effects are expected to be missed: the pipeline is deliberately strict, trading missed opportunities for fewer false discoveries.
- Synthetic tests use 20% of normal costs; real-data nulls use zero costs so that the statistics, not the costs, do the rejecting.

Total registry trials: 4187.
