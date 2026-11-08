"""Binance public data archive (https://data.binance.vision) — free, no account.

Downloads monthly archives, verifies their SHA-256 checksums, and stores them
in the lake as one Parquet file per month.

Datasets:
- Spot 1-minute klines  -> crypto/binance/<SYMBOL>/bars_1m
- USD-M perpetual funding rates -> crypto/binance/<SYMBOL>/funding

Notes:
- Spot archive timestamps switched from milliseconds to microseconds in 2025;
  both are handled.
- Bars are stamped at their open time (UTC).
- Trading on Binance.com is unavailable to US residents; the archive is used for
  research only.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import date

import polars as pl

from lab.data import lake, schemas
from lab.data.ingest.http import get

BASE = "https://data.binance.vision/data"

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def months(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' strings."""
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    out = []
    while (y, m) <= (ye, me):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def last_complete_month(today: date | None = None) -> str:
    today = today or date.today()
    y, m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return f"{y:04d}-{m:02d}"


def _download_zip(url: str) -> bytes | None:
    r = get(url, ok_404=True)
    if r is None:
        return None
    data = r.content
    chk = get(url + ".CHECKSUM", ok_404=True)
    if chk is not None:
        expected = chk.text.split()[0].strip().lower()
        actual = hashlib.sha256(data).hexdigest()
        if expected != actual:
            raise IOError(f"Checksum mismatch for {url}")
    return data


def _read_csv_from_zip(data: bytes, columns: list[str]) -> pl.DataFrame:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        raw = zf.read(zf.namelist()[0])
    first = raw.split(b"\n", 1)[0]
    has_header = not first[:1].isdigit()
    df = pl.read_csv(io.BytesIO(raw), has_header=has_header, new_columns=columns if not has_header else None,
                     infer_schema_length=10000)
    return df


def _epoch_to_ts(col: pl.Expr) -> pl.Expr:
    """Binance epoch -> UTC datetime; values > 1e14 are microseconds, else milliseconds."""
    us = pl.when(col > 10**14).then(col).otherwise(col * 1000)
    return pl.from_epoch(us, time_unit="us").dt.replace_time_zone("UTC")


def parse_klines(data: bytes) -> pl.DataFrame:
    df = _read_csv_from_zip(data, KLINE_COLS)
    df.columns = KLINE_COLS[: len(df.columns)]
    df = df.with_columns(ts=_epoch_to_ts(pl.col("open_time").cast(pl.Int64)))
    return schemas.conform(df, "bars")


def parse_funding(data: bytes) -> pl.DataFrame:
    df = _read_csv_from_zip(data, ["calc_time", "funding_interval_hours", "last_funding_rate"])
    rename = {"calc_time": "ts_raw", "funding_interval_hours": "interval_hours",
              "last_funding_rate": "funding_rate"}
    df = df.rename({k: v for k, v in rename.items() if k in df.columns})
    df = df.with_columns(ts=_epoch_to_ts(pl.col("ts_raw").cast(pl.Int64)))
    # Funding is settled on 8h boundaries; round the calc timestamp to the settlement minute.
    df = df.with_columns(pl.col("ts").dt.truncate("1m"))
    return schemas.conform(df, "funding")


def ingest_spot_klines(symbol: str, start: str, end: str | None = None, interval: str = "1m",
                       force: bool = False, log=print) -> lake.DatasetKey:
    key = lake.DatasetKey("crypto", "binance", symbol, f"bars_{interval}")
    for mo in months(start, end or last_complete_month()):
        if not force and lake.has_chunk(key, mo):
            continue
        url = f"{BASE}/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{mo}.zip"
        data = _download_zip(url)
        if data is None:
            log(f"  {key} {mo}: not available")
            continue
        df = parse_klines(data)
        lake.write_chunk(key, mo, df)
        log(f"  {key} {mo}: {df.height:,} bars")
    return key


def ingest_funding(symbol: str, start: str, end: str | None = None, force: bool = False,
                   log=print) -> lake.DatasetKey:
    key = lake.DatasetKey("crypto", "binance", symbol, "funding")
    for mo in months(start, end or last_complete_month()):
        if not force and lake.has_chunk(key, mo):
            continue
        url = f"{BASE}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{mo}.zip"
        data = _download_zip(url)
        if data is None:
            log(f"  {key} {mo}: not available")
            continue
        df = parse_funding(data)
        lake.write_chunk(key, mo, df)
        log(f"  {key} {mo}: {df.height:,} rows")
    return key
