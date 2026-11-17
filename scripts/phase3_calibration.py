"""Phase 3 calibration (RESEARCH_PROTOCOL.md §8): does the promotion pipeline reject luck and
detect real effects?

  A. Null, synthetic: random walks, momentum and breakout parameter grids.
  B. Null, real data: best-of-12 random-entry strategies on real BTC 1h (costs off).
  C. Null, real data: BTC 1h with returns shuffled in time (destroys any real pattern).
  D. Power: synthetic data with planted momentum of increasing strength.

Only the DEVELOPMENT split of real data is used (cut 80/20 into pseudo dev/validation), so
the real validation and vault partitions are never touched. Every run is recorded in the
registry under calibration families (one family per run, as a standalone study would be).

    uv run python scripts/phase3_calibration.py
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import polars as pl

from lab.engine.backtest import ExecutionConfig, RiskConfig  # noqa: E402
from lab.engine.data import load  # noqa: E402
from lab.registry.db import Registry  # noqa: E402
from lab.strategies.examples import DonchianBreakout, RandomEntry, TimeSeriesMomentum  # noqa: E402
from lab.validation.evaluate import evaluate  # noqa: E402
from lab.validation.synthetic import dev_val, path_bars  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "phase3_calibration.md"
SYM = "BTCUSDT"


def split(df: pl.DataFrame, tf: str, frac=0.8):
    return dev_val(df, SYM, tf, frac)


def synthetic(seed, n, phi=0.0, vol=0.004):
    return dev_val(path_bars(seed, n, phi=phi, vol=vol), SYM, "1h")


def shuffled(real: pl.DataFrame, seed):
    """Real BTC bars with the ORDER of hourly returns randomly permuted (bar shapes kept)."""
    rng = np.random.default_rng(seed)
    c = real["close"].to_numpy()
    o, h, lo = (real[x].to_numpy() for x in ("open", "high", "low"))
    lr = np.diff(np.log(c), prepend=np.log(o[0]))
    perm = rng.permutation(len(c))
    hi_rel, lo_rel = (h / np.maximum(o, c))[perm], (lo / np.minimum(o, c))[perm]
    cn = c[0] / np.exp(lr[0]) * np.exp(np.cumsum(lr[perm]))
    on = np.concatenate([[cn[0] / np.exp(lr[perm][0])], cn[:-1]])
    df = real.with_columns(open=pl.Series(on), close=pl.Series(cn), high=pl.Series(np.maximum(on, cn) * hi_rel),
                           low=pl.Series(np.minimum(on, cn) * lo_rel))
    return split(df, "1h")


def run_block(reg, label, family, datasets, strategy_cls, space, fixed, execution, risk):
    verdicts, screened = [], 0
    t0 = time.time()
    for i, (dev, val) in enumerate(datasets):
        sp = space(i) if callable(space) else space
        fam = f"{family}-{i:03d}"
        hid = reg.register_hypothesis(id=f"H-{fam}", family=fam, title=f"{label} #{i}",
                                      question="Calibration: should this pass? (known truth)", source="calibration",
                                      asset_classes=["crypto"], instruments=[SYM], timeframe="1h",
                                      style="calibration", spec={"strategy": strategy_cls.name, "space": sp,
                                                                 "fixed": fixed, "dataset": i})
        if reg.hypothesis(hid)["status"] != "IDEA":   # already evaluated in an earlier run: reuse
            verdicts.append(reg.hypothesis(hid)["status"])
            continue
        ev = evaluate(strategy_cls, sp, [SYM], "1h", hypothesis_id=hid, registry=reg, dev_data=dev, val_data=val,
                      fixed_params=fixed, execution=execution, risk=risk, record_detail=False, write_report=False,
                      export=False, n_boot=200, seed=i, notes=f"calibration: {label}")
        verdicts.append(ev.verdict)
        screened += any(g.name == "profitable_at_2x_costs" and g.passed for g in ev.gates)
    n = len(verdicts)
    cand = sum(v == "CANDIDATE" for v in verdicts)
    return {"label": label, "n": n, "candidates": cand, "rate": cand / n if n else float("nan"),
            "screen_pass": screened, "seconds": time.time() - t0}


def main(n_null=60, n_real=20, n_power=20):
    reg = Registry()
    low_cost = ExecutionConfig(cost_profile="crypto_perp", cost_multiplier=0.2)
    no_cost = ExecutionConfig(cost_profile="crypto_perp", cost_multiplier=0.0)
    mom_risk = RiskConfig(sizing="pct_equity", position_pct=0.5)
    n_syn = 24 * 365 * 4
    rows = []

    print("A. synthetic null")
    rows.append(("A", "Null: random walk, momentum grid (6 lookbacks)", "0 expected",
                 run_block(reg, "null-synthetic-momentum", "CAL2-A1",
                           (synthetic(1000 + i, n_syn) for i in range(n_null)), TimeSeriesMomentum,
                           {"lookback": [1, 2, 4, 8, 16, 24]}, {}, low_cost, mom_risk)))
    rows.append(("A", "Null: random walk, breakout grid (3×3)", "0 expected",
                 run_block(reg, "null-synthetic-breakout", "CAL2-A2",
                           (synthetic(2000 + i, n_syn) for i in range(n_null)), DonchianBreakout,
                           {"n": [20, 55, 100], "trail_atr": [2.0, 3.0, 4.0]}, {}, low_cost, RiskConfig())))

    print("B/C. real-data nulls")
    real = load(SYM, "1h", "development").frames[SYM]
    rows.append(("B", "Null: best of 12 random-entry strategies, real BTC 1h, no costs", "0 expected",
                 run_block(reg, "null-real-random-entry", "CAL2-B",
                           (split(real, "1h") for _ in range(n_real)), RandomEntry,
                           lambda i: {"seed": list(range(12 * i, 12 * i + 12))}, {"prob": 0.01}, no_cost, RiskConfig(max_bars_held=24))))
    rows.append(("C", "Null: BTC 1h with shuffled return order, momentum grid, no costs", "0 expected",
                 run_block(reg, "null-real-shuffled", "CAL2-C",
                           (shuffled(real, 3000 + i) for i in range(n_real)), TimeSeriesMomentum,
                           {"lookback": [1, 2, 4, 8, 16, 24]}, {}, no_cost, mom_risk)))

    print("D. power")
    for phi in (0.03, 0.06, 0.10, 0.15):
        rows.append(("D", f"Power: planted momentum φ={phi}", "high expected",
                     run_block(reg, f"power-phi-{phi}", f"CAL2-D-{int(phi * 100):02d}",
                               (synthetic(4000 + i, n_syn, phi=phi) for i in range(n_power)), TimeSeriesMomentum,
                               {"lookback": [1, 2, 4, 8, 16, 24]}, {}, low_cost, mom_risk)))
    reg.export()

    lines = ["# Phase 3 — Pipeline Calibration", "",
             f"*Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `scripts/phase3_calibration.py`.*",
             "", "Does the promotion pipeline (docs/VALIDATION.md) reject luck and detect real effects? Each row runs "
             "the **full pipeline** — parameter search, cost screen, Deflated Sharpe, PBO, SPA, walk-forward, "
             "parameter plateau, year consistency and one validation look — on datasets where the truth is known.", "",
             "Synthetic bars are built from a continuous price path (`lab.validation.synthetic`). An earlier run "
             "used a flawed generator and is kept in the registry as `H-CAL-*` but is **invalid** (DECISIONS D-016).", "",
             "| Test | Setting | Truth | Datasets | Became CANDIDATE | Rate | Passed cost screen |",
             "|---|---|---|---|---|---|---|"]
    for grp, setting, truth, r in rows:
        lines.append(f"| {grp} | {setting} | {truth} | {r['n']} | {r['candidates']} | {r['rate']:.1%} | "
                     f"{r['screen_pass']} |")
    nulls = [r for g, *_, r in rows if g in "ABC"]
    tot_n = sum(r["n"] for r in nulls)
    tot_c = sum(r["candidates"] for r in nulls)
    lines += ["", f"**False-positive rate across all null tests: {tot_c}/{tot_n} = {tot_c / tot_n:.1%}** "
              "(the protocol requires this to be at or below the nominal 5%).", "",
              "## How to read this", "",
              "- *Null* rows contain no real edge by construction, so every CANDIDATE there is a false discovery.",
              "- *Power* rows contain a real momentum effect of strength φ (autocorrelation of hourly returns). "
              "Weak effects are expected to be missed: the pipeline is deliberately strict, trading missed "
              "opportunities for fewer false discoveries.",
              "- Synthetic tests use 20% of normal costs; real-data nulls use zero costs so that the statistics, "
              "not the costs, do the rejecting.", "",
              f"Total registry trials: {reg.trial_count()}."]
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
