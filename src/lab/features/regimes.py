"""Market regime labels for performance breakdowns (all lagged; no look-ahead).

Labels for a day use information up to the PREVIOUS day's close.
"""

from __future__ import annotations

import numpy as np
import polars as pl


def daily_regimes(daily: pl.DataFrame, trend_window: int = 200, vol_window: int = 20) -> pl.DataFrame:
    """daily: columns ts (date-level, UTC), close. Returns ts, trend, volatility labels.

    trend:      "up" if yesterday's close > its trailing `trend_window`-day mean, else "down"
    volatility: "high" if yesterday's trailing realized volatility is above its expanding
                median (computed only from data before that day), else "low"
    """
    d = daily.sort("ts").with_columns(r=pl.col("close").log().diff())
    d = d.with_columns(
        ma=pl.col("close").rolling_mean(trend_window, min_samples=trend_window // 2),
        rv=pl.col("r").rolling_std(vol_window),
    )
    rv = d["rv"].to_numpy()
    med = np.full_like(rv, np.nan)
    hist = []
    for i, v in enumerate(rv):  # expanding median of past values only
        if hist:
            med[i] = float(np.median(hist))
        if v == v:
            hist.append(v)
    d = d.with_columns(rv_med=pl.Series(med))
    d = d.with_columns(
        trend=pl.when(pl.col("ma").is_null()).then(pl.lit("unknown"))
        .when(pl.col("close") > pl.col("ma")).then(pl.lit("up")).otherwise(pl.lit("down")).shift(1),
        volatility=pl.when(pl.col("rv").is_null() | pl.col("rv_med").is_nan()).then(pl.lit("unknown"))
        .when(pl.col("rv") > pl.col("rv_med")).then(pl.lit("high")).otherwise(pl.lit("low")).shift(1),
    )
    return d.select("ts", pl.col("trend").fill_null("unknown"), pl.col("volatility").fill_null("unknown"))
