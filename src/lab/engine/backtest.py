"""High-level backtest API.

    data = load(["BTCUSDT"], "1h", split="development", funding=True)
    result = run_backtest(MyStrategy(n=20), data, RiskConfig(), ExecutionConfig(cost_profile="crypto_perp"))
    print(result.summary())

Prefer `lab.research.run_experiment`, which also records the run in the research registry.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
import polars as pl

from lab import costs as costs_mod
from lab.engine import core, metrics
from lab.engine.data import MarketData, timeframe_seconds
from lab.engine.strategy import SignalGrid, Strategy
from lab.features.regimes import daily_regimes

US_PER_YEAR = 365.25 * 86400 * 1e6


@dataclass
class RiskConfig:
    """Account and risk settings. No leverage by default (gross exposure <= 1× equity)."""

    initial_cash: float = 5000.0
    sizing: str = "risk"                 # risk | pct_equity | fixed_notional
    risk_per_trade: float = 0.01         # fraction of equity lost if the stop is hit (sizing="risk")
    position_pct: float = 1.0            # fraction of equity per position (sizing="pct_equity")
    fixed_notional: float = 1000.0       # currency per position (sizing="fixed_notional")
    max_position_pct: float = 1.0        # cap on any single position's value / equity
    max_gross_exposure: float = 1.0      # cap on sum of |position values| / equity (1.0 = no leverage)
    max_open_positions: int = 10
    max_daily_loss: float = 0.0          # e.g. 0.03 = flatten & stop for the day after −3% (0 = off)
    max_drawdown: float = 0.0            # e.g. 0.25 = flatten & halt after −25% from peak (0 = off)
    max_bars_held: int = 0               # time exit after N bars (0 = off)

    def __post_init__(self):
        if self.sizing not in ("risk", "pct_equity", "fixed_notional"):
            raise ValueError(f"unknown sizing {self.sizing!r}")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.max_gross_exposure > 1.0:
            # Allowed for research, but never silently: recorded in the experiment config.
            pass


@dataclass
class ExecutionConfig:
    delay_bars: int = 1                  # signals fill no earlier than the open of the next bar
    cost_profile: str | None = None      # configs/costs.yaml profile (default per asset class)
    profile_by_symbol: dict = field(default_factory=dict)
    cost_multiplier: float = 1.0         # stress testing: scales spread, slippage, fees, borrow
    cost_overrides: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.delay_bars < 1:
            raise ValueError("delay_bars must be >= 1: a signal cannot fill on the bar that produced it")


@dataclass
class BacktestResult:
    strategy: dict
    data: dict
    risk: dict
    execution: dict
    cost_models: dict
    equity: pl.DataFrame
    trades: pl.DataFrame
    metrics: dict
    monthly: pl.DataFrame
    regimes: pl.DataFrame
    skipped: dict
    warnings: list[str]

    def summary(self) -> str:
        m = self.metrics
        lines = [f"{self.strategy['name']} {self.strategy['params']} on {','.join(self.data['symbols'])} "
                 f"{self.data['timeframe']} [{self.data['split']}] cost×{self.execution['cost_multiplier']}"]
        keys = ["total_return", "cagr", "sharpe", "sortino", "calmar", "max_drawdown", "trades", "win_rate",
                "profit_factor", "expectancy", "expectancy_r", "avg_holding_hours", "exposure", "turnover",
                "cost_share_of_gross", "benchmark_total_return", "benchmark_sharpe", "benchmark_max_drawdown"]
        for k in keys:
            v = m.get(k)
            lines.append(f"  {k:24s} {_fmt(v)}")
        for w in self.warnings:
            lines.append(f"  ! {w}")
        return "\n".join(lines)


def _fmt(v):
    if isinstance(v, float):
        return "nan" if math.isnan(v) else f"{v:,.4f}"
    return str(v)


def _cost_models(data: MarketData, ex: ExecutionConfig) -> dict[str, costs_mod.CostModel]:
    out = {}
    for s in data.symbols:
        prof = ex.profile_by_symbol.get(s, ex.cost_profile)
        cm = costs_mod.for_instrument(s, prof, **ex.cost_overrides)
        out[s] = cm.scaled(ex.cost_multiplier) if ex.cost_multiplier != 1.0 else cm
    return out


def run_backtest(strategy: Strategy, data: MarketData, risk: RiskConfig | None = None,
                 execution: ExecutionConfig | None = None, signals: SignalGrid | None = None,
                 regime_symbol: str | None = None) -> BacktestResult:
    risk = risk or RiskConfig()
    execution = execution or ExecutionConfig()
    sig = signals if signals is not None else strategy.generate(data)
    cms = _cost_models(data, execution)
    syms = data.symbols
    N = len(syms)
    warnings: list[str] = []

    o, h, l, c = (data.grid(k) for k in ("open", "high", "low", "close"))
    vol = np.nan_to_num(data.grid("volume"), nan=0.0)
    valid = data.valid()
    bad = valid & ~(np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & (c > 0))
    if bad.any():
        warnings.append(f"{int(bad.sum())} bars with missing/invalid prices treated as missing")
        valid &= ~bad

    hs = data.grid("half_spread")
    fund = np.nan_to_num(data.grid("funding"), nan=0.0)
    div = np.nan_to_num(data.grid("dividend"), nan=0.0)
    for j, s in enumerate(syms):
        cm = cms[s]
        col = hs[:, j]
        has_quotes = np.isfinite(col[valid[:, j]]).any()
        if has_quotes:
            hs[:, j] = col * cm.cost_multiplier + cm.spread_markup_bps / 1e4
        else:
            hs[:, j] = cm.half_spread_bps / 1e4
        if not cm.funding:
            fund[:, j] = 0.0
        elif not np.any(fund[:, j]):
            warnings.append(f"{s}: perpetual profile but no funding data loaded (use funding=True)")
    hs = np.nan_to_num(hs, nan=0.0)

    def arr(attr, scale=1.0, dtype=np.float64):
        return np.array([getattr(cms[s], attr) * scale for s in syms], dtype=dtype)

    ts = data.ts
    day_id = (ts // int(86400 * 1e6)).astype(np.int64)
    bar_us = timeframe_seconds(data.timeframe) * 1e6
    dt_years = np.diff(ts, prepend=ts[0] - bar_us) / US_PER_YEAR
    n_entries = int(sig.entry_long.sum() + sig.entry_short.sum())
    sizing_mode = {"risk": core.SIZING_RISK, "pct_equity": core.SIZING_PCT_EQUITY,
                   "fixed_notional": core.SIZING_FIXED_NOTIONAL}[risk.sizing]

    eq, cash, gexp, nexp, npos, tr, skipped, stats = core.simulate(
        day_id, dt_years, o, h, l, c, vol, valid, hs, fund, div,
        sig.entry_long & valid, sig.entry_short & valid, sig.exit_long & valid, sig.exit_short & valid,
        sig.stop_dist, sig.target_dist, sig.trail_dist, sig.priority,
        arr("multiplier"), arr("lot_size"), arr("min_notional"), arr("fee_bps", 1e-4),
        arr("maker_fee_bps", 1e-4), arr("sell_fee_bps", 1e-4), arr("fee_per_unit"), arr("min_fee"),
        arr("slippage_bps", 1e-4), arr("slippage_range_frac"), arr("allow_short", dtype=np.bool_),
        arr("borrow_rate_annual"), arr("financing_rate_annual"), arr("max_participation"),
        float(risk.initial_cash), sizing_mode, float(risk.risk_per_trade), float(risk.position_pct),
        float(risk.fixed_notional), float(risk.max_position_pct), float(risk.max_gross_exposure),
        int(risk.max_open_positions), float(risk.max_daily_loss), float(risk.max_drawdown),
        int(risk.max_bars_held), int(execution.delay_bars), n_entries + N + 16,
    )
    if stats[4] > tr.shape[0]:
        raise RuntimeError("trade buffer overflow — engine bug")

    ts_dt = data.ts_datetime
    equity = pl.DataFrame({"ts": ts_dt, "equity": eq, "cash": cash, "gross_exposure": gexp,
                           "net_exposure": nexp, "positions": npos})
    trades = _trades_frame(tr, syms, ts_dt)
    skipped_d = {core.SKIP_REASONS[k]: int(v) for k, v in enumerate(skipped) if v}

    m = analyze(equity, trades, risk.initial_cash, stats, data)
    bench = buy_and_hold(data, valid, c, cms, risk.initial_cash)
    m.update(benchmark_stats(equity, bench, risk.initial_cash))
    monthly = metrics.monthly_returns(equity, risk.initial_cash)
    reg = regime_breakdown(equity, data, risk.initial_cash, regime_symbol or syms[0])
    warnings += fidelity_warnings(data, m, cms)

    return BacktestResult(
        strategy=strategy.describe(),
        data={"symbols": syms, "timeframe": data.timeframe, "split": data.split, "market": data.market,
              "start": str(ts_dt[0]), "end": str(ts_dt[-1]), "bars": data.n_bars,
              "fingerprints": data.fingerprints},
        risk=asdict(risk), execution=asdict(execution),
        cost_models={s: cm.to_dict() for s, cm in cms.items()},
        equity=equity, trades=trades, metrics=m, monthly=monthly, regimes=reg,
        skipped=skipped_d, warnings=warnings,
    )


def _trades_frame(tr: np.ndarray, syms: list[str], ts_dt: pl.Series) -> pl.DataFrame:
    C = core
    if tr.shape[0] == 0:
        return pl.DataFrame(schema={"symbol": pl.Utf8, "side": pl.Int8, "entry_ts": ts_dt.dtype,
                                    "exit_ts": ts_dt.dtype, "qty": pl.Float64, "entry_ref": pl.Float64,
                                    "entry_price": pl.Float64, "exit_ref": pl.Float64, "exit_price": pl.Float64,
                                    "fees": pl.Float64, "carry": pl.Float64, "pnl_gross": pl.Float64,
                                    "pnl_net": pl.Float64, "initial_risk": pl.Float64, "exit_reason": pl.Utf8,
                                    "bars_held": pl.Int64, "notional": pl.Float64})
    ei, xi = tr[:, C.T_ENTRY_IDX].astype(int), tr[:, C.T_EXIT_IDX].astype(int)
    return pl.DataFrame({
        "symbol": [syms[int(i)] for i in tr[:, C.T_INST]],
        "side": tr[:, C.T_SIDE].astype(np.int8),
        "entry_ts": ts_dt.gather(ei), "exit_ts": ts_dt.gather(xi),
        "qty": tr[:, C.T_QTY], "entry_ref": tr[:, C.T_ENTRY_REF], "entry_price": tr[:, C.T_ENTRY_PX],
        "exit_ref": tr[:, C.T_EXIT_REF], "exit_price": tr[:, C.T_EXIT_PX], "fees": tr[:, C.T_FEES],
        "carry": tr[:, C.T_CARRY], "pnl_gross": tr[:, C.T_PNL_GROSS], "pnl_net": tr[:, C.T_PNL_NET],
        "initial_risk": tr[:, C.T_INIT_RISK],
        "exit_reason": [C.EXIT_REASONS[int(r)] for r in tr[:, C.T_REASON]],
        "bars_held": tr[:, C.T_BARS].astype(np.int64), "notional": tr[:, C.T_NOTIONAL],
    })


def analyze(equity: pl.DataFrame, trades: pl.DataFrame, initial_cash: float, stats: np.ndarray,
            data: MarketData) -> dict:
    eq = equity["equity"].to_numpy()
    ts_us = data.ts
    bar_us = timeframe_seconds(data.timeframe) * 1e6
    years = (ts_us[-1] - ts_us[0] + bar_us) / US_PER_YEAR
    total = float(eq[-1] / initial_cash - 1.0)
    de = metrics.daily_equity(equity, initial_cash)
    r = metrics.returns_from_equity(de["equity"].to_numpy())
    periods = len(r) / years if years > 0 else float("nan")
    mdd, _, _ = metrics.max_drawdown(eq, initial_cash)
    days = (ts_us - ts_us[0]) / 86400e6
    cg = metrics.cagr(total, years)
    traded, fees, carry, spread_slip = stats[:4]
    gross = float(trades["pnl_gross"].sum()) if trades.height else 0.0
    out = {
        "initial_cash": initial_cash, "final_equity": float(eq[-1]), "net_profit": float(eq[-1] - initial_cash),
        "total_return": total, "years": years, "cagr": cg,
        "sharpe": metrics.sharpe(r, periods), "sortino": metrics.sortino(r, periods),
        "max_drawdown": mdd, "max_drawdown_days": metrics.drawdown_durations(np.concatenate([[initial_cash], eq]),
                                                                             np.concatenate([[0.0], days])),
        "calmar": cg / abs(mdd) if mdd < 0 and cg == cg else float("nan"),
        "daily_periods_per_year": periods,
        "exposure": float((equity["positions"] > 0).mean()),
        "avg_gross_exposure": float(equity["gross_exposure"].mean()),
        "turnover": float(traded / np.mean(eq) / years) if years > 0 else float("nan"),
        "traded_notional": float(traded), "total_fees": float(fees), "total_spread_slippage": float(spread_slip),
        "total_carry": float(carry), "pnl_gross": gross,
        "cost_share_of_gross": float((fees + spread_slip) / gross) if gross > 0 else float("nan"),
    }
    out.update(metrics.trade_stats(trades))
    return out


def buy_and_hold(data: MarketData, valid: np.ndarray, close: np.ndarray, cms: dict, initial_cash: float) -> np.ndarray:
    """Equal-weight buy-and-hold of the instruments, entered at each one's first close,
    with one-way entry cost (half-spread + slippage + fee) and the same cost on exit."""
    T, N = close.shape
    eq = np.zeros(T)
    alloc = initial_cash / N
    for j, s in enumerate(data.symbols):
        cm = cms[s]
        rows = np.flatnonzero(valid[:, j])
        first = rows[0]
        oneway = cm.half_spread_bps / 1e4 + cm.slippage_bps / 1e4 + cm.fee_bps / 1e4
        units = alloc * (1 - oneway) / close[first, j]
        px = close[:, j].copy()
        px[~valid[:, j]] = np.nan
        px = pl.Series(px).fill_null(strategy="forward").fill_nan(None).fill_null(strategy="forward").to_numpy()
        val = np.where(np.arange(T) < first, alloc, units * np.nan_to_num(px, nan=close[first, j]))
        # Dividends reinvested approximation: add cash dividends received.
        div = np.nan_to_num(data.grid("dividend")[:, j], nan=0.0)
        val = val + np.cumsum(np.where(np.arange(T) >= first, div * units, 0.0))
        val[-1] *= (1 - oneway)
        eq += val
    return eq


def benchmark_stats(equity: pl.DataFrame, bench: np.ndarray, initial_cash: float) -> dict:
    b = equity.select("ts").with_columns(equity=pl.Series(bench))
    years = max((equity["ts"][-1] - equity["ts"][0]).total_seconds() / (365.25 * 86400), 1e-9)
    bd = metrics.daily_equity(b, initial_cash)
    sd = metrics.daily_equity(equity, initial_cash)
    rb = metrics.returns_from_equity(bd["equity"].to_numpy())
    rs = metrics.returns_from_equity(sd["equity"].to_numpy())
    periods = len(rb) / years
    out = {
        "benchmark": "equal-weight buy & hold (after one-way costs each side)",
        "benchmark_total_return": float(bench[-1] / initial_cash - 1),
        "benchmark_cagr": metrics.cagr(float(bench[-1] / initial_cash - 1), years),
        "benchmark_sharpe": metrics.sharpe(rb, periods),
        "benchmark_max_drawdown": metrics.max_drawdown(bench, initial_cash)[0],
    }
    if len(rs) > 2 and np.std(rb) > 0 and np.std(rs) > 0:
        cov = np.cov(rs, rb)
        out["beta_to_benchmark"] = float(cov[0, 1] / cov[1, 1])
        out["correlation_to_benchmark"] = float(np.corrcoef(rs, rb)[0, 1])
    return out


def regime_breakdown(equity: pl.DataFrame, data: MarketData, initial_cash: float, symbol: str) -> pl.DataFrame:
    """Strategy daily returns grouped by trend and volatility regimes of `symbol` (lagged labels)."""
    f = data.frames[symbol]
    daily = f.group_by(pl.col("ts").dt.truncate("1d")).agg(pl.col("close").last()).sort("ts")
    if daily.height < 30:
        return pl.DataFrame()
    reg = daily_regimes(daily)
    de = metrics.daily_equity(equity, initial_cash)
    r = de.with_columns(ret=pl.col("equity") / pl.col("equity").shift(1) - 1).drop_nulls().rename({"day": "ts"})
    j = r.join(reg.with_columns(pl.col("ts").cast(r["ts"].dtype)), on="ts", how="left").fill_null("unknown")
    rows = []
    for col in ("trend", "volatility"):
        g = j.group_by(col).agg(
            days=pl.len(), compounded=(pl.col("ret") + 1).product() - 1,
            mean_daily=pl.col("ret").mean(), std_daily=pl.col("ret").std())
        for rec in g.iter_rows(named=True):
            rows.append({"dimension": col, "regime": rec[col], "days": rec["days"],
                         "compounded_return": rec["compounded"], "mean_daily": rec["mean_daily"],
                         "std_daily": rec["std_daily"]})
    return pl.DataFrame(rows).sort("dimension", "regime")


def fidelity_warnings(data: MarketData, m: dict, cms: dict) -> list[str]:
    """Flag results whose execution realism is limited by data granularity."""
    w = []
    tf = timeframe_seconds(data.timeframe)
    has_quotes = any(np.isfinite(data.frames[s]["half_spread"].to_numpy()).any() for s in data.symbols)
    bars = m.get("avg_bars_held", float("nan"))
    if tf <= 300 and bars == bars and bars < 30:
        w.append("SCALPING FIDELITY: average holding is short relative to bar size; intrabar fill order, queue "
                 "position and latency are not modelled. Not validatable without tick/quote data.")
    if tf < 86400 and not has_quotes:
        w.append("No bid/ask data: spreads are assumed constants from configs, not observed.")
    if tf >= 86400:
        w.append("Daily bars: entries/exits assume market-on-open fills; intraday path of stops is approximated "
                 "from daily high/low (stop assumed to win when stop and target share a bar).")
    if m.get("trades", 0) < 30:
        w.append(f"Only {m.get('trades', 0)} trades: statistically meaningless.")
    return w
