"""Tests designed to catch look-ahead bias in indicators, strategies, data alignment and the engine."""

from datetime import timedelta

import numpy as np
import pytest

from engine_helpers import ZERO_COSTS, bars, market
from lab.engine import lookahead
from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import resample
from lab.engine.strategy import Strategy
from lab.features import indicators as ind
from lab.strategies.examples import EXAMPLES


def _random_walk(n=3000, seed=0, symbol="BTCUSDT", step=timedelta(minutes=1)):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    o = np.concatenate([[100], c[:-1]])
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.002, n))
    l = np.minimum(o, c) * (1 - rng.uniform(0, 0.002, n))
    return bars(o, h, l, c, v=rng.uniform(100, 1000, n), step=step)


class Peeking(Strategy):
    """Deliberately cheats: buys when the NEXT close is higher."""
    name = "peeking"

    def signals(self, df, symbol):
        c = df["close"].to_numpy()
        nxt = np.append(c[1:], np.nan)
        return {"entry_long": nxt > c, "exit_long": nxt < c}


class CenteredMA(Strategy):
    """Subtle cheat: a centred moving average uses future bars."""
    name = "centered_ma"

    def signals(self, df, symbol):
        c = df["close"]
        ma = c.rolling_mean(21, center=True).to_numpy()
        return {"entry_long": c.to_numpy() > ma}


INDICATORS = {
    "sma": lambda d: ind.sma(d["close"], 20),
    "ema": lambda d: ind.ema(d["close"], 20),
    "std": lambda d: ind.rolling_std(d["close"], 20),
    "atr": lambda d: ind.atr(d["high"], d["low"], d["close"], 14),
    "rsi": lambda d: ind.rsi(d["close"], 14),
    "zscore": lambda d: ind.zscore(d["close"], 20),
    "donchian_hi": lambda d: ind.donchian_prior(d["high"], d["low"], 20)[0],
    "realized_vol": lambda d: ind.realized_vol(d["close"], 30),
    "vwap": lambda d: ind.rolling_vwap(d["close"], d["volume"], 30),
    "cross": lambda d: ind.cross_above(ind.sma(d["close"], 5), ind.sma(d["close"], 20)).astype(float),
}


@pytest.mark.parametrize("name", list(INDICATORS))
def test_indicators_are_causal(name):
    df = _random_walk()
    full = INDICATORS[name](df)
    for k in (100, 1000, 2500):
        part = INDICATORS[name](df.head(k))
        assert np.allclose(full[:k], part, equal_nan=True), f"{name} changes when future bars are removed"


def test_shift_refuses_future():
    with pytest.raises(ValueError):
        ind.shift(np.arange(5.0), -1)


@pytest.mark.parametrize("cls", [Peeking, CenteredMA])
def test_detector_catches_cheating_strategies(cls):
    data = market({"BTCUSDT": _random_walk()})
    rep = lookahead.check_strategy(cls(), data)
    assert not rep.passed and rep.failures


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_example_strategies_are_causal(name):
    data = market({"BTCUSDT": _random_walk(), "ETHUSDT": _random_walk(seed=1)})
    rep = lookahead.check_strategy(EXAMPLES[name](), data)
    assert rep.passed, rep.failures


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_engine_is_causal(name):
    data = market({"BTCUSDT": _random_walk(), "ETHUSDT": _random_walk(seed=1, n=2900)})
    runner = lambda s, d: run_backtest(s, d, RiskConfig(), ExecutionConfig(cost_profile="crypto_perp"))  # noqa
    rep = lookahead.check_engine(EXAMPLES[name](), data, runner)
    assert rep.passed, rep.failures


def test_peeking_strategy_would_look_spectacular():
    """Sanity check of why the detector matters: the cheat is hugely 'profitable'."""
    data = market({"BTCUSDT": _random_walk(n=2000)})
    r = run_backtest(Peeking(), data, RiskConfig(sizing="pct_equity"),
                     ExecutionConfig(cost_overrides=ZERO_COSTS, delay_bars=1))
    # Even with the cheat, next-bar execution removes most of the edge on a random walk where
    # open[t+1] == close[t]: the engine fills at the next open, so the peek at close[t+1] still
    # leaks (it knows the direction of bar t+1). The detector, not the engine, must catch this.
    assert r.metrics["total_return"] > 1.0
    assert not lookahead.check_strategy(Peeking(), data).passed


def test_resampled_bars_only_contain_their_own_period():
    df = _random_walk(n=180)
    h = resample(df, "1h")
    assert h.height == 3
    first = df.head(60)
    assert h["open"][0] == first["open"][0] and h["close"][0] == first["close"][-1]
    assert h["high"][0] == first["high"].max() and h["volume"][0] == pytest.approx(first["volume"].sum())


def test_higher_timeframe_alignment_has_no_leakage():
    # Hourly bar stamped 00:00 is complete at 01:00: minute bars before 01:00 must not see it.
    m = _random_walk(n=180)
    h = resample(m, "1h")
    hour_us = 3600 * 10**6
    vals = ind.align_higher_timeframe(m["ts"].dt.epoch("us").to_numpy(), h["ts"].dt.epoch("us").to_numpy(),
                                      h["close"].to_numpy(), hour_us)
    assert np.isnan(vals[:60]).all()
    assert (vals[60:120] == h["close"][0]).all()
    assert (vals[120:] == h["close"][1]).all()


def test_research_runner_refuses_vault_and_cheaters(tmp_path, monkeypatch):
    from lab.registry.db import Registry
    from lab.research import run_experiment
    reg = Registry(tmp_path / "r.sqlite")
    hid = reg.register_hypothesis(family="test", title="t", question="q", source="manual",
                                  asset_classes=["crypto"], instruments=["BTCUSDT"], timeframe="1m", spec={"x": 1})
    data = market({"BTCUSDT": _random_walk()})
    with pytest.raises(PermissionError):
        run_experiment(Peeking(), "BTCUSDT", "1m", hypothesis_id=hid, split="vault", registry=reg, data=data,
                       export=False)
    with pytest.raises(RuntimeError, match="future data"):
        run_experiment(Peeking(), "BTCUSDT", "1m", hypothesis_id=hid, registry=reg, data=data, export=False)
    # The failed experiment is still recorded.
    rows = reg.query("SELECT outcome, error FROM experiments")
    assert rows[-1]["outcome"] == "error" and "future data" in rows[-1]["error"]
