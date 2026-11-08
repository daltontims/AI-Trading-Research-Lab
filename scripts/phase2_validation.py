"""Phase 2 completion checks on real data.

Runs engine demonstrations on BTC, ETH and SPY (development split only), cost stress
tests, an account-size study, real-data look-ahead checks and a random-entry calibration,
records everything in the research registry (stage="diagnostic") and writes
reports/phase2_engine_validation.md.

These are ENGINE DIAGNOSTICS with textbook rules, not research findings.

    uv run python scripts/phase2_validation.py
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np

from lab.engine import lookahead
from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import load
from lab.registry.db import Registry
from lab.research import run_experiment
from lab.strategies.examples import BollingerReversion, DonchianBreakout, RandomEntry, SmaCross

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "phase2_engine_validation.md"


def f(v, pct=False, d=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if isinstance(v, float) and math.isinf(v):
        return "∞"
    return f"{v:.{d}%}" if pct else (f"{v:,.{d}f}" if isinstance(v, float) else str(v))


def hyp(reg, key, title, question, instruments, tf, strategy):
    return reg.register_hypothesis(
        id=f"H-DEMO-{key}", family="engine_demo", title=title, question=question, source="manual",
        asset_classes=sorted({"equity" if s == "SPY" else "crypto" for s in instruments}), instruments=instruments,
        timeframe=tf, style=strategy.style, spec={"strategy": strategy.name, "params": strategy.params},
        rationale="Engine demonstration with a textbook rule; not a research hypothesis.", trial_budget=10)


def metrics_row(name, m):
    return (f"| {name} | {f(m['total_return'], True)} | {f(m['cagr'], True)} | {f(m['sharpe'])} | "
            f"{f(m['sortino'])} | {f(m['max_drawdown'], True)} | {m['trades']} | {f(m['win_rate'], True, 1)} | "
            f"{f(m['profit_factor'])} | {f(m['expectancy'])} | {f(m['exposure'], True, 0)} | "
            f"{f(m['cost_share_of_gross'], True, 0)} |")


HEADER = ("| Run | Net return | CAGR | Sharpe | Sortino | Max DD | Trades | Win rate | PF | Expectancy $ | "
          "Exposure | Costs/gross |\n|---|---|---|---|---|---|---|---|---|---|---|---|")


def main():
    reg = Registry()
    lines = ["# Phase 2 — Engine Validation Report", "",
             f"*Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `scripts/phase2_validation.py`.*",
             "", "**These are engine diagnostics using textbook rules on the development split only. They are "
             "not research findings and none of these strategies is a candidate.** Every run below is recorded "
             "in the research registry (family `engine_demo`, stage `diagnostic`).", ""]

    demos = [
        ("SPY-SMA", "SPY 50/200-day moving-average trend (long only, no stop)", ["SPY"], "1d",
         SmaCross(fast=50, slow=200, stop_atr=0), RiskConfig(sizing="pct_equity", position_pct=1.0),
         ExecutionConfig(), False),
        ("BTC-DONCHIAN", "BTC 1h 55-bar breakout, perpetual, long/short", ["BTCUSDT"], "1h",
         DonchianBreakout(n=55), RiskConfig(sizing="risk", risk_per_trade=0.01),
         ExecutionConfig(cost_profile="crypto_perp"), True),
        ("ETH-BOLL", "ETH 15m Bollinger mean reversion, perpetual, long/short", ["ETHUSDT"], "15m",
         BollingerReversion(n=20, k=2.5), RiskConfig(sizing="risk", risk_per_trade=0.005, max_bars_held=96),
         ExecutionConfig(cost_profile="crypto_perp"), True),
    ]
    lines += ["## 1. Sample backtests (after all costs)", "", HEADER]
    detail = []
    stress_rows = []
    for key, title, syms, tf, strat, risk, ex, funding in demos:
        hid = hyp(reg, key, title, "Does the engine produce sensible, fully-costed results?", syms, tf, strat)
        t0 = time.time()
        res, eid = run_experiment(strat, syms, tf, hypothesis_id=hid, stage="diagnostic", risk=risk, execution=ex,
                                  funding=funding, registry=reg, cost_multipliers=(1.0, 1.5, 2.0, 3.0),
                                  notes="Phase 2 engine demonstration", export=False)
        secs = time.time() - t0
        m = res.metrics
        lines.append(metrics_row(f"{title} (`{eid}`)", m))
        lines_b = (f"| Buy & hold {','.join(syms)} | {f(m['benchmark_total_return'], True)} | "
                   f"{f(m['benchmark_cagr'], True)} | {f(m['benchmark_sharpe'])} | – | "
                   f"{f(m['benchmark_max_drawdown'], True)} | – | – | – | – | 100% | – |")
        lines.append(lines_b)
        trials = reg.query("SELECT cost_multiplier, net_return, sharpe, profit_factor, max_drawdown, n_trades "
                           "FROM trials WHERE experiment_id=? ORDER BY cost_multiplier", (eid,))
        for t in trials:
            stress_rows.append(f"| {title} | ×{t['cost_multiplier']:.1f} | {f(t['net_return'], True)} | "
                               f"{f(t['sharpe'])} | {f(t['profit_factor'])} | {f(t['max_drawdown'], True)} |")
        reasons = res.trades.group_by("exit_reason").len().sort("len", descending=True)
        detail += [f"### {title}", "",
                   f"- Data: {res.data['start'][:10]} → {res.data['end'][:10]}, {res.data['bars']:,} bars "
                   f"({tf}), split `{res.data['split']}`; run time {secs:.1f}s for 4 cost levels.",
                   f"- Cost profile: `{res.cost_models[syms[0]]['profile']}` — fee {res.cost_models[syms[0]]['fee_bps']} bps/side, "
                   f"half-spread {res.cost_models[syms[0]]['half_spread_bps']} bps, slippage "
                   f"{res.cost_models[syms[0]]['slippage_bps']} bps + {res.cost_models[syms[0]]['slippage_range_frac']}×bar range.",
                   f"- Costs paid: fees ${m['total_fees']:,.0f}, spread+slippage ${m['total_spread_slippage']:,.0f}, "
                   f"carry (funding/borrow/dividends) ${m['total_carry']:,.0f}; gross P&L before costs ${m['pnl_gross']:,.0f}.",
                   f"- Avg win ${f(m['avg_win'])}, avg loss ${f(m['avg_loss'])}, payoff {f(m['payoff_ratio'])}, "
                   f"expectancy {f(m['expectancy_r'])} R, avg holding {f(m['avg_holding_hours'], d=1)} h, "
                   f"max consecutive wins/losses {m['max_consecutive_wins']}/{m['max_consecutive_losses']}, "
                   f"turnover {f(m['turnover'], d=1)}×/yr, Calmar {f(m['calmar'])}.",
                   "- Exit reasons: " + ", ".join(f"{r['exit_reason']} {r['len']}" for r in reasons.iter_rows(named=True)),
                   "- Regimes (trend / volatility of the traded instrument, lagged): " + "; ".join(
                       f"{r['dimension']}={r['regime']}: {r['compounded_return']:+.1%} over {r['days']} d"
                       for r in res.regimes.iter_rows(named=True)),
                   "- Warnings: " + (" ".join(res.warnings) if res.warnings else "none"), ""]
        # Real-data engine causality check (shorter window for speed)
        sub = load(syms, tf, "development", funding=funding)
        sub = sub.head(min(sub.n_bars, 6000))
        rep = lookahead.check_engine(strat, sub, lambda s, d: run_backtest(s, d, risk, ex))
        reg.add_stat_test(eid, "lookahead_engine_causality_real_data", passed=rep.passed,
                          details={"failures": rep.failures})
        detail.append(f"- Engine causality check on real data: {'PASSED' if rep.passed else 'FAILED ' + str(rep.failures)}")
        detail.append("")

    lines += ["", "## 2. Cost stress tests", "",
              "Each strategy re-run with spread, slippage, fees and borrow multiplied. A strategy whose result "
              "flips sign between ×1 and ×2 is *fragile*.", "",
              "| Run | Costs | Net return | Sharpe | PF | Max DD |", "|---|---|---|---|---|---|", *stress_rows, ""]
    lines += ["## 3. Details", "", *detail]

    # Account size study (SPY): lot rounding matters for small accounts.
    lines += ["## 4. Account size sensitivity (SPY 50/200, whole shares)", "",
              "| Starting balance | Net return | Max DD | Trades |", "|---|---|---|---|"]
    hid = reg.hypothesis("H-DEMO-SPY-SMA")["id"]
    for cash in (1000, 5000, 25000, 100000):
        res, _ = run_experiment(SmaCross(fast=50, slow=200, stop_atr=0), "SPY", "1d", hypothesis_id=hid, stage="diagnostic",
                                risk=RiskConfig(initial_cash=cash, sizing="pct_equity"), registry=reg,
                                check_lookahead=False, notes=f"account size {cash}", export=False)
        m = res.metrics
        lines.append(f"| ${cash:,} | {f(m['total_return'], True)} | {f(m['max_drawdown'], True)} | {m['trades']} |")
    lines += ["", "Small accounts hold more idle cash because only whole shares are bought.", ""]

    # Random-entry calibration on real BTC 1-minute data.
    lines += ["## 5. Random-entry calibration on real data (BTC 1-minute, development split)", ""]
    data = load("BTCUSDT", "1m", "development", funding=True)
    hid = reg.register_hypothesis(id="H-CALIB-RANDOM-BTC1M", family="calibration", title="Random entries, BTC 1m",
                                  question="Do random entries look profitable after costs? (must not)",
                                  source="manual", asset_classes=["crypto"], instruments=["BTCUSDT"], timeframe="1m",
                                  style="calibration", spec={"strategy": "random_entry", "seeds": 30},
                                  rationale="Pipeline calibration.", trial_budget=200)
    rets = {"crypto_perp": [], "crypto_spot": [], "crypto_perp, costs ×0": []}
    timings = []
    for prof in rets:
        for seed in range(30):
            venue = prof.split(",")[0]
            strat = RandomEntry(seed=seed, prob=0.002, allow_short=(venue == "crypto_perp"))
            mult = 0.0 if "×0" in prof else 1.0
            t0 = time.time()
            res, _ = run_experiment(strat, "BTCUSDT", "1m", hypothesis_id=hid, stage="diagnostic", data=data,
                                    risk=RiskConfig(sizing="risk", risk_per_trade=0.005, max_bars_held=60),
                                    execution=ExecutionConfig(cost_profile=venue, cost_multiplier=mult),
                                    registry=reg, check_lookahead=(seed == 0), export=False, seed=seed)
            timings.append(time.time() - t0)
            rets[prof].append((res.metrics["total_return"], res.metrics["trades"], res.metrics["sharpe"]))
    lines += ["30 seeds per venue; entries with 0.2% probability per minute, stop and target at 2×ATR, "
              "max 60 minutes holding, 0.5% risk per trade.", "",
              "| Venue profile | Mean net return | Median | Profitable seeds | Mean trades | Mean Sharpe |",
              "|---|---|---|---|---|---|"]
    for prof, rows in rets.items():
        r = np.array([x[0] for x in rows])
        lines.append(f"| `{prof}` | {r.mean():.1%} | {np.median(r):.1%} | {(r > 0).sum()}/30 | "
                     f"{np.mean([x[1] for x in rows]):,.0f} | {np.mean([x[2] for x in rows]):.2f} |")
    z = np.array([x[0] for x in rets["crypto_perp, costs ×0"]])
    tstat = z.mean() / (z.std(ddof=1) / np.sqrt(len(z)))
    lines += ["", "With realistic costs every seed should lose: costs are paid on every trade and random entries "
              "have no edge. The stronger test is the **zero-cost** row: random long/short entries should average "
              f"close to zero if the engine has no built-in bias. Observed t-statistic of the mean: **{tstat:.2f}** "
              f"({'consistent with zero' if abs(tstat) < 2.5 else 'INVESTIGATE: possible bias'}).", ""]
    lines += ["## 6. Speed", "",
              f"One BTC 1-minute backtest over {data.n_bars:,} bars (signals + simulation + metrics + registry write): "
              f"median {np.median(timings):.2f} s. Signals are computed once per strategy and reused across cost "
              "levels.", ""]

    total = reg.trial_count()
    lines += ["## 7. Registry", "", f"Total trials recorded so far: **{total}**.", ""]
    reg.export()
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
