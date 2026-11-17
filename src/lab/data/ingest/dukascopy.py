"""Dukascopy historical forex ticks — free, no account.

Each hour of data is one LZMA-compressed ".bi5" file of 20-byte records:
    uint32 ms-since-hour, uint32 ask, uint32 bid, float32 ask_volume, float32 bid_volume
(big-endian). Prices are integers divided by the pair's "point" (1e5, or 1e3 for JPY pairs).
URL months are zero-based (January = 00).

Two download modes:
- "candles" (default): one file per day per side (BID/ASK) of 1-minute candles,
  24-byte records: uint32 sec-since-day, open, close, low, high (int), float32 volume.
  48 requests per trading day pair-month instead of ~600: practical for multi-year history.
  Spread stats are approximated from the open/close bid-ask differences; `ticks` is null.
- "ticks": hourly tick files (exact spreads, tick counts). Needed for scalping
  research (Phase 7); slow — use for short windows.

Stored datasets:
- fx/dukascopy/<PAIR>/quote_bars_1m  1-minute bid/ask OHLC + spread stats
- fx/dukascopy/<PAIR>/quote_ticks    (ticks mode + keep_ticks only, large) raw ticks

Caveats: one liquidity provider's quotes, not the whole (decentralised) FX market.
Retail broker spreads are usually wider; cost models add a markup on top.
"""

from __future__ import annotations

import lzma
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl

from lab.data import lake, schemas
from lab.data.ingest.binance import last_complete_month, months
from lab.data.ingest.http import get

BASE = "https://datafeed.dukascopy.com/datafeed"
CANDLE = np.dtype([("sec", ">u4"), ("open", ">u4"), ("close", ">u4"), ("low", ">u4"), ("high", ">u4"), ("vol", ">f4")])
RECORD = np.dtype([("ms", ">u4"), ("ask", ">u4"), ("bid", ">u4"), ("ask_vol", ">f4"), ("bid_vol", ">f4")])


def point(pair: str) -> float:
    return 1e3 if pair.upper().endswith("JPY") else 1e5


def hour_url(pair: str, hour: datetime) -> str:
    return f"{BASE}/{pair}/{hour.year:04d}/{hour.month - 1:02d}/{hour.day:02d}/{hour.hour:02d}h_ticks.bi5"


def decode_bi5(blob: bytes, hour: datetime, pt: float) -> pl.DataFrame:
    """Decode one hourly .bi5 file into a quote-tick frame."""
    if not blob:
        return pl.DataFrame(schema=schemas.QUOTE_TICKS)
    arr = np.frombuffer(lzma.decompress(blob), dtype=RECORD)
    base_us = int(hour.replace(tzinfo=timezone.utc).timestamp() * 1_000_000)
    df = pl.DataFrame({
        "ts": base_us + arr["ms"].astype(np.int64) * 1000,
        "bid": arr["bid"].astype(np.float64) / pt,
        "ask": arr["ask"].astype(np.float64) / pt,
        "bid_size": arr["bid_vol"].astype(np.float64),
        "ask_size": arr["ask_vol"].astype(np.float64),
    })
    return df.with_columns(pl.from_epoch("ts", time_unit="us").dt.replace_time_zone("UTC"))


def day_url(pair: str, day: datetime, side: str) -> str:
    return f"{BASE}/{pair}/{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/{side}_candles_min_1.bi5"


def decode_candles(blob: bytes, day: datetime, pt: float, side: str) -> pl.DataFrame:
    """Decode one daily 1-minute candle file for one side ("BID" or "ASK")."""
    p = side.lower()
    cols = {"ts": pl.Datetime("us", "UTC"), f"{p}_open": pl.Float64, f"{p}_high": pl.Float64,
            f"{p}_low": pl.Float64, f"{p}_close": pl.Float64, f"{p}_vol": pl.Float64}
    if not blob:
        return pl.DataFrame(schema=cols)
    arr = np.frombuffer(lzma.decompress(blob), dtype=CANDLE)
    base_us = int(day.replace(tzinfo=timezone.utc).timestamp() * 1_000_000)
    df = pl.DataFrame({
        "ts": base_us + arr["sec"].astype(np.int64) * 1_000_000,
        f"{p}_open": arr["open"] / pt, f"{p}_high": arr["high"] / pt,
        f"{p}_low": arr["low"] / pt, f"{p}_close": arr["close"] / pt,
        f"{p}_vol": arr["vol"].astype(np.float64),
    })
    return df.with_columns(pl.from_epoch("ts", time_unit="us").dt.replace_time_zone("UTC"))


def merge_candles(bid: pl.DataFrame, ask: pl.DataFrame) -> pl.DataFrame:
    """Join bid and ask candles into quote bars, dropping minutes with no activity.

    Dukascopy fills closed-market minutes with flat zero-volume candles; those are removed
    so no strategy can "trade" at stale prices.
    """
    df = bid.join(ask, on="ts", how="inner")
    df = df.filter((pl.col("bid_vol") > 0) | (pl.col("ask_vol") > 0))
    so, sc = pl.col("ask_open") - pl.col("bid_open"), pl.col("ask_close") - pl.col("bid_close")
    df = df.with_columns(
        spread_mean=(so + sc) / 2,
        spread_max=pl.max_horizontal(so, sc),
        ticks=pl.lit(None, dtype=pl.Int64),
    )
    return schemas.conform(df, "quote_bars")


MIN_INTERVAL_S = 1.0  # Dukascopy rate-limits aggressively (HTTP 429 / temporary blocks)
_throttle_lock = threading.Lock()
_last_request = [0.0]


def _throttle() -> None:
    with _throttle_lock:
        wait = _last_request[0] + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()


def _cached_get(url: str, cache) -> bytes:
    if cache.exists():
        return cache.read_bytes()
    _throttle()
    r = get(url, ok_404=True, retries=6)
    blob = r.content if r is not None else b""
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(blob)
    tmp.replace(cache)
    return blob


def fetch_month_candles(pair: str, month: str, workers: int = 1) -> pl.DataFrame:
    y, m = map(int, month.split("-"))
    day = datetime(y, m, 1)
    days = []
    while day.month == m:
        if day.weekday() != 5:  # no Saturday sessions
            days.append(day)
        day += timedelta(days=1)
    pt = point(pair)
    root = lake.raw_cache_dir("dukascopy") / pair

    def one(d: datetime) -> pl.DataFrame:
        sides = {}
        for side in ("BID", "ASK"):
            blob = _cached_get(day_url(pair, d, side), root / f"{d:%Y/%m/%d}" / f"{side}_m1.bi5")
            sides[side] = decode_candles(blob, d, pt, side)
        return merge_candles(sides["BID"], sides["ASK"])

    with ThreadPoolExecutor(max_workers=workers) as ex:
        frames = [f for f in ex.map(one, days) if not f.is_empty()]
    if not frames:
        return pl.DataFrame(schema=schemas.QUOTE_BARS)
    return schemas.conform(pl.concat(frames), "quote_bars")


def ticks_to_bars(ticks: pl.DataFrame, every: str = "1m") -> pl.DataFrame:
    """Aggregate quote ticks into bid/ask bars. Bars with no ticks are omitted (no fake prices)."""
    if ticks.is_empty():
        return pl.DataFrame(schema=schemas.QUOTE_BARS)
    t = ticks.sort("ts").with_columns(spread=pl.col("ask") - pl.col("bid"))
    bars = t.group_by_dynamic("ts", every=every, closed="left", label="left").agg(
        bid_open=pl.col("bid").first(), bid_high=pl.col("bid").max(),
        bid_low=pl.col("bid").min(), bid_close=pl.col("bid").last(),
        ask_open=pl.col("ask").first(), ask_high=pl.col("ask").max(),
        ask_low=pl.col("ask").min(), ask_close=pl.col("ask").last(),
        spread_mean=pl.col("spread").mean(), spread_max=pl.col("spread").max(),
        ticks=pl.len(),
    )
    return schemas.conform(bars, "quote_bars")


def _fetch_hour(pair: str, hour: datetime, pt: float) -> pl.DataFrame:
    """Fetch one hour of ticks via the raw cache (empty file = no ticks that hour)."""
    cache = lake.raw_cache_dir("dukascopy") / pair / f"{hour:%Y/%m/%d/%H}h.bi5"
    return decode_bi5(_cached_get(hour_url(pair, hour), cache), hour, pt)


def fetch_month_ticks(pair: str, month: str, workers: int = 1) -> pl.DataFrame:
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1)
    end = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1)
    hours = []
    h = start
    while h < end:
        # FX is closed from ~Friday 22:00 to Sunday 21:00 UTC; skip all of Saturday.
        if h.weekday() != 5:
            hours.append(h)
        h += timedelta(hours=1)
    pt = point(pair)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        frames = list(ex.map(lambda hr: _fetch_hour(pair, hr, pt), hours))
    frames = [f for f in frames if not f.is_empty()]
    if not frames:
        return pl.DataFrame(schema=schemas.QUOTE_TICKS)
    return schemas.conform(pl.concat(frames), "quote_ticks")


def _clear_raw(pair: str, month: str) -> None:
    """Delete a month's raw hourly cache once its bars are safely written (saves disk)."""
    import shutil
    y, m = month.split("-")
    shutil.rmtree(lake.raw_cache_dir("dukascopy") / pair / y / m, ignore_errors=True)


def ingest(pair: str, start: str, end: str | None = None, mode: str = "candles",
           keep_ticks: bool = False, keep_raw: bool = False, force: bool = False,
           log=print) -> lake.DatasetKey:
    pair = pair.upper()
    bars_key = lake.DatasetKey("fx", "dukascopy", pair, "quote_bars_1m")
    ticks_key = lake.DatasetKey("fx", "dukascopy", pair, "quote_ticks")
    for mo in months(start, end or last_complete_month()):
        need_bars = force or not lake.has_chunk(bars_key, mo)
        need_ticks = mode == "ticks" and keep_ticks and (force or not lake.has_chunk(ticks_key, mo))
        if not (need_bars or need_ticks):
            continue
        if mode == "candles":
            bars = fetch_month_candles(pair, mo)
            msg = f"{bars.height:,} bars"
        else:
            ticks = fetch_month_ticks(pair, mo)
            bars = ticks_to_bars(ticks)
            if keep_ticks and not ticks.is_empty():
                lake.write_chunk(ticks_key, mo, ticks)
            msg = f"{ticks.height:,} ticks -> {bars.height:,} bars"
        if bars.is_empty():
            log(f"  {bars_key} {mo}: no data")
            continue
        lake.write_chunk(bars_key, mo, bars)
        log(f"  {bars_key} {mo}: {msg}")
        if not keep_raw:
            _clear_raw(pair, mo)
    return bars_key
