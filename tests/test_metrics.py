"""Known-answer tests for performance metrics."""

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from lab.engine import metrics as M


def test_sharpe_sortino_known_values():
    r = np.array([0.01, -0.02, 0.03, 0.0, 0.01])
    mean, sd = r.mean(), r.std(ddof=1)
    assert M.sharpe(r, 252) == pytest.approx(mean / sd * math.sqrt(252))
    dd = math.sqrt(np.mean(np.minimum(r, 0) ** 2))  # sqrt(0.0004/5)
    assert dd == pytest.approx(math.sqrt(0.0004 / 5))
    assert M.sortino(r, 252) == pytest.approx(mean / dd * math.sqrt(252))
    assert math.isnan(M.sharpe(np.array([0.01, 0.01]), 252))  # zero variance


def test_max_drawdown_known_value():
    eq = np.array([110, 120, 90, 100, 130, 117])
    dd, peak, trough = M.max_drawdown(eq, initial=100)
    assert dd == pytest.approx(90 / 120 - 1) and peak == 1 and trough == 2
    dd2, *_ = M.max_drawdown(np.array([90.0, 95.0]), initial=100)
    assert dd2 == pytest.approx(-0.10)  # initial balance counts as the first peak


def test_drawdown_duration():
    eq = np.array([100, 90, 95, 101, 99, 100])
    days = np.array([0, 1, 2, 3, 4, 5.0])
    assert M.drawdown_durations(eq, days) == 3.0  # below 100 from day 0 to day 3


def test_cagr():
    assert M.cagr(0.21, 2.0) == pytest.approx(0.1)
    assert math.isnan(M.cagr(0.5, 1 / 365))
    assert M.cagr(-1.0, 1.0) == -1.0


def test_trade_stats_known_values():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    pnl = [100.0, -50.0, -50.0, 200.0, -25.0, 10.0]
    tr = pl.DataFrame({
        "pnl_net": pnl, "initial_risk": [50.0] * 6, "bars_held": [1, 2, 3, 4, 5, 6],
        "side": [1, 1, -1, -1, 1, 1],
        "entry_ts": [t0] * 6, "exit_ts": [t0 + timedelta(hours=h) for h in (1, 2, 3, 4, 5, 6)],
    })
    s = M.trade_stats(tr)
    assert s["trades"] == 6 and s["win_rate"] == pytest.approx(3 / 6)
    assert s["avg_win"] == pytest.approx(310 / 3) and s["avg_loss"] == pytest.approx(-125 / 3)
    assert s["profit_factor"] == pytest.approx(310 / 125)
    assert s["expectancy"] == pytest.approx(185 / 6)
    assert s["expectancy_r"] == pytest.approx(185 / 6 / 50)
    assert s["payoff_ratio"] == pytest.approx((310 / 3) / (125 / 3))
    assert s["max_consecutive_losses"] == 2 and s["max_consecutive_wins"] == 1
    assert s["avg_holding_hours"] == pytest.approx(3.5)
    assert s["long_trades"] == 4 and s["short_trades"] == 2


def test_profit_factor_edge_cases():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    base = {"initial_risk": [1.0], "bars_held": [1], "side": [1], "entry_ts": [t0], "exit_ts": [t0]}
    assert M.trade_stats(pl.DataFrame({"pnl_net": [5.0], **base}))["profit_factor"] == float("inf")
    assert M.trade_stats(pl.DataFrame({"pnl_net": [-5.0], **base}))["profit_factor"] == 0.0
    assert M.trade_stats(pl.DataFrame(schema={"pnl_net": pl.Float64}))["trades"] == 0


def test_daily_equity_and_monthly_returns():
    t0 = datetime(2024, 1, 31, tzinfo=timezone.utc)
    eq = pl.DataFrame({"ts": [t0, t0 + timedelta(hours=12), t0 + timedelta(days=1), t0 + timedelta(days=30)],
                       "equity": [101.0, 102.0, 110.0, 99.0]})
    d = M.daily_equity(eq, 100.0)
    assert d["equity"].to_list() == [100.0, 102.0, 110.0, 99.0]
    m = M.monthly_returns(eq, 100.0)
    assert m["month"].to_list() == ["2024-01", "2024-02", "2024-03"]
    assert m["ret"].to_list() == pytest.approx([0.02, 110 / 102 - 1, 99 / 110 - 1])


def test_backtest_metrics_consistent_with_equity(tmp_path):
    """End-to-end: metrics reported by a backtest match independent recomputation."""
    from engine_helpers import bars, run
    rng = np.random.default_rng(5)
    n = 24 * 60 * 20  # 20 days of minutes
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    df = bars(np.concatenate([[100], c[:-1]]), c=c)
    script = {"BTCUSDT": {"entry_long": rng.random(n) < 0.002, "exit_long": rng.random(n) < 0.01}}
    r = run(script, {"BTCUSDT": df}, {"fee_bps": 5.0})
    eq = r.equity["equity"].to_numpy()
    assert r.metrics["total_return"] == pytest.approx(eq[-1] / 5000 - 1)
    assert r.metrics["max_drawdown"] == pytest.approx((np.concatenate([[5000], eq]) /
                                                       np.maximum.accumulate(np.concatenate([[5000], eq])) - 1).min())
    assert r.metrics["exposure"] == pytest.approx((r.equity["positions"] > 0).mean())
    assert r.metrics["trades"] == r.trades.height
    assert 300 < r.metrics["daily_periods_per_year"] < 420  # crypto: ~365 daily observations per year
    assert r.monthly.height >= 1
