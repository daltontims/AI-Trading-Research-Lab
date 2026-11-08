"""Technical indicators — trailing windows only.

Every function returns an array aligned with its input where value[t] depends only on
inputs[0..t]. Values are NaN until enough history exists. A value at bar t uses bar t's
close, so it is only known at the close of t; the engine fills orders on a later bar.

These properties are enforced by tests (tests/test_lookahead.py) which recompute each
indicator on truncated data and require identical results.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from numba import njit


def _s(x) -> pl.Series:
    return pl.Series(np.asarray(x, dtype=np.float64))


def sma(x, n: int) -> np.ndarray:
    return _s(x).rolling_mean(n).to_numpy()


def ema(x, n: int) -> np.ndarray:
    """Exponential moving average (alpha = 2/(n+1)), NaN for the first n-1 bars."""
    out = _s(x).ewm_mean(span=n, adjust=False).to_numpy().copy()
    out[: n - 1] = np.nan
    return out


def rolling_std(x, n: int) -> np.ndarray:
    return _s(x).rolling_std(n).to_numpy()


def rolling_max(x, n: int) -> np.ndarray:
    return _s(x).rolling_max(n).to_numpy()


def rolling_min(x, n: int) -> np.ndarray:
    return _s(x).rolling_min(n).to_numpy()


def shift(x, k: int = 1) -> np.ndarray:
    """Value from k bars ago (k >= 1). Negative k (the future) is refused."""
    if k < 0:
        raise ValueError("shift(k<0) would read the future")
    x = np.asarray(x, dtype=np.float64)
    out = np.full_like(x, np.nan)
    if k == 0:
        return x.copy()
    out[k:] = x[:-k]
    return out


def returns(close, n: int = 1) -> np.ndarray:
    c = np.asarray(close, dtype=np.float64)
    return c / shift(c, n) - 1.0


def log_returns(close, n: int = 1) -> np.ndarray:
    c = np.asarray(close, dtype=np.float64)
    return np.log(c / shift(c, n))


def zscore(x, n: int) -> np.ndarray:
    return (np.asarray(x, dtype=np.float64) - sma(x, n)) / rolling_std(x, n)


def true_range(high, low, close) -> np.ndarray:
    h, l, c = (np.asarray(a, dtype=np.float64) for a in (high, low, close))
    pc = shift(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    return tr


@njit(cache=True)
def _wilder(x, n):
    out = np.full(x.shape[0], np.nan)
    if x.shape[0] < n:
        return out
    acc = 0.0
    for i in range(n):
        acc += x[i]
    out[n - 1] = acc / n
    for i in range(n, x.shape[0]):
        out[i] = out[i - 1] + (x[i] - out[i - 1]) / n
    return out


def atr(high, low, close, n: int = 14) -> np.ndarray:
    """Average true range (Wilder smoothing)."""
    return _wilder(true_range(high, low, close), n)


def rsi(close, n: int = 14) -> np.ndarray:
    """Relative strength index (Wilder), 0..100."""
    c = np.asarray(close, dtype=np.float64)
    d = np.diff(c, prepend=np.nan)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    g = _wilder(gain[1:], n)
    l = _wilder(loss[1:], n)
    out = np.full_like(c, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = g / l
        out[1:] = np.where(l == 0, 100.0, 100.0 - 100.0 / (1.0 + rs))
    return out


def donchian_prior(high, low, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Highest high / lowest low of the n bars BEFORE the current one (breakout levels)."""
    return shift(rolling_max(high, n), 1), shift(rolling_min(low, n), 1)


def realized_vol(close, n: int) -> np.ndarray:
    """Rolling standard deviation of log returns (per bar, not annualised)."""
    return rolling_std(log_returns(close), n)


def rolling_vwap(close, volume, n: int) -> np.ndarray:
    c, v = np.asarray(close, dtype=np.float64), np.asarray(volume, dtype=np.float64)
    num = _s(c * v).rolling_sum(n).to_numpy()
    den = _s(v).rolling_sum(n).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return num / den


def cross_above(a, b) -> np.ndarray:
    """True at t when a crosses from <= b at t-1 to > b at t."""
    a, b = np.asarray(a, dtype=np.float64), np.broadcast_to(np.asarray(b, dtype=np.float64), np.shape(a))
    pa, pb = shift(a, 1), shift(b, 1)
    with np.errstate(invalid="ignore"):
        return (a > b) & (pa <= pb)


def cross_below(a, b) -> np.ndarray:
    a, b = np.asarray(a, dtype=np.float64), np.broadcast_to(np.asarray(b, dtype=np.float64), np.shape(a))
    pa, pb = shift(a, 1), shift(b, 1)
    with np.errstate(invalid="ignore"):
        return (a < b) & (pa >= pb)


def align_higher_timeframe(lower_ts, higher_ts, higher_values, higher_period_us: int) -> np.ndarray:
    """Map a higher-timeframe series onto lower-timeframe bars without leakage.

    A higher bar stamped H (covering [H, H+period)) is only known once complete, i.e. from
    the lower bar whose close >= H+period. For a lower bar stamped L with length l, its close
    is L+l; we conservatively use the last higher bar with H + period <= L (complete before
    the lower bar even opens).
    """
    lower_ts = np.asarray(lower_ts, dtype=np.int64)
    avail = np.asarray(higher_ts, dtype=np.int64) + higher_period_us
    idx = np.searchsorted(avail, lower_ts, side="right") - 1
    vals = np.asarray(higher_values, dtype=np.float64)
    out = np.where(idx >= 0, vals[np.clip(idx, 0, None)], np.nan)
    return out
