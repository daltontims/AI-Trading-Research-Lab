"""Known-answer and Monte Carlo calibration tests for the statistical toolkit."""

import math

import numpy as np
import pytest
from scipy import stats as st

from lab.validation import cv, stats


def test_probabilistic_sharpe_known_value():
    assert stats.probabilistic_sharpe(0.0, 100) == pytest.approx(0.5)
    expected = st.norm.cdf(0.1 * 10 / math.sqrt(1 + 0.5 * 0.01))  # skew 0, kurtosis 3
    assert stats.probabilistic_sharpe(0.1, 101) == pytest.approx(expected)
    # Negative skew and fat tails make the same Sharpe less convincing.
    assert stats.probabilistic_sharpe(0.1, 101, skew=-1.0, kurt=8.0) < expected


def test_expected_max_sharpe_matches_simulation():
    rng = np.random.default_rng(0)
    n_trials, T = 100, 500
    sims = [max(stats.sharpe_per_period(rng.normal(0, 1, T)) for _ in range(n_trials)) for _ in range(60)]
    formula = stats.expected_max_sharpe(n_trials, 1 / T)
    assert np.mean(sims) == pytest.approx(formula, rel=0.1)
    assert stats.expected_max_sharpe(1, 1 / T) == 0.0


def test_deflated_sharpe_rejects_best_of_many_random_strategies():
    """The best of 50 zero-edge strategies looks significant undeflated, but the DSR sees through it."""
    rng = np.random.default_rng(1)
    psr_pass = dsr_pass = 0
    sims = 150
    for _ in range(sims):
        R = rng.normal(0, 0.01, (500, 50))
        best = R[:, np.argmax(R.mean(axis=0) / R.std(axis=0, ddof=1))]
        srs = R.mean(axis=0) / R.std(axis=0, ddof=1)
        d = stats.deflated_sharpe(best, 50, float(np.var(srs, ddof=1)))
        psr_pass += d["psr"] >= 0.95
        dsr_pass += d["dsr"] >= 0.95
    assert psr_pass / sims > 0.6        # naive significance: fooled most of the time
    assert dsr_pass / sims <= 0.10      # deflated: false positives near the nominal 5%


def test_deflated_sharpe_accepts_a_real_edge():
    rng = np.random.default_rng(2)
    r = rng.normal(0.003, 0.01, 1000)   # daily Sharpe 0.3 (≈4.8 annualised)
    assert stats.deflated_sharpe(r, 100)["dsr"] > 0.99


def test_min_track_record():
    assert stats.min_track_record(0.0, 0, 3) == float("inf")
    n = stats.min_track_record(0.1, 0, 3)
    assert stats.probabilistic_sharpe(0.1, int(math.ceil(n))) >= 0.95 - 1e-6


def test_stationary_bootstrap_block_length():
    rng = np.random.default_rng(3)
    idx = stationary_idx = stats.stationary_bootstrap_indices(100_000, 10.0, rng)
    assert idx.min() >= 0 and idx.max() < 100_000
    breaks = (np.diff(stationary_idx) != 1).sum()
    assert 100_000 / breaks == pytest.approx(10.0, rel=0.1)


def test_bootstrap_metric_interval_covers_truth():
    rng = np.random.default_rng(4)
    r = rng.normal(0.001, 0.01, 2000)
    b = stats.bootstrap_metric(r, np.mean, n_boot=500, mean_block=5)
    assert b["ci_low"] < 0.001 < b["ci_high"]


def test_trade_monte_carlo():
    out = stats.trade_monte_carlo(np.array([10.0, 20.0, 5.0]), 1000)
    assert out["prob_loss"] == 0 and out["max_dd_p95"] == 0
    out2 = stats.trade_monte_carlo(np.array([100.0, -150.0] * 20), 1000)
    assert 0 < out2["prob_loss"] < 1 and out2["max_dd_p95"] < 0


def test_reality_check_size_and_power():
    rng = np.random.default_rng(5)
    rej_rc = rej_spa = 0
    sims = 40
    for s in range(sims):
        d = rng.normal(0, 0.01, (400, 20))
        out = stats.reality_check(d, n_boot=300, mean_block=5, seed=s)
        rej_rc += out["rc_p_value"] <= 0.05
        rej_spa += out["spa_p_value"] <= 0.05
    assert rej_rc / sims <= 0.15 and rej_spa / sims <= 0.15  # ≈5% nominal; small-sample slack
    d = rng.normal(0, 0.01, (400, 20))
    d[:, 7] += 0.004
    out = stats.reality_check(d, n_boot=300, mean_block=5)
    assert out["spa_p_value"] < 0.05 and out["best_index"] == 7


def test_benjamini_hochberg_known_example():
    p = [0.01, 0.04, 0.03, 0.005, 0.2]
    assert stats.benjamini_hochberg(p, 0.05).tolist() == [True, True, True, True, False]
    assert stats.benjamini_hochberg([0.03, 0.04], 0.05).tolist() == [True, True]
    assert stats.benjamini_hochberg([0.03, 0.9], 0.05).tolist() == [False, False]
    q = stats.bh_adjusted(p)
    assert q.tolist() == pytest.approx([0.025, 0.05, 0.05, 0.025, 0.2])


def test_newey_west_wider_than_naive_for_autocorrelated_data():
    rng = np.random.default_rng(6)
    e = rng.normal(0, 1, 5000)
    x = np.empty_like(e)
    x[0] = e[0]
    for t in range(1, len(e)):
        x[t] = 0.6 * x[t - 1] + e[t]
    x += 0.05
    naive_t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))
    nw = stats.newey_west_tstat(x, lags=20)
    assert abs(nw["t"]) < abs(naive_t) * 0.75
    iid = stats.newey_west_tstat(rng.normal(0, 1, 5000), lags=5)
    assert abs(iid["t"]) < 4


def test_pbo_noise_vs_real_skill():
    # Pure noise: selection is luck, PBO averages 0.5 (a single dataset varies widely).
    pbos = [cv.pbo_cscv(np.random.default_rng(s).normal(0, 0.01, (800, 30)))["pbo"] for s in range(30)]
    assert 0.4 < np.mean(pbos) < 0.6
    noise = np.random.default_rng(7).normal(0, 0.01, (800, 30))
    skilled = noise.copy()
    skilled[:, 3] += 0.003
    out = cv.pbo_cscv(skilled)
    assert out["pbo"] < 0.05


def test_walk_forward_mechanics():
    T = 400
    M = np.zeros((T, 2))
    M[:200, 0], M[200:, 1] = 0.01, 0.01          # column 0 good first, column 1 good later
    M += np.random.default_rng(8).normal(0, 1e-4, M.shape)
    wf = cv.walk_forward(M, train=100, test=50)
    for seg in wf.segments:
        assert seg["train"][1] <= seg["test"][0]   # never tests on training data
    tests = [s["test"] for s in wf.segments]
    assert all(a[1] == b[0] for a, b in zip(tests, tests[1:]))  # contiguous, non-overlapping
    assert wf.chosen[0] == 0 and wf.chosen[-1] == 1
    assert len(wf.oos_returns) == sum(t[1] - t[0] for t in tests)
    with pytest.raises(ValueError):
        cv.walk_forward(M, train=390, test=50)


def test_purged_kfold():
    n, k, h, emb = 100, 5, 3, 2
    seen = []
    for train, test in cv.purged_kfold(n, k, horizon=h, embargo=emb):
        seen.extend(test)
        t0, t1 = test.min(), test.max() + 1
        assert not set(train) & set(test)
        assert not any(t0 - h <= i < t0 for i in train)          # purged before the fold
        assert not any(t1 <= i < t1 + emb for i in train)        # embargoed after the fold
    assert sorted(seen) == list(range(n))
