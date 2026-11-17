"""Time-series splitting: walk-forward windows, purged/embargoed k-fold, CSCV / PBO.

Everything operates on a *returns matrix* M (T periods × N configurations): column j is the
daily return series of parameter set j over the development period. Because strategies are
causal (checked by lab.engine.lookahead), a configuration's returns on any window equal what
it would have earned trading only that window — so selection can be simulated on slices of M.
(Approximation: positions open across a window boundary carry their P&L into the next window.)
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np


def _sharpe_cols(M: np.ndarray) -> np.ndarray:
    mu = M.mean(axis=0)
    sd = M.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 0, mu / sd, -np.inf)


# ----------------------------------------------------------------- walk-forward

@dataclass
class WalkForwardResult:
    oos_returns: np.ndarray           # stitched out-of-sample returns
    oos_index: np.ndarray             # row indices into M
    segments: list[dict]              # per window: train/test ranges, chosen column, IS/OOS Sharpe
    chosen: list[int]

    @property
    def fraction_positive(self) -> float:
        s = [seg["oos_return"] for seg in self.segments]
        return float(np.mean([x > 0 for x in s])) if s else float("nan")

    @property
    def efficiency(self) -> float:
        """Walk-forward efficiency: mean OOS Sharpe / mean IS Sharpe of the chosen configs."""
        is_ = np.mean([s["is_sharpe"] for s in self.segments])
        oos = np.mean([s["oos_sharpe"] for s in self.segments])
        return float(oos / is_) if is_ > 0 else float("nan")


def walk_forward(M: np.ndarray, train: int, test: int, anchored: bool = False, embargo: int = 0) -> WalkForwardResult:
    """Choose the best column (by Sharpe) on each training window, record its next-window returns.

    train/test/embargo are in rows (days). With anchored=True the training window grows from row 0.
    """
    T, N = M.shape
    if train + embargo + test > T:
        raise ValueError(f"not enough data: need {train + embargo + test} rows, have {T}")
    segs, oos, idx, chosen = [], [], [], []
    start = 0
    while True:
        tr0 = 0 if anchored else start
        tr1 = start + train
        te0 = tr1 + embargo
        te1 = min(te0 + test, T)
        if te0 >= T or te1 - te0 < max(5, test // 4):
            break
        sh = _sharpe_cols(M[tr0:tr1])
        j = int(np.argmax(sh))
        r = M[te0:te1, j]
        sd = r.std(ddof=1) if len(r) > 1 else 0
        segs.append({"train": (tr0, tr1), "test": (te0, te1), "chosen": j, "is_sharpe": float(sh[j]),
                     "oos_sharpe": float(r.mean() / sd) if sd > 0 else 0.0,
                     "oos_return": float(np.prod(1 + r) - 1)})
        oos.append(r)
        idx.append(np.arange(te0, te1))
        chosen.append(j)
        start += test
    return WalkForwardResult(np.concatenate(oos) if oos else np.array([]),
                             np.concatenate(idx) if idx else np.array([], dtype=int), segs, chosen)


# ----------------------------------------------------------------- purged k-fold

def purged_kfold(n: int, k: int, horizon: int = 0, embargo: int = 0):
    """Yield (train_idx, test_idx) for k contiguous folds over n time-ordered samples.

    Purging removes training samples whose label window [i, i+horizon] overlaps the test fold;
    the embargo additionally removes `embargo` samples after each test fold (serial correlation).
    """
    bounds = np.linspace(0, n, k + 1).astype(int)
    all_idx = np.arange(n)
    for f in range(k):
        t0, t1 = bounds[f], bounds[f + 1]
        test = all_idx[t0:t1]
        keep = np.ones(n, dtype=bool)
        keep[t0:t1] = False
        keep[max(0, t0 - horizon):t0] = False      # labels of these samples reach into the test fold
        keep[t1:min(n, t1 + embargo)] = False      # embargo after the test fold
        yield all_idx[keep], test


# ----------------------------------------------------------------- CSCV / PBO

def pbo_cscv(M: np.ndarray, n_blocks: int = 16) -> dict:
    """Probability of Backtest Overfitting (Bailey, Borwein, López de Prado & Zhu, 2015).

    Splits time into n_blocks; for every way of choosing half the blocks as in-sample, picks the
    best configuration in-sample and records its rank out-of-sample. PBO = probability that the
    in-sample winner ranks in the bottom half out-of-sample. ~0.5 = selection is pure luck.
    """
    T, N = M.shape
    if N < 2:
        return {"pbo": float("nan"), "n_combinations": 0, "reason": "needs >= 2 configurations"}
    if n_blocks % 2:
        raise ValueError("n_blocks must be even")
    T_use = (T // n_blocks) * n_blocks
    X = M[:T_use].reshape(n_blocks, T_use // n_blocks, N)
    s1 = X.sum(axis=1)               # (blocks, N)
    s2 = (X ** 2).sum(axis=1)
    m = T_use // n_blocks
    combos = np.array(list(itertools.combinations(range(n_blocks), n_blocks // 2)))
    mask = np.zeros((len(combos), n_blocks), dtype=np.float64)
    mask[np.arange(len(combos))[:, None], combos] = 1.0
    n_is = m * n_blocks / 2

    def sharpe(ms1, ms2):
        mu = ms1 / n_is
        var = (ms2 - n_is * mu**2) / (n_is - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(var > 0, mu / np.sqrt(var), -np.inf)

    is_sh = sharpe(mask @ s1, mask @ s2)
    oos_sh = sharpe((1 - mask) @ s1, (1 - mask) @ s2)
    best = np.argmax(is_sh, axis=1)
    oos_best = oos_sh[np.arange(len(combos)), best]
    rank = (oos_sh < oos_best[:, None]).sum(axis=1) + 0.5 * ((oos_sh == oos_best[:, None]).sum(axis=1) - 1) + 1
    w = rank / (N + 1)
    logits = np.log(w / (1 - w))
    is_best = is_sh[np.arange(len(combos)), best]
    slope = np.polyfit(is_best, oos_best, 1)[0] if np.isfinite(is_best).all() and len(combos) > 2 else float("nan")
    return {"pbo": float((logits <= 0).mean()), "n_combinations": len(combos), "median_logit": float(np.median(logits)),
            "degradation_slope": float(slope), "prob_oos_loss": float((oos_best <= 0).mean())}


def rows_per_year(n_rows: int, years: float) -> float:
    return n_rows / years if years > 0 else float("nan")


def annualize_sharpe(sr: float, periods: float) -> float:
    return sr * math.sqrt(periods) if np.isfinite(sr) else float("nan")
