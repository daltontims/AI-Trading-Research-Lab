"""Parquet data lake.

Layout: <root>/<asset_class>/<source>/<symbol>/<dataset>/<chunk>.parquet
where <chunk> is "YYYY-MM" for intraday data or "all" for small daily datasets.
Per-month files make downloads resumable and incremental.

The root defaults to ./data and can be overridden with LAB_DATA_DIR.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return Path(os.environ.get("LAB_DATA_DIR", PROJECT_ROOT / "data"))


@dataclass(frozen=True)
class DatasetKey:
    asset_class: str  # crypto | fx | equity | futures | options | macro
    source: str  # binance | dukascopy | yahoo | ...
    symbol: str
    dataset: str  # e.g. bars_1m, bars_1d, quote_bars_1m, funding

    @property
    def path(self) -> Path:
        return data_root() / self.asset_class / self.source / self.symbol / self.dataset

    def __str__(self) -> str:
        return f"{self.asset_class}/{self.source}/{self.symbol}/{self.dataset}"


def raw_cache_dir(source: str) -> Path:
    p = data_root() / "_raw" / source
    p.mkdir(parents=True, exist_ok=True)
    return p


def chunk_path(key: DatasetKey, chunk: str) -> Path:
    return key.path / f"{chunk}.parquet"


def has_chunk(key: DatasetKey, chunk: str) -> bool:
    return chunk_path(key, chunk).exists()


def write_chunk(key: DatasetKey, chunk: str, df: pl.DataFrame) -> Path:
    """Atomically write one chunk (write to temp file, then rename)."""
    path = chunk_path(key, chunk)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.write_parquet(tmp, compression="zstd", statistics=True)
    tmp.replace(path)
    return path


def chunks(key: DatasetKey) -> list[Path]:
    return sorted(key.path.glob("*.parquet")) if key.path.exists() else []


def scan(key: DatasetKey) -> pl.LazyFrame:
    files = chunks(key)
    if not files:
        raise FileNotFoundError(f"No data for {key} under {key.path}")
    return pl.scan_parquet(files).sort("ts")


def read(key: DatasetKey, start=None, end=None) -> pl.DataFrame:
    """Read a dataset, optionally filtered to [start, end). Prefer lab.data.splits for research."""
    lf = scan(key)
    if start is not None:
        lf = lf.filter(pl.col("ts") >= pl.lit(start).cast(pl.Datetime("us", "UTC")))
    if end is not None:
        lf = lf.filter(pl.col("ts") < pl.lit(end).cast(pl.Datetime("us", "UTC")))
    return lf.collect()


def list_datasets() -> list[DatasetKey]:
    root = data_root()
    keys = []
    for p in sorted(root.glob("*/*/*/*")):
        if p.is_dir() and not p.parts[-4].startswith("_") and any(p.glob("*.parquet")):
            keys.append(DatasetKey(*p.parts[-4:]))
    return keys


def fingerprint(key: DatasetKey) -> str:
    """Content fingerprint of a dataset: hash of each chunk's bytes.

    Stored with every experiment so results can be tied to an exact data snapshot.
    """
    h = hashlib.sha256()
    for f in chunks(key):
        h.update(f.name.encode())
        h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()[:16]
