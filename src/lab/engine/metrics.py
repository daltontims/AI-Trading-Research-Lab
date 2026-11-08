"""Performance metrics. All functions are pure and covered by known-answer tests.

Conventions
- Returns are simple returns. Annualisation uses the observed number of daily
  observations per year (≈365 for crypto, ≈252 for US equities).
- Sharpe = mean(daily r − rf) / std(daily r, ddof=1) × √periods; rf defaults to 0.
- Sortino = mean(daily r − rf) / sqrt(mean(min(r − rf, 0)²)) × √periods (target 0, all periods).
- Max drawdown is measured on bar-level equity, including the starting balance as first peak.
- Trade statistics use net P&L (after fees, spread, slippage, funding, borrow, dividends).
"""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import polars as pl


def daily_equity(equity: pl.DataFrame, initial_cash: float) -> pl.DataFrame:
    """Last equity of each UTC day, preceded by the initial balance on the day before."""
    d = equity.group_by(pl.col("ts").dt.truncate("1d").alias("day")).agg(pl.col("equity").last()).sort("day")
    start = pl.DataFrame({"day": [d["day"][0] - timedelta(days=1)], "equity": [float(initial_cash)]},
                         schema=d.schema)
    return pl.concat([start, d])


def returns_from_equity(eq: np.ndarray) -> np.ndarray:
    eq = np.asarray(eq, dtype=np.float64)
    return eq[1:] / eq[:-1] - 1.0


def sharpe(r: np.ndarray, periods: float, rf: float = 0.0) -> float:
    r = np.asarray(r, dtype=np.float64) - rf / periods
    if len(r) < 2:
        return float("nan")
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(periods)) if sd > 0 else float("nan")


def sortino(r: np.ndarray, periods: float, rf: float = 0.0) -> float:
    r = np.asarray(r, dtype=np.float64) - rf / periods
    if len(r) < 2:
        return float("nan")
    dd = math.sqrt(np.mean(np.minimum(r, 0.0) ** 2))
    return float(r.mean() / dd * math.sqrt(periods)) if dd > 0 else float("nan")


def max_drawdown(eq: np.ndarray, initial: float | None = None) -> tuple[float, int, int]:
    """(max drawdown as a negative fraction, peak index, trough index)."""
    eq = np.asarray(eq, dtype=np.float64)
    if initial is not None:
        eq = np.concatenate([[initial], eq])
    peaks = np.maximum.accumulate(eq)
    dd = eq / peaks - 1.0
    trough = int(np.argmin(dd))
    peak = int(np.argmax(eq[: trough + 1])) if trough > 0 else 0
    off = 1 if initial is not None else 0
    return float(dd[trough]), peak - off, trough - off


def drawdown_durations(eq: np.ndarray, ts_days: np.ndarray) -> float:
    """Longest time (days) from an equity peak until equity first gets back to that peak
    (or until the end of the data if it never recovers)."""
    eq = np.asarray(eq, dtype=np.float64)
    longest, peak_val, peak_i, under = 0.0, -np.inf, 0, False
    for i in range(len(eq)):
        if eq[i] >= peak_val:
            if under:
                longest = max(longest, ts_days[i] - ts_days[peak_i])
                under = False
            peak_val, peak_i = eq[i], i
        else:
            under = True
    if under:
        longest = max(longest, ts_days[-1] - ts_days[peak_i])
    return float(longest)


def cagr(total_return: float, years: float, min_years: float = 7 / 365.25) -> float:
    """Compound annual growth rate. Undefined (NaN) for samples shorter than `min_years`:
    annualising a few days of returns produces meaningless numbers."""
    if years < min_years:
        return float("nan")
    if total_return <= -1:
        return -1.0
    try:
        return float((1.0 + total_return) ** (1.0 / years) - 1.0)
    except OverflowError:
        return float("inf")


def max_consecutive(flags: np.ndarray) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def trade_stats(trades: pl.DataFrame) -> dict:
    n = trades.height
    if n == 0:
        return {"trades": 0, "win_rate": float("nan"), "avg_win": float("nan"), "avg_loss": float("nan"),
                "payoff_ratio": float("nan"), "profit_factor": float("nan"), "expectancy": float("nan"),
                "expectancy_r": float("nan"), "avg_holding_hours": float("nan"), "avg_bars_held": float("nan"),
                "max_consecutive_wins": 0, "max_consecutive_losses": 0, "long_trades": 0, "short_trades": 0}
    pnl = trades["pnl_net"].to_numpy()
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_win, gross_loss = wins.sum(), -losses.sum()
    risk = trades["initial_risk"].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        r_mult = pnl / risk
    r_mult = r_mult[np.isfinite(r_mult)]
    hold = (trades["exit_ts"] - trades["entry_ts"]).dt.total_seconds().to_numpy() / 3600.0
    return {
        "trades": n,
        "win_rate": float(len(wins) / n),
        "avg_win": float(wins.mean()) if len(wins) else float("nan"),
        "avg_loss": float(losses.mean()) if len(losses) else float("nan"),
        "payoff_ratio": float(wins.mean() / -losses.mean()) if len(wins) and len(losses) else float("nan"),
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else float("nan")),
        "expectancy": float(pnl.mean()),
        "expectancy_r": float(r_mult.mean()) if len(r_mult) else float("nan"),
        "avg_holding_hours": float(hold.mean()),
        "avg_bars_held": float(trades["bars_held"].mean()),
        "max_consecutive_wins": max_consecutive(pnl > 0),
        "max_consecutive_losses": max_consecutive(pnl < 0),
        "long_trades": int((trades["side"] > 0).sum()),
        "short_trades": int((trades["side"] < 0).sum()),
    }


def monthly_returns(equity: pl.DataFrame, initial_cash: float) -> pl.DataFrame:
    m = equity.group_by(pl.col("ts").dt.truncate("1mo").alias("month")).agg(pl.col("equity").last()).sort("month")
    prev = np.concatenate([[initial_cash], m["equity"].to_numpy()[:-1]])
    return m.with_columns(ret=pl.col("equity") / pl.Series(prev) - 1.0).select(
        pl.col("month").dt.strftime("%Y-%m"), "ret")
