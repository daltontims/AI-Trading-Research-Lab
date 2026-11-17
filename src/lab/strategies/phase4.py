"""Phase 4 research strategies: the first batch of hand-designed hypotheses.

Each class implements the rules of one pre-registered hypothesis (scripts/phase4_batch.py).
Rules are deliberately simple with few parameters. All signals use completed bars only and
fill at the next bar's open (engine rule); look-ahead is checked automatically.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from lab.engine.strategy import ContextStrategy, PortfolioStrategy, Strategy, asof_daily
from lab.features import indicators as ind
from lab.features.calendar import is_last_session_of_month, session_position


def _hour(df):
    return df["ts"].dt.hour().to_numpy()


def _weekday(df):
    return df["ts"].dt.weekday().to_numpy()  # Mon=1 .. Sun=7


# ======================================================================= crypto, single asset

class FadeExtremeMove(Strategy):
    """Short-term reversal: fade bar returns beyond k robust standard deviations."""

    name = "fade_extreme_move"
    version = "1"
    style = "mean_reversion"
    default_params = {"k": 3.0, "vol_n": 168, "allow_short": True}

    def signals(self, df, symbol):
        p = self.params
        r = ind.log_returns(df["close"].to_numpy())
        sd = ind.rolling_std(r, p["vol_n"])
        with np.errstate(invalid="ignore"):
            z = r / ind.shift(sd, 1)
            out = {"entry_long": z < -p["k"]}
            if p["allow_short"]:
                out["entry_short"] = z > p["k"]
        return out


class FundingContrarian(Strategy):
    """Funding-rate contrarian/carry: short when longs pay high funding, long when shorts pay."""

    name = "funding_contrarian"
    version = "1"
    style = "carry"
    default_params = {"threshold": 0.0003, "exit_threshold": 0.0001}

    def signals(self, df, symbol):
        p = self.params
        f = df["funding"].to_numpy()
        # Last published funding rate, carried forward between settlements (known at each bar).
        last = pl.Series(np.where(f != 0, f, np.nan)).fill_nan(None).fill_null(strategy="forward").to_numpy()
        last = np.nan_to_num(last.astype(np.float64), nan=0.0)
        with np.errstate(invalid="ignore"):
            return {"entry_short": last > p["threshold"], "exit_short": last < p["exit_threshold"],
                    "entry_long": last < -p["threshold"], "exit_long": last > -p["exit_threshold"]}


class SessionWindow(Strategy):
    """Time-of-day: hold long only during one UTC session window, flat otherwise."""

    name = "session_window"
    version = "1"
    style = "seasonality"
    default_params = {"session": "asia"}
    SESSIONS = {"asia": (0, 8), "europe": (7, 13), "us": (13, 21)}

    def signals(self, df, symbol):
        start, end = self.SESSIONS[self.params["session"]]
        h = _hour(df)
        # Signal on the bar BEFORE the window so the order fills at the window's first open.
        return {"entry_long": h == (start - 1) % 24, "exit_long": h == (end - 1) % 24}


class WeekendHold(Strategy):
    """Weekend drift: hold long from the Saturday 00:00 UTC open to the Monday 00:00 UTC open."""

    name = "weekend_hold"
    version = "1"
    style = "seasonality"
    default_params = {"side": "long"}

    def signals(self, df, symbol):
        wd, h = _weekday(df), _hour(df)
        enter = (wd == 5) & (h == 23)
        leave = (wd == 7) & (h == 23)
        if self.params["side"] == "long":
            return {"entry_long": enter, "exit_long": leave}
        return {"entry_short": enter, "exit_short": leave}


class DailyRangeBreakout(Strategy):
    """Volatility breakout: enter when price moves k × yesterday's range away from today's open;
    exit at the end of the UTC day."""

    name = "daily_range_breakout"
    version = "1"
    style = "breakout"
    default_params = {"k": 0.5, "allow_short": True}

    def signals(self, df, symbol):
        k = self.params["k"]
        day = df["ts"].dt.truncate("1d")
        d = df.with_columns(day=day)
        daily = d.group_by("day").agg(pl.col("open").first().alias("dopen"), pl.col("high").max().alias("dh"),
                                      pl.col("low").min().alias("dl")).sort("day")
        daily = daily.with_columns(prev_range=(pl.col("dh") - pl.col("dl")).shift(1))
        j = d.select("day").with_row_index("i").join(daily.select("day", "dopen", "prev_range"), on="day",
                                                    how="left").sort("i")
        dopen, rng = j["dopen"].to_numpy(), j["prev_range"].to_numpy()
        c = df["close"].to_numpy()
        h = _hour(df)
        with np.errstate(invalid="ignore"):
            up = (c > dopen + k * rng) & (h < 22)
            dn = (c < dopen - k * rng) & (h < 22)
        eod = h == 23
        out = {"entry_long": up, "exit_long": eod}
        if self.params["allow_short"]:
            out |= {"entry_short": dn, "exit_short": eod}
        return out


class VolumeShock(Strategy):
    """Volume-confirmed momentum: a large move on abnormal volume continues for a few bars."""

    name = "volume_shock"
    version = "1"
    style = "momentum"
    default_params = {"vol_z": 3.0, "ret_z": 2.0, "n": 96, "allow_short": True}

    def signals(self, df, symbol):
        p = self.params
        lv = np.log(np.maximum(df["volume"].to_numpy(), 1e-12))
        vz = (lv - ind.shift(ind.sma(lv, p["n"]), 1)) / ind.shift(ind.rolling_std(lv, p["n"]), 1)
        r = ind.log_returns(df["close"].to_numpy())
        rz = r / ind.shift(ind.rolling_std(r, p["n"]), 1)
        with np.errstate(invalid="ignore"):
            shock = vz > p["vol_z"]
            out = {"entry_long": shock & (rz > p["ret_z"])}
            if p["allow_short"]:
                out["entry_short"] = shock & (rz < -p["ret_z"])
        return out


class TrendFilter(Strategy):
    """Price above its n-bar moving average -> long (or short below, if allowed)."""

    name = "trend_filter"
    version = "1"
    style = "trend"
    default_params = {"n": 50, "allow_short": False}

    def signals(self, df, symbol):
        c = df["close"].to_numpy()
        ma = ind.sma(c, self.params["n"])
        with np.errstate(invalid="ignore"):
            above, below = c > ma, c < ma
        out = {"entry_long": above, "exit_long": below}
        if self.params["allow_short"]:
            out |= {"entry_short": below, "exit_short": above}
        return out


# ======================================================================= crypto, multi asset

class LeadLag(PortfolioStrategy):
    """Lead-lag: trade the follower in the direction of the leader's last bar move."""

    name = "lead_lag"
    version = "1"
    style = "cross_asset"
    default_params = {"leader": "BTCUSDT", "follower": "ETHUSDT", "z": 1.5, "n": 168}

    def portfolio_signals(self, data, closes):
        p = self.params
        li, fi = data.symbols.index(p["leader"]), data.symbols.index(p["follower"])
        T, N = closes.shape
        lr = ind.log_returns(closes[:, li])
        fr = ind.log_returns(closes[:, fi])
        # Leader's move relative to the follower's same-bar move: only the unexplained lead counts.
        gap = lr - fr
        z = gap / ind.shift(ind.rolling_std(gap, p["n"]), 1)
        el, es = np.zeros((T, N), bool), np.zeros((T, N), bool)
        with np.errstate(invalid="ignore"):
            el[:, fi] = z > p["z"]
            es[:, fi] = z < -p["z"]
        return {"entry_long": el, "entry_short": es}


class PairReversion(PortfolioStrategy):
    """Statistical arbitrage: trade the log price ratio of two coins back to its moving mean."""

    name = "pair_reversion"
    version = "1"
    style = "stat_arb"
    default_params = {"a": "ETHUSDT", "b": "BTCUSDT", "n": 120, "entry_z": 2.0, "exit_z": 0.5}

    def portfolio_signals(self, data, closes):
        p = self.params
        ia, ib = data.symbols.index(p["a"]), data.symbols.index(p["b"])
        T, N = closes.shape
        spread = np.log(closes[:, ia]) - np.log(closes[:, ib])
        z = ind.zscore(spread, p["n"])
        el, es, xl, xs = (np.zeros((T, N), bool) for _ in range(4))
        with np.errstate(invalid="ignore"):
            rich, cheap, flat = z > p["entry_z"], z < -p["entry_z"], np.abs(z) < p["exit_z"]
        # a rich vs b: short a, long b; a cheap: long a, short b.
        es[:, ia], el[:, ib] = rich, rich
        el[:, ia], es[:, ib] = cheap, cheap
        xl[:, ia] = xl[:, ib] = xs[:, ia] = xs[:, ib] = flat
        return {"entry_long": el, "entry_short": es, "exit_long": xl, "exit_short": xs}


# ======================================================================= ETFs

class RsiReversion(Strategy):
    """Short-term pullback in an uptrend: buy oversold RSI(2) above the 200-day average."""

    name = "rsi2_reversion"
    version = "1"
    style = "mean_reversion"
    default_params = {"entry_rsi": 10.0, "exit_rsi": 70.0, "trend_n": 200}

    def signals(self, df, symbol):
        p = self.params
        c = df["close"].to_numpy()
        r = ind.rsi(c, 2)
        ma = ind.sma(c, p["trend_n"])
        with np.errstate(invalid="ignore"):
            return {"entry_long": (r < p["entry_rsi"]) & (c > ma), "exit_long": r > p["exit_rsi"]}


class TurnOfMonth(Strategy):
    """Turn-of-the-month: hold from the last trading day of the month for the first n trading days."""

    name = "turn_of_month"
    version = "1"
    style = "seasonality"
    default_params = {"days_after": 3}

    def signals(self, df, symbol):
        n = self.params["days_after"]
        first_idx, last_idx = session_position(df["ts"], "XNYS")
        # Order on the 2nd-to-last session fills at the last session's open; the exit order placed on
        # session n of the new month fills at session n+1's open.
        return {"entry_long": last_idx == 2, "exit_long": first_idx == n}


class VixTermStructure(ContextStrategy):
    """Hold equities only when VIX is below VIX3M (contango = calm); cash when inverted."""

    name = "vix_term_structure"
    version = "1"
    style = "regime"
    context_symbols = ("IDX_VIX", "IDX_VIX3M")
    default_params = {"ratio": 1.0}

    def signals(self, df, symbol):
        vix = asof_daily(df["ts"], self.context["IDX_VIX"])
        v3 = asof_daily(df["ts"], self.context["IDX_VIX3M"])
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = vix / v3
            calm = ratio < self.params["ratio"]
            stress = ratio >= self.params["ratio"]
        return {"entry_long": calm, "exit_long": stress}


class VixSpike(ContextStrategy):
    """Buy equities after VIX spikes far above its recent average; hold for a fixed period."""

    name = "vix_spike"
    version = "1"
    style = "mean_reversion"
    context_symbols = ("IDX_VIX",)
    default_params = {"spike": 1.3, "n": 10}

    def signals(self, df, symbol):
        vix = asof_daily(df["ts"], self.context["IDX_VIX"])
        avg = ind.shift(ind.sma(vix, self.params["n"]), 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            return {"entry_long": vix / avg > self.params["spike"]}


class LowVolTrend(Strategy):
    """Hold equities when realised volatility is below its trailing one-year median."""

    name = "low_vol_regime"
    version = "1"
    style = "regime"
    default_params = {"vol_n": 20, "median_n": 252}

    def signals(self, df, symbol):
        p = self.params
        rv = ind.realized_vol(df["close"].to_numpy(), p["vol_n"])
        med = ind.shift(pl.Series(rv).rolling_median(p["median_n"]).to_numpy(), 1)
        with np.errstate(invalid="ignore"):
            return {"entry_long": rv < med, "exit_long": rv > med}


class SectorMomentum(PortfolioStrategy):
    """Cross-sectional momentum: each month hold the top-k ETFs by trailing return (skip last month)."""

    name = "sector_momentum"
    version = "1"
    style = "momentum"
    default_params = {"lookback": 126, "skip": 21, "top": 3}

    def portfolio_signals(self, data, closes):
        p = self.params
        T, N = closes.shape
        last_of_month = is_last_session_of_month(data.ts_datetime)  # rebalance at month-end closes
        past = np.full_like(closes, np.nan)
        lb, sk = p["lookback"], p["skip"]
        past[lb:] = closes[lb - sk:T - sk] / closes[:T - lb] - 1 if sk else closes[lb:] / closes[:T - lb] - 1
        el, xl = np.zeros((T, N), bool), np.zeros((T, N), bool)
        hold = np.zeros(N, bool)
        for t in np.flatnonzero(last_of_month):
            m = past[t]
            ok = np.isfinite(m)
            if ok.sum() < p["top"]:
                continue
            ranks = np.argsort(-np.where(ok, m, -np.inf))[: p["top"]]
            new = np.zeros(N, bool)
            new[ranks] = True
            el[t] = new & ~hold
            xl[t] = hold & ~new
            hold = new
        return {"entry_long": el, "exit_long": xl}


class DualMomentum(PortfolioStrategy):
    """Absolute + relative momentum: hold the best of the assets by trailing return if it is
    positive, otherwise hold nothing. Monthly."""

    name = "dual_momentum"
    version = "1"
    style = "momentum"
    default_params = {"lookback": 126}

    def portfolio_signals(self, data, closes):
        lb = self.params["lookback"]
        T, N = closes.shape
        last_of_month = is_last_session_of_month(data.ts_datetime)
        mom = np.full_like(closes, np.nan)
        mom[lb:] = closes[lb:] / closes[:-lb] - 1
        el, xl = np.zeros((T, N), bool), np.zeros((T, N), bool)
        held = -1
        for t in np.flatnonzero(last_of_month):
            m = mom[t]
            if not np.isfinite(m).all():
                continue
            j = int(np.argmax(m))
            new = j if m[j] > 0 else -1
            if new != held:
                if held >= 0:
                    xl[t, held] = True
                if new >= 0:
                    el[t, new] = True
                held = new
        return {"entry_long": el, "exit_long": xl}


PHASE4 = {c.name: c for c in (FadeExtremeMove, FundingContrarian, SessionWindow, WeekendHold, DailyRangeBreakout,
                              VolumeShock, TrendFilter, LeadLag, PairReversion, RsiReversion, TurnOfMonth,
                              VixTermStructure, VixSpike, LowVolTrend, SectorMomentum, DualMomentum)}
