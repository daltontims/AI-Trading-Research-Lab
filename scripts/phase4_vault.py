"""Final vault test for the Phase 4 candidates (settings fixed in DECISIONS D-021).

    uv run python scripts/phase4_vault.py
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import phase4_batch as B
from lab.engine.backtest import ExecutionConfig, RiskConfig
from lab.registry.db import Registry
from lab.research import run_experiment
from lab.validation.evaluate import vault_test

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "phase4_vault.md"
SETTINGS = {"H4-17": {"cash_interest": True}, "H4-02": {"cash_interest": False}}


def pct(v):
    return "–" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:.1%}"


def num(v, d=2):
    return "–" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:.{d}f}"


def main():
    reg = Registry()
    hyps = {h.id: h for h in B.BATCH}
    lines = ["# Phase 4 — Vault (final) test", "",
             f"*Run {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Settings fixed beforehand in "
             "docs/DECISIONS.md D-021. Each candidate's frozen rules were run once on data never used before "
             "(the vault). The outcome is final.*", ""]
    for hid, extra in SETTINGS.items():
        h = hyps[hid]
        js = json.loads((B.EXP_DIR / f"{hid}.json").read_text())
        params = {**h.fixed, **js["best_params"]}
        risk = RiskConfig(**h.risk, **extra)
        ex = ExecutionConfig(cost_profile=h.profile)
        dev_note = ""
        if extra.get("cash_interest"):
            r, _ = run_experiment(h.strategy(**params), h.symbols, h.timeframe, hypothesis_id=hid,
                                  stage="robustness", risk=risk, execution=ex, funding=h.funding, registry=reg,
                                  export=False, notes="development re-run with cash interest (diagnostic)")
            dev_note = (f"Development re-run with cash interest (diagnostic): {pct(r.metrics['total_return'])} "
                        f"(was {pct(js['dev']['total_return'])} without), CAGR {pct(r.metrics['cagr'])}, Sharpe "
                        f"{num(r.metrics['sharpe'])}, interest earned ${r.metrics['total_interest']:,.0f}.")
        out = vault_test(h.strategy, params, h.symbols, h.timeframe, hypothesis_id=hid, registry=reg, risk=risk,
                         execution=ex, funding=h.funding, notes="Phase 4 final vault test (D-021)")
        m = out["metrics"]
        v = js["val"]
        lines += [f"## {hid} — {h.title}: **{out['verdict']}**", "",
                  f"Vault period {out['period'][0]} → {out['period'][1]} (`{out['experiment']}`).", "",
                  "| Metric | Development | Validation | **Vault** |", "|---|---|---|---|",
                  f"| Net return | {pct(js['dev']['total_return'])} | {pct(v['total_return'])} | **{pct(m['total_return'])}** |",
                  f"| CAGR | {pct(js['dev']['cagr'])} | {pct(v['cagr'])} | {pct(m['cagr'])} |",
                  f"| Sharpe | {num(js['dev']['sharpe'])} | {num(v['sharpe'])} | {num(m['sharpe'])} |",
                  f"| Max drawdown | {pct(js['dev']['max_drawdown'])} | {pct(v['max_drawdown'])} | {pct(m['max_drawdown'])} |",
                  f"| Trades | {js['dev']['trades']} | {v['trades']} | {m['trades']} |",
                  f"| Win rate | {pct(js['dev']['win_rate'])} | {pct(v['win_rate'])} | {pct(m['win_rate'])} |",
                  f"| Profit factor | {num(js['dev']['profit_factor'])} | {num(v['profit_factor'])} | {num(m['profit_factor'])} |",
                  f"| Buy & hold return | {pct(js['dev']['benchmark_total_return'])} | {pct(v['benchmark_total_return'])} | "
                  f"{pct(m['benchmark_total_return'])} |",
                  f"| Buy & hold Sharpe | {num(js['dev']['benchmark_sharpe'])} | {num(v['benchmark_sharpe'])} | "
                  f"{num(m['benchmark_sharpe'])} |",
                  f"| Buy & hold max DD | {pct(js['dev']['benchmark_max_drawdown'])} | {pct(v['benchmark_max_drawdown'])} | "
                  f"{pct(m['benchmark_max_drawdown'])} |", "",
                  f"- Probability vault Sharpe > 0 (PSR): {num(out['psr'])}; at 2× costs: "
                  f"{pct(out['stress']['net_return']) if out['stress'] else '–'}.",
                  f"- Interest on idle cash: ${m.get('total_interest', 0):,.0f}." if extra.get("cash_interest") else
                  "- No interest on idle cash (crypto).",
                  *( [f"- {dev_note}"] if dev_note else []),
                  *( [f"- Failed: {r}" for r in out["reasons"]] ),
                  ""]
        js["vault"] = {"verdict": out["verdict"], "experiment": out["experiment"], "period": out["period"],
                       "psr": out["psr"], "reasons": out["reasons"],
                       "metrics": {k: m.get(k) for k in ("total_return", "cagr", "sharpe", "max_drawdown", "trades",
                                                         "win_rate", "profit_factor", "benchmark_total_return",
                                                         "benchmark_sharpe", "total_interest")}}
        (B.EXP_DIR / f"{hid}.json").write_text(json.dumps(js, indent=2, default=str) + "\n")
        card = ROOT / js["report"]
        txt = card.read_text().replace("— CANDIDATE", f"— {out['verdict']}", 1)
        txt += "\n## Vault (final) test\n\n" + "\n".join(lines[lines.index(f"## {hid} — {h.title}: **{out['verdict']}**") + 2:]) + "\n"
        card.write_text(txt)
        print(hid, out["verdict"], out["reasons"])
    reg.export()
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
