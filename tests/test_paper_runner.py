"""Paper-trading runner: replay must match the backtest engine; safety rules must hold."""

from datetime import timedelta

import numpy as np
import pytest

from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import MarketData
from lab.paper import runner
from lab.paper.broker import AlpacaPaperBroker, LiveTradingRefused, SimBroker
from lab.registry.db import Registry
from lab.strategies.phase4 import RsiReversion, TrendFilter
from lab.validation.synthetic import path_bars


def _spy(n=900, seed=3):
    df = path_bars(seed, n, vol=0.012, step=timedelta(days=1))
    return df.filter(df["ts"].dt.weekday() <= 5)


@pytest.mark.parametrize("strat,maxbars", [(RsiReversion(trend_n=100, entry_rsi=15), 0),
                                            (TrendFilter(n=30, allow_short=True), 0),
                                            (RsiReversion(trend_n=100, entry_rsi=15), 3)])
def test_replay_matches_engine_positions(strat, maxbars):
    df = _spy()
    held, _ = runner.replay_target(strat, df, "SPY", maxbars)
    res = run_backtest(strat, MarketData(["SPY"], "1d", {"SPY": df}),
                       RiskConfig(sizing="pct_equity", position_pct=0.9, max_bars_held=maxbars),
                       ExecutionConfig(cost_profile="equity_us"))
    eng = np.zeros(df.height, dtype=np.int64)
    idx = {t: i for i, t in enumerate(df["ts"].to_list())}
    for row in res.trades.iter_rows(named=True):
        a, b = idx[row["entry_ts"]], idx[row["exit_ts"]]
        end = b + 1 if row["exit_reason"] == "end_of_data" else b
        eng[a:end] = row["side"]
    assert res.trades.height > 5
    assert (held == eng).all()


@pytest.fixture
def validated(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_REGISTRY", str(tmp_path / "reg.sqlite"))
    reg = Registry()
    reg.register_hypothesis(id="H4-17", family="t", title="t", question="q", source="manual",
                            asset_classes=["equity"], instruments=["SPY"], timeframe="1d", spec={})
    reg.set_status("H4-17", "VALIDATED", "test")
    return reg


CFG = {"mode": "paper", "kill_switch": False, "max_order_notional_pct": 1.05,
       "strategies": [{"hypothesis": "H4-17", "strategy": "trend_filter", "params": {"n": 30},
                       "symbols": ["SPY"], "timeframe": "1d", "allocation": 1.0}]}


def test_plans_buy_when_strategy_wants_long_and_is_idempotent(validated, tmp_path):
    df = _spy()
    _, target = runner.replay_target(TrendFilter(n=30), df, "SPY")
    b = SimBroker(cash=5000.0)
    out = runner.run(b, submit=True, cfg=CFG, bars={"SPY": df}, journal=tmp_path / "j.jsonl")
    p = out["plans"][0]
    assert p["target_side"] == target
    if target == 1:
        assert p["order_side"] == "buy" and p["order_qty"] == int(5000 // df["close"][-1])
        runner.run(b, submit=True, cfg=CFG, bars={"SPY": df}, journal=tmp_path / "j.jsonl")
        assert len(b.submitted) == 1  # same day re-run: no duplicate order
        assert Registry().hypothesis("H4-17")["status"] == "PAPER"  # protocol: VALIDATED -> PAPER
        b.fill_open({"SPY": float(df["close"][-1])})
        again = runner.plan_orders(b, CFG, {"SPY": df})[0]
        assert again.order_side is None  # already holding: hold, do not resize
    else:
        assert p["order_side"] is None


def test_capital_cap_limits_sizing(validated):
    df = _spy()
    b = SimBroker(cash=100_000.0)
    p = runner.plan_orders(b, {**CFG, "capital": 5000}, {"SPY": df})[0]
    if p.order_side == "buy":
        assert p.order_qty == int(5000 // df["close"][-1])


def test_exit_when_strategy_goes_flat(validated, tmp_path):
    df = _spy()
    held, target = runner.replay_target(TrendFilter(n=30), df, "SPY")
    b = SimBroker(cash=0.0, held={"SPY": 10.0}, last_price={"SPY": float(df["close"][-1])})
    p = runner.plan_orders(b, CFG, {"SPY": df})[0]
    if target == 0:
        assert p.order_side == "sell" and p.order_qty == 10
    else:
        assert p.order_side is None


def test_only_validated_strategies_may_trade(validated):
    validated.set_status("H4-17", "REJECTED", "test")
    with pytest.raises(runner.SafetyError, match="only VALIDATED"):
        runner.plan_orders(SimBroker(), CFG, {"SPY": _spy()})


def test_kill_switch_places_nothing(validated, tmp_path):
    b = SimBroker()
    out = runner.run(b, submit=True, cfg={**CFG, "kill_switch": True}, bars={"SPY": _spy()},
                     journal=tmp_path / "j.jsonl")
    assert out["event"] == "kill_switch" and not b.submitted


def test_strategies_with_stops_are_refused():
    from lab.strategies.examples import DonchianBreakout
    with pytest.raises(runner.SafetyError, match="not supported"):
        runner.replay_target(DonchianBreakout(n=20), _spy(), "SPY")


def test_live_endpoint_refused(monkeypatch):
    monkeypatch.setenv("ALPACA_KEY_ID", "x")
    with pytest.raises(LiveTradingRefused):
        AlpacaPaperBroker(base_url="https://api.alpaca.markets")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    with pytest.raises(LiveTradingRefused):
        AlpacaPaperBroker()


def test_deployment_config_is_paper_and_validated_only():
    cfg = runner.deployment()
    assert cfg["mode"] == "paper"
    assert [d["hypothesis"] for d in cfg["strategies"]] == ["H4-17"]


def test_plan_only_run_does_not_change_status(validated, tmp_path):
    runner.run(SimBroker(cash=5000.0), submit=False, cfg=CFG, bars={"SPY": _spy()}, journal=tmp_path / "j.jsonl")
    assert Registry().hypothesis("H4-17")["status"] == "VALIDATED"
