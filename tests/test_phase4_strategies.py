"""Every Phase 4 strategy must be causal (signals and engine) and produce trades on suitable data."""

from datetime import timedelta

import numpy as np
import pytest

from lab.data import lake, schemas
from lab.engine import lookahead
from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import MarketData
from lab.features.calendar import is_last_session_of_month, session_position
from lab.strategies import phase4 as P
from lab.validation.synthetic import path_bars

HOURLY = timedelta(hours=1)
DAILY = timedelta(days=1)


def _crypto(n=24 * 120, funding=False):
    frames = {}
    for j, s in enumerate(("BTCUSDT", "ETHUSDT")):
        df = path_bars(10 + j, n, vol=0.006, step=HOURLY)
        df = df.with_columns(volume=np.random.default_rng(20 + j).lognormal(10, 0.6, df.height))
        if funding:
            rng = np.random.default_rng(j)
            f = np.where(df["ts"].dt.hour().to_numpy() % 8 == 0, rng.normal(0.0001, 0.0006, df.height), 0.0)
            df = df.with_columns(funding=f)
        frames[s] = df
    return MarketData(list(frames), "1h", frames, market="crypto")


def _business_days(df):
    return df.filter(df["ts"].dt.weekday() <= 5)


def _etfs(symbols=("SPY", "TLT", "GLD", "XLK", "XLF", "XLE"), n=1500):
    frames = {s: _business_days(path_bars(30 + j, n, vol=0.012, step=DAILY)) for j, s in enumerate(symbols)}
    return MarketData(list(frames), "1d", frames, market="equity")


@pytest.fixture
def vix_lake():
    for j, s in enumerate(("IDX_VIX", "IDX_VIX3M")):
        df = path_bars(50 + j, 1500, vol=0.06, step=DAILY, p0=20.0)
        lake.write_chunk(lake.DatasetKey("macro", "yahoo", s, "bars_1d"), "all", schemas.conform(df, "bars"))


CASES = {
    "fade_extreme_move": (lambda: P.FadeExtremeMove(k=2.0), lambda: _crypto(), RiskConfig(max_bars_held=4, sizing="pct_equity")),
    "funding_contrarian": (lambda: P.FundingContrarian(threshold=0.0005), lambda: _crypto(funding=True), RiskConfig(sizing="pct_equity")),
    "session_window": (lambda: P.SessionWindow(session="us"), lambda: _crypto(), RiskConfig(sizing="pct_equity")),
    "weekend_hold": (lambda: P.WeekendHold(), lambda: _crypto(), RiskConfig(sizing="pct_equity")),
    "daily_range_breakout": (lambda: P.DailyRangeBreakout(k=0.3), lambda: _crypto(), RiskConfig(sizing="pct_equity")),
    "volume_shock": (lambda: P.VolumeShock(vol_z=-10, ret_z=1.5), lambda: _crypto(), RiskConfig(max_bars_held=3, sizing="pct_equity")),
    "trend_filter": (lambda: P.TrendFilter(n=50, allow_short=True), lambda: _crypto(), RiskConfig(sizing="pct_equity")),
    "lead_lag": (lambda: P.LeadLag(z=1.0), lambda: _crypto(), RiskConfig(max_bars_held=1, sizing="pct_equity")),
    "pair_reversion": (lambda: P.PairReversion(n=48, entry_z=1.5), lambda: _crypto(), RiskConfig(sizing="pct_equity", position_pct=0.5)),
    "rsi2_reversion": (lambda: P.RsiReversion(trend_n=50, entry_rsi=20), lambda: _etfs(("SPY",)), RiskConfig(sizing="pct_equity")),
    "turn_of_month": (lambda: P.TurnOfMonth(), lambda: _etfs(("SPY",)), RiskConfig(sizing="pct_equity")),
    "vix_term_structure": (lambda: P.VixTermStructure(), lambda: _etfs(("SPY",)), RiskConfig(sizing="pct_equity")),
    "vix_spike": (lambda: P.VixSpike(spike=1.05), lambda: _etfs(("SPY",)), RiskConfig(max_bars_held=10, sizing="pct_equity")),
    "low_vol_regime": (lambda: P.LowVolTrend(median_n=100), lambda: _etfs(("SPY",)), RiskConfig(sizing="pct_equity")),
    "sector_momentum": (lambda: P.SectorMomentum(lookback=63, skip=0, top=2), lambda: _etfs(), RiskConfig(sizing="pct_equity", position_pct=0.5)),
    "dual_momentum": (lambda: P.DualMomentum(lookback=63), lambda: _etfs(("SPY", "TLT", "GLD")), RiskConfig(sizing="pct_equity")),
}


def test_all_phase4_strategies_have_cases():
    assert set(CASES) == set(P.PHASE4)


@pytest.mark.parametrize("name", list(CASES))
def test_phase4_strategy_is_causal_and_trades(name, vix_lake):
    make, data_fn, risk = CASES[name]
    data = data_fn()
    profile = "crypto_perp" if data.market == "crypto" else None
    ex = ExecutionConfig(cost_profile=profile)
    rep = lookahead.check_strategy(make(), data)
    assert rep.passed, rep.failures
    eng = lookahead.check_engine(make(), data, lambda s, d: run_backtest(s, d, risk, ex))
    assert eng.passed, eng.failures
    res = run_backtest(make(), data, risk, ex)
    assert res.trades.height > 0, f"{name} produced no trades on test data"


def test_calendar_month_positions():
    import polars as pl
    from datetime import datetime, timezone
    ts = pl.Series([datetime(2024, 1, d, tzinfo=timezone.utc) for d in (2, 3, 30, 31)])
    first, last = session_position(ts)
    assert first[0] == 1 and first[1] == 2       # Jan 1 2024 is a holiday
    assert last[-1] == 1 and last[-2] == 2
    assert is_last_session_of_month(ts).tolist() == [False, False, False, True]


def test_turn_of_month_trades_at_month_end():
    data = _etfs(("SPY",), 400)
    res = run_backtest(P.TurnOfMonth(days_after=3), data, RiskConfig(sizing="pct_equity"),
                       ExecutionConfig())
    first, last = session_position(res.trades["entry_ts"])
    assert (last == 1).all()                     # entries fill on the month's last session
    fx, _ = session_position(res.trades["exit_ts"].filter(res.trades["exit_reason"] == "signal"))
    assert (fx == 4).all()                       # exits fill on the 4th session of the new month
