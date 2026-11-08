"""Yahoo Finance daily bars (unofficial chart API) — free, no account.

Stores equity/ETF/index daily bars -> <asset_class>/yahoo/<SYMBOL>/bars_1d/all.parquet

- open/high/low/close are split-adjusted but NOT dividend-adjusted (Yahoo convention).
- adj_close is adjusted for splits and dividends; use it for total-return studies.
- Dividends and splits are kept as columns.

Caveats (documented in the research protocol):
- Survivorship bias: delisted symbols are missing. Suitable for ETFs and indices,
  NOT for stock-selection studies.
- Unofficial API: it can change or rate-limit without notice.
- Daily bars are stamped at 00:00 UTC of the trading date (date-level resolution only).
"""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl

from lab.data import lake, schemas
from lab.data.ingest.http import get

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def fetch_daily(symbol: str) -> pl.DataFrame:
    params = {"period1": 0, "period2": int(datetime.now(timezone.utc).timestamp()),
              "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"}
    r = get(URL.format(symbol=symbol), params=params)
    res = r.json()["chart"]["result"][0]
    return parse_chart(res)


def parse_chart(res: dict) -> pl.DataFrame:
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    gmtoffset = res["meta"].get("gmtoffset", 0)
    df = pl.DataFrame({
        "epoch": res["timestamp"],
        "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
        "volume": q["volume"],
        "adj_close": adj if adj is not None else q["close"],
    }, schema_overrides={c: pl.Float64 for c in ["open", "high", "low", "close", "volume", "adj_close"]})
    # Convert exchange-local timestamp to the trading date, stamped 00:00 UTC.
    df = df.with_columns(
        ts=pl.from_epoch(pl.col("epoch") + gmtoffset, time_unit="s").dt.date().cast(pl.Datetime("us")).dt.replace_time_zone("UTC")
    )
    ev = res.get("events", {})
    divs = pl.DataFrame(
        [{"epoch": int(k), "dividend": float(v["amount"])} for k, v in ev.get("dividends", {}).items()],
        schema={"epoch": pl.Int64, "dividend": pl.Float64})
    splits = pl.DataFrame(
        [{"epoch": int(k), "split": float(v["numerator"]) / float(v["denominator"])}
         for k, v in ev.get("splits", {}).items()],
        schema={"epoch": pl.Int64, "split": pl.Float64})
    df = df.with_columns(pl.col("epoch").cast(pl.Int64))
    df = df.join(divs, on="epoch", how="left").join(splits, on="epoch", how="left")
    df = df.with_columns(pl.col("dividend").fill_null(0.0), pl.col("split").fill_null(1.0))
    # Drop rows with missing prices (Yahoo sometimes emits null rows).
    df = df.drop_nulls(subset=["open", "high", "low", "close"])
    return schemas.conform(df, "bars")


def ingest(symbol: str, asset_class: str = "equity", log=print) -> lake.DatasetKey:
    """Full refresh (daily history is small)."""
    key = lake.DatasetKey(asset_class, "yahoo", symbol.replace("^", "IDX_"), "bars_1d")
    df = fetch_daily(symbol)
    lake.write_chunk(key, "all", df)
    log(f"  {key}: {df.height:,} bars {df['ts'].min():%Y-%m-%d} -> {df['ts'].max():%Y-%m-%d}")
    return key
