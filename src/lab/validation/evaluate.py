"""The promotion pipeline: development screen -> statistical validation -> one validation look.

    ev = evaluate(DonchianBreakout, {"n": [20, 55, 100], "trail_atr": [2, 3, 4]}, ["BTCUSDT"], "1h",
                  hypothesis_id=hid, execution=ExecutionConfig(cost_profile="crypto_perp"), funding=True)
    print(ev.verdict, ev.reasons)

Stages (docs/RESEARCH_PROTOCOL.md §7):
  1. SCREEN (development, after costs): enough trades, profitable, still profitable at 2× costs.
  2. STATISTICAL (development): Deflated Sharpe vs all trials in the hypothesis family, PBO,
     Hansen SPA, walk-forward, parameter plateau, year consistency. Diagnostics: bootstrap Sharpe
     interval, trade-order Monte Carlo, delay sensitivity, cross-market replication.
  3. VALIDATION (one look per hypothesis): the chosen parameters on unseen validation data.
Outcome: REJECTED (with reasons), SCREENED (passed 1 only) or CANDIDATE (passed 1–3).
The vault is never touched here. Every backtest is a recorded trial; every gate a stat_test.
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from lab.engine import lookahead
from lab.engine import metrics as M
from lab.engine.backtest import BacktestResult, ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import MarketData, load
from lab.registry.db import Registry
from lab.validation import cv, stats

CONFIG = Path(__file__).resolve().parents[3] / "configs" / "protocol.yaml"
REPORT_DIR = Path(__file__).resolve().parents[3] / "reports" / "strategies"


def protocol() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def param_grid(space: dict[str, list]) -> list[dict]:
    keys = list(space)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(space[k] for k in keys))]


@dataclass
class Gate:
    name: str
    passed: bool | None          # None = not applicable / informational
    value: object = None
    threshold: object = None
    note: str = ""


@dataclass
class Evaluation:
    hypothesis_id: str
    verdict: str                 # REJECTED | SCREENED | CANDIDATE
    reasons: list[str]
    best_params: dict
    gates: list[Gate]
    dev_metrics: dict
    val_metrics: dict | None
    diagnostics: dict
    experiments: list[str]
    confidence: str
    grid_size: int
    family_trials: int
    warnings: list[str] = field(default_factory=list)
    report_path: str | None = None


# ----------------------------------------------------------------- helpers

def daily_returns(res: BacktestResult) -> tuple[np.ndarray, np.ndarray]:
    de = M.daily_equity(res.equity, res.metrics["initial_cash"])
    eq = de["equity"].to_numpy()
    return de["day"].to_numpy()[1:], eq[1:] / eq[:-1] - 1.0


def _neighbours(grid: list[dict], space: dict, best: int) -> list[int]:
    keys = list(space)
    pos = {k: {v: i for i, v in enumerate(space[k])} for k in keys}
    b = grid[best]
    out = []
    for j, g in enumerate(grid):
        diffs = [k for k in keys if g[k] != b[k]]
        if len(diffs) == 1 and abs(pos[diffs[0]][g[diffs[0]]] - pos[diffs[0]][b[diffs[0]]]) == 1:
            out.append(j)
    return out


def _year_returns(days: np.ndarray, r: np.ndarray) -> dict[int, float]:
    df = pl.DataFrame({"day": days, "r": r}).with_columns(y=pl.col("day").dt.year())
    g = df.group_by("y").agg(((pl.col("r") + 1).product() - 1).alias("ret")).sort("y")
    return dict(zip(g["y"].to_list(), g["ret"].to_list()))


def _style(metrics: dict) -> str:
    h = metrics.get("avg_holding_hours", float("nan"))
    return "intraday" if h == h and h < 24 else "swing"


def _confidence(verdict: str, gates: list[Gate], dev: dict, val: dict | None) -> str:
    if verdict == "REJECTED":
        return "none"
    if verdict == "SCREENED":
        return "very_low"
    fails = [g for g in gates if g.passed is False]
    trades = dev.get("trades", 0) + (val or {}).get("trades", 0)
    if not fails and trades >= 300:
        return "moderate"  # "high" requires passing paper trading
    return "low"


# ----------------------------------------------------------------- main entry

def evaluate(strategy_cls, space: dict[str, list], symbols: list[str] | str, timeframe: str, *,
             hypothesis_id: str, registry: Registry | None = None, risk: RiskConfig | None = None,
             execution: ExecutionConfig | None = None, funding: bool = False,
             dev_data: MarketData | None = None, val_data: MarketData | None = None,
             fixed_params: dict | None = None, cross_symbols: list[str] | None = None,
             open_validation: bool = True, record_detail: bool = True, write_report: bool = True,
             export: bool = True, n_boot: int = 500, seed: int = 0, notes: str = "") -> Evaluation:
    reg = registry or Registry()
    risk = risk or RiskConfig()
    execution = execution or ExecutionConfig()
    symbols = [symbols] if isinstance(symbols, str) else list(symbols)
    cfg = protocol()
    fixed_params = fixed_params or {}
    grid = [{**fixed_params, **g} for g in param_grid(space)] if space else [dict(fixed_params)]
    hyp = reg.hypothesis(hypothesis_id)
    gates: list[Gate] = []
    diag: dict = {}
    experiments: list[str] = []
    warnings: list[str] = []

    dev = dev_data if dev_data is not None else load(symbols, timeframe, "development", funding=funding)

    # ---------------- stage 1: grid on development data (every config is a trial)
    eid = reg.start_experiment(
        hypothesis_id=hypothesis_id, strategy_id=strategy_cls.name, strategy_version=strategy_cls().strategy_version,
        stage="screen", market=dev.market, instruments=symbols, timeframe=timeframe, data_split=dev.split,
        data_versions=dev.fingerprints, config={"risk": risk.__dict__, "execution": execution.__dict__,
                                                "space": space, "fixed": fixed_params, "funding": funding},
        data_start=str(dev.ts_datetime[0]), data_end=str(dev.ts_datetime[-1]), seed=seed, notes=notes)
    experiments.append(eid)
    try:
        sample = dev.head(min(dev.n_bars, 5000))
        cols, results_metrics = [], []
        days = None
        for params in grid:
            strat = strategy_cls(**params)
            rep = lookahead.check_strategy(strat, sample)
            if not rep.passed:
                raise RuntimeError(f"look-ahead detected for {params}: {rep.failures[:2]}")
            res = run_backtest(strat, dev, risk, execution)
            reg.add_trial(eid, params, res.metrics, execution.cost_multiplier,
                          monthly=res.monthly.to_dicts() if record_detail else None,
                          regimes=res.regimes.to_dicts() if record_detail else None)
            d, r = daily_returns(res)
            days = d if days is None else days
            cols.append(r)
            results_metrics.append(res.metrics)
        reg.add_stat_test(eid, "lookahead_signal_causality", passed=True, details={"configs": len(grid)})
        Mx = np.column_stack(cols)
        sharpes = np.array([m["sharpe"] if m["sharpe"] == m["sharpe"] else -np.inf for m in results_metrics])
        best = int(np.argmax(sharpes))
        best_params = grid[best]
        strat = strategy_cls(**best_params)
        best_res = run_backtest(strat, dev, risk, execution)
        dm = best_res.metrics
        style = _style(dm)
        warnings += best_res.warnings

        # ---------------- screen gates
        min_tr = cfg["min_trades"][style]
        gates.append(Gate("min_trades", dm["trades"] >= min_tr, dm["trades"], min_tr, f"style={style}"))
        gates.append(Gate("net_profit_after_costs", dm["total_return"] > 0, dm["total_return"], 0))
        pf = dm["profit_factor"]
        gates.append(Gate("profit_factor", pf == pf and pf > cfg["screen"]["min_profit_factor"], pf,
                          cfg["screen"]["min_profit_factor"]))
        mult = cfg["screen"]["cost_stress_multiplier"]
        stress_ex = ExecutionConfig(**{**execution.__dict__, "cost_multiplier": execution.cost_multiplier * mult})
        stress = run_backtest(strat, dev, risk, stress_ex)
        reg.add_trial(eid, best_params, stress.metrics, stress_ex.cost_multiplier)
        gates.append(Gate("profitable_at_2x_costs", stress.metrics["total_return"] > 0,
                          stress.metrics["total_return"], 0, f"cost x{mult}"))
        screen_ok = all(g.passed for g in gates)

        # ---------------- statistical gates (always computed, for the record)
        st_cfg = cfg["statistical"]
        r_best = Mx[:, best]
        family_trials = max(reg.trial_count(family=hyp["family"]), len(grid))
        col_sr = np.array([stats.sharpe_per_period(Mx[:, j]) for j in range(Mx.shape[1])])
        col_sr = col_sr[np.isfinite(col_sr)]
        var_sr = float(np.var(col_sr, ddof=1)) if len(col_sr) >= 5 else None
        dsr = stats.deflated_sharpe(r_best, family_trials, var_sr)
        diag["deflated_sharpe"] = dsr
        gates.append(Gate("deflated_sharpe", dsr["dsr"] >= st_cfg["dsr_min"], dsr["dsr"], st_cfg["dsr_min"],
                          f"{family_trials} trials in family '{hyp['family']}'"))

        if Mx.shape[1] >= 4:
            pbo = cv.pbo_cscv(Mx, 16 if Mx.shape[0] >= 160 else 8)
            diag["pbo"] = pbo
            gates.append(Gate("pbo", pbo["pbo"] <= st_cfg["pbo_max"], pbo["pbo"], st_cfg["pbo_max"]))
        else:
            gates.append(Gate("pbo", None, None, st_cfg["pbo_max"], "fewer than 4 configurations"))

        spa = stats.reality_check(Mx, n_boot=n_boot, mean_block=10, seed=seed)
        diag["spa"] = spa
        gates.append(Gate("spa", spa["spa_p_value"] <= st_cfg["spa_p_max"], spa["spa_p_value"], st_cfg["spa_p_max"],
                          f"{Mx.shape[1]} configurations"))

        T = Mx.shape[0]
        ppy = dm["daily_periods_per_year"]
        train = int(max(min(ppy * 1.5, T * 0.4), 60))
        test = int(max(min(ppy * 0.5, T * 0.15), 20))
        try:
            wf = cv.walk_forward(Mx, train, test)
            oos_sr = cv.annualize_sharpe(stats.sharpe_per_period(wf.oos_returns), ppy)
            diag["walk_forward"] = {"train_days": train, "test_days": test, "segments": len(wf.segments),
                                    "fraction_positive": wf.fraction_positive, "oos_sharpe": oos_sr,
                                    "oos_return": float(np.prod(1 + wf.oos_returns) - 1),
                                    "efficiency": wf.efficiency, "chosen": [grid[j] for j in wf.chosen]}
            gates.append(Gate("walk_forward_oos_sharpe", oos_sr > st_cfg["wf_min_oos_sharpe"], oos_sr,
                              st_cfg["wf_min_oos_sharpe"], f"{len(wf.segments)} windows"))
            gates.append(Gate("walk_forward_positive_windows", wf.fraction_positive >= st_cfg["wf_min_fraction_positive"],
                              wf.fraction_positive, st_cfg["wf_min_fraction_positive"]))
        except ValueError as e:
            gates.append(Gate("walk_forward_oos_sharpe", False, None, None, str(e)))

        nb = _neighbours(grid, space, best) if space else []
        if nb:
            nsr = sharpes[nb]
            ratio = float(np.median(nsr) / sharpes[best]) if sharpes[best] > 0 else float("nan")
            pos = float((nsr > 0).mean())
            diag["parameter_stability"] = {"neighbours": [grid[j] for j in nb], "neighbour_sharpes": nsr.tolist(),
                                           "median_ratio": ratio, "fraction_positive": pos}
            gates.append(Gate("parameter_plateau", ratio == ratio and ratio >= st_cfg["neighbour_sharpe_ratio_min"]
                              and pos >= st_cfg["neighbour_positive_min"], ratio, st_cfg["neighbour_sharpe_ratio_min"],
                              f"{len(nb)} neighbours, {pos:.0%} positive"))
        else:
            gates.append(Gate("parameter_plateau", None, None, None, "no parameter search"))
        diag["grid_fraction_positive"] = float((sharpes > 0).mean())

        yrs = _year_returns(days, r_best)
        diag["yearly_returns"] = yrs
        if len(yrs) >= 2:
            pos_frac = float(np.mean([v > 0 for v in yrs.values()]))
            gates.append(Gate("years_positive", pos_frac >= st_cfg["year_positive_min"], pos_frac,
                              st_cfg["year_positive_min"], f"{len(yrs)} years"))
            best_year = max(yrs, key=yrs.get)
            ex = float(np.prod([1 + v for y, v in yrs.items() if y != best_year]) - 1)
            gates.append(Gate("profitable_without_best_year", ex > 0, ex, 0, f"best year {best_year}"))
        else:
            gates.append(Gate("years_positive", None, None, None, "less than two years of data"))

        # diagnostics (reported, not gated)
        diag["bootstrap_sharpe_annual"] = {k: (v * math.sqrt(ppy) if k != "p_le_zero" else v) for k, v in
                                           stats.bootstrap_metric(r_best, stats.sharpe_per_period, n_boot, 10, seed).items()}
        diag["bootstrap_max_drawdown"] = stats.bootstrap_metric(r_best, stats.max_drawdown_of_returns, n_boot, 10, seed)
        diag["trade_monte_carlo"] = stats.trade_monte_carlo(best_res.trades["pnl_net"].to_numpy(), risk.initial_cash,
                                                            seed=seed)
        delay = run_backtest(strat, dev, risk, ExecutionConfig(**{**execution.__dict__,
                                                                  "delay_bars": execution.delay_bars + 1}))
        reg.add_trial(eid, {**best_params, "_delay_bars": execution.delay_bars + 1}, delay.metrics,
                      execution.cost_multiplier)
        diag["one_bar_extra_delay"] = {"total_return": delay.metrics["total_return"], "sharpe": delay.metrics["sharpe"]}
        if cross_symbols:
            cross = {}
            for s in cross_symbols:
                try:
                    cd = load([s], timeframe, "development", funding=funding)
                    cr = run_backtest(strat, cd, risk, execution)
                    reg.add_trial(eid, {**best_params, "_symbol": s}, cr.metrics, execution.cost_multiplier)
                    cross[s] = {"total_return": cr.metrics["total_return"], "sharpe": cr.metrics["sharpe"],
                                "trades": cr.metrics["trades"]}
                except Exception as e:  # noqa: BLE001 - record and continue
                    cross[s] = {"error": str(e)}
            diag["cross_market"] = cross
        diag["cost_stress_2x"] = {"total_return": stress.metrics["total_return"], "sharpe": stress.metrics["sharpe"]}
        diag["regimes"] = best_res.regimes.to_dicts()

        for g in gates:
            reg.add_stat_test(eid, g.name, statistic=g.value if isinstance(g.value, (int, float)) else None,
                              passed=g.passed, details={"threshold": g.threshold, "note": g.note})
        reg.finish_experiment(eid, "pass" if screen_ok else "fail", warnings=warnings)
    except Exception as e:
        import traceback
        reg.finish_experiment(eid, "error", error="".join(traceback.format_exception(e))[-4000:])
        if export:
            reg.export()
        raise

    stat_ok = all(g.passed is not False for g in gates)
    reasons = [f"{g.name}: {_fmt(g.value)} (needs {_cmp(g)} {_fmt(g.threshold)})" for g in gates if g.passed is False]

    # ---------------- stage 3: one validation look (only if everything above passed)
    val_metrics = None
    if screen_ok and stat_ok and open_validation:
        prior = reg.query("SELECT id FROM experiments WHERE hypothesis_id=? AND stage='validation'", (hypothesis_id,))
        if prior:
            raise PermissionError(f"validation split already used for {hypothesis_id} ({prior[0]['id']}); "
                                  "register a new hypothesis for a new idea")
        val = val_data if val_data is not None else load(symbols, timeframe, "validation", funding=funding)
        veid = reg.start_experiment(
            hypothesis_id=hypothesis_id, strategy_id=strategy_cls.name, strategy_version=strat.strategy_version,
            stage="validation", market=val.market, instruments=symbols, timeframe=timeframe, data_split=val.split,
            data_versions=val.fingerprints, config={"risk": risk.__dict__, "execution": execution.__dict__,
                                                    "params": best_params, "funding": funding},
            data_start=str(val.ts_datetime[0]), data_end=str(val.ts_datetime[-1]), notes="single validation look")
        experiments.append(veid)
        vres = run_backtest(strat, val, risk, execution)
        reg.add_trial(veid, best_params, vres.metrics, execution.cost_multiplier,
                      monthly=vres.monthly.to_dicts(), regimes=vres.regimes.to_dicts())
        val_metrics = vres.metrics
        _, vr = daily_returns(vres)
        vpsr = stats.probabilistic_sharpe(stats.sharpe_per_period(vr), len(vr))
        vc = cfg["validation"]
        vgates = [
            Gate("validation_net_profit", val_metrics["total_return"] > 0, val_metrics["total_return"], 0),
            Gate("validation_profit_factor", val_metrics["profit_factor"] > vc["min_profit_factor"],
                 val_metrics["profit_factor"], vc["min_profit_factor"]),
            Gate("validation_psr", vpsr >= vc["min_psr"], vpsr, vc["min_psr"]),
            Gate("validation_trades", val_metrics["trades"] >= min_tr * vc["min_trades_fraction"],
                 val_metrics["trades"], min_tr * vc["min_trades_fraction"]),
        ]
        for g in vgates:
            reg.add_stat_test(veid, g.name, statistic=g.value if isinstance(g.value, (int, float)) else None,
                              passed=g.passed, details={"threshold": g.threshold})
        gates += vgates
        val_ok = all(g.passed for g in vgates)
        reg.finish_experiment(veid, "pass" if val_ok else "fail", warnings=vres.warnings)
        reasons += [f"{g.name}: {_fmt(g.value)} (needs {_cmp(g)} {_fmt(g.threshold)})" for g in vgates if not g.passed]
        verdict = "CANDIDATE" if val_ok else "REJECTED"
    elif screen_ok and stat_ok:
        verdict = "SCREENED"
        reasons.append("validation look not opened")
    elif screen_ok:
        verdict = "REJECTED"
    else:
        verdict = "REJECTED"

    # Scalping results on bar data can never be more than a candidate pending tick validation.
    if any("SCALPING FIDELITY" in w for w in warnings) and verdict == "CANDIDATE":
        reasons.append("scalping fidelity: needs tick/quote validation before any further promotion")

    status = {"CANDIDATE": "CANDIDATE", "SCREENED": "SCREENED", "REJECTED": "REJECTED"}[verdict]
    reg.set_status(hypothesis_id, status, "; ".join(reasons) if reasons else "all gates passed", experiments[-1])
    conf = _confidence(verdict, gates, dm, val_metrics)
    reg.con.execute("UPDATE hypotheses SET confidence=? WHERE id=?", (conf, hypothesis_id))
    reg.con.commit()
    ev = Evaluation(hypothesis_id, verdict, reasons, best_params, gates, dm, val_metrics, diag, experiments, conf,
                    len(grid), family_trials, warnings)
    if write_report:
        ev.report_path = str(write_strategy_report(ev, strategy_cls, hyp, symbols, timeframe, risk, best_res))
    if export:
        reg.export()
    return ev


# ----------------------------------------------------------------- reporting

def _fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "n/a"
        if math.isinf(v):
            return "∞"
        return f"{v:.3f}"
    return str(v)


def _cmp(g: Gate) -> str:
    return "≤" if g.name in ("pbo", "spa") else "≥" if g.name not in ("net_profit_after_costs",) else ">"


def _pct(v):
    return "n/a" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:.1%}"


def write_strategy_report(ev: Evaluation, strategy_cls, hyp: dict, symbols, timeframe, risk: RiskConfig,
                          res: BacktestResult) -> Path:
    """Strategy card with every field the owner asked for (README §7)."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    d, v = ev.dev_metrics, ev.val_metrics
    doc = (strategy_cls.__doc__ or "").strip().splitlines()
    lines = [
        f"# {hyp['title']} — {ev.verdict}", "",
        f"*Hypothesis `{ev.hypothesis_id}` · family `{hyp['family']}` · experiments {', '.join(f'`{e}`' for e in ev.experiments)}*", "",
        f"**Status: {ev.verdict}. Confidence: {ev.confidence}.** "
        + ("A candidate is *promising*, not validated: it still needs the vault test, tick-level checks and paper trading."
           if ev.verdict == "CANDIDATE" else ""), "",
        "| Field | Value |", "|---|---|",
        f"| Strategy | `{strategy_cls.name}` — {doc[0] if doc else ''} |",
        f"| Market | {', '.join(symbols)} ({res.data['market']}) |",
        f"| Timeframe | {timeframe} |",
        f"| Question | {hyp['question']} |",
        f"| Chosen parameters | `{json.dumps(ev.best_params)}` (best of {ev.grid_size} on development data) |",
        f"| Entry / exit rules | See `{strategy_cls.__module__}.{strategy_cls.__name__}`; fills at the next bar's open |",
        f"| Stop-loss | {'ATR-based stop' if 'stop_atr' in ev.best_params or 'stop_atr' in strategy_cls.default_params else 'none'}"
        f"{', trailing stop' if 'trail_atr' in strategy_cls.default_params else ''} |",
        f"| Position sizing | {risk.sizing}, risk/trade {risk.risk_per_trade:.1%}, start ${risk.initial_cash:,.0f}, no leverage |",
        f"| Cost profile | `{res.cost_models[symbols[0]]['profile']}` |",
        "", "## Performance (after all costs)", "",
        "| Metric | Development | Validation |", "|---|---|---|",
    ]
    rows = [("Trades", "trades", str), ("Win rate", "win_rate", _pct), ("Profit factor", "profit_factor", _fmt),
            ("Expectancy per trade ($)", "expectancy", _fmt), ("Expectancy (R)", "expectancy_r", _fmt),
            ("Net return", "total_return", _pct), ("CAGR", "cagr", _pct), ("Max drawdown", "max_drawdown", _pct),
            ("Sharpe", "sharpe", _fmt), ("Sortino", "sortino", _fmt), ("Avg holding (h)", "avg_holding_hours", _fmt),
            ("Costs / gross profit", "cost_share_of_gross", _pct), ("Buy & hold return", "benchmark_total_return", _pct)]
    for label, k, f in rows:
        lines.append(f"| {label} | {f(d.get(k))} | {f(v.get(k)) if v else 'not opened'} |")
    lines += ["", "## Gates", "", "| Gate | Result | Value | Threshold | Note |", "|---|---|---|---|---|"]
    for g in ev.gates:
        res_s = "n/a" if g.passed is None else ("PASS" if g.passed else "**FAIL**")
        lines.append(f"| {g.name} | {res_s} | {_fmt(g.value)} | {_fmt(g.threshold)} | {g.note} |")
    dg = ev.diagnostics
    wf = dg.get("walk_forward", {})
    lines += ["", "## Diagnostics", "",
              f"- Deflated Sharpe: {_fmt(dg['deflated_sharpe']['dsr'])} (observed daily Sharpe "
              f"{_fmt(dg['deflated_sharpe']['sharpe'])} vs luck threshold {_fmt(dg['deflated_sharpe']['sr_threshold'])} "
              f"for {ev.family_trials} trials)",
              f"- Walk-forward: {wf.get('segments', 'n/a')} windows, {_pct(wf.get('fraction_positive'))} positive, "
              f"out-of-sample Sharpe {_fmt(wf.get('oos_sharpe'))}, efficiency {_fmt(wf.get('efficiency'))}",
              f"- PBO: {_fmt(dg.get('pbo', {}).get('pbo'))}; SPA p-value {_fmt(dg['spa']['spa_p_value'])}; "
              f"share of grid with positive Sharpe {_pct(dg['grid_fraction_positive'])}",
              f"- Bootstrap annual Sharpe 95% CI: [{_fmt(dg['bootstrap_sharpe_annual']['ci_low'])}, "
              f"{_fmt(dg['bootstrap_sharpe_annual']['ci_high'])}]",
              f"- Trade-order Monte Carlo: 95th-percentile drawdown {_pct(dg['trade_monte_carlo'].get('max_dd_p95'))}, "
              f"probability of loss {_pct(dg['trade_monte_carlo'].get('prob_loss'))}",
              f"- 2× costs: {_pct(dg['cost_stress_2x']['total_return'])}; one extra bar of delay: "
              f"{_pct(dg['one_bar_extra_delay']['total_return'])}",
              "- Yearly returns: " + ", ".join(f"{y}: {_pct(r)}" for y, r in dg["yearly_returns"].items())]
    if "cross_market" in dg:
        lines.append("- Other markets: " + ", ".join(
            f"{s}: {_pct(x.get('total_return'))}" for s, x in dg["cross_market"].items()))
    lines += ["", "## Weaknesses and risks", ""]
    weak = [f"Failed: {r}" for r in ev.reasons] + [f"Warning: {w}" for w in ev.warnings]
    lines += [f"- {w}" for w in weak] or ["- None flagged by the automated checks (this is not proof of an edge)."]
    path = REPORT_DIR / f"{ev.hypothesis_id}.md"
    path.write_text("\n".join(lines) + "\n")
    return path
