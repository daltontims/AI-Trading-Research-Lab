"""Look-ahead (future information) detectors.

1. `check_strategy` — signal causality: signals computed on data truncated at bar k must
   equal the signals computed on the full data for every bar before k. Any difference means
   the strategy used future bars.
2. `check_engine` — fill causality: scrambling all prices after bar k must not change
   equity or trades before bar k.

Both run in the test suite for every built-in strategy and can be run on any new strategy
(`run_experiment(..., check_lookahead=True)` does it automatically).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from lab.engine.data import MarketData


@dataclass
class LookaheadReport:
    passed: bool
    checks: int
    failures: list[str] = field(default_factory=list)


def _equal(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.dtype == np.bool_:
        return a == b
    return (a == b) | (np.isnan(a) & np.isnan(b)) | np.isclose(a, b, rtol=1e-9, atol=1e-12, equal_nan=True)


def check_strategy(strategy, data: MarketData, cut_fractions=(0.3, 0.6, 0.9)) -> LookaheadReport:
    full = strategy.generate(data)
    failures = []
    for frac in cut_fractions:
        k = max(2, int(data.n_bars * frac))
        part = strategy.generate(data.head(k))
        for name in full.__dataclass_fields__:
            a = getattr(full, name)[:k]
            b = getattr(part, name)
            bad = ~_equal(a, b)
            if bad.any():
                row, col = np.argwhere(bad)[0]
                failures.append(f"{name}: differs at bar {row} ({data.symbols[col]}) when data is cut at bar {k}")
    return LookaheadReport(passed=not failures, checks=len(cut_fractions), failures=failures)


def scramble_after(data: MarketData, k: int, seed: int = 0) -> MarketData:
    """Copy of `data` whose prices/volumes after grid bar k-1 are randomly perturbed."""
    rng = np.random.default_rng(seed)
    cutoff = data.ts[k - 1]
    frames = {}
    for s, f in data.frames.items():
        after = (f["ts"].dt.epoch("us") > cutoff).to_numpy()
        n = int(after.sum())
        factor = np.ones(f.height)
        factor[after] = np.exp(np.cumsum(rng.normal(0, 0.02, n)))
        o, h, lo, c = (f[x].to_numpy() * factor for x in ("open", "high", "low", "close"))
        h = np.maximum.reduce([o, h, lo, c])
        lo = np.minimum.reduce([o, h, lo, c])
        frames[s] = f.with_columns(open=pl.Series(o), high=pl.Series(h), low=pl.Series(lo), close=pl.Series(c),
                                   volume=f["volume"] * pl.Series(np.where(after, rng.uniform(0.2, 5, f.height), 1.0)))
    return MarketData(data.symbols, data.timeframe, frames, split=data.split, market=data.market,
                      fingerprints=data.fingerprints)


def check_engine(strategy, data: MarketData, run, cut_fractions=(0.4, 0.8), seed: int = 0) -> LookaheadReport:
    """`run(strategy, data) -> BacktestResult`. Equity before the cut must not depend on later data."""
    base = run(strategy, data)
    failures = []
    for frac in cut_fractions:
        k = max(2, int(data.n_bars * frac))
        other = run(strategy, scramble_after(data, k, seed))
        a = base.equity["equity"].to_numpy()[:k]
        b = other.equity["equity"].to_numpy()[:k]
        if not np.allclose(a, b, rtol=1e-12, atol=1e-9):
            i = int(np.argmax(~np.isclose(a, b, rtol=1e-12, atol=1e-9)))
            failures.append(f"equity differs at bar {i} after scrambling data from bar {k}")
        cut_ts = base.equity["ts"][k - 1]
        ta = base.trades.filter(pl.col("exit_ts") < cut_ts)
        tb = other.trades.filter(pl.col("exit_ts") < cut_ts)
        if ta.height != tb.height or (ta.height and not np.allclose(ta["pnl_net"], tb["pnl_net"])):
            failures.append(f"trades closed before bar {k} changed after scrambling later data")
    return LookaheadReport(passed=not failures, checks=len(cut_fractions), failures=failures)
