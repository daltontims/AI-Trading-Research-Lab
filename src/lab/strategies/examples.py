"""Example strategies used to exercise and demonstrate the engine.

These are textbook rules, not discoveries. Their backtests are diagnostics of the engine
and are recorded as such (stage="diagnostic").
"""

from __future__ import annotations

import zlib

import numpy as np
import polars as pl

from lab.engine.strategy import Strategy
from lab.features import indicators as ind


class SmaCross(Strategy):
    """Trend following: long when the fast moving average is above the slow one."""

    name = "sma_cross"
    version = "1"
    style = "trend"
    default_params = {"fast": 50, "slow": 200, "atr_n": 14, "stop_atr": 3.0, "allow_short": False}

    def signals(self, df: pl.DataFrame, symbol: str) -> dict:
        p = self.params
        c = df["close"].to_numpy()
        f, s = ind.sma(c, p["fast"]), ind.sma(c, p["slow"])
        up, down = ind.cross_above(f, s), ind.cross_below(f, s)
        # Also enter on the first bar where the regime is already established.
        with np.errstate(invalid="ignore"):
            first_valid = np.isfinite(s) & ~np.isfinite(ind.shift(s, 1))
            up = up | (first_valid & (f > s))
        out = {"entry_long": up, "exit_long": down}
        if p["stop_atr"] > 0:  # stop_atr=0: classic version without a protective stop
            out["stop_dist"] = p["stop_atr"] * ind.atr(df["high"], df["low"], c, p["atr_n"])
        if p["allow_short"]:
            out |= {"entry_short": down, "exit_short": up}
        return out


class DonchianBreakout(Strategy):
    """Breakout: enter when price closes beyond the prior N-bar range; ATR stop and trailing stop."""

    name = "donchian_breakout"
    version = "1"
    style = "breakout"
    default_params = {"n": 55, "atr_n": 20, "stop_atr": 2.0, "trail_atr": 3.0, "allow_short": True}

    def signals(self, df: pl.DataFrame, symbol: str) -> dict:
        p = self.params
        h, lo, c = (df[x].to_numpy() for x in ("high", "low", "close"))
        hi_n, lo_n = ind.donchian_prior(h, lo, p["n"])
        a = ind.atr(h, lo, c, p["atr_n"])
        with np.errstate(invalid="ignore"):
            long_ = c > hi_n
            short = c < lo_n
        out = {"entry_long": long_, "exit_long": short, "stop_dist": p["stop_atr"] * a,
               "trail_dist": p["trail_atr"] * a}
        if p["allow_short"]:
            out |= {"entry_short": short, "exit_short": long_}
        return out


class BollingerReversion(Strategy):
    """Mean reversion: fade moves beyond k standard deviations; exit at the mean."""

    name = "bollinger_reversion"
    version = "1"
    style = "mean_reversion"
    default_params = {"n": 20, "k": 2.0, "atr_n": 14, "stop_atr": 2.0, "allow_short": True}

    def signals(self, df: pl.DataFrame, symbol: str) -> dict:
        p = self.params
        c = df["close"].to_numpy()
        z = ind.zscore(c, p["n"])
        a = ind.atr(df["high"], df["low"], c, p["atr_n"])
        with np.errstate(invalid="ignore"):
            out = {"entry_long": ind.cross_below(z, -p["k"]), "exit_long": z >= 0,
                   "stop_dist": p["stop_atr"] * a}
            if p["allow_short"]:
                out |= {"entry_short": ind.cross_above(z, p["k"]), "exit_short": z <= 0}
        return out


class RandomEntry(Strategy):
    """Calibration strategy: random entries, ATR stop/target. Must not look profitable after costs."""

    name = "random_entry"
    version = "1"
    style = "calibration"
    default_params = {"prob": 0.01, "seed": 0, "atr_n": 14, "stop_atr": 2.0, "target_atr": 2.0,
                      "allow_short": True}

    def signals(self, df: pl.DataFrame, symbol: str) -> dict:
        p = self.params
        # Seeded per symbol and per bar time, so truncating the data never changes earlier draws.
        rng = np.random.default_rng([p["seed"], zlib.crc32(symbol.encode())])
        draws = rng.random((df.height, 2))  # row t is the same whatever the data length
        u, side = draws[:, 0], draws[:, 1]
        a = ind.atr(df["high"], df["low"], df["close"], p["atr_n"])
        hit = u < p["prob"]
        out = {"entry_long": hit & ((side < 0.5) | (not p["allow_short"])),
               "stop_dist": p["stop_atr"] * a, "target_dist": p["target_atr"] * a}
        if p["allow_short"]:
            out["entry_short"] = hit & (side >= 0.5)
        return out


EXAMPLES = {c.name: c for c in (SmaCross, DonchianBreakout, BollingerReversion, RandomEntry)}
