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


if __name__ == "__main__":
    app()
