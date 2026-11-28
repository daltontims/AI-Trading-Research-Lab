"""Discovery engine: rule templates are causal, and the event-study screen rejects luck
but finds a planted effect (protocol §8 calibration for the new stage)."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from lab.data import lake, schemas
from lab.discovery import screen, templates as T
from lab.engine import lookahead
from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import MarketData
from lab.validation import stats
from lab.validation.synthetic import path_bars


def daily(seed, n=2500, phi=0.0):
    return path_bars(seed, n, phi=phi, vol=0.012, step=timedelta(days=1))


@pytest.fixture
def vix_lake():
    """Synthetic VIX / VIX3M daily series in the (per-test, isolated) data lake."""
    out = {}
    for j, s in enumerate(("IDX_VIX", "IDX_VIX3M")):
        df = path_bars(50 + j, 2600, vol=0.06, step=timedelta(days=1), p0=20.0)
        lake.write_chunk(lake.DatasetKey("macro", "yahoo", s, "bars_1d"), "all", schemas.conform(df, "bars"))
        out[s] = df
    return out


def all_rules():
    for entry, e in T.ENTRIES.items():
        for filt in T.FILTERS:
            for ex in e.exits:
                yield entry, filt, ex


@pytest.mark.parametrize("entry,filt,ex", list(all_rules()))
def test_rule_templates_have_no_lookahead_and_trade(entry, filt, ex, vix_lake):
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


def test_pooled_screen_rejects_luck_and_counts_one_observation_per_date():
    frames = {f"RW{i}": daily(300 + i) for i in range(10)}
    res = screen.screen_group(("eq", frames, list(T.FILTERS)))
    q = stats.bh_adjusted([t.p_value for t in res])
    assert (q < 0.05).sum() == 0
    # Identical copies of one market must not add evidence: same dates, same per-date mean.
    one = screen.pooled_event_test({"A": frames["RW0"]}, "rsi2_low", "none", "eq", 10.0)
    ten = screen.pooled_event_test({f"C{i}": frames["RW0"] for i in range(10)}, "rsi2_low", "none", "eq", 10.0)
    assert one.events == ten.events and np.isclose(one.t_stat, ten.t_stat)


def test_pooled_screen_finds_effect_spread_over_markets():
    frames = {f"MR{i}": daily(400 + i, 2500, phi=-0.15) for i in range(10)}
    res = screen.screen_group(("eq", frames, ["none"]))
    assert min(t.p_value for t in res if t.entry in ("rsi2_low", "drop_z")) < 1e-4


def test_vix_entries_screen_with_context_and_find_planted_effect(vix_lake):
    """Plant an effect: the market rebounds over the 5 days after each VIX spike."""
    import polars as pl
    vix = vix_lake["IDX_VIX"]["close"].to_numpy()
    df = daily(7, 2600)
    spike = T.entry_signal("vix_spike", df, 1.15, vix_lake)
    assert spike.sum() > 20
    r = np.diff(np.log(df["close"].to_numpy()), prepend=np.nan)
    boost = np.zeros(len(r))
    for i in np.flatnonzero(spike):
        boost[i + 2: i + 7] += 0.004              # from the next session after the fill, for 5 days
    c = df["close"].to_numpy()[0] * np.exp(np.nancumsum(np.nan_to_num(r) + boost))
    planted = df.with_columns(close=pl.Series(c), open=pl.Series(np.r_[c[0], c[:-1]]),
                              high=pl.Series(np.maximum(c, np.r_[c[0], c[:-1]])),
                              low=pl.Series(np.minimum(c, np.r_[c[0], c[:-1]])))
    res = screen.screen_symbol(("SPY", planted, ["none"], T.VIX_ENTRIES, vix_lake))
    assert min(t.p_value for t in res if t.entry == "vix_spike") < 1e-3
    null = screen.screen_symbol(("SPY", df, list(T.FILTERS), T.VIX_ENTRIES, vix_lake))
    assert min(t.p_value for t in null) > 1e-3
    assert len(vix) == 2600
