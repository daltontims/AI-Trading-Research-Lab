"""Phase 4 candidate review: extra scrutiny for anything that passed, and corrected diagnostics.

1. Recomputes the trade-order Monte Carlo on every strategy card (D-019: the first version
   resampled dollar P&L, which is wrong for compounding strategies).
2. For candidates: cross-market replication with the SAME rules (development split only, recorded
   as robustness trials), Deflated Sharpe recomputed with the final family trial count, comparison
   with buy-and-hold in validation.

    uv run python scripts/phase4_review.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

import phase4_batch as B
from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import load
from lab.registry.db import Registry
from lab.research import run_experiment
from lab.validation import stats
from lab.validation.evaluate import daily_returns, param_grid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "phase4_candidate_review.md"
CROSS = {"H4-02": ["ETHUSDT", "SOLUSDT"], "H4-17": ["QQQ", "IWM", "DIA", "XLK", "XLF", "XLI"]}


def pct(v):
    return "–" if v is None or not np.isfinite(v) else f"{v:.1%}"


def main():
    reg = Registry()
    hyps = {h.id: h for h in B.BATCH}
    lines = ["# Phase 4 — Candidate Review", "",
             "Extra scrutiny for hypotheses that passed every gate. Cross-market runs use the exact same rules "
             "and parameters on the development split and are recorded as robustness trials.", ""]
    for hid, h in hyps.items():
        js = json.loads((B.EXP_DIR / f"{hid}.json").read_text())
        params = {**h.fixed, **js["best_params"]}
        dev = load(h.symbols, h.timeframe, "development", funding=h.funding)
        ex = ExecutionConfig(cost_profile=h.profile)
        res = run_backtest(h.strategy(**params), dev, RiskConfig(**h.risk), ex)
        mc = stats.trade_monte_carlo(stats.trade_returns(res.trades, res.equity), 5000.0)
        card = ROOT / js["report"]
        if card.exists() and mc:
            txt = card.read_text()
            txt = re.sub(r"- Trade-order Monte Carlo:.*\n",
                         f"- Trade-order Monte Carlo (per-trade returns, compounded): 95th-percentile drawdown "
                         f"{pct(mc['max_dd_p95'])}, probability of loss {pct(mc['prob_loss'])}, probability of "
                         f"halving the account {pct(mc['prob_ruin_50pct'])}\n", txt)
            card.write_text(txt)
        js["trade_monte_carlo"] = mc
        if js["verdict"] != "CANDIDATE":
            (B.EXP_DIR / f"{hid}.json").write_text(json.dumps(js, indent=2, default=str) + "\n")
            continue

        # ---- candidate scrutiny
        hyp = reg.hypothesis(hid)
        grid = [{**h.fixed, **g} for g in param_grid(h.space)]
        cols = [daily_returns(run_backtest(h.strategy(**g), dev, RiskConfig(**h.risk), ex))[1] for g in grid]
        M = np.column_stack(cols)
        srs = np.array([stats.sharpe_per_period(M[:, j]) for j in range(M.shape[1])])
        best = int(np.argmax(srs))
        cross = {}
        for s in CROSS.get(hid, []):
            r, eid = run_experiment(h.strategy(**params), [s], h.timeframe, hypothesis_id=hid, stage="robustness",
                                    risk=RiskConfig(**h.risk), execution=ExecutionConfig(cost_profile=h.profile),
                                    funding=h.funding, registry=reg, export=False,
                                    notes="Phase 4 review: cross-market replication with identical rules")
            cross[s] = r.metrics
        n_family = reg.trial_count(family=hyp["family"])
        dsr_final = stats.deflated_sharpe(M[:, best], n_family, float(np.var(srs, ddof=1)) if len(srs) > 2 else None)
        d, v = js["dev"], js["val"]
        lines += [f"## {hid} — {h.title}", "",
                  f"Rules: `{h.strategy.__name__}` with `{json.dumps(params)}`; {', '.join(h.symbols)} {h.timeframe}.", "",
                  "| | Development | Validation |", "|---|---|---|",
                  f"| Strategy net return | {pct(d['total_return'])} | {pct(v['total_return'])} |",
                  f"| Buy & hold | {pct(d['benchmark_total_return'])} | {pct(v['benchmark_total_return'])} |",
                  f"| Strategy Sharpe / buy & hold Sharpe | {d['sharpe']:.2f} / {d['benchmark_sharpe']:.2f} | "
                  f"{v['sharpe']:.2f} / {v['benchmark_sharpe']:.2f} |",
                  f"| Strategy max DD / buy & hold max DD | {pct(d['max_drawdown'])} / {pct(d['benchmark_max_drawdown'])} | "
                  f"{pct(v['max_drawdown'])} / {pct(v['benchmark_max_drawdown'])} |",
                  f"| Exposure (time in market) | {pct(d['exposure'])} | {pct(v['exposure'])} |",
                  f"| Trades | {d['trades']} | {v['trades']} |", "",
                  f"- Deflated Sharpe at evaluation: {js['dsr']:.3f} ({js['family_trials']} family trials); "
                  f"recomputed with all {n_family} trials now in family `{hyp['family']}`: **{dsr_final['dsr']:.3f}**.",
                  f"- Trade-order Monte Carlo: 95th-percentile drawdown {pct(mc['max_dd_p95'])}, "
                  f"probability of halving the account {pct(mc['prob_ruin_50pct'])}."]
        if js.get("extra", {}).get("us_retail_costs"):
            lines.append(f"- At US-retail crypto costs (≈40 bps/side): "
                         f"{pct(js['extra']['us_retail_costs']['total_return'])} on development data.")
        lines += ["", "Cross-market replication (same rules, development split):", "",
                  "| Market | Net return | Sharpe | Max DD | Trades | Buy & hold |", "|---|---|---|---|---|---|"]
        for s, m in cross.items():
            lines.append(f"| {s} | {pct(m['total_return'])} | {m['sharpe']:.2f} | {pct(m['max_drawdown'])} | "
                         f"{m['trades']} | {pct(m['benchmark_total_return'])} |")
        rep = sum(m["total_return"] > 0 and m["sharpe"] > 0 for m in cross.values())
        lines += ["", f"Replicated (profitable with positive Sharpe) on **{rep}/{len(cross)}** other markets.", ""]
        js["review"] = {"dsr_final": dsr_final["dsr"], "family_trials_final": n_family,
                        "cross_market": {s: {"total_return": m["total_return"], "sharpe": m["sharpe"],
                                             "trades": m["trades"]} for s, m in cross.items()},
                        "replicated": f"{rep}/{len(cross)}"}
        (B.EXP_DIR / f"{hid}.json").write_text(json.dumps(js, indent=2, default=str) + "\n")
    reg.export()
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
