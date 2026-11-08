"""Instrument definitions: tick size, multiplier, currency, sessions, costs.

Loaded from configs/instruments.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[3] / "configs" / "instruments.yaml"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: str
    source: str
    calendar: str
    currency: str = "USD"
    tick_size: float | None = None
    multiplier: float = 1.0
    fee_bps: float = 0.0
    fee_per_unit: float = 0.0
    spread_bps: float | None = None
    spread_markup_bps: float = 0.0
    tradable: bool = True
    yahoo_symbol: str | None = None
    price_kind: str = "price"  # price | yield
    extra: dict = field(default_factory=dict)


@lru_cache(maxsize=1)
def registry(path: Path = CONFIG) -> dict[str, Instrument]:
    cfg = yaml.safe_load(path.read_text())
    defaults = cfg.get("defaults", {})
    known = set(Instrument.__dataclass_fields__) - {"symbol", "extra"}
    out = {}
    for sym, spec in cfg["instruments"].items():
        merged = {**defaults, **spec}
        out[sym] = Instrument(symbol=sym, **{k: v for k, v in merged.items() if k in known},
                              extra={k: v for k, v in merged.items() if k not in known})
    return out


def find(symbol: str) -> Instrument | None:
    """Look up by registry name or by Yahoo symbol; None if unknown."""
    reg = registry()
    if symbol in reg:
        return reg[symbol]
    return next((i for i in reg.values() if i.yahoo_symbol == symbol), None)


def get(symbol: str) -> Instrument:
    try:
        return registry()[symbol]
    except KeyError:
        raise KeyError(f"Unknown instrument {symbol!r}; add it to {CONFIG}") from None
