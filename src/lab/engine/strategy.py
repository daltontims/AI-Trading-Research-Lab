"""Strategy interface.

A strategy turns each instrument's own bars into signal arrays. It never places orders
or sees fills: the engine decides when and at what price orders execute.

Subclasses implement `signals(df, symbol)` returning a dict with any of:
    entry_long, entry_short, exit_long, exit_short : bool arrays
    stop_dist, target_dist, trail_dist             : price distances (NaN = none),
                                                     measured from the entry fill price
    priority                                       : float, higher fills first when
                                                     buying power is limited
All arrays have one value per row of `df`; row t may only use rows 0..t
(enforced by tests via lab.engine.lookahead.check_strategy).
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass

import numpy as np
import polars as pl

from lab.engine.data import MarketData

SIGNAL_KEYS = ("entry_long", "entry_short", "exit_long", "exit_short")
LEVEL_KEYS = ("stop_dist", "target_dist", "trail_dist", "priority")


@dataclass
class SignalGrid:
    entry_long: np.ndarray
    entry_short: np.ndarray
    exit_long: np.ndarray
    exit_short: np.ndarray
    stop_dist: np.ndarray
    target_dist: np.ndarray
    trail_dist: np.ndarray
    priority: np.ndarray


class Strategy:
    """Base class. Set `name`, `version` and `default_params`; implement `signals`."""

    name: str = "strategy"
    version: str = "1"
    default_params: dict = {}
    style: str = "unspecified"  # scalping | intraday | swing | trend | mean_reversion | ...

    def __init__(self, **params):
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: unknown parameters {unknown}")
        self.params = {**self.default_params, **params}

    def signals(self, df: pl.DataFrame, symbol: str) -> dict[str, np.ndarray]:
        raise NotImplementedError

    def generate(self, data: MarketData) -> SignalGrid:
        per = {s: self.signals(data.frames[s], s) for s in data.symbols}
        out = {}
        for k in SIGNAL_KEYS:
            g = data.scatter({s: _as_bool(v.get(k)) for s, v in per.items()}, False, np.bool_)
            out[k] = g
        for k in LEVEL_KEYS:
            out[k] = data.scatter({s: v.get(k) for s, v in per.items()}, 0.0 if k == "priority" else np.nan,
                                  np.float64)
        return SignalGrid(**out)

    @property
    def code_hash(self) -> str:
        """Hash of the strategy's source code: changes whenever its logic changes."""
        src = "".join(inspect.getsource(c) for c in type(self).__mro__
                      if c not in (object, Strategy) and c.__module__ != "builtins")
        return hashlib.sha256(src.encode()).hexdigest()[:12]

    @property
    def strategy_version(self) -> str:
        return f"{self.version}+{self.code_hash}"

    def describe(self) -> dict:
        return {"name": self.name, "version": self.strategy_version, "style": self.style, "params": self.params}


def _as_bool(v):
    if v is None:
        return None
    a = np.asarray(v)
    if a.dtype != np.bool_:
        a = np.nan_to_num(a.astype(np.float64), nan=0.0) != 0
    return a
