"""Unified data schemas shared by every asset class.

All timestamps are timezone-aware UTC and mark the *start* of a bar
(a bar stamped 10:00 covers [10:00, 10:01) for 1-minute data).
Features must only use a bar once it has closed: ts + bar length.
"""

from __future__ import annotations

import polars as pl

TS = pl.Datetime("us", "UTC")

# Trade-price bars (crypto, equities, futures).
BARS = {
    "ts": TS,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,  # base-asset units (shares, coins, contracts)
}
BARS_OPTIONAL = {
    "quote_volume": pl.Float64,  # volume in quote currency (e.g. USDT)
    "trades": pl.Int64,
    "taker_buy_volume": pl.Float64,
    "adj_close": pl.Float64,  # split/dividend adjusted close (equities)
    "dividend": pl.Float64,
    "split": pl.Float64,
}

# Bid/ask bars built from quotes (forex). Mid = (bid + ask) / 2.
QUOTE_BARS = {
    "ts": TS,
    "bid_open": pl.Float64,
    "bid_high": pl.Float64,
    "bid_low": pl.Float64,
    "bid_close": pl.Float64,
    "ask_open": pl.Float64,
    "ask_high": pl.Float64,
    "ask_low": pl.Float64,
    "ask_close": pl.Float64,
    "spread_mean": pl.Float64,  # average quoted spread within the bar, in price units
    "spread_max": pl.Float64,
    "ticks": pl.Int64,  # number of quote updates in the bar
}

# Raw quote ticks (forex, later futures top-of-book).
QUOTE_TICKS = {
    "ts": TS,
    "bid": pl.Float64,
    "ask": pl.Float64,
    "bid_size": pl.Float64,
    "ask_size": pl.Float64,
}

# Perpetual futures funding rates (crypto).
FUNDING = {
    "ts": TS,
    "funding_rate": pl.Float64,  # fraction paid by longs to shorts for the interval
    "interval_hours": pl.Float64,
}

SCHEMAS = {
    "bars": (BARS, BARS_OPTIONAL),
    "quote_bars": (QUOTE_BARS, {}),
    "quote_ticks": (QUOTE_TICKS, {}),
    "funding": (FUNDING, {}),
}


def conform(df: pl.DataFrame, kind: str) -> pl.DataFrame:
    """Cast to the canonical schema, keep known columns, sort by time, drop duplicate timestamps.

    Raises ValueError if a required column is missing.
    """
    required, optional = SCHEMAS[kind]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{kind}: missing required columns {missing}")
    cols = list(required) + [c for c in optional if c in df.columns]
    types = {**required, **optional}
    out = df.select([pl.col(c).cast(types[c]) for c in cols])
    return out.sort("ts").unique(subset="ts", keep="last", maintain_order=True)
