"""Trading-calendar features. Exchange calendars are published in advance, so using them is not
look-ahead (unlike inferring the last trading day from whether the next bar exists)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import polars as pl


@lru_cache(maxsize=4)
def _sessions(calendar: str) -> np.ndarray:
    import exchange_calendars as xcals
    cal = xcals.get_calendar(calendar)
    return np.array([d.date() for d in cal.sessions], dtype="datetime64[D]")


def session_position(ts: pl.Series, calendar: str = "XNYS") -> tuple[np.ndarray, np.ndarray]:
    """For each date: (trading-day number within its month, 1 = first; trading days remaining
    in the month including this one, 1 = last), from the official exchange calendar."""
    sess = _sessions(calendar)
    months = sess.astype("datetime64[M]")
    first = np.ones(len(sess), dtype=np.int64)
    last = np.ones(len(sess), dtype=np.int64)
    for i in range(1, len(sess)):
        first[i] = first[i - 1] + 1 if months[i] == months[i - 1] else 1
    for i in range(len(sess) - 2, -1, -1):
        last[i] = last[i + 1] + 1 if months[i] == months[i + 1] else 1
    days = ts.dt.date().to_numpy().astype("datetime64[D]")
    idx = np.searchsorted(sess, days)
    idx = np.clip(idx, 0, len(sess) - 1)
    ok = sess[idx] == days
    return np.where(ok, first[idx], -1), np.where(ok, last[idx], -1)


def is_last_session_of_month(ts: pl.Series, calendar: str = "XNYS") -> np.ndarray:
    return session_position(ts, calendar)[1] == 1
