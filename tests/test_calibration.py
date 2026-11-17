"""Calibration: random-entry strategies must not look consistently profitable.

On a driftless random walk, random entries have zero expected gross profit. After
realistic costs they must lose on average, and only a minority of seeds may profit.
"""

from datetime import timedelta

import numpy as np
import pytest

from engine_helpers import market
from lab.validation.synthetic import path_bars
from lab.engine.backtest import ExecutionConfig, RiskConfig, run_backtest
from lab.strategies.examples import RandomEntry


def _walk(seed, n=20_000):
    return path_bars(seed, n, vol=0.002, step=timedelta(minutes=1))


@pytest.fixture(scope="module")
def results():
    out = {"costs": [], "free": []}
    for seed in range(20):
        data = market({"BTCUSDT": _walk(seed)})
        strat = RandomEntry(seed=seed, prob=0.01)
        risk = RiskConfig(sizing="pct_equity", position_pct=0.5, max_bars_held=60)
        out["costs"].append(run_backtest(strat, data, risk, ExecutionConfig(cost_profile="crypto_perp")).metrics)
        free = ExecutionConfig(cost_profile="crypto_perp", cost_multiplier=0.0)
        out["free"].append(run_backtest(strat, data, risk, free).metrics)
    return out


def test_random_entries_lose_after_costs(results):
    rets = np.array([m["total_return"] for m in results["costs"]])
    assert rets.mean() < 0
    assert (rets > 0).mean() <= 0.2, f"{(rets > 0).mean():.0%} of random strategies profitable after costs"
    assert all(m["trades"] > 100 for m in results["costs"])


def test_random_entries_are_zero_edge_without_costs(results):
    """Without costs, random entries on a driftless walk average ~0 (unbiased engine)."""
    rets = np.array([m["total_return"] for m in results["free"]])
    se = rets.std(ddof=1) / np.sqrt(len(rets))
    assert abs(rets.mean()) < 3 * se + 0.005, f"mean {rets.mean():.4f} vs s.e. {se:.4f}: engine bias?"


def test_costs_scale_monotonically():
    data = market({"BTCUSDT": _walk(99)})
    strat = RandomEntry(seed=1, prob=0.01)
    risk = RiskConfig(sizing="pct_equity", position_pct=0.5, max_bars_held=60)
    rets = [run_backtest(strat, data, risk, ExecutionConfig(cost_profile="crypto_perp", cost_multiplier=m))
            .metrics["total_return"] for m in (0.0, 1.0, 2.0, 4.0)]
    assert rets == sorted(rets, reverse=True)
