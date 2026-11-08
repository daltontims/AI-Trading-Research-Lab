"""Automated data-quality checks.

Bad data creates fake trading edges, so every dataset is checked before research
uses it. Each check produces findings rated:
  FAIL - data must not be used until fixed (e.g. impossible prices)
  WARN - usable, but researchers must know (e.g. exchange outages, extreme moves)
  INFO - descriptive statistics

`check(key)` returns a DatasetReport; `write_report()` renders all reports to Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from lab.data import lake

LEVELS = {"INFO": 0, "WARN": 1, "FAIL": 2}


@dataclass
class Finding:
    level: str
    check: str
    message: str


@dataclass
class DatasetReport:
    key: str
    rows: int = 0
    start: str = ""
    end: str = ""
    fingerprint: str = ""
    findings: list[Finding] = field(default_factory=list)

    @property
    def status(self) -> str:
        worst = max((LEVELS[f.level] for f in self.findings), default=0)
        return {0: "PASS", 1: "WARN", 2: "FAIL"}[worst]

    def add(self, level: str, check: str, message: str) -> None:
        self.findings.append(Finding(level, check, message))


# ----------------------------------------------------------------- helpers

def _price_cols(df: pl.DataFrame) -> tuple[str, str, str, str]:
    if "close" in df.columns:
        return "open", "high", "low", "close"
    # quote bars: use mid prices
    return "mid_open", "mid_high", "mid_low", "mid_close"


def _with_mid(df: pl.DataFrame) -> pl.DataFrame:
    if "bid_close" not in df.columns:
        return df
    return df.with_columns(
        mid_open=(pl.col("bid_open") + pl.col("ask_open")) / 2,
        mid_high=(pl.col("bid_high") + pl.col("ask_high")) / 2,
        mid_low=(pl.col("bid_low") + pl.col("ask_low")) / 2,
        mid_close=(pl.col("bid_close") + pl.col("ask_close")) / 2,
    )


def expected_minutes_fx(start: datetime, end: datetime) -> pl.Series:
    """Approximate FX trading minutes: Sunday 22:00 UTC to Friday 21:00 UTC.

    (True hours shift by an hour with US daylight saving; the slack is acceptable
    for gap detection, which only flags long gaps.)
    """
    rng = pl.datetime_range(start, end, "1m", closed="left", time_zone="UTC", eager=True)
    wd = rng.dt.weekday()  # Mon=1 .. Sun=7
    hr = rng.dt.hour()
    open_ = ((wd >= 1) & (wd <= 4)) | ((wd == 5) & (hr < 21)) | ((wd == 7) & (hr >= 22))
    return rng.filter(open_)


def _gaps(ts: pl.Series, expected: pl.Series, min_gap: int) -> pl.DataFrame:
    """Runs of consecutive expected timestamps that are missing, longer than min_gap bars."""
    missing = expected.filter(~expected.is_in(ts.implode()))
    if missing.is_empty():
        return pl.DataFrame({"start": [], "bars": []}, schema={"start": ts.dtype, "bars": pl.Int64})
    m = pl.DataFrame({"ts": missing})
    # A new run starts whenever the gap to the previous missing timestamp exceeds one expected step.
    exp_idx = pl.DataFrame({"ts": expected, "i": pl.int_range(0, len(expected), eager=True)})
    m = m.join(exp_idx, on="ts").with_columns(run=(pl.col("i").diff().fill_null(1) != 1).cum_sum())
    runs = m.group_by("run").agg(start=pl.col("ts").min(), bars=pl.len()).filter(pl.col("bars") >= min_gap)
    return runs.select("start", "bars").sort("bars", descending=True)


# ------------------------------------------------------------------ checks

def check_frame(df: pl.DataFrame, key: lake.DatasetKey, report: DatasetReport) -> DatasetReport:
    n = df.height
    report.rows = n
    if n == 0:
        report.add("FAIL", "rows", "dataset is empty")
        return report
    report.start = f"{df['ts'].min():%Y-%m-%d %H:%M}"
    report.end = f"{df['ts'].max():%Y-%m-%d %H:%M}"

    # Ordering and duplicates (chunks are concatenated, so cross-file duplicates are possible).
    dup = n - df["ts"].n_unique()
    if dup:
        report.add("FAIL", "duplicates", f"{dup:,} duplicate timestamps")
    if not df["ts"].is_sorted():
        report.add("FAIL", "ordering", "timestamps are not sorted")

    nulls = {c: v for c, v in zip(df.columns, df.null_count().row(0)) if v and c not in ("ticks", "trades")}
    if nulls:
        report.add("WARN", "nulls", f"null values: {nulls}")

    if key.dataset == "funding":
        return _check_funding(df, report)

    df = _with_mid(df)
    o, h, l, c = _price_cols(df)

    nonpos = df.filter(pl.min_horizontal(o, h, l, c) <= 0).height
    if nonpos:
        report.add("FAIL", "prices", f"{nonpos:,} bars with zero/negative prices")

    bad_ohlc = df.filter((pl.col(h) < pl.max_horizontal(o, c) - 1e-9) | (pl.col(l) > pl.min_horizontal(o, c) + 1e-9)
                         | (pl.col(h) < pl.col(l))).height
    if bad_ohlc:
        lvl = "FAIL" if bad_ohlc / n > 0.001 else "WARN"
        report.add(lvl, "ohlc", f"{bad_ohlc:,} bars where high/low do not contain open/close ({bad_ohlc / n:.4%})")

    # Extreme returns: robust z-score using the median absolute deviation.
    r = df.select(pl.col(c).log().diff().alias("r")).drop_nulls()["r"].to_numpy()
    r = r[np.isfinite(r)]  # zero prices are reported separately above
    if len(r) > 100:
        # Floor the robust scale with a fraction of the standard deviation: minute data with
        # many unchanged prices can have a median absolute deviation of ~0.
        mad = max(np.median(np.abs(r - np.median(r))) * 1.4826, 0.25 * float(np.std(r)))
        if mad > 0:
            z = np.abs(r) / mad
            thresh = 50 if key.dataset.endswith("1m") else 15
            k = int((z > thresh).sum())
            if k:
                top = df["ts"][1:].to_numpy()[np.argsort(-z)[: min(k, 5)]]
                when = ", ".join(str(t)[:16] for t in top)
                report.add("WARN", "outliers", f"{k:,} returns beyond {thresh} robust σ (largest at: {when})")

    # Stale prices: longest run of identical closes.
    runs = df.select((pl.col(c) != pl.col(c).shift()).cum_sum().alias("g")).group_by("g").len()
    longest = int(runs["len"].max())
    stale_limit = 240 if key.dataset.endswith("1m") else 5
    if longest > stale_limit:
        report.add("WARN", "stale", f"longest run of unchanged close: {longest} bars")

    if "volume" in df.columns and key.asset_class != "macro":
        zero = df.filter(pl.col("volume") <= 0).height
        if zero / n > 0.01:
            report.add("WARN", "volume", f"{zero / n:.2%} of bars have zero volume")

    if "bid_close" in df.columns:
        _check_quotes(df, report)

    _check_coverage(df, key, report)
    return report


def _check_quotes(df: pl.DataFrame, report: DatasetReport) -> None:
    crossed = df.filter((pl.col("ask_close") < pl.col("bid_close")) | (pl.col("ask_open") < pl.col("bid_open"))).height
    if crossed:
        lvl = "FAIL" if crossed / df.height > 0.001 else "WARN"
        report.add(lvl, "spread", f"{crossed:,} bars with ask below bid")
    bps = df.select((pl.col("spread_mean") / pl.col("mid_close") * 1e4).alias("s"))["s"]
    q = bps.quantile(0.5), bps.quantile(0.95), bps.quantile(0.99)
    report.add("INFO", "spread", f"spread (bps) median {q[0]:.2f}, p95 {q[1]:.2f}, p99 {q[2]:.2f}")
    # Spread by hour of day: scalping costs depend heavily on the session.
    by_hr = (df.with_columns(s=pl.col("spread_mean") / pl.col("mid_close") * 1e4, hr=pl.col("ts").dt.hour())
             .group_by("hr").agg(pl.col("s").median()).sort("s"))
    report.add("INFO", "spread_by_hour",
               f"tightest hour (UTC) {by_hr['hr'][0]:02d}:00 = {by_hr['s'][0]:.2f} bps; "
               f"widest {by_hr['hr'][-1]:02d}:00 = {by_hr['s'][-1]:.2f} bps")


def _check_funding(df: pl.DataFrame, report: DatasetReport) -> DatasetReport:
    fr = df["funding_rate"]
    report.add("INFO", "funding", f"mean {fr.mean() * 1e4:.2f} bps/interval, min {fr.min() * 1e4:.1f}, max {fr.max() * 1e4:.1f}")
    big = df.filter(pl.col("funding_rate").abs() > 0.0075).height
    if big:
        report.add("WARN", "funding", f"{big} intervals with |funding| > 75 bps")
    gaps = df.select(pl.col("ts").diff().dt.total_hours().alias("h"))["h"].drop_nulls()
    long = int((gaps > 8.5).sum())
    if long:
        report.add("WARN", "coverage", f"{long} gaps longer than one funding interval")
    return report


def _check_coverage(df: pl.DataFrame, key: lake.DatasetKey, report: DatasetReport) -> None:
    ts = df["ts"]
    start, end = ts.min(), ts.max()
    if key.dataset.endswith("1m"):
        if key.asset_class == "crypto":
            expected = pl.datetime_range(start, end, "1m", time_zone="UTC", eager=True)
            min_gap = 5
        elif key.asset_class == "fx":
            expected = expected_minutes_fx(start, end)
            min_gap = 60  # quiet minutes without quotes are normal; flag only long gaps
        else:
            return
        cov = ts.len() / max(len(expected), 1)
        report.add("INFO", "coverage", f"{cov:.2%} of expected minutes present")
        gaps = _gaps(ts, expected, min_gap)
        if gaps.height:
            total = int(gaps["bars"].sum())
            top = ", ".join(f"{r['start']:%Y-%m-%d %H:%M} ({r['bars']}m)" for r in gaps.head(5).iter_rows(named=True))
            report.add("WARN", "gaps", f"{gaps.height} gaps ≥ {min_gap} min, {total:,} minutes total; longest: {top}")
    elif key.dataset.endswith("1d") and key.asset_class in ("equity", "macro"):
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XNYS")
        lo = max(start.date(), cal.first_session.date())
        sessions = cal.sessions_in_range(str(lo), str(end.date()))
        expected = set(sessions.date)
        have = set(ts.dt.date().to_list())
        missing = sorted(d for d in expected - have)
        extra = sorted(d for d in have - expected if d >= lo)
        if missing:
            lvl = "WARN" if len(missing) > 3 else "INFO"
            report.add(lvl, "sessions", f"{len(missing)} NYSE sessions missing (first: {', '.join(map(str, missing[:5]))})")
        if extra:
            report.add("WARN", "sessions", f"{len(extra)} bars on non-trading days (first: {', '.join(map(str, extra[:5]))})")
        if key.asset_class == "equity":
            report.add("WARN", "survivorship",
                       "free daily data omits delisted symbols; do not use for stock-selection studies")


def check(key: lake.DatasetKey) -> DatasetReport:
    report = DatasetReport(key=str(key), fingerprint=lake.fingerprint(key))
    df = pl.concat([pl.read_parquet(f) for f in lake.chunks(key)], how="vertical_relaxed")
    return check_frame(df, key, report)


def write_report(reports: list[DatasetReport], path: Path) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Data Quality Report", "",
        f"*Generated {now} by `lab quality`.*", "",
        "PASS = no issues · WARN = usable with known caveats · FAIL = must not be used until fixed.", "",
        "| Dataset | Status | Rows | Start | End | Fingerprint |",
        "|---|---|---:|---|---|---|",
    ]
    for r in reports:
        lines.append(f"| `{r.key}` | **{r.status}** | {r.rows:,} | {r.start} | {r.end} | `{r.fingerprint}` |")
    lines.append("")
    for r in reports:
        lines += [f"## `{r.key}` — {r.status}", ""]
        if not r.findings:
            lines.append("No findings.")
        for f in sorted(r.findings, key=lambda f: -LEVELS[f.level]):
            lines.append(f"- **{f.level}** · {f.check}: {f.message}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    return path
