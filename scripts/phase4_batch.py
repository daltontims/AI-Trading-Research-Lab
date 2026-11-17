"""Phase 4: first research batch — hand-designed hypotheses across crypto and US ETFs.

    uv run python scripts/phase4_batch.py --register   # pre-register only (commit before running!)
    uv run python scripts/phase4_batch.py              # evaluate everything not yet evaluated

Each hypothesis is pre-registered with its question, rationale, rules (strategy + fixed params),
parameter grid, data and costs. Evaluation uses lab.validation.evaluate on the DEVELOPMENT split;
the validation split is opened once, only for ideas that pass every development gate. The vault
is never touched. Results: reports/phase4_research_batch.md, reports/strategies/<id>.md,
research/experiments/<id>.json, research/hypotheses/<id>.md.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import load
from lab.registry.db import Registry
from lab.strategies import phase4 as P
from lab.strategies.examples import DonchianBreakout, TimeSeriesMomentum
from lab.validation import stats
from lab.validation.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[1]
HYP_DIR = ROOT / "research" / "hypotheses"
EXP_DIR = ROOT / "research" / "experiments"
GRAVE = ROOT / "research" / "graveyard"
REPORT = ROOT / "reports" / "phase4_research_batch.md"

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU"]


@dataclass
class H:
    id: str
    title: str
    question: str
    rationale: str
    strategy: type
    space: dict
    symbols: list
    timeframe: str
    family: str = ""
    fixed: dict = field(default_factory=dict)
    profile: str | None = None
    funding: bool = False
    risk: dict = field(default_factory=lambda: {"sizing": "pct_equity", "position_pct": 1.0})


BATCH = [
    # ------------------------------------------------------------------ crypto
    H("H4-01", "BTC hourly time-series momentum",
      "Does the sign of BTC's return over the last 6–96 hours predict the next hours (long/short)?",
      "Crypto prices are said to trend because of slow information diffusion and retail herding; "
      "time-series momentum is documented across asset classes.",
      TimeSeriesMomentum, {"lookback": [6, 12, 24, 48, 96]}, ["BTCUSDT"], "1h", profile="crypto_perp", funding=True),
    H("H4-02", "BTC daily trend filter (long/flat)",
      "Does holding BTC only when it is above its 20–200 day average beat buy-and-hold on a risk-adjusted basis?",
      "Trend filters avoid the deepest drawdowns of trending assets; crypto has had long bear markets.",
      P.TrendFilter, {"n": [20, 50, 100, 200]}, ["BTCUSDT"], "1d", family="crypto-daily-trend", profile="crypto_spot"),
    H("H4-03", "ETH daily trend filter (long/flat)",
      "Same rule as H4-02 on ETH: does it replicate?",
      "Replication on a second major coin; shares H4-02's family so trials are counted together.",
      P.TrendFilter, {"n": [20, 50, 100, 200]}, ["ETHUSDT"], "1d", family="crypto-daily-trend", profile="crypto_spot"),
    H("H4-04", "BTC+ETH 4-hour channel breakout (long/short)",
      "Do breaks of the prior 20–100 bar high/low on 4h bars continue enough to pay for costs?",
      "Breakout systems profit from volatility expansion after consolidation if trends follow.",
      DonchianBreakout, {"n": [20, 55, 100]}, ["BTCUSDT", "ETHUSDT"], "4h", fixed={"trail_atr": 3.0},
      profile="crypto_perp", funding=True,
      risk={"sizing": "risk", "risk_per_trade": 0.01, "max_position_pct": 0.5}),
    H("H4-05", "BTC hourly overreaction reversal",
      "After an hourly move beyond 2.5–4 robust standard deviations, does BTC reverse over the next 6 hours?",
      "Liquidation cascades and stop runs can overshoot fair value, followed by partial reversal.",
      P.FadeExtremeMove, {"k": [2.5, 3.0, 4.0]}, ["BTCUSDT"], "1h", profile="crypto_perp", funding=True,
      risk={"sizing": "pct_equity", "position_pct": 1.0, "max_bars_held": 6}),
    H("H4-06", "BTC funding-rate contrarian carry",
      "When perpetual funding is very high (crowded longs), does shorting earn funding plus a price reversal?",
      "High funding means leveraged longs pay shorts; crowded positioning may unwind.",
      P.FundingContrarian, {"threshold": [0.0003, 0.0005, 0.001]}, ["BTCUSDT"], "1h",
      fixed={"exit_threshold": 0.0001}, profile="crypto_perp", funding=True),
    H("H4-07", "BTC time-of-day session effect",
      "Is BTC's return concentrated in one trading session (Asia 00–08, Europe 07–13, US 13–21 UTC)?",
      "Regional participation differs by hour; some studies report intraday seasonality in crypto.",
      P.SessionWindow, {"session": ["asia", "europe", "us"]}, ["BTCUSDT"], "1h", profile="crypto_spot"),
    H("H4-08", "BTC weekend drift (long)",
      "Does holding BTC only over weekends (Sat–Sun UTC) earn positive returns after costs?",
      "Weekend liquidity is thinner and retail-dominated; a weekend premium has been suggested.",
      P.WeekendHold, {}, ["BTCUSDT"], "1h", fixed={"side": "long"}, profile="crypto_spot"),
    H("H4-09", "BTC daily volatility breakout (intraday)",
      "Does a move of k×(yesterday's range) away from today's open continue until the end of the UTC day?",
      "Classic volatility-breakout logic: range expansion early in a day signals directional flow.",
      P.DailyRangeBreakout, {"k": [0.3, 0.5, 0.7]}, ["BTCUSDT"], "1h", profile="crypto_perp", funding=True),
    H("H4-10", "BTC 15-minute volume-shock continuation",
      "Does a large 15-minute move on abnormal volume continue for the next hour?",
      "Volume spikes reveal informed or forced flow that may not be fully absorbed in one bar.",
      P.VolumeShock, {"vol_z": [2.5, 3.0, 4.0]}, ["BTCUSDT"], "15m", fixed={"ret_z": 2.0},
      profile="crypto_perp", funding=True, risk={"sizing": "pct_equity", "position_pct": 1.0, "max_bars_held": 4}),
    H("H4-11", "ETH follows BTC (lead-lag)",
      "When BTC outperforms ETH in an hour by an unusual margin, does ETH catch up in the next hour?",
      "BTC is the most liquid crypto market; price discovery may start there and spread to ETH.",
      P.LeadLag, {"z": [1.5, 2.0, 3.0]}, ["BTCUSDT", "ETHUSDT"], "1h", profile="crypto_perp", funding=True,
      risk={"sizing": "pct_equity", "position_pct": 1.0, "max_bars_held": 1}),
    H("H4-12", "ETH/BTC ratio mean reversion (pairs)",
      "Does the ETH/BTC price ratio revert to its 4-hour moving mean after a 2σ deviation?",
      "The two largest coins share drivers; temporary divergences may revert (statistical arbitrage).",
      P.PairReversion, {"n": [60, 120, 240]}, ["ETHUSDT", "BTCUSDT"], "4h", fixed={"entry_z": 2.0, "exit_z": 0.5},
      profile="crypto_perp", funding=True, risk={"sizing": "pct_equity", "position_pct": 0.5}),
    H("H4-13", "BTC daily time-series momentum (long/short)",
      "Does the sign of BTC's 7–60 day return predict the next days, long and short?",
      "Daily-horizon momentum is the most documented form of trend following.",
      TimeSeriesMomentum, {"lookback": [7, 14, 30, 60]}, ["BTCUSDT"], "1d", profile="crypto_perp", funding=True),
    # ------------------------------------------------------------------ US ETFs (daily)
    H("H4-14", "SPY trend filter (long/flat)",
      "Does holding SPY only above its 50–250 day average beat buy-and-hold risk-adjusted?",
      "Avoiding long bear markets; one of the most cited timing rules.",
      P.TrendFilter, {"n": [50, 100, 150, 200, 250]}, ["SPY"], "1d"),
    H("H4-15", "Sector ETF momentum rotation",
      "Does holding the 3 sector ETFs with the best 3–12 month returns (skipping the last month) beat equal weight?",
      "Industry momentum is one of the strongest documented cross-sectional effects.",
      P.SectorMomentum, {"lookback": [63, 126, 252]}, SECTORS, "1d", fixed={"skip": 21, "top": 3},
      risk={"sizing": "pct_equity", "position_pct": 0.33}),
    H("H4-16", "Dual momentum SPY/TLT/GLD",
      "Does holding the best of stocks, bonds and gold by trailing return (cash if all negative) improve risk-adjusted returns?",
      "Combines relative and absolute momentum across asset classes.",
      P.DualMomentum, {"lookback": [63, 126, 252]}, ["SPY", "TLT", "GLD"], "1d"),
    H("H4-17", "SPY 2-day RSI pullback",
      "Does buying SPY after an oversold 2-day RSI (in an uptrend) produce short-term gains?",
      "Short-term overreaction in index ETFs; widely published, possibly arbitraged away.",
      P.RsiReversion, {"entry_rsi": [5.0, 10.0, 15.0]}, ["SPY"], "1d", fixed={"exit_rsi": 70.0, "trend_n": 200}),
    H("H4-18", "SPY turn-of-the-month",
      "Does SPY earn most of its return from the last trading day of a month to the first 2–4 days of the next?",
      "Month-end pension and payroll flows; one of the oldest calendar anomalies.",
      P.TurnOfMonth, {"days_after": [2, 3, 4]}, ["SPY"], "1d"),
    H("H4-19", "SPY with VIX term-structure filter",
      "Does holding SPY only when VIX is below VIX3M (calm, upward-sloping term structure) improve risk-adjusted returns?",
      "An inverted volatility curve signals acute stress, when equity returns are poor and volatile.",
      P.VixTermStructure, {"ratio": [0.9, 0.95, 1.0]}, ["SPY"], "1d"),
    H("H4-20", "Buy SPY after VIX spikes",
      "After VIX jumps 20–50% above its 10-day average, does SPY rise over the next 10 days?",
      "Fear spikes may overshoot; volatility risk premia reward providing liquidity in panics.",
      P.VixSpike, {"spike": [1.2, 1.3, 1.5]}, ["SPY"], "1d", fixed={"n": 10},
      risk={"sizing": "pct_equity", "position_pct": 1.0, "max_bars_held": 10}),
    H("H4-21", "SPY low-volatility regime",
      "Does holding SPY only when realized volatility is below its one-year median improve risk-adjusted returns?",
      "Volatility clusters; high-volatility regimes have historically had worse risk-adjusted equity returns.",
      P.LowVolTrend, {"vol_n": [10, 20, 40]}, ["SPY"], "1d", fixed={"median_n": 252}),
]


def register(reg: Registry) -> None:
    HYP_DIR.mkdir(parents=True, exist_ok=True)
    for h in BATCH:
        from lab import instruments
        reg.register_hypothesis(
            id=h.id, family=h.family or h.id, title=h.title, question=h.question, rationale=h.rationale,
            source="manual", asset_classes=sorted({instruments.get(s).asset_class for s in h.symbols}),
            instruments=h.symbols, timeframe=h.timeframe, style=h.strategy.style,
            spec={"strategy": h.strategy.name, "strategy_version": h.strategy().strategy_version, "fixed": h.fixed,
                  "profile": h.profile, "funding": h.funding, "risk": h.risk},
            param_space=h.space, trial_budget=max(1, math.prod(len(v) for v in h.space.values())))
        card = [f"# {h.id} — {h.title}", "", f"*Pre-registered {time.strftime('%Y-%m-%d')} before any test was run.*",
                "", f"**Question.** {h.question}", "", f"**Rationale.** {h.rationale}", "",
                f"**Rules.** `{h.strategy.__module__}.{h.strategy.__name__}` — {(h.strategy.__doc__ or '').strip()}",
                f"Fixed parameters: `{json.dumps(h.fixed)}`. Parameter grid: `{json.dumps(h.space)}`.", "",
                f"**Data.** {', '.join(h.symbols)}, {h.timeframe} bars, development split only for the search.",
                f"**Costs.** profile `{h.profile or 'default'}`{', with funding' if h.funding else ''}. "
                f"**Sizing/risk.** `{json.dumps(h.risk)}`; $5,000 start, no leverage.", "",
                "**Success criteria.** All gates in configs/protocol.yaml (screen at 2× costs, Deflated Sharpe ≥ 0.95, "
                "PBO ≤ 0.2, SPA p ≤ 0.05, walk-forward, parameter plateau, yearly consistency), then one validation look."]
        (HYP_DIR / f"{h.id}.md").write_text("\n".join(card) + "\n")
    reg.export()


def run(reg: Registry) -> None:
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    cache = {}
    for h in BATCH:
        out = EXP_DIR / f"{h.id}.json"
        if reg.hypothesis(h.id)["status"] != "IDEA" and out.exists():
            print(f"{h.id}: already evaluated ({reg.hypothesis(h.id)['status']})")
            continue
        key = (tuple(h.symbols), h.timeframe, h.funding)
        if key not in cache:
            cache[key] = load(h.symbols, h.timeframe, "development", funding=h.funding)
        t0 = time.time()
        ev = evaluate(h.strategy, h.space, h.symbols, h.timeframe, hypothesis_id=h.id, registry=reg,
                      dev_data=cache[key], fixed_params=h.fixed, execution=ExecutionConfig(cost_profile=h.profile),
                      funding=h.funding, risk=RiskConfig(**h.risk), export=False, n_boot=500,
                      notes="Phase 4 batch")
        extra = {}
        if ev.verdict in ("CANDIDATE", "SCREENED") and h.profile and h.profile.startswith("crypto"):
            # Robustness: the same rules at US-retail crypto costs (DECISIONS D-010).
            # US-accessible crypto venues: ~40 bps fees; shorting assumed available via regulated futures.
            us = run_backtest(h.strategy(**{**h.fixed, **ev.best_params}), cache[key], RiskConfig(**h.risk),
                              ExecutionConfig(cost_profile="crypto_spot_us_retail",
                                              cost_overrides={"allow_short": True, "funding": h.funding}))
            reg.add_trial(ev.experiments[0], {**ev.best_params, "_profile": "us_retail_costs"}, us.metrics)
            extra["us_retail_costs"] = {"total_return": us.metrics["total_return"], "sharpe": us.metrics["sharpe"]}
        spa_p = ev.diagnostics.get("spa", {}).get("spa_p_value")
        summary = {"id": h.id, "title": h.title, "verdict": ev.verdict, "confidence": ev.confidence,
                   "best_params": ev.best_params, "reasons": ev.reasons, "grid_size": ev.grid_size,
                   "family_trials": ev.family_trials, "experiments": ev.experiments, "spa_p": spa_p,
                   "dsr": ev.diagnostics["deflated_sharpe"]["dsr"], "dev": _slim(ev.dev_metrics),
                   "val": _slim(ev.val_metrics) if ev.val_metrics else None,
                   "walk_forward": {k: v for k, v in ev.diagnostics.get("walk_forward", {}).items() if k != "chosen"},
                   "pbo": ev.diagnostics.get("pbo", {}).get("pbo"), "extra": extra, "warnings": ev.warnings,
                   "report": str(Path(ev.report_path).relative_to(ROOT)), "seconds": round(time.time() - t0, 1)}
        out.write_text(json.dumps(summary, indent=2, default=_jsonable) + "\n")
        print(f"{h.id}: {ev.verdict} ({summary['seconds']}s) {ev.reasons[:2]}")
        reg.export()
    write_report(reg)


def _jsonable(x):
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    return str(x)


def _slim(m: dict) -> dict:
    keys = ["trades", "win_rate", "profit_factor", "expectancy", "expectancy_r", "total_return", "cagr", "sharpe",
            "sortino", "calmar", "max_drawdown", "exposure", "avg_holding_hours", "cost_share_of_gross",
            "benchmark_total_return", "benchmark_sharpe", "benchmark_max_drawdown", "years"]
    return {k: (None if isinstance(m.get(k), float) and not math.isfinite(m[k]) else m.get(k)) for k in keys}


def _p(v, pct=True, d=1):
    if v is None:
        return "–"
    return f"{v:.{d}%}" if pct else f"{v:.{d}f}"


def write_report(reg: Registry) -> None:
    rows = [json.loads((EXP_DIR / f"{h.id}.json").read_text()) for h in BATCH if (EXP_DIR / f"{h.id}.json").exists()]
    spa = [r["spa_p"] if r["spa_p"] is not None else 1.0 for r in rows]
    q = stats.bh_adjusted(spa) if rows else []
    order = {"CANDIDATE": 0, "SCREENED": 1, "REJECTED": 2}
    rows_sorted = sorted(zip(rows, q), key=lambda x: (order[x[0]["verdict"]], -(x[0]["dev"]["sharpe"] or -9)))
    n_c = sum(r["verdict"] == "CANDIDATE" for r in rows)
    n_s = sum(r["verdict"] == "SCREENED" for r in rows)
    lines = ["# Phase 4 — First Research Batch", "",
             f"*Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `scripts/phase4_batch.py`. "
             f"{len(rows)} pre-registered hypotheses (research/hypotheses/), development split "
             "(crypto 2019–2023, ETFs 1993–2017); validation opened only for ideas passing every development gate. "
             "Vault untouched.*", "",
             f"**Outcome: {n_c} candidate(s), {n_s} screened, {len(rows) - n_c - n_s} rejected.** "
             "A *candidate* is promising, not validated: it still needs the vault test, tick-level checks where "
             "relevant, and paper trading. Nothing here is a proven edge.", "",
             "## Leaderboard", "",
             "| ID | Hypothesis | Verdict | Dev net return | Dev Sharpe | Max DD | Trades | PF | Buy & hold | "
             "Deflated Sharpe | Batch FDR q | Validation return | Main reason |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r, qq in rows_sorted:
        d, v = r["dev"], r["val"]
        reason = r["reasons"][0].split(" (")[0] if r["reasons"] else "all gates passed"
        lines.append(f"| [{r['id']}]({r['report'].removeprefix('reports/')}) | "
                     f"{r['title']} | **{r['verdict']}** | {_p(d['total_return'])} | {_p(d['sharpe'], False, 2)} | "
                     f"{_p(d['max_drawdown'])} | {d['trades']} | {_p(d['profit_factor'], False, 2)} | "
                     f"{_p(d['benchmark_total_return'])} | {_p(r['dsr'], False, 2)} | {qq:.2f} | "
                     f"{_p(v['total_return']) if v else 'not opened'} | {reason} |")
    lines += ["", "*Batch FDR q*: Benjamini–Hochberg adjusted SPA p-values across this batch — the chance that a "
              "result this good is a false discovery given that all of these ideas were tested.", "",
              "## What failed most often", ""]
    from collections import Counter
    cnt = Counter(reason.split(":")[0] for r in rows for reason in r["reasons"] if reason)
    lines += [f"- `{k}`: {v} hypotheses" for k, v in cnt.most_common()]
    lines += ["", "## Notes per hypothesis", ""]
    for r, _ in rows_sorted:
        wf = r.get("walk_forward") or {}
        extra = r.get("extra", {}).get("us_retail_costs")
        lines.append(f"- **{r['id']} {r['title']}** — {r['verdict']}; best `{json.dumps(r['best_params'])}` of "
                     f"{r['grid_size']}; walk-forward OOS Sharpe {_p(wf.get('oos_sharpe'), False, 2)}, "
                     f"{_p(wf.get('fraction_positive'))} windows positive; PBO {_p(r['pbo'], False, 2)}; "
                     f"avg holding {_p(r['dev']['avg_holding_hours'], False, 1)} h"
                     + (f"; at US-retail crypto costs: {_p(extra['total_return'])}" if extra else "")
                     + (f". Failed: {'; '.join(x.split(' (')[0] for x in r['reasons'][:4])}" if r["reasons"] else ""))
    lines += ["", f"Registry trials so far: {reg.trial_count()}."]
    REPORT.write_text("\n".join(lines) + "\n")
    GRAVE.mkdir(parents=True, exist_ok=True)
    g = ["# Graveyard", "", "Rejected hypotheses and why. Failures are data: they stop us re-testing dead ideas "
         "and they count towards multiple-testing corrections.", "", "| ID | Hypothesis | Failed gates |", "|---|---|---|"]
    for r in rows:
        if r["verdict"] == "REJECTED":
            g.append(f"| {r['id']} | {r['title']} | {'; '.join(x.split(' (')[0] for x in r['reasons'])} |")
    (GRAVE / "README.md").write_text("\n".join(g) + "\n")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true", help="pre-register only")
    args = ap.parse_args()
    reg = Registry()
    register(reg)
    if not args.register:
        run(reg)
