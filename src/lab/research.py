"""Research entry point: every backtest run through here is recorded in the registry.

    from lab.research import run_experiment
    res, eid = run_experiment(strategy, ["BTCUSDT"], "1h", hypothesis_id="H-...", stage="screen")

- Failed runs are recorded too (outcome="error" with the traceback) and the error re-raised.
- The vault split requires stage="vault", is allowed once per hypothesis, and is logged.
- `cost_sensitivity` re-runs a strategy under worse execution costs; each run is a trial.
"""

from __future__ import annotations

import traceback

from lab.engine import lookahead
from lab.engine.backtest import BacktestResult, ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import MarketData, load
from lab.engine.strategy import Strategy
from lab.registry.db import Registry

NORMAL_SPLITS = ("development", "validation", "development+validation")


def _registry(registry: Registry | None) -> Registry:
    return registry or Registry()


def run_experiment(strategy: Strategy, symbols: list[str] | str, timeframe: str, *, hypothesis_id: str,
                   stage: str = "screen", split: str = "development", risk: RiskConfig | None = None,
                   execution: ExecutionConfig | None = None, funding: bool = False,
                   data: MarketData | None = None, registry: Registry | None = None,
                   check_lookahead: bool = True, cost_multipliers: tuple[float, ...] = (1.0,),
                   seed: int | None = None, notes: str = "", export: bool = True,
                   ) -> tuple[BacktestResult, str]:
    """Run, record and return (result at the first cost multiplier, experiment id)."""
    reg = _registry(registry)
    risk = risk or RiskConfig()
    execution = execution or ExecutionConfig()
    symbols = [symbols] if isinstance(symbols, str) else list(symbols)
    if split == "vault":
        if stage != "vault":
            raise PermissionError("the vault split may only be used with stage='vault'")
        if reg.vault_opened(hypothesis_id):
            raise PermissionError(f"vault already opened for {hypothesis_id}")
    elif split not in NORMAL_SPLITS and data is None:
        raise ValueError(f"unknown split {split!r}")

    eid = reg.start_experiment(
        hypothesis_id=hypothesis_id, strategy_id=strategy.name, strategy_version=strategy.strategy_version,
        stage=stage, market=data.market if data else "pending", instruments=symbols, timeframe=timeframe,
        data_split=split if data is None else data.split, data_versions={},
        config={"risk": risk.__dict__, "execution": execution.__dict__, "params": strategy.params,
                "funding": funding, "cost_multipliers": list(cost_multipliers)},
        seed=seed, notes=notes)
    try:
        if split == "vault":
            reg.record_vault_access(hypothesis_id, eid)
        if data is None:
            data = load(symbols, timeframe, split, funding=funding, allow_vault=(split == "vault"))
        reg.con.execute("UPDATE experiments SET market=?, data_versions=?, data_start=?, data_end=?, "
                        "data_fingerprint=? WHERE id=?",
                        (data.market, _dumps(data.fingerprints), str(data.ts_datetime[0]),
                         str(data.ts_datetime[-1]), _fp(data.fingerprints), eid))
        reg.con.commit()
        if check_lookahead:
            sample = data.head(min(data.n_bars, 20_000))
            rep = lookahead.check_strategy(strategy, sample)
            reg.add_stat_test(eid, "lookahead_signal_causality", passed=rep.passed,
                              details={"failures": rep.failures[:10], "checks": rep.checks})
            if not rep.passed:
                raise RuntimeError("strategy uses future data: " + "; ".join(rep.failures[:3]))
        signals = strategy.generate(data)
        first = None
        for m in cost_multipliers:
            ex = ExecutionConfig(**{**execution.__dict__, "cost_multiplier": execution.cost_multiplier * m})
            res = run_backtest(strategy, data, risk, ex, signals=signals)
            reg.add_trial(eid, strategy.params, res.metrics, cost_multiplier=ex.cost_multiplier,
                          monthly=res.monthly.to_dicts(), regimes=res.regimes.to_dicts())
            if first is None:
                first = res
                reg.con.execute("UPDATE experiments SET cost_models=? WHERE id=?", (_dumps(res.cost_models), eid))
        reg.finish_experiment(eid, "diagnostic" if stage == "diagnostic" else "complete", warnings=first.warnings)
        return first, eid
    except Exception as e:
        reg.finish_experiment(eid, "error", error="".join(traceback.format_exception(e))[-4000:])
        raise
    finally:
        if export:
            reg.export()


def cost_sensitivity(strategy: Strategy, symbols, timeframe: str, *, hypothesis_id: str,
                     multipliers=(1.0, 1.5, 2.0, 3.0), **kw):
    """Run the same strategy at increasing execution costs; returns (rows, experiment id)."""
    reg = _registry(kw.pop("registry", None))
    first, eid = run_experiment(strategy, symbols, timeframe, hypothesis_id=hypothesis_id, stage="robustness",
                                cost_multipliers=tuple(multipliers), registry=reg, **kw)
    rows = reg.query("SELECT cost_multiplier, n_trades, net_return, sharpe, profit_factor, max_drawdown "
                     "FROM trials WHERE experiment_id=? ORDER BY cost_multiplier", (eid,))
    return rows, eid


def _dumps(x):
    from lab.registry.db import _json
    return _json(x)


def _fp(d: dict) -> str:
    import hashlib
    return hashlib.sha256(_dumps(d).encode()).hexdigest()[:16]
