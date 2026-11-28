"""Rule templates for the discovery engine (Phase 5).

A discovery strategy is assembled from three building blocks:

    entry condition (1 parameter x)  +  trend filter (fixed per hypothesis)  +  exit rule (1 parameter y)

so every generated hypothesis has at most two tunable parameters (protocol §6 allows four).
All conditions use completed bars only; the engine fills at the next bar's open, and every
generated strategy is checked for look-ahead by the evaluation pipeline.

Long-only by design: the $5,000 account trades ETFs and spot crypto without leverage or shorting.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lab.engine.strategy import Strategy
from lab.features import indicators as ind


# ----------------------------------------------------------------------- entry conditions
def _streak_down(c: np.ndarray) -> np.ndarray:
    """Number of consecutive closes below the previous close, ending at each bar."""
    out = np.zeros(len(c))
    for t in range(1, len(c)):
        out[t] = out[t - 1] + 1 if c[t] < c[t - 1] else 0
    return out


def _ibs(df) -> np.ndarray:
    h, lo, c = (df[k].to_numpy() for k in ("high", "low", "close"))
    rng = h - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(rng > 0, (c - lo) / rng, 0.5)


def entry_signal(kind: str, df, x: float) -> np.ndarray:
    c = df["close"].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        if kind == "rsi2_low":                       # short-term oversold
            return ind.rsi(c, 2) < x
        if kind == "n_day_low":                      # lowest close of the last x bars
            return c <= ind.rolling_min(c, int(x))
        if kind == "down_streak":                    # x or more consecutive down closes
            return _streak_down(c) >= x
        if kind == "drop_z":                         # one-bar drop beyond x standard deviations
            r = ind.log_returns(c)
            return r / ind.shift(ind.rolling_std(r, 60), 1) < -x
        if kind == "ibs_low":                        # close near the bar's low
            return _ibs(df) < x
        if kind == "n_day_high":                     # breakout: highest close of the last x bars
            return c >= ind.rolling_max(c, int(x))
        if kind == "ma_cross_up":                    # close crosses above its x-bar average
            return ind.cross_above(c, ind.sma(c, int(x)))
    raise ValueError(f"unknown entry {kind}")


def trend_filter(kind: str, df) -> np.ndarray:
    c = df["close"].to_numpy()
    if kind == "none":
        return np.ones(len(c), dtype=bool)
    ma = ind.sma(c, 200)
    with np.errstate(invalid="ignore"):
        if kind == "up":
            return c > ma
        if kind == "down":
            return c < ma
    raise ValueError(f"unknown filter {kind}")


def exit_signal(kind: str, df, y: float, entry: np.ndarray) -> np.ndarray:
    c = df["close"].to_numpy()
    with np.errstate(invalid="ignore"):
        if kind == "hold_bars":                      # y bars after the most recent entry trigger
            idx = np.where(entry, np.arange(len(c)), -1)
            last = np.maximum.accumulate(idx)
            return (last >= 0) & (np.arange(len(c)) - last >= y)
        if kind == "close_above_ma":                 # mean reverted: close back above its y-bar average
            return c > ind.sma(c, int(y))
        if kind == "rsi2_high":
            return ind.rsi(c, 2) > y
        if kind == "close_below_ma":                 # trend over: close below its y-bar average
            return c < ind.sma(c, int(y))
        if kind == "n_day_low_exit":                 # trailing channel: lowest close of y bars
            return c <= ind.rolling_min(c, int(y))
    raise ValueError(f"unknown exit {kind}")


# ----------------------------------------------------------------------- catalogue
@dataclass(frozen=True)
class EntryKind:
    name: str
    grid: tuple
    style: str
    exits: tuple          # exit kinds that make sense for this entry
    describe: str


@dataclass(frozen=True)
class ExitKind:
    name: str
    grid: tuple
    describe: str


ENTRIES = {
    "rsi2_low": EntryKind("rsi2_low", (5.0, 10.0, 20.0), "mean_reversion", ("hold_bars", "close_above_ma"),
                          "2-bar RSI below x (short-term oversold)"),
    "n_day_low": EntryKind("n_day_low", (5, 10, 20), "mean_reversion", ("hold_bars", "close_above_ma"),
                           "close is the lowest of the last x bars"),
    "down_streak": EntryKind("down_streak", (2, 3, 4), "mean_reversion", ("hold_bars", "close_above_ma"),
                             "x or more consecutive down closes"),
    "drop_z": EntryKind("drop_z", (1.5, 2.0, 2.5), "mean_reversion", ("hold_bars", "close_above_ma"),
                        "one-bar drop larger than x standard deviations (60-bar volatility)"),
    "ibs_low": EntryKind("ibs_low", (0.1, 0.2, 0.3), "mean_reversion", ("hold_bars", "close_above_ma"),
                         "close in the bottom x of the bar's high-low range"),
    "n_day_high": EntryKind("n_day_high", (20, 55, 120), "trend", ("close_below_ma", "n_day_low_exit"),
                            "close is the highest of the last x bars (breakout)"),
    "ma_cross_up": EntryKind("ma_cross_up", (20, 50, 100), "trend", ("close_below_ma", "n_day_low_exit"),
                             "close crosses above its x-bar average"),
}

EXITS = {
    "hold_bars": ExitKind("hold_bars", (3, 5, 10), "exit y bars after the last entry trigger"),
    "close_above_ma": ExitKind("close_above_ma", (5, 10), "exit when the close is back above its y-bar average"),
    "close_below_ma": ExitKind("close_below_ma", (20, 50), "exit when the close falls below its y-bar average"),
    "n_day_low_exit": ExitKind("n_day_low_exit", (10, 20), "exit at the lowest close of the last y bars"),
}

FILTERS = {"none": "no trend filter", "up": "only above the 200-bar average",
           "down": "only below the 200-bar average"}

# Event-study horizon (bars) used to screen each entry family before any backtest.
HORIZON = {"mean_reversion": 5, "trend": 20}

_CLASSES: dict[tuple, type] = {}


class RuleStrategy(Strategy):
    """Base of generated rule strategies. Their code is this module, so the version hash covers it."""

    @property
    def code_hash(self) -> str:
        import hashlib
        import inspect
        import sys
        src = inspect.getsource(sys.modules[__name__]) + self.name
        return hashlib.sha256(src.encode()).hexdigest()[:12]


def rule_strategy(entry: str, filt: str, exit_: str) -> type:
    """A Strategy class for one (entry, filter, exit) combination, with parameters x and y."""
    key = (entry, filt, exit_)
    if key in _CLASSES:
        return _CLASSES[key]
    e, x = ENTRIES[entry], EXITS[exit_]

    def signals(self, df, symbol):
        en = entry_signal(entry, df, self.params["x"]) & trend_filter(filt, df)
        en = np.nan_to_num(en.astype(float), nan=0.0).astype(bool)
        ex = exit_signal(exit_, df, self.params["y"], en)
        return {"entry_long": en, "exit_long": np.nan_to_num(ex.astype(float), nan=0.0).astype(bool)}

    cls = type(f"Rule_{entry}_{filt}_{exit_}", (RuleStrategy,), {
        "name": f"rule:{entry}:{filt}:{exit_}", "version": "1", "style": e.style,
        "default_params": {"x": e.grid[1], "y": x.grid[0]}, "signals": signals,
        "__doc__": f"Long when {e.describe} ({FILTERS[filt]}); {x.describe}.",
        "__module__": __name__})
    _CLASSES[key] = cls
    return cls


def strategy_from_name(name: str) -> type:
    """Inverse of rule_strategy(...).name, used by the paper runner and reports."""
    _, entry, filt, exit_ = name.split(":")
    return rule_strategy(entry, filt, exit_)
