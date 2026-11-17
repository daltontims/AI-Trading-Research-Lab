"""Statistical tests for separating real edges from luck.

All Sharpe ratios here are PER PERIOD (e.g. daily) unless stated; annualise by √periods.

References
- Bailey & López de Prado (2012) "The Sharpe Ratio Efficient Frontier" — Probabilistic Sharpe Ratio.
- Bailey & López de Prado (2014) "The Deflated Sharpe Ratio".
- White (2000) "A Reality Check for Data Snooping"; Hansen (2005) "A Test for Superior Predictive Ability".
- Politis & Romano (1994) "The Stationary Bootstrap".
- Benjamini & Hochberg (1995) false discovery rate.
- Newey & West (1987) HAC standard errors.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats as st

EULER_GAMMA = 0.5772156649015329


# ----------------------------------------------------------------- Sharpe inference

def sharpe_per_period(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=np.float64)
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(r.mean() / sd) if sd > 0 else float("nan")


def probabilistic_sharpe(sr: float, n: int, skew: float = 0.0, kurt: float = 3.0, sr_benchmark: float = 0.0) -> float:
    """P(true Sharpe > sr_benchmark) given an observed per-period Sharpe `sr` over n observations,
    adjusting for non-normal returns (skew, kurtosis — NOT excess kurtosis)."""
    if n < 2 or not np.isfinite(sr):
        return float("nan")
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if denom <= 0:
        denom = 1e-12
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom)
    return float(st.norm.cdf(z))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Expected maximum of n_trials Sharpe estimates when every true Sharpe is zero
    (the 'luck threshold' a best-of-N result must beat)."""
    if n_trials <= 1:
        return 0.0
    z1 = st.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = st.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(math.sqrt(var_sr) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def deflated_sharpe(r: np.ndarray, n_trials: int, var_sr_trials: float | None = None) -> dict:
    """Deflated Sharpe Ratio: probability the observed Sharpe beats what the best of
    `n_trials` zero-skill strategies would show by luck.

    var_sr_trials: variance of the per-period Sharpe estimates across all trials. If unknown,
    the null sampling variance 1/n is used.
    """
    r = np.asarray(r, dtype=np.float64)
    n = len(r)
    sr = sharpe_per_period(r)
    skew = float(st.skew(r)) if n > 2 else 0.0
    kurt = float(st.kurtosis(r, fisher=False)) if n > 3 else 3.0
    v = var_sr_trials if (var_sr_trials is not None and var_sr_trials > 0) else 1.0 / max(n, 1)
    sr_star = expected_max_sharpe(max(int(n_trials), 1), v)
    return {"dsr": probabilistic_sharpe(sr, n, skew, kurt, sr_star), "sharpe": sr, "sr_threshold": sr_star,
            "psr": probabilistic_sharpe(sr, n, skew, kurt, 0.0), "n_obs": n, "n_trials": int(n_trials),
            "skew": skew, "kurtosis": kurt, "var_sr_trials": v}


def min_track_record(sr: float, skew: float, kurt: float, sr_benchmark: float = 0.0, conf: float = 0.95) -> float:
    """Minimum number of observations for PSR(sr_benchmark) >= conf."""
    if not np.isfinite(sr) or sr <= sr_benchmark:
        return float("inf")
    z = st.norm.ppf(conf)
    return float(1 + (1 - skew * sr + (kurt - 1) / 4 * sr**2) * (z / (sr - sr_benchmark)) ** 2)


# ----------------------------------------------------------------- bootstrap

def stationary_bootstrap_indices(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    """One stationary-bootstrap resample of indices 0..n-1 (random block lengths, mean `mean_block`),
    preserving short-range dependence such as volatility clustering."""
    p = 1.0 / max(mean_block, 1.0)
    new = rng.random(n) < p
    new[0] = True
    starts = rng.integers(0, n, n)
    t = np.arange(n)
    block_start_t = np.maximum.accumulate(np.where(new, t, 0))
    return (starts[block_start_t] + (t - block_start_t)) % n


def bootstrap_metric(r: np.ndarray, fn, n_boot: int = 1000, mean_block: float = 10.0, seed: int = 0,
                     ci: float = 0.95) -> dict:
    """Stationary-bootstrap distribution of fn(returns)."""
    r = np.asarray(r, dtype=np.float64)
    rng = np.random.default_rng(seed)
    vals = np.array([fn(r[stationary_bootstrap_indices(len(r), mean_block, rng)]) for _ in range(n_boot)])
    vals = vals[np.isfinite(vals)]
    lo, hi = np.quantile(vals, [(1 - ci) / 2, 1 - (1 - ci) / 2]) if len(vals) else (np.nan, np.nan)
    return {"estimate": float(fn(r)), "ci_low": float(lo), "ci_high": float(hi),
            "p_le_zero": float((vals <= 0).mean()) if len(vals) else float("nan")}


def max_drawdown_of_returns(r: np.ndarray) -> float:
    eq = np.cumprod(1 + np.asarray(r, dtype=np.float64))
    eq = np.concatenate([[1.0], eq])
    return float((eq / np.maximum.accumulate(eq) - 1).min())


def trade_monte_carlo(returns: np.ndarray, initial: float, n_sims: int = 2000, seed: int = 0) -> dict:
    """Resample trades with replacement (same count) to see the range of outcomes and drawdowns
    that the same edge could have produced in a different order.

    `returns` are per-trade returns on account equity (P&L / equity before the trade), compounded.
    (Resampling dollar P&L is wrong for compounding strategies: a late, large trade replayed early
    can exceed the whole account.)
    """
    r = np.asarray(returns, dtype=np.float64)
    if len(r) == 0:
        return {}
    rng = np.random.default_rng(seed)
    sims = rng.choice(r, size=(n_sims, len(r)), replace=True)
    eq = initial * np.cumprod(1.0 + np.maximum(sims, -1.0), axis=1)
    eq = np.concatenate([np.full((n_sims, 1), initial), eq], axis=1)
    dd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
    final = eq[:, -1]
    return {"final_p05": float(np.quantile(final, 0.05)), "final_p50": float(np.median(final)),
            "final_p95": float(np.quantile(final, 0.95)), "prob_loss": float((final < initial).mean()),
            "max_dd_p50": float(np.median(dd)), "max_dd_p95": float(np.quantile(dd, 0.05)),
            "prob_ruin_50pct": float((eq.min(axis=1) <= initial * 0.5).mean())}


def trade_returns(trades, equity) -> np.ndarray:
    """Per-trade return on account equity: net P&L / equity at the bar before entry."""
    import polars as pl
    if trades.height == 0:
        return np.array([])
    eq = equity.select("ts", pl.col("equity").shift(1).fill_null(equity["equity"][0]).alias("eq_before"))
    j = trades.select("entry_ts", "pnl_net").join(eq.rename({"ts": "entry_ts"}), on="entry_ts", how="left")
    return (j["pnl_net"] / j["eq_before"]).to_numpy()


# ----------------------------------------------------------------- data-snooping tests

def reality_check(d: np.ndarray, n_boot: int = 1000, mean_block: float = 10.0, seed: int = 0) -> dict:
    """White's Reality Check and Hansen's SPA (consistent) for H0: no strategy beats the benchmark.

    d: (T, K) per-period excess returns of K strategies over the benchmark (use raw returns
       for a zero benchmark). Returns p-values for the best strategy accounting for all K tried.
    """
    d = np.asarray(d, dtype=np.float64)
    if d.ndim == 1:
        d = d[:, None]
    T, K = d.shape
    dbar = d.mean(axis=0)
    rng = np.random.default_rng(seed)
    boots = np.empty((n_boot, K))
    for b in range(n_boot):
        idx = stationary_bootstrap_indices(T, mean_block, rng)
        boots[b] = d[idx].mean(axis=0)
    omega = np.sqrt(T) * boots.std(axis=0, ddof=1)
    omega = np.where(omega > 0, omega, np.inf)
    sq = math.sqrt(T)
    # White RC (unstudentized, recentred at the sample mean)
    rc_stat = sq * dbar.max()
    rc_boot = (sq * (boots - dbar)).max(axis=1)
    # Hansen SPA_c (studentized, consistent recentring: poor strategies are not penalised)
    t_k = sq * dbar / omega
    spa_stat = max(0.0, float(t_k.max()))
    thresh = -math.sqrt(2 * math.log(math.log(max(T, 16))))
    mu_c = np.where(t_k >= thresh, dbar, 0.0)
    spa_boot = np.maximum(0.0, (sq * (boots - mu_c) / omega).max(axis=1))
    return {"rc_p_value": float((rc_boot >= rc_stat).mean()), "spa_p_value": float((spa_boot >= spa_stat).mean()),
            "best_index": int(np.argmax(dbar)), "n_strategies": K, "n_obs": T}


def benjamini_hochberg(p_values, alpha: float = 0.05) -> np.ndarray:
    """Boolean array: which hypotheses are discoveries at false-discovery rate alpha."""
    p = np.asarray(p_values, dtype=np.float64)
    m = len(p)
    if m == 0:
        return np.zeros(0, dtype=bool)
    order = np.argsort(p)
    thresh = alpha * np.arange(1, m + 1) / m
    passed = p[order] <= thresh
    k = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    out = np.zeros(m, dtype=bool)
    out[order[:k]] = True
    return out


def bh_adjusted(p_values) -> np.ndarray:
    """Benjamini–Hochberg adjusted p-values (q-values)."""
    p = np.asarray(p_values, dtype=np.float64)
    m = len(p)
    order = np.argsort(p)
    q = p[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(q, 1.0)
    return out


def newey_west_tstat(x: np.ndarray, lags: int | None = None) -> dict:
    """t-statistic of the mean with autocorrelation-robust (HAC) standard error."""
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return {"mean": float("nan"), "t": float("nan"), "p_value": float("nan"), "n": n}
    lags = lags if lags is not None else int(math.floor(4 * (n / 100) ** (2 / 9)))
    e = x - x.mean()
    s = e @ e / n
    for L in range(1, min(lags, n - 1) + 1):
        w = 1 - L / (lags + 1)
        s += 2 * w * (e[L:] @ e[:-L]) / n
    se = math.sqrt(max(s, 1e-300) / n)
    t = x.mean() / se
    return {"mean": float(x.mean()), "t": float(t), "p_value": float(2 * st.norm.sf(abs(t))), "n": n, "lags": lags}
