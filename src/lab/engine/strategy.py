"""Strategy interface.

A strategy turns each instrument's own bars into signal arrays. It never places orders
or sees fills: the engine decides when and at what price orders execute.

Subclasses implement `signals(df, symbol)` returning a dict with any of:
    entry_long, entry_short, exit_long, exit_short : bool arrays
    stop_dist, target_dist, trail_dist             : price distances (NaN = none),
                                                     measured from the entry fill price
    priority                                       : float, higher fills first when
                                                     buying power is limited
All arrays have one value per row of `df`; row t may only use rows 0..t
(enforced by tests via lab.engine.lookahead.check_strategy).
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass

import numpy as np
import polars as pl

from lab.engine.data import MarketData

SIGNAL_KEYS = ("entry_long", "entry_short", "exit_long", "exit_short")
LEVEL_KEYS = ("stop_dist", "target_dist", "trail_dist", "priority")


@dataclass
class SignalGrid:
    entry_long: np.ndarray
    entry_short: np.ndarray
    exit_long: np.ndarray
    exit_short: np.ndarray
    stop_dist: np.ndarray
    target_dist: np.ndarray
    trail_dist: np.ndarray
    priority: np.ndarray


class Strategy:
    """Base class. Set `name`, `version` and `default_params`; implement `signals`."""

    name: str = "strategy"
    version: str = "1"
    default_params: dict = {}
    style: str = "unspecified"  # scalping | intraday | swing | trend | mean_reversion | ...

    def __init__(self, **params):
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: unknown parameters {unknown}")
        self.params = {**self.default_params, **params}

    def signals(self, df: pl.DataFrame, symbol: str) -> dict[str, np.ndarray]:
        raise NotImplementedError

    def generate(self, data: MarketData) -> SignalGrid:
        per = {s: self.signals(data.frames[s], s) for s in data.symbols}
        out = {}
        for k in SIGNAL_KEYS:
            g = data.scatter({s: _as_bool(v.get(k)) for s, v in per.items()}, False, np.bool_)
            out[k] = g
        for k in LEVEL_KEYS:
            out[k] = data.scatter({s: v.get(k) for s, v in per.items()}, 0.0 if k == "priority" else np.nan,
                                  np.float64)
        return SignalGrid(**out)

    @property
    def code_hash(self) -> str:
        """Hash of the strategy's source code: changes whenever its logic changes."""
        src = "".join(inspect.getsource(c) for c in type(self).__mro__
                      if c not in (object, Strategy) and c.__module__ != "builtins")
        return hashlib.sha256(src.encode()).hexdigest()[:12]

    @property
    def strategy_version(self) -> str:
        return f"{self.version}+{self.code_hash}"

    def describe(self) -> dict:
        return {"name": self.name, "version": self.strategy_version, "style": self.style, "params": self.params}


def _as_bool(v):
    if v is None:
        return None
    a = np.asarray(v)
    if a.dtype != np.bool_:
        a = np.nan_to_num(a.astype(np.float64), nan=0.0) != 0
    return a


# ----------------------------------------------------------------- context (non-traded inputs)

def load_context(symbol: str, until_us: int) -> pl.DataFrame:
    """Daily bars of a context series (e.g. IDX_VIX), restricted to dates up to `until_us`.

    Restricting to the traded data's last timestamp means context never extends into later
    research partitions (no vault leakage) and is truncated together with the data in
    look-ahead checks.
    """
    from lab import instruments
    from lab.data import lake
    inst = instruments.get(symbol)
    key = lake.DatasetKey(inst.asset_class, inst.source, symbol, "bars_1d")
    df = lake.scan(key).select("ts", "open", "high", "low", "close").collect()
    return df.filter(pl.col("ts").dt.epoch("us") <= until_us)


def asof_daily(bar_ts: pl.Series, daily: pl.DataFrame, column: str = "close", same_day: bool = True,
               bar_is_daily: bool = True) -> np.ndarray:
    """Value of a daily series known at each bar's close.

    For daily bars (`bar_is_daily`), the context value of the same date is allowed when
    `same_day=True` (e.g. VIX close at 16:15 ET is known before the next US open, where orders
    fill). For intraday bars, only fully completed previous days are used.
    """
    d = daily.select("ts", pl.col(column).alias("_v")).sort("ts")
    if not (bar_is_daily and same_day):
        d = d.with_columns(pl.col("ts") + pl.duration(days=1))  # available from the next day
    left = pl.DataFrame({"ts": bar_ts}).with_row_index("_i")
    j = left.sort("ts").join_asof(d, on="ts", strategy="backward").sort("_i")
    return j["_v"].to_numpy().astype(np.float64)


class ContextStrategy(Strategy):
    """Strategy that also reads non-traded daily series (VIX, yields, ...): `context_symbols`."""

    context_symbols: tuple = ()

    def generate(self, data: MarketData) -> SignalGrid:
        until = int(data.ts[-1])
        self.context = {c: load_context(c, until) for c in self.context_symbols}
        return super().generate(data)


class PortfolioStrategy(Strategy):
    """Strategy that sees all instruments at once on the common grid (rotation, pairs, lead-lag).

    Implement `portfolio_signals(data, closes)` returning a dict of (T, N) arrays with the same
    keys as `signals`. `closes` is the (T, N) close grid, forward-filled, NaN before each
    instrument's first bar. Row t may only use rows <= t.
    """

    def portfolio_signals(self, data: MarketData, closes: np.ndarray) -> dict:
        raise NotImplementedError

    def generate(self, data: MarketData) -> SignalGrid:
        raw = data.grid("close")
        closes = pl.DataFrame(raw, schema=data.symbols, orient="row").fill_nan(None).fill_null(strategy="forward").to_numpy()
        closes = np.where(np.isnan(closes), np.nan, closes).astype(np.float64)
        out = self.portfolio_signals(data, closes)
        T, N = raw.shape
        valid = data.valid()
        res = {}
        for k in SIGNAL_KEYS:
            v = out.get(k)
            res[k] = (np.zeros((T, N), dtype=bool) if v is None else _as_bool(v).reshape(T, N)) & valid
        for k in LEVEL_KEYS:
            v = out.get(k)
            fill = 0.0 if k == "priority" else np.nan
            res[k] = np.full((T, N), fill) if v is None else np.asarray(v, dtype=np.float64).reshape(T, N)
        return SignalGrid(**res)
