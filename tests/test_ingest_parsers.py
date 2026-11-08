"""Offline tests for the source parsers using synthetic files in each source's format."""

import io
import lzma
import zipfile
from datetime import datetime, timezone

import numpy as np
import polars as pl

from lab.data.ingest import binance, dukascopy, yahoo


def _zip(name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, text)
    return buf.getvalue()


def test_binance_klines_milliseconds_and_microseconds():
    ms = "1704067200000,100,101,99,100.5,10,1704067259999,1005,7,4,402,0\n"
    us = "1735689600000000,200,202,198,201,5,1735689659999999,1005,3,2,402,0\n"
    a = binance.parse_klines(_zip("a.csv", ms))
    b = binance.parse_klines(_zip("b.csv", us))
    assert a["ts"][0] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert b["ts"][0] == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert a["close"][0] == 100.5 and a["trades"][0] == 7


def test_binance_funding_with_header():
    csv = "calc_time,funding_interval_hours,last_funding_rate\n1704067200001,8,0.0001\n1704096000000,8,-0.0002\n"
    df = binance.parse_funding(_zip("f.csv", csv))
    assert df["ts"][0] == datetime(2024, 1, 1, tzinfo=timezone.utc)  # truncated to the minute
    assert df["funding_rate"].to_list() == [0.0001, -0.0002]


def test_months_range():
    assert binance.months("2023-11", "2024-02") == ["2023-11", "2023-12", "2024-01", "2024-02"]


def test_dukascopy_tick_decode_and_bars():
    hour = datetime(2024, 1, 3, 10)
    recs = np.array([(0, 110005, 110000, 1.0, 2.0), (30_000, 110010, 110002, 1.0, 1.0),
                     (61_000, 110020, 110012, 1.0, 1.0)], dtype=dukascopy.RECORD)
    ticks = dukascopy.decode_bi5(lzma.compress(recs.tobytes()), hour, 1e5)
    assert ticks["bid"][0] == 1.1 and abs(ticks["ask"][0] - 1.10005) < 1e-12
    assert ticks["ts"][1] == datetime(2024, 1, 3, 10, 0, 30, tzinfo=timezone.utc)
    bars = dukascopy.ticks_to_bars(ticks)
    assert bars.height == 2
    assert bars["bid_high"][0] == 1.10002 and bars["ticks"][0] == 2
    assert abs(bars["spread_mean"][0] - (0.00005 + 0.00008) / 2) < 1e-12


def test_dukascopy_jpy_point_and_candles_drop_flat_minutes():
    day = datetime(2024, 1, 3)
    bid = np.array([(0, 141000, 141010, 140990, 141020, 5.0), (60, 141010, 141010, 141010, 141010, 0.0)],
                   dtype=dukascopy.CANDLE)
    ask = np.array([(0, 141008, 141018, 140998, 141028, 5.0), (60, 141018, 141018, 141018, 141018, 0.0)],
                   dtype=dukascopy.CANDLE)
    pt = dukascopy.point("USDJPY")
    b = dukascopy.decode_candles(lzma.compress(bid.tobytes()), day, pt, "BID")
    a = dukascopy.decode_candles(lzma.compress(ask.tobytes()), day, pt, "ASK")
    bars = dukascopy.merge_candles(b, a)
    assert bars.height == 1  # zero-volume filler minute removed
    assert bars["bid_open"][0] == 141.0 and abs(bars["spread_mean"][0] - 0.008) < 1e-9


def test_dukascopy_month_index_is_zero_based():
    assert "/2024/00/03/10h_ticks" in dukascopy.hour_url("EURUSD", datetime(2024, 1, 3, 10))


def test_yahoo_parse_chart():
    res = {
        "meta": {"gmtoffset": -18000},
        "timestamp": [1704205800, 1704292200, 1704378600],  # 2024-01-02..04 09:30 New York
        "indicators": {"quote": [{"open": [1, 2, None], "high": [1.5, 2.5, None], "low": [0.5, 1.5, None],
                                  "close": [1.2, 2.2, None], "volume": [100, 200, None]}],
                       "adjclose": [{"adjclose": [1.1, 2.2, None]}]},
        "events": {"dividends": {"1704205800": {"amount": 0.5, "date": 1704205800}}},
    }
    df = yahoo.parse_chart(res)
    assert df.height == 2  # null row dropped
    assert df["ts"][0] == datetime(2024, 1, 2, tzinfo=timezone.utc)
    assert df["dividend"].to_list() == [0.5, 0.0] and df["split"].to_list() == [1.0, 1.0]
