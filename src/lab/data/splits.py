"""Research data partitions: development / validation / vault.

The vault (most recent data) may only be opened deliberately, once per strategy,
at the promotion decision (RESEARCH_PROTOCOL.md §2). `load()` refuses to return
vault rows unless `allow_vault=True` is passed, and every vault access must be
recorded in the registry's `vault_access` table by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import polars as pl
import yaml

from lab.data import lake

CONFIG = Path(__file__).resolve().parents[3] / "configs" / "splits.yaml"
SPLITS = ("development", "validation", "vault")


class VaultLockedError(PermissionError):
    pass


@dataclass(frozen=True)
class Boundaries:
    validation_start: datetime
    vault_start: datetime


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@lru_cache(maxsize=None)
def boundaries(market: str, path: Path = CONFIG) -> Boundaries:
    cfg = yaml.safe_load(path.read_text())["markets"][market]
    b = Boundaries(_utc(cfg["validation_start"]), _utc(cfg["vault_start"]))
    if not b.validation_start < b.vault_start:
        raise ValueError(f"splits for {market}: validation_start must precede vault_start")
    return b


def apply(df: pl.DataFrame | pl.LazyFrame, market: str, split: str, *, allow_vault: bool = False):
    """Filter a frame (with a UTC `ts` column) to one partition.

    `split` may also be "development+validation" for final walk-forward runs.
    """
    if split not in SPLITS + ("development+validation",):
        raise ValueError(f"unknown split {split!r}")
    if split == "vault" and not allow_vault:
        raise VaultLockedError(
            "The vault is locked. Open it only once per strategy at the promotion decision "
            "(pass allow_vault=True and record the access in the registry).")
    b = boundaries(market)
    ts = pl.col("ts")
    cond = {
        "development": ts < b.validation_start,
        "validation": (ts >= b.validation_start) & (ts < b.vault_start),
        "development+validation": ts < b.vault_start,
        "vault": ts >= b.vault_start,
    }[split]
    return df.filter(cond)


def load(key: lake.DatasetKey, split: str, *, market: str | None = None,
         allow_vault: bool = False) -> pl.DataFrame:
    """Read one dataset partition. Market defaults to the dataset's asset class."""
    return apply(lake.scan(key), market or key.asset_class, split, allow_vault=allow_vault).collect()
