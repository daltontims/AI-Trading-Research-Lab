"""Known-answer tests for fills, exits, costs and portfolio accounting."""

from datetime import timedelta

import numpy as np
import pytest

from engine_helpers import bars, run

S = "BTCUSDT"


def test_profitable_long_fills_at_next_open():
    # Signal on bar 0 (close 100) -> buy at bar 1 OPEN (101). Exit signal bar 2 -> sell at bar 3 open (120).
    df = bars(o=[100, 101, 110, 120, 125], c=[100, 108, 115, 122, 125])
    r = run({S: {"entry_long": {0: True}, "exit_long": {2: True}}}, {S: df})
    t = r.trades.row(0, named=True)
    qty = 5000 / 101  # all cash at the fill price (no costs)
    assert t["entry_price"] == pytest.approx(101) and t["exit_price"] == pytest.approx(120)
    assert t["qty"] == pytest.approx(qty)
    assert t["pnl_net"] == pytest.approx(qty * 19)
    assert r.metrics["final_equity"] == pytest.approx(5000 + qty * 19)
    assert t["exit_reason"] == "signal" and t["bars_held"] == 2


def test_losing_long_and_metrics():
    df = bars(o=[100, 100, 90, 80, 80])
    r = run({S: {"entry_long": {0: True}, "exit_long": {1: True}}}, {S: df})
    assert r.trades["pnl_net"][0] == pytest.approx(5000 / 100 * (90 - 100))
    assert r.metrics["win_rate"] == 0 and r.metrics["total_return"] == pytest.approx(-0.1)


def test_signal_never_fills_at_signal_bar_close():
    # Bar 0 closes at 200 (a spike). A strategy buying on that signal must pay the next open.
    df = bars(o=[100, 150, 150], c=[200, 150, 150], h=[200, 150, 150], l=[100, 150, 150])
    r = run({S: {"entry_long": {0: True}}}, {S: df})
    assert r.trades["entry_price"][0] == 150
    assert r.trades["entry_ts"][0] == df["ts"][1]


def test_stop_loss_exact_and_gap():
    # Long at 100 (bar 1 open), stop distance 5 -> stop 95. Bar 2 trades down to 94 -> exit at 95.
    df = bars(o=[100, 100, 99, 90], h=[100, 101, 99, 90], l=[100, 99, 94, 90], c=[100, 100, 96, 90])
    r = run({S: {"entry_long": {0: True}, "stop_dist": {0: 5.0}}}, {S: df})
    t = r.trades.row(0, named=True)
    assert t["exit_reason"] == "stop" and t["exit_price"] == pytest.approx(95)
    # Gap: bar 2 opens at 90, below the stop -> filled at the open (worse than the stop).
    df2 = bars(o=[100, 100, 90, 90], h=[100, 101, 92, 90], l=[100, 99, 88, 90], c=[100, 100, 91, 90])
    t2 = run({S: {"entry_long": {0: True}, "stop_dist": {0: 5.0}}}, {S: df2}).trades.row(0, named=True)
    assert t2["exit_price"] == pytest.approx(90) and t2["exit_reason"] == "stop"


def test_profit_target_and_pessimistic_same_bar_rule():
    df = bars(o=[100, 100, 104], h=[100, 101, 111], l=[100, 99, 103], c=[100, 100, 109])
    r = run({S: {"entry_long": {0: True}, "stop_dist": {0: 5.0}, "target_dist": {0: 10.0}}}, {S: df})
    t = r.trades.row(0, named=True)
    assert t["exit_reason"] == "target" and t["exit_price"] == pytest.approx(110)
    # Both stop (95) and target (110) inside one bar: assume the stop happened first.
    df2 = bars(o=[100, 100, 100], h=[100, 101, 112], l=[100, 99, 94], c=[100, 100, 105])
    t2 = run({S: {"entry_long": {0: True}, "stop_dist": {0: 5.0}, "target_dist": {0: 10.0}}},
             {S: df2}).trades.row(0, named=True)
    assert t2["exit_reason"] == "stop" and t2["exit_price"] == pytest.approx(95)


def test_target_requires_trade_through_by_half_spread_and_no_gap_improvement():
    # Half-spread 10 bps: target 110 needs a high >= 110.11. A high of exactly 110 does not fill.
    df = bars(o=[100, 100, 105, 120], h=[100, 101, 110, 125], l=[100, 99, 104, 119], c=[100, 100, 106, 121])
    costs = {"half_spread_bps": 10.0}
    r = run({S: {"entry_long": {0: True}, "target_dist": {0: 10.0}}}, {S: df}, costs)
    t = r.trades.row(0, named=True)
    entry = 100 * 1.001
    assert t["entry_price"] == pytest.approx(entry)
    # Bar 3 gaps up to 120: the resting limit fills at the target price, not the better open.
    assert t["exit_reason"] == "target" and t["exit_price"] == pytest.approx(entry + 10.0)


def test_trailing_stop_uses_only_completed_bars():
    # Entry at 100, trail 5. Bar 2 high 120 (trail -> 115 from bar 3). Bar 2's own low 114 must NOT
    # trigger the 115 level within the same bar (the high's timing inside the bar is unknown).
    o = [100, 100, 110, 118, 116]
    h = [100, 101, 120, 119, 117]
    l = [100, 99, 114, 117, 113]
    c = [100, 100, 118, 118, 114]
    r = run({S: {"entry_long": {0: True}, "trail_dist": {0: 5.0}}}, {S: bars(o, h, l, c)})
    t = r.trades.row(0, named=True)
    assert t["exit_reason"] == "trailing_stop"
    assert t["exit_ts"] == bars(o)["ts"][4] and t["exit_price"] == pytest.approx(115)


def test_short_profit_and_borrow_cost():
    # Daily bars, short 1 unit-equivalent of equity at 100, cover at 90 after 2 days with 10% borrow.
    step = timedelta(days=1)
    df = bars(o=[100, 100, 95, 90, 90], step=step)
    r = run({S: {"entry_short": {0: True}, "exit_short": {2: True}}}, {S: df},
            costs={"borrow_rate_annual": 0.10}, timeframe="1d")
    t = r.trades.row(0, named=True)
    qty = 5000 / 100
    dt = 1 / 365.25
    borrow = qty * 100 * 0.10 * dt + qty * 95 * 0.10 * dt  # charged at bar 1 and bar 2 closes
    assert t["side"] == -1 and t["pnl_gross"] == pytest.approx(qty * 10)
    assert t["carry"] == pytest.approx(-borrow)
    assert t["pnl_net"] == pytest.approx(qty * 10 - borrow)
    assert r.metrics["final_equity"] == pytest.approx(5000 + qty * 10 - borrow)


def test_transaction_costs_exact():
    # fee 10 bps, half-spread 5 bps, slippage 2 bps per side.
    df = bars(o=[100, 100, 110, 110])
    costs = {"fee_bps": 10.0, "half_spread_bps": 5.0, "slippage_bps": 2.0}
    r = run({S: {"entry_long": {0: True}, "exit_long": {1: True}}}, {S: df}, costs)
    t = r.trades.row(0, named=True)
    buy = 100 * (1 + 0.0007)
    sell = 110 * (1 - 0.0007)
    qty = 5000 / (buy * 1.001)  # cash must cover price + fee
    fees = qty * buy * 0.001 + qty * sell * 0.001
    assert t["entry_price"] == pytest.approx(buy) and t["exit_price"] == pytest.approx(sell)
    assert t["qty"] == pytest.approx(qty)
    assert t["fees"] == pytest.approx(fees)
    assert t["pnl_net"] == pytest.approx(qty * (sell - buy) - fees)
    assert r.metrics["final_equity"] == pytest.approx(5000 + t["pnl_net"])
    assert r.metrics["total_fees"] == pytest.approx(fees)


def test_cost_multiplier_scales_costs():
    df = bars(o=[100, 100, 110, 110])
    base = run({S: {"entry_long": {0: True}, "exit_long": {1: True}}}, {S: df}, {"fee_bps": 10.0})
    from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
    from engine_helpers import Scripted, ZERO_COSTS, market
    worse = run_backtest(Scripted({S: {"entry_long": {0: True}, "exit_long": {1: True}}}), market({S: df}),
                         RiskConfig(sizing="pct_equity"),
                         ExecutionConfig(cost_overrides={**ZERO_COSTS, "fee_bps": 10.0}, cost_multiplier=2.0))
    assert worse.trades["fees"][0] == pytest.approx(base.trades["fees"][0] * 2, rel=1e-3)
    assert worse.metrics["final_equity"] < base.metrics["final_equity"]


def test_funding_payments():
    # Long through a funding time with rate +0.01% -> pays qty * price * rate. Short receives.
    df = bars(o=[100, 100, 100, 100], funding=[0, 0, 0.0001, 0])
    for side, sign in (("long", -1), ("short", +1)):
        r = run({S: {f"entry_{side}": {0: True}}}, {S: df}, {"funding": True})
        qty = 5000 / 100
        assert r.trades["carry"][0] == pytest.approx(sign * qty * 100 * 0.0001)
    # Funding is ignored for spot profiles.
    r = run({S: {"entry_long": {0: True}}}, {S: df}, {"funding": False})
    assert r.trades["carry"][0] == 0


def test_dividends_credited_to_longs_debited_to_shorts():
    step = timedelta(days=1)
    df = bars(o=[100, 100, 100, 100], dividend=[0, 0, 1.0, 0], step=step)
    rl = run({"SPY": {"entry_long": {0: True}}}, {"SPY": df}, timeframe="1d")
    rs = run({"SPY": {"entry_short": {0: True}}}, {"SPY": df}, timeframe="1d")
    assert rl.trades["carry"][0] == pytest.approx(50.0)
    assert rs.trades["carry"][0] == pytest.approx(-50.0)


def test_missing_bars_fill_at_next_available_bar_and_gaps_hit_stops():
    # Bars 2-3 missing. Signal at bar 1 fills at bar 4's open, never at a missing bar.
    df = bars(o=[100, 100, 999, 999, 80, 80], skip=(2, 3))
    r = run({S: {"entry_long": {1: True}}}, {S: df})
    t = r.trades.row(0, named=True)
    assert t["entry_price"] == 80 and t["entry_ts"] == df["ts"][2]
    # A position open across missing bars is stopped at the first bar after the gap, at its open.
    df2 = bars(o=[100, 100, 100, 999, 70, 70], skip=(3,))
    t2 = run({S: {"entry_long": {0: True}, "stop_dist": {0: 5.0}}}, {S: df2}).trades.row(0, named=True)
    assert t2["exit_reason"] == "stop" and t2["exit_price"] == 70


def test_multiple_positions_respect_exposure_and_priority():
    a = bars(o=[100, 100, 100])
    b = bars(o=[50, 50, 50])
    script = {"BTCUSDT": {"entry_long": {0: True}, "priority": {0: 1.0}},
              "ETHUSDT": {"entry_long": {0: True}, "priority": {0: 2.0}}}
    r = run(script, {"BTCUSDT": a, "ETHUSDT": b}, position_pct=0.6)
    n = {row["symbol"]: row["notional"] for row in r.trades.iter_rows(named=True)}
    # ETH has priority: gets 60%; BTC is capped by the 100% gross exposure / cash limit to 40%.
    assert n["ETHUSDT"] == pytest.approx(3000) and n["BTCUSDT"] == pytest.approx(2000)
    r2 = run(script, {"BTCUSDT": a, "ETHUSDT": b}, position_pct=0.6, max_open_positions=1)
    assert r2.trades.height == 1 and r2.trades["symbol"][0] == "ETHUSDT"
    assert r2.skipped["max_open_positions"] == 1


def test_risk_based_position_sizing_and_lots():
    df = bars(o=[100, 100, 100])
    r = run({S: {"entry_long": {0: True}, "stop_dist": {0: 2.0}}}, {S: df}, sizing="risk", risk_per_trade=0.01)
    assert r.trades["qty"][0] == pytest.approx(5000 * 0.01 / 2.0)  # 25 units, $50 at risk
    assert r.trades["initial_risk"][0] == pytest.approx(50.0)
    r2 = run({S: {"entry_long": {0: True}, "stop_dist": {0: 3.0}}}, {S: df}, {"lot_size": 1.0},
             sizing="risk", risk_per_trade=0.01)
    assert r2.trades["qty"][0] == 16  # 16.67 rounded down to whole units
    # Risk sizing without a stop is refused (no silent full-size positions).
    r3 = run({S: {"entry_long": {0: True}}}, {S: df}, sizing="risk")
    assert r3.trades.height == 0 and r3.skipped["no_stop_for_risk_sizing"] == 1
    # Position cap and min notional
    r4 = run({S: {"entry_long": {0: True}}}, {S: df}, max_position_pct=0.25)
    assert r4.trades["notional"][0] == pytest.approx(1250)
    r5 = run({S: {"entry_long": {0: True}}}, {S: df}, {"min_notional": 2000}, max_position_pct=0.25)
    assert r5.trades.height == 0


def test_liquidity_cap_and_short_permission():
    df = bars(o=[100, 100, 100], v=[10, 10, 10])
    r = run({S: {"entry_long": {0: True}}}, {S: df}, {"max_participation": 0.1})
    assert r.trades["qty"][0] == pytest.approx(1.0)  # 10% of the signal bar's volume
    r2 = run({S: {"entry_short": {0: True}}}, {S: df}, {"allow_short": False})
    assert r2.trades.height == 0 and r2.skipped["short_not_allowed"] == 1


def test_daily_loss_limit_flattens_and_blocks():
    # Day 1: entry, then -5% -> limit 3% hit -> exit next bar, new entries blocked that day.
    o = [100, 100, 95, 95, 95, 95]
    df = bars(o=o)
    r = run({S: {"entry_long": {0: True, 3: True}}}, {S: df}, max_daily_loss=0.03)
    assert r.trades.height == 1 and r.trades["exit_reason"][0] == "daily_loss_limit"
    assert r.skipped.get("risk_limit_block", 0) >= 1


def test_max_drawdown_halt():
    df = bars(o=[100, 100, 70, 70, 100, 100])
    r = run({S: {"entry_long": {0: True, 4: True}}}, {S: df}, max_drawdown=0.2)
    assert r.trades.height == 1 and r.trades["exit_reason"][0] == "max_drawdown_limit"


def test_time_exit_and_delay():
    df = bars(o=list(range(100, 110)))
    r = run({S: {"entry_long": {0: True}}}, {S: df}, max_bars_held=3)
    t = r.trades.row(0, named=True)
    assert t["exit_reason"] == "time" and t["bars_held"] == 3
    from lab.engine.backtest import ExecutionConfig
    with pytest.raises(ValueError):
        ExecutionConfig(delay_bars=0)


def test_futures_multiplier_and_per_contract_fees():
    df = bars(o=[5000, 5000, 5010, 5010])
    script = {"MES": {"entry_long": {0: True}, "exit_long": {1: True}}}
    costs = {"fee_per_unit": 1.25, "lot_size": 1.0}
    # One micro contract is $25,000 of exposure: impossible for $5,000 without leverage (the default).
    r0 = run(script, {"MES": df}, costs, sizing="fixed_notional", fixed_notional=25000)
    assert r0.trades.height == 0
    # Explicitly allowing 6x gross exposure (futures margin) makes it possible.
    r = run(script, {"MES": df}, costs, sizing="fixed_notional", fixed_notional=25000,
            max_gross_exposure=6.0, max_position_pct=6.0)
    t = r.trades.row(0, named=True)
    assert t["qty"] == 1  # one contract = $25,000 notional (5000 x $5)
    assert t["pnl_net"] == pytest.approx(10 * 5 - 2 * 1.25)


def test_reversal_closes_and_reopens():
    df = bars(o=[100, 100, 110, 100, 100])
    r = run({S: {"entry_long": {0: True}, "entry_short": {1: True}}}, {S: df})
    assert list(r.trades["side"]) == [1, -1]
    assert r.trades["exit_ts"][0] == r.trades["entry_ts"][1]


def test_accounting_identity_with_all_cost_types():
    """Final equity − initial == sum of trade net P&L, with fees, spread, slippage, borrow, funding."""
    rng = np.random.default_rng(3)
    n = 3000
    frames = {}
    for s, p0 in (("BTCUSDT", 100.0), ("ETHUSDT", 50.0)):
        c = p0 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
        o = np.concatenate([[p0], c[:-1]]) * np.exp(rng.normal(0, 0.0005, n))
        h = np.maximum(o, c) * 1.001
        l = np.minimum(o, c) * 0.999
        fund = np.where(np.arange(n) % 480 == 0, rng.normal(0.0001, 0.0002, n), 0.0)
        frames[s] = bars(o, h, l, c, v=np.full(n, 1e6), funding=fund, skip=tuple(rng.choice(n, 50, replace=False)))
    script = {s: {"entry_long": rng.random(frames[s].height) < 0.01,
                  "entry_short": rng.random(frames[s].height) < 0.01,
                  "exit_long": rng.random(frames[s].height) < 0.02,
                  "exit_short": rng.random(frames[s].height) < 0.02,
                  "stop_dist": np.full(frames[s].height, 1.0),
                  "trail_dist": np.full(frames[s].height, 1.5)} for s in frames}
    costs = {"fee_bps": 7.0, "half_spread_bps": 3.0, "slippage_bps": 1.0, "slippage_range_frac": 0.1,
             "borrow_rate_annual": 0.05, "funding": True, "lot_size": 0.001, "min_notional": 10}
    r = run(script, frames, costs, position_pct=0.4)
    assert r.trades.height > 50
    assert r.metrics["final_equity"] - 5000 == pytest.approx(r.trades["pnl_net"].sum(), abs=1e-6)
    # Gross P&L minus costs plus carry equals net P&L, trade by trade.
    spread_slip = ((r.trades["entry_price"] - r.trades["entry_ref"]).abs()
                   + (r.trades["exit_price"] - r.trades["exit_ref"]).abs()) * r.trades["qty"]
    recon = r.trades["pnl_gross"] - spread_slip - r.trades["fees"] + r.trades["carry"]
    # Targets/limits have zero spread cost; all others pay it: reconciliation is exact for this script.
    assert np.allclose(recon.to_numpy(), r.trades["pnl_net"].to_numpy(), atol=1e-8)
    assert (r.equity["gross_exposure"] <= 1.0 + 1e-9).all()
