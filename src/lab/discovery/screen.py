"""Event-study screening: protocol stage IDEA -> EFFECT.

For one entry condition on one instrument (development data only) we ask a narrow question
before any backtest: after the condition fires, is the return over the next h bars better than
an ordinary h-bar return on the same instrument?

  * The event return is measured as the engine would trade it: from the NEXT bar's open to the
    close h bars later.
  * Overlapping events are thinned (an event within h bars of the previous kept one is dropped)
    so the events are close to independent and a plain one-sided t-test is honest.
  * The baseline is the mean of all h-bar open-to-close returns on the same data.

Across all tests of a batch, Benjamini-Hochberg controls the false-discovery rate (protocol §5).
Only (entry, filter, instrument) combinations with a BH-significant effect go on to backtests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps

from lab.discovery.templates import CORE_ENTRIES, ENTRIES, HORIZON, entry_signal, trend_filter


@dataclass
class EventTest:
    entry: str
    filt: str
    symbol: str
    x: float
    horizon: int
    events: int
    mean_excess: float      # mean event return minus baseline (log return)
    t_stat: float
    p_value: float          # one-sided: event return > baseline


def forward_returns(df, h: int) -> np.ndarray:
    """log(close[t+h] / open[t+1]): the return of entering at the next open and holding h bars.
    Used only to MEASURE outcomes in the event study, never inside a strategy."""
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    n = len(c)
    out = np.full(n, np.nan)
    if n > h:
        with np.errstate(invalid="ignore", divide="ignore"):
            out[: n - h] = np.log(c[h:] / o[1: n - h + 1])
    return out


def thin(mask: np.ndarray, h: int) -> np.ndarray:
    """Keep an event only if it is at least h bars after the previous kept event."""
    idx = np.flatnonzero(mask)
    keep, last = [], -10**9
    for i in idx:
        if i - last >= h:
            keep.append(i)
            last = i
    return np.asarray(keep, dtype=int)


def event_test(df, entry: str, filt: str, symbol: str, x: float, h: int | None = None,
               min_events: int = 20, ctx: dict | None = None) -> EventTest:
    h = h or HORIZON[ENTRIES[entry].style]
    fwd = forward_returns(df, h)
    sig = entry_signal(entry, df, x, ctx) & trend_filter(filt, df)
    sig = np.nan_to_num(sig.astype(float), nan=0.0).astype(bool) & np.isfinite(fwd)
    base = float(np.nanmean(fwd))
    ev = fwd[thin(sig, h)] - base
    n = len(ev)
    if n < min_events or not np.isfinite(ev).all() or np.std(ev, ddof=1) == 0:
        return EventTest(entry, filt, symbol, x, h, n, float(np.mean(ev)) if n else math.nan, math.nan, 1.0)
    t = float(np.mean(ev) / (np.std(ev, ddof=1) / math.sqrt(n)))
    p = float(sps.t.sf(t, df=n - 1))
    return EventTest(entry, filt, symbol, x, h, n, float(np.mean(ev)), t, p)


def screen_symbol(args) -> list[EventTest]:
    """All (entry, filter, x) tests for one instrument's development bars.
    args = (symbol, df, filters[, entries[, ctx]]); entries default to the core entries."""
    symbol, df, filters, *rest = args
    entries = rest[0] if rest else CORE_ENTRIES
    ctx = rest[1] if len(rest) > 1 else None
    return [event_test(df, entry, filt, symbol, x, ctx=ctx)
            for entry in entries for filt in filters for x in ENTRIES[entry].grid]


def pooled_event_test(frames: dict, entry: str, filt: str, group: str, x: float, h: int | None = None,
                      min_dates: int = 30, ctx: dict | None = None) -> EventTest:
    """The same question asked of a whole market group at once (e.g. all 14 US ETFs).

    Each instrument's events are found and thinned as in event_test, and measured against that
    instrument's own baseline. Events are then averaged per DATE, so ten correlated ETFs firing on
    the same day count as one observation, not ten. The per-date averages are thinned again (kept
    dates at least h bars apart on the group's common calendar) and tested with a one-sided t-test.
    """
    h = h or HORIZON[ENTRIES[entry].style]
    per_date: dict = {}
    for sym, df in frames.items():
        fwd = forward_returns(df, h)
        sig = entry_signal(entry, df, x, ctx) & trend_filter(filt, df)
        sig = np.nan_to_num(sig.astype(float), nan=0.0).astype(bool) & np.isfinite(fwd)
        base = float(np.nanmean(fwd))
        days = df["ts"].dt.date().to_numpy()
        for i in thin(sig, h):
            per_date.setdefault(days[i], []).append(fwd[i] - base)
    calendar = np.unique(np.concatenate([df["ts"].dt.date().to_numpy() for df in frames.values()]))
    pos = {d: i for i, d in enumerate(calendar)}
    dates = sorted(per_date)
    mask = np.zeros(len(calendar), bool)
    mask[[pos[d] for d in dates]] = True
    kept = [calendar[i] for i in thin(mask, h)]
    ev = np.array([np.mean(per_date[d]) for d in kept])
    n = len(ev)
    if n < min_dates or np.std(ev, ddof=1) == 0:
        return EventTest(entry, filt, group, x, h, n, float(np.mean(ev)) if n else math.nan, math.nan, 1.0)
    t = float(np.mean(ev) / (np.std(ev, ddof=1) / math.sqrt(n)))
    return EventTest(entry, filt, group, x, h, n, float(np.mean(ev)), t, float(sps.t.sf(t, df=n - 1)))


def screen_group(args) -> list[EventTest]:
    """All (entry, filter, x) pooled tests for one market group. args = (group, frames, filters)."""
    group, frames, filters, *rest = args
    entries = rest[0] if rest else CORE_ENTRIES
    ctx = rest[1] if len(rest) > 1 else None
    return [pooled_event_test(frames, entry, filt, group, x, ctx=ctx)
            for entry in entries for filt in filters for x in ENTRIES[entry].grid]
