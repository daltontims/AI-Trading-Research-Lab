"""Helpers for engine tests: synthetic bars and scripted strategies with known answers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl

from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.engine.data import MarketData, standardize
from lab.engine.strategy import Strategy

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)

ZERO_COSTS = dict(fee_bps=0.0, maker_fee_bps=0.0, sell_fee_bps=0.0, fee_per_unit=0.0, min_fee=0.0,
                  half_spread_bps=0.0, spread_markup_bps=0.0, slippage_bps=0.0, slippage_range_frac=0.0,
                  borrow_rate_annual=0.0, financing_rate_annual=0.0, max_participation=1.0, allow_short=True,
                  lot_size=0.0, min_notional=0.0, funding=False)


def bars(o, h=None, l=None, c=None, v=None, start=T0, step=timedelta(minutes=1), skip=(), **extra) -> pl.DataFrame:
    """Build standardized bars. If only `o` is given, h=l=c=o. `skip` removes rows (missing bars)."""
    o = np.asarray(o, dtype=float)
    c = np.asarray(c if c is not None else o, dtype=float)
    h = np.asarray(h if h is not None else np.maximum(o, c), dtype=float)
    l = np.asarray(l if l is not None else np.minimum(o, c), dtype=float)
    v = np.asarray(v if v is not None else np.full(len(o), 1e9), dtype=float)
    ts = [start + i * step for i in range(len(o))]
    df = pl.DataFrame({"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v,
                       **{k: np.asarray(val, dtype=float) for k, val in extra.items()}})
    df = standardize(df)
    if skip:
        df = df.with_row_index("i").filter(~pl.col("i").is_in(list(skip))).drop("i")
    return df


def market(frames: dict[str, pl.DataFrame], timeframe="1m") -> MarketData:
    return MarketData(list(frames), timeframe, frames)


class Scripted(Strategy):
    """Signals given explicitly per symbol (aligned with that symbol's own bars)."""

    name = "scripted"

    def __init__(self, script: dict[str, dict]):
        super().__init__()
        self.script = script

    def signals(self, df, symbol):
        n = df.height
        out = {}
        for k, v in self.script.get(symbol, {}).items():
            if isinstance(v, dict):  # {row: value}
                arr = np.zeros(n, dtype=bool) if k.startswith(("entry", "exit")) else np.full(n, np.nan)
                for i, val in v.items():
                    arr[i] = val
                out[k] = arr
            else:
                out[k] = np.asarray(v)
        return out


def run(script, frames, costs=None, timeframe="1m", **risk_kw):
    data = market(frames, timeframe)
    risk = RiskConfig(**{"sizing": "pct_equity", "position_pct": 1.0, **risk_kw})
    ex = ExecutionConfig(cost_overrides={**ZERO_COSTS, **(costs or {})})
    return run_backtest(Scripted(script), data, risk, ex)
