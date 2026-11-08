from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from lab import instruments
from lab.data import lake, quality, schemas, splits


def _bars(start, n, step=timedelta(minutes=1), price=100.0):
    ts = [start + i * step for i in range(n)]
    import numpy as np
    p = list(price * np.exp(np.cumsum(np.random.default_rng(0).normal(0, 1e-3, n))))
    return pl.DataFrame({"ts": ts, "open": p, "high": [x + 0.2 for x in p], "low": [x - 0.2 for x in p],
                         "close": p, "volume": [1.0] * n}).with_columns(pl.col("ts").dt.replace_time_zone("UTC"))


def test_conform_sorts_dedups_and_requires_columns():
    t0 = datetime(2024, 1, 1)
    df = pl.concat([_bars(t0, 3), _bars(t0, 1)]).sample(fraction=1.0, shuffle=True, seed=1)
    out = schemas.conform(df, "bars")
    assert out.height == 3 and out["ts"].is_sorted()
    with pytest.raises(ValueError):
        schemas.conform(df.drop("close"), "bars")


def test_lake_roundtrip_and_fingerprint():
    key = lake.DatasetKey("crypto", "test", "XYZ", "bars_1m")
    df = schemas.conform(_bars(datetime(2024, 1, 1), 100), "bars")
    lake.write_chunk(key, "2024-01", df)
    assert lake.has_chunk(key, "2024-01")
    assert lake.read(key).equals(df)
    fp = lake.fingerprint(key)
    lake.write_chunk(key, "2024-01", df.with_columns(pl.col("close") * 2))
    assert lake.fingerprint(key) != fp
    assert key in lake.list_datasets()


def test_vault_is_locked():
    b = splits.boundaries("crypto")
    df = schemas.conform(_bars(b.vault_start - timedelta(days=1), 3, step=timedelta(days=1)), "bars")
    dev_val = splits.apply(df, "crypto", "development+validation")
    assert dev_val["ts"].max() < b.vault_start
    with pytest.raises(splits.VaultLockedError):
        splits.apply(df, "crypto", "vault")
    assert splits.apply(df, "crypto", "vault", allow_vault=True).height == 2


def test_splits_partition_is_complete_and_disjoint():
    b = splits.boundaries("fx")
    df = schemas.conform(_bars(b.validation_start - timedelta(days=400), 1200, step=timedelta(days=1)), "bars")
    parts = [splits.apply(df, "fx", s, allow_vault=True).height for s in splits.SPLITS]
    assert sum(parts) == df.height and all(parts)


def test_quality_detects_problems():
    key = lake.DatasetKey("crypto", "test", "BAD", "bars_1m")
    df = schemas.conform(_bars(datetime(2024, 1, 1), 2000), "bars")
    # Remove a 30-minute block (exchange outage) and corrupt one bar's high.
    df = df.filter(~pl.col("ts").is_between(datetime(2024, 1, 1, 5, tzinfo=timezone.utc),
                                            datetime(2024, 1, 1, 5, 29, tzinfo=timezone.utc)))
    df = df.with_columns(pl.when(pl.int_range(pl.len()) == 10).then(0.0).otherwise(pl.col("close")).alias("close"))
    rep = quality.check_frame(df, key, quality.DatasetReport(key=str(key)))
    checks = {f.check for f in rep.findings}
    assert {"gaps", "prices", "ohlc"} <= checks
    assert rep.status == "FAIL"


def test_quality_clean_data_passes():
    key = lake.DatasetKey("crypto", "test", "OK", "bars_1m")
    df = schemas.conform(_bars(datetime(2024, 1, 1), 2000), "bars")
    rep = quality.check_frame(df, key, quality.DatasetReport(key=str(key)))
    assert rep.status == "PASS", rep.findings


def test_fx_expected_minutes_exclude_weekend():
    mins = quality.expected_minutes_fx(datetime(2024, 1, 5, tzinfo=timezone.utc),
                                       datetime(2024, 1, 8, tzinfo=timezone.utc))
    assert not mins.dt.weekday().is_in([6]).any()  # no Saturday
    assert mins.min() == datetime(2024, 1, 5, tzinfo=timezone.utc)


def test_instrument_registry_loads():
    spy = instruments.get("SPY")
    assert spy.asset_class == "equity" and spy.calendar == "XNYS"
    assert instruments.get("IDX_VIX").tradable is False
    with pytest.raises(KeyError):
        instruments.get("NOPE")


def test_quality_allows_zero_yields():
    key = lake.DatasetKey("macro", "yahoo", "IDX_IRX", "bars_1d")
    df = schemas.conform(_bars(datetime(2015, 1, 5), 50, step=timedelta(days=1), price=0.05), "bars")
    df = df.with_columns(pl.when(pl.int_range(pl.len()) < 5).then(0.0).otherwise(pl.col(c)).alias(c)
                         for c in ["open", "high", "low", "close"])
    rep = quality.check_frame(df, key, quality.DatasetReport(key=str(key)))
    assert all(f.level != "FAIL" for f in rep.findings), rep.findings
