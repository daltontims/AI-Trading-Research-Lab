"""Execution-cost models per market.

A CostModel combines an instrument's properties (configs/instruments.yaml) with a
venue profile (configs/costs.yaml). The engine applies it at every fill:

    executed price = reference price × (1 ± (half_spread + slippage))
    fee            = notional × fee_bps + |qty| × fee_per_unit (+ sell fee), at least min_fee

where the half-spread comes from bid/ask data when available, otherwise from the
instrument's assumed spread. Funding (perpetuals), borrow (shorts) and financing are
charged while positions are held. `scaled(m)` returns a stressed copy for sensitivity tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path

import yaml

from lab import instruments

CONFIG = Path(__file__).resolve().parents[3] / "configs" / "costs.yaml"


@dataclass(frozen=True)
class CostModel:
    symbol: str
    profile: str
    multiplier: float = 1.0          # contract multiplier ($ per 1.0 price move per unit)
    lot_size: float = 0.0            # 0 = fractional quantities
    min_notional: float = 0.0
    fee_bps: float = 0.0
    maker_fee_bps: float = 0.0
    sell_fee_bps: float = 0.0
    fee_per_unit: float = 0.0
    min_fee: float = 0.0
    half_spread_bps: float = 0.0     # fallback when data has no bid/ask
    spread_markup_bps: float = 0.0   # added to data spreads (retail broker markup)
    slippage_bps: float = 0.0
    slippage_range_frac: float = 0.0
    allow_short: bool = False
    borrow_rate_annual: float = 0.0
    financing_rate_annual: float = 0.0
    funding: bool = False
    max_participation: float = 1.0
    cost_multiplier: float = 1.0     # >1 in stress tests

    def scaled(self, m: float) -> "CostModel":
        """Stress-test copy: spread, slippage, fees and borrow multiplied by m."""
        return replace(
            self,
            fee_bps=self.fee_bps * m, maker_fee_bps=self.maker_fee_bps * m,
            sell_fee_bps=self.sell_fee_bps * m, fee_per_unit=self.fee_per_unit * m,
            min_fee=self.min_fee * m, half_spread_bps=self.half_spread_bps * m,
            spread_markup_bps=self.spread_markup_bps * m, slippage_bps=self.slippage_bps * m,
            slippage_range_frac=self.slippage_range_frac * m,
            borrow_rate_annual=self.borrow_rate_annual * m,
            financing_rate_annual=self.financing_rate_annual * m,
            cost_multiplier=self.cost_multiplier * m,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _config(path: Path = CONFIG) -> dict:
    return yaml.safe_load(path.read_text())


def profiles() -> list[str]:
    return list(_config()["profiles"])


def for_instrument(symbol: str, profile: str | None = None, **overrides) -> CostModel:
    """Build the cost model for a registry instrument under a venue profile."""
    inst = instruments.get(symbol)
    if not inst.tradable:
        raise ValueError(f"{symbol} is not tradable (signal/regime input only)")
    cfg = _config()
    profile = profile or cfg["default_profile"][inst.asset_class]
    p = dict(cfg["profiles"][profile])
    p.setdefault("maker_fee_bps", p.get("fee_bps", 0.0))
    fields = set(CostModel.__dataclass_fields__)
    unknown = set(p) - fields
    if unknown:
        raise ValueError(f"unknown cost fields in profile {profile}: {unknown}")
    model = CostModel(
        symbol=symbol, profile=profile, multiplier=float(inst.multiplier),
        lot_size=float(inst.lot_size or 0.0), min_notional=float(inst.min_notional or 0.0),
        half_spread_bps=float(inst.spread_bps if inst.spread_bps is not None else p.pop("half_spread_bps", 0.0)),
        spread_markup_bps=float(inst.spread_markup_bps),
        **{k: v for k, v in p.items() if k != "half_spread_bps"},
    )
    return replace(model, **overrides) if overrides else model
