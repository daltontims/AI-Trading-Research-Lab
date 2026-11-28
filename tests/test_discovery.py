"""Discovery engine: rule templates are causal, and the event-study screen rejects luck
but finds a planted effect (protocol §8 calibration for the new stage)."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from lab.discovery import screen, templates as T
from lab.engine import lookahead
from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import MarketData
from lab.validation import stats
from lab.validation.synthetic import path_bars


def daily(seed, n=2500, phi=0.0):
    return path_bars(seed, n, phi=phi, vol=0.012, step=timedelta(days=1))


def all_rules():
    for entry, e in T.ENTRIES.items():
        for filt in T.FILTERS:
            for ex in e.exits:
                yield entry, filt, ex


@pytest.mark.parametrize("entry,filt,ex", list(all_rules()))
def test_rule_templates_have_no_lookahead_and_trade(entry, filt, ex):
    df = daily(1)
    data = MarketData(["SPY"], "1d", {"SPY": df}, market="equity")
    cls = T.rule_strategy(entry, filt, ex)
    assert T.strategy_from_name(cls.name) is cls
    assert len(cls.default_params) <= 4
    for x in T.ENTRIES[entry].grid:
        for y in T.EXITS[ex].grid:
            s = cls(x=x, y=y)
            rep = lookahead.check_strategy(s, data)
            assert rep.passed, rep.failures[:2]
    res = run_backtest(cls(), data, RiskConfig(sizing="pct_equity", position_pct=1.0), ExecutionConfig())
    assert res.metrics["trades"] > 0 or filt != "none"


def test_forward_returns_are_next_open_to_later_close():
    df = daily(2, 50)
    f = screen.forward_returns(df, 3)
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    assert np.isclose(f[10], np.log(c[13] / o[11]))
    assert np.isnan(f[-3:]).all()


def test_thinning_keeps_events_at_least_h_apart():
    m = np.zeros(30, bool)
    m[[1, 2, 3, 7, 8, 20]] = True
    assert screen.thin(m, 5).tolist() == [1, 7, 20]


def test_event_screen_false_discovery_rate_on_random_walks():
    """30 random-walk 'instruments' x every entry/filter/x: BH must find (almost) nothing."""
    tests = []
    for seed in range(30):
        tests += screen.screen_symbol((f"RW{seed}", daily(100 + seed), list(T.FILTERS)))
    p = np.array([t.p_value for t in tests])
    q = stats.bh_adjusted(p)
    assert (q < 0.05).sum() <= max(1, int(0.01 * len(p)))
    valid = p[p < 1.0]
    assert 0.35 < valid.mean() < 0.65          # roughly uniform under the null


def test_event_screen_finds_planted_mean_reversion():
    """Daily returns with negative autocorrelation: oversold entries must show an effect."""
    hits = 0
    for seed in range(5):
        res = screen.screen_symbol(("MR", daily(200 + seed, 6000, phi=-0.25), ["none"]))
        ps = [t.p_value for t in res if t.entry in ("rsi2_low", "drop_z", "down_streak")]
        hits += min(ps) < 1e-3
    assert hits == 5
