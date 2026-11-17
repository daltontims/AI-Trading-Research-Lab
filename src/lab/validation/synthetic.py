"""Synthetic market data with known truth, for calibrating the engine and the pipeline.

Bars are built from a simulated continuous price path (Brownian bridge with `substeps` points per
bar), so each bar's high and low are consistent with the path between its open and close.

LESSON (DECISIONS D-016): an earlier generator used close-to-close jumps with tiny independent
"wicks". Its bars were physically inconsistent (large moves with almost no range beyond the open
and close), which let stop orders fill at prices the path effectively jumped over, and made
breakout strategies look profitable on pure random walks. Always build bars from a path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl

from lab.engine.data import MarketData, standardize

T0 = datetime(2018, 1, 1, tzinfo=timezone.utc)


def path_bars(seed: int, n: int, *, phi: float = 0.0, vol: float = 0.004, substeps: int = 60,
              step: timedelta = timedelta(hours=1), start: datetime = T0, p0: float = 100.0,
              volume: float = 1e7) -> pl.DataFrame:
    """n bars whose bar returns follow AR(1) with coefficient phi (phi=0: random walk, no edge).

    Returns are demeaned (zero drift). Within each bar the log price follows a Brownian bridge
    from the open to the close; high/low are the path extremes.
    """
    rng = np.random.default_rng(seed)
    e = rng.normal(0.0, vol * np.sqrt(1 - phi**2) if abs(phi) < 1 else vol, n)
    r = np.empty(n)
    r[0] = e[0]
    for t in range(1, n):
        r[t] = phi * r[t - 1] + e[t]
    r -= r.mean()
    # Brownian bridge inside each bar: W(s) - s*W(1) + s*r, s in (0, 1]
    k = substeps
    w = np.cumsum(rng.normal(0.0, vol / np.sqrt(k), (n, k)), axis=1)
    s = np.arange(1, k + 1) / k
    bridge = w - s * w[:, -1:] + s * r[:, None]                 # ends exactly at r
    lo_open = np.log(p0) + np.concatenate([[0.0], np.cumsum(r)[:-1]])
    path = lo_open[:, None] + bridge
    o = np.exp(lo_open)
    c = np.exp(path[:, -1])
    h = np.maximum(np.exp(path.max(axis=1)), np.maximum(o, c))
    lo = np.minimum(np.exp(path.min(axis=1)), np.minimum(o, c))
    ts = [start + i * step for i in range(n)]
    return standardize(pl.DataFrame({"ts": ts, "open": o, "high": h, "low": lo, "close": c,
                                     "volume": np.full(n, volume)}))


def market(df: pl.DataFrame, symbol: str = "BTCUSDT", timeframe: str = "1h", split: str = "synthetic",
           market_name: str = "crypto") -> MarketData:
    return MarketData([symbol], timeframe, {symbol: df}, split=split, market=market_name)


def dev_val(df: pl.DataFrame, symbol: str = "BTCUSDT", timeframe: str = "1h", frac: float = 0.8):
    """Split into pseudo development / validation sets (time-ordered)."""
    cut = int(df.height * frac)
    return (market(df.head(cut), symbol, timeframe, "calib_dev"), market(df.slice(cut), symbol, timeframe, "calib_val"))
