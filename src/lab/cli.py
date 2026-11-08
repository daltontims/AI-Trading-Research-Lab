"""Command-line interface: `uv run lab --help`."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from lab.data import lake

app = typer.Typer(help="AI Trading Research Lab (simulation only).", no_args_is_help=True)
ingest_app = typer.Typer(help="Download market data into the lake.", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")

ROOT = Path(__file__).resolve().parents[2]


@ingest_app.command("binance")
def ingest_binance(symbols: list[str], start: str = "2019-01", end: str | None = None,
                   funding: bool = typer.Option(False, help="Download funding rates instead of 1m bars")):
    """Binance spot 1-minute bars (or USD-M funding rates)."""
    from lab.data.ingest import binance
    for s in symbols:
        (binance.ingest_funding if funding else binance.ingest_spot_klines)(s.upper(), start, end)


@ingest_app.command("dukascopy")
def ingest_dukascopy(pairs: list[str], start: str = "2018-01", end: str | None = None,
                     mode: str = typer.Option("candles", help="candles (fast) or ticks (exact, slow)"),
                     keep_ticks: bool = False):
    """Dukascopy forex 1-minute bid/ask bars."""
    from lab.data.ingest import dukascopy
    for p in pairs:
        dukascopy.ingest(p, start, end, mode=mode, keep_ticks=keep_ticks)


@ingest_app.command("yahoo")
def ingest_yahoo(symbols: list[str], asset_class: str = "equity"):
    """Yahoo daily bars (full refresh)."""
    from lab.data.ingest import yahoo
    for s in symbols:
        yahoo.ingest(s, asset_class)


@ingest_app.command("all")
def ingest_all(only: str | None = typer.Option(None, help="binance | dukascopy | yahoo")):
    """Download the standard universe in configs/datasets.yaml (resumable)."""
    from lab.data.ingest import binance, dukascopy, yahoo
    cfg = yaml.safe_load((ROOT / "configs" / "datasets.yaml").read_text())
    failures = []

    def run(label, fn, *args, **kw):
        try:
            fn(*args, **kw)
        except Exception as e:  # keep going; one source failing must not stop the rest
            failures.append(f"{label}: {e}")
            typer.echo(f"  ! {label} failed: {e}")

    if only in (None, "yahoo"):
        typer.echo("Yahoo daily")
        for s in cfg["yahoo"]["equity"]:
            run(s, yahoo.ingest, s, "equity")
        for s in cfg["yahoo"]["macro"]:
            run(s, yahoo.ingest, s, "macro")
    if only in (None, "binance"):
        b = cfg["binance"]
        typer.echo("Binance")
        for s in b["spot_klines"]:
            run(f"{s} klines", binance.ingest_spot_klines, s, b["start"])
        for s in b["funding"]:
            run(f"{s} funding", binance.ingest_funding, s, b["funding_start"])
    if only in (None, "dukascopy"):
        d = cfg["dukascopy"]
        typer.echo("Dukascopy")
        for p in d["pairs"]:
            run(p, dukascopy.ingest, p, d["start"])
    if failures:
        typer.echo(f"\n{len(failures)} failure(s); re-run to resume:\n  " + "\n  ".join(failures))
        raise typer.Exit(1)


@app.command()
def datasets():
    """List datasets in the lake."""
    for k in lake.list_datasets():
        files = lake.chunks(k)
        mb = sum(f.stat().st_size for f in files) / 1e6
        typer.echo(f"{str(k):45s} {len(files):4d} files {mb:9.1f} MB")


@app.command()
def quality(output: Path = ROOT / "reports" / "data_quality.md"):
    """Run data-quality checks on every dataset and write a Markdown report."""
    from lab.data import quality as q
    reports = []
    for k in lake.list_datasets():
        r = q.check(k)
        typer.echo(f"{r.status:4s}  {k}")
        reports.append(r)
    q.write_report(reports, output)
    typer.echo(f"Report: {output}")


@app.command()
def backtest(strategy: str, symbols: list[str], timeframe: str = "1h", split: str = "development",
             profile: str | None = typer.Option(None, help="cost profile from configs/costs.yaml"),
             param: list[str] = typer.Option([], help="strategy parameter, e.g. --param n=20"),
             sizing: str = "risk", risk_per_trade: float = 0.01, cash: float = 5000.0,
             max_bars_held: int = 0, funding: bool = False,
             stress: bool = typer.Option(False, help="also run at 1.5x, 2x and 3x costs"),
             hypothesis: str = typer.Option("H-ADHOC-CLI", help="registry hypothesis id")):
    """Backtest an example strategy and record it in the registry (development split by default)."""
    import ast

    from lab.engine.backtest import ExecutionConfig, RiskConfig
    from lab.registry.db import Registry
    from lab.research import run_experiment
    from lab.strategies.examples import EXAMPLES

    if strategy not in EXAMPLES:
        raise typer.BadParameter(f"choose from {list(EXAMPLES)}")
    params = {}
    for kv in param:
        k, v = kv.split("=", 1)
        try:
            params[k] = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            params[k] = v
    strat = EXAMPLES[strategy](**params)
    reg = Registry()
    if hypothesis == "H-ADHOC-CLI":
        reg.register_hypothesis(id=hypothesis, family="adhoc", title="Ad-hoc CLI backtests",
                                question="Exploratory runs from the command line (counted as trials).",
                                source="manual", asset_classes=["any"], instruments=["any"], timeframe="any",
                                spec={"note": "ad hoc"})
    res, eid = run_experiment(strat, symbols, timeframe, hypothesis_id=hypothesis, split=split, registry=reg,
                              risk=RiskConfig(initial_cash=cash, sizing=sizing, risk_per_trade=risk_per_trade,
                                              max_bars_held=max_bars_held),
                              execution=ExecutionConfig(cost_profile=profile), funding=funding,
                              cost_multipliers=(1.0, 1.5, 2.0, 3.0) if stress else (1.0,))
    typer.echo(res.summary())
    typer.echo(f"recorded as {eid}")


if __name__ == "__main__":
    app()
