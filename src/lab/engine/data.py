"""Market data prepared for backtesting.

`MarketData` aligns one or more instruments on a common timestamp grid (the union of
their bar times). An instrument without a bar at a grid time is marked invalid there:
nothing fills, nothing is interpolated, and its last close is used only for valuation.

Strategies see each instrument's *own* bars (`frames[symbol]`), so indicators are never
distorted by other instruments' timestamps. Their outputs are scattered back to the grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from lab import instruments
from lab.data import lake, splits

TIMEFRAMES = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200,
              "4h": 14400, "1d": 86400}


def timeframe_seconds(tf: str) -> int:
    if tf not in TIMEFRAMES:
        raise ValueError(f"unsupported timeframe {tf!r}; choose from {list(TIMEFRAMES)}")
    return TIMEFRAMES[tf]


def resample(df: pl.DataFrame, every: str) -> pl.DataFrame:
    """Aggregate bars (trade or bid/ask) to a coarser timeframe. Empty periods are omitted.

    The output bar stamped T covers [T, T+every) and is complete only at T+every.
    """
    if "bid_open" in df.columns:
        aggs = [pl.col("bid_open").first(), pl.col("bid_high").max(), pl.col("bid_low").min(),
                pl.col("bid_close").last(), pl.col("ask_open").first(), pl.col("ask_high").max(),
                pl.col("ask_low").min(), pl.col("ask_close").last(), pl.col("spread_mean").mean(),
                pl.col("spread_max").max(), pl.col("ticks").sum()]
    else:
        aggs = [pl.col("open").first(), pl.col("high").max(), pl.col("low").min(), pl.col("close").last(),
                pl.col("volume").sum()]
        for c in ("quote_volume", "taker_buy_volume"):
            if c in df.columns:
                aggs.append(pl.col(c).sum())
        if "trades" in df.columns:
            aggs.append(pl.col("trades").sum())
        for c, how in (("dividend", "sum"), ("split", "product")):
            if c in df.columns:
                aggs.append(getattr(pl.col(c), how)())
    return df.sort("ts").group_by_dynamic("ts", every=every, closed="left", label="left").agg(aggs)


def standardize(df: pl.DataFrame) -> pl.DataFrame:
    """Give every frame the columns open/high/low/close/volume/half_spread/funding/dividend.

    Bid/ask bars are converted to mid prices; half_spread (fraction of price) is the quoted
    spread at the bar open, where market orders fill. Trade-price bars get NaN half_spread
    (the cost model supplies an assumption).
    """
    if "bid_open" in df.columns:
        mid = lambda s: (pl.col(f"bid_{s}") + pl.col(f"ask_{s}")) / 2  # noqa: E731
        df = df.with_columns(
            open=mid("open"), high=mid("high"), low=mid("low"), close=mid("close"),
            volume=pl.col("ticks").cast(pl.Float64).fill_null(0.0) if "ticks" in df.columns else pl.lit(0.0),
            half_spread=(pl.col("ask_open") - pl.col("bid_open")) / (pl.col("ask_open") + pl.col("bid_open")),
        )
    else:
        df = df.with_columns(half_spread=pl.lit(None, dtype=pl.Float64))
    if "funding" not in df.columns:
        df = df.with_columns(funding=pl.lit(0.0))
    if "dividend" not in df.columns:
        df = df.with_columns(dividend=pl.lit(0.0))
    return df.select("ts", "open", "high", "low", "close", "volume", "half_spread", "funding", "dividend",
                     *[c for c in df.columns if c in ("quote_volume", "taker_buy_volume", "trades")])


@dataclass
class MarketData:
    symbols: list[str]
    timeframe: str
    frames: dict[str, pl.DataFrame]          # each instrument's own bars (standardized)
    ts: np.ndarray = field(init=False)        # grid timestamps, int64 microseconds UTC
    index: dict[str, np.ndarray] = field(init=False)  # own-bar row -> grid row
    split: str = "custom"
    market: str = "custom"
    fingerprints: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        for s in self.symbols:
            f = self.frames[s]
            if not f["ts"].is_sorted() or f["ts"].n_unique() != f.height:
                raise ValueError(f"{s}: timestamps must be sorted and unique")
        all_ts = np.unique(np.concatenate([self.frames[s]["ts"].dt.epoch("us").to_numpy() for s in self.symbols]))
        self.ts = all_ts
        self.index = {s: np.searchsorted(all_ts, self.frames[s]["ts"].dt.epoch("us").to_numpy())
                      for s in self.symbols}

    @property
    def n_bars(self) -> int:
        return len(self.ts)

    @property
    def ts_datetime(self) -> pl.Series:
        return pl.Series("ts", self.ts).cast(pl.Datetime("us")).dt.replace_time_zone("UTC")

    def grid(self, column: str, fill=np.nan, dtype=np.float64) -> np.ndarray:
        """(T, N) array of a column; cells without a bar get `fill`."""
        out = np.full((self.n_bars, len(self.symbols)), fill, dtype=dtype)
        for j, s in enumerate(self.symbols):
            col = self.frames[s][column].to_numpy()
            out[self.index[s], j] = col if dtype is not np.bool_ else col.astype(bool)
        return out

    def scatter(self, values: dict[str, np.ndarray], fill, dtype) -> np.ndarray:
        """Place per-instrument arrays (aligned to own bars) onto the grid."""
        out = np.full((self.n_bars, len(self.symbols)), fill, dtype=dtype)
        for j, s in enumerate(self.symbols):
            if s in values and values[s] is not None:
                v = np.asarray(values[s])
                if v.shape[0] != self.frames[s].height:
                    raise ValueError(f"{s}: signal length {v.shape[0]} != bars {self.frames[s].height}")
                out[self.index[s], j] = v
        return out

    def valid(self) -> np.ndarray:
        v = np.zeros((self.n_bars, len(self.symbols)), dtype=bool)
        for j, s in enumerate(self.symbols):
            v[self.index[s], j] = True
        return v

    def head(self, n_bars_grid: int) -> "MarketData":
        """Data truncated to the first n grid bars (used by look-ahead tests)."""
        cutoff = self.ts[n_bars_grid - 1]
        frames = {s: f.filter(pl.col("ts").dt.epoch("us") <= cutoff) for s, f in self.frames.items()}
        return MarketData(self.symbols, self.timeframe, frames, split=self.split, market=self.market,
                          fingerprints=self.fingerprints)


def _dataset_for(symbol: str) -> lake.DatasetKey:
    inst = instruments.get(symbol)
    name = {"crypto": "bars_1m", "fx": "quote_bars_1m", "equity": "bars_1d"}.get(inst.asset_class)
    if name is None:
        raise ValueError(f"no dataset configured for {symbol} ({inst.asset_class})")
    return lake.DatasetKey(inst.asset_class, inst.source, symbol, name)


def _funding_for(symbol: str, bars: pl.DataFrame) -> pl.DataFrame:
    """Attach funding rates. Each funding event is charged on the first bar starting at or
    after the bar period that contains it (so events during exchange outages are not lost).
    """
    key = lake.DatasetKey("crypto", "binance", symbol, "funding")
    if not lake.chunks(key):
        raise FileNotFoundError(f"funding data missing for {symbol}; run `lab ingest binance --funding {symbol}`")
    return attach_funding(bars, lake.read(key).select("ts", "funding_rate"))


def attach_funding(bars: pl.DataFrame, funding: pl.DataFrame) -> pl.DataFrame:
    """Sum funding events onto bars: an event at time f goes to the last bar with ts <= f if
    that bar covers f, otherwise to the next bar."""
    b = bars.select("ts").with_row_index("row")
    ev = funding.sort("ts")
    # Bar covering or preceding the event...
    prev = ev.join_asof(b, on="ts", strategy="backward")
    nxt = ev.join_asof(b.rename({"row": "row_next"}), on="ts", strategy="forward")
    ts_np = b["ts"].dt.epoch("us").to_numpy()
    step = np.median(np.diff(ts_np)) if len(ts_np) > 1 else 0
    ev_us = ev["ts"].dt.epoch("us").to_numpy()
    rows = []
    for r_prev, r_next, t_ev in zip(prev["row"].to_list(), nxt["row_next"].to_list(), ev_us):
        if r_prev is not None and t_ev < ts_np[r_prev] + step:
            rows.append(r_prev)
        else:
            rows.append(r_next)  # None if after the last bar
    ev = ev.with_columns(row=pl.Series(rows, dtype=pl.UInt32)).drop_nulls("row")
    agg = ev.group_by("row").agg(pl.col("funding_rate").sum())
    out = bars.with_row_index("row").drop("funding").join(agg, on="row", how="left")
    return out.with_columns(funding=pl.col("funding_rate").fill_null(0.0)).drop("funding_rate", "row")


def load(symbols: list[str] | str, timeframe: str = "1m", split: str = "development", *,
         start=None, end=None, funding: bool = False, allow_vault: bool = False) -> MarketData:
    """Load instruments from the lake for one research partition.

    The vault partition is refused unless allow_vault=True (see lab.data.splits).
    funding=True attaches perpetual funding rates (crypto only).
    """
    symbols = [symbols] if isinstance(symbols, str) else list(symbols)
    classes = {instruments.get(s).asset_class for s in symbols}
    market = classes.pop() if len(classes) == 1 else "mixed"
    every = f"{timeframe_seconds(timeframe)}s"
    frames, fps = {}, {}
    for s in symbols:
        inst = instruments.get(s)
        if inst.currency not in ("USD",):
            raise NotImplementedError(f"{s} is quoted in {inst.currency}; only USD-quoted instruments are supported")
        key = _dataset_for(s)
        if split == "all":
            if not allow_vault:
                raise splits.VaultLockedError("split='all' includes the vault; pass allow_vault=True")
            df = lake.scan(key).collect()
        else:
            df = splits.apply(lake.scan(key), inst.asset_class, split, allow_vault=allow_vault).collect()
        if start is not None:
            df = df.filter(pl.col("ts") >= pl.lit(start).cast(pl.Datetime("us", "UTC")))
        if end is not None:
            df = df.filter(pl.col("ts") < pl.lit(end).cast(pl.Datetime("us", "UTC")))
        native = key.dataset.rsplit("_", 1)[-1]
        if timeframe != native:
            if timeframe_seconds(timeframe) < timeframe_seconds(native):
                raise ValueError(f"{s}: cannot build {timeframe} bars from {native} data")
            df = resample(df, every)
        df = standardize(df)
        if funding:
            if inst.asset_class != "crypto":
                raise ValueError("funding applies to crypto perpetuals only")
            df = _funding_for(s, df)
        if df.is_empty():
            raise ValueError(f"{s}: no data in split {split!r}")
        frames[s] = df
        fps[str(key)] = lake.fingerprint(key)
    return MarketData(symbols, timeframe, frames, split=split, market=market, fingerprints=fps)
