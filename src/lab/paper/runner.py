"""Paper-trading runner: turns deployed strategies' signals into opening-auction orders.

Daily cycle (run before the US open on trading days, e.g. 08:40 New York time):
  1. Fetch fresh daily bars for each deployed symbol (Yahoo), through the last completed session.
  2. Replay the strategy over that history exactly as the backtest engine would (same signals,
     same next-open fills, same time exits) to get the position it wants at the NEXT open.
  3. Compare with the broker's actual position and plan orders (whole shares).
  4. Safety checks, then submit market-on-open ("opg") orders with deterministic client ids
     (a second run the same day cannot duplicate orders).
  5. Journal everything to research/paper/journal.jsonl; `reconcile` later records fill prices
     against the expected open to measure real slippage.

Supports strategies whose exits are signals or time limits (no intrabar stops/targets yet).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from lab.engine.data import MarketData, standardize
from lab.engine.strategy import Strategy

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "configs" / "deployment.yaml"
JOURNAL = ROOT / "research" / "paper" / "journal.jsonl"


class SafetyError(RuntimeError):
    pass


@dataclass
class Plan:
    hypothesis: str
    symbol: str
    signal_date: str            # last completed session used for the decision
    target_side: int            # desired position after the next open: 1 long, -1 short, 0 flat
    current_qty: float
    order_side: str | None      # buy / sell / None
    order_qty: int
    reference_price: float      # last close (sizing reference)
    reason: str
    client_order_id: str = ""
    target_qty: int = 0         # signed position size wanted after the next open
    time_in_force: str = "opg"  # "opg" = opening auction; "day" = market order at the open (top-ups, D-024)


def deployment(path: Path = CONFIG) -> dict:
    cfg = yaml.safe_load(path.read_text())
    if cfg.get("mode") != "paper":
        raise SafetyError("deployment mode must be 'paper'")
    check_deployment(cfg)
    return cfg


PAPER_ASSET_CLASSES = ("equity",)   # crypto paper trading is not supported yet (24/7 market, other symbols)


def check_deployment(cfg: dict) -> None:
    """Rules for running several strategies on one account (D-027):
    one strategy per symbol (the broker holds one position per symbol), allocations sum to at
    most 1 (no leverage), and only supported asset classes."""
    from lab import instruments
    seen, total = {}, 0.0
    for d in cfg.get("strategies", []):
        total += float(d["allocation"])
        for sym in d["symbols"]:
            if sym in seen:
                raise SafetyError(f"{sym} is traded by both {seen[sym]} and {d['hypothesis']}: one strategy per symbol")
            seen[sym] = d["hypothesis"]
            if instruments.get(sym).asset_class not in PAPER_ASSET_CLASSES:
                raise SafetyError(f"{sym}: paper trading supports {PAPER_ASSET_CLASSES} only")
    if total > 1.0 + 1e-9:
        raise SafetyError(f"allocations sum to {total:.2f} > 1.0 (no leverage)")


def strategy_class(name: str):
    from lab.discovery.templates import strategy_from_name
    from lab.strategies.examples import EXAMPLES
    from lab.strategies.phase4 import PHASE4
    if name.startswith("rule:"):
        return strategy_from_name(name)
    return {**EXAMPLES, **PHASE4}[name]


def replay_target(strategy: Strategy, df: pl.DataFrame, symbol: str, max_bars_held: int = 0) -> tuple[np.ndarray, int]:
    """Replay engine order logic for one instrument without stops.

    Returns (held, target): held[t] = position held during bar t (after fills at t's open), and the
    position wanted after the next open following the last bar.
    """
    data = MarketData([symbol], "1d", {symbol: df})
    sig = strategy.generate(data)
    for k in ("stop_dist", "target_dist", "trail_dist"):
        if np.isfinite(getattr(sig, k)).any():
            raise SafetyError(f"{strategy.name}: intrabar {k} is not supported by the paper runner yet")
    el, es, xl, xs = (getattr(sig, k)[:, 0] for k in ("entry_long", "entry_short", "exit_long", "exit_short"))
    T = len(el)
    held = np.zeros(T, dtype=np.int64)
    pos, pend_entry, pend_exit, bars = 0, 0, False, 0
    for t in range(T):
        # open: exits then entries
        if pend_exit and pos != 0:
            pos, bars = 0, 0
        pend_exit = False
        if pend_entry != 0 and pos == 0:
            pos, bars = pend_entry, 0
        pend_entry = 0
        held[t] = pos
        if pos != 0:
            bars += 1
            if max_bars_held and bars >= max_bars_held:
                pend_exit = True
        # close: signals
        if pos > 0 and xl[t]:
            pend_exit = True
        elif pos < 0 and xs[t]:
            pend_exit = True
        if el[t] and es[t]:
            continue
        side = 1 if el[t] else (-1 if es[t] else 0)
        if side and side != pos:
            if pos != 0:
                pend_exit = True
            pend_entry = side
    target = pos
    if pend_exit:
        target = 0
    if pend_entry != 0 and target == 0:
        target = pend_entry
    return held, target


def fetch_bars(symbol: str, days: int) -> pl.DataFrame:
    from lab.data.ingest import yahoo
    df = yahoo.fetch_daily(symbol)
    df = df.filter(pl.col("ts").dt.date() < datetime.now(timezone.utc).date())  # completed sessions only
    return standardize(df.tail(days))


def intended_entry_sizes(journal: Path | None) -> dict[tuple[str, str], int]:
    """Signed position size each (hypothesis, symbol) meant to hold, from its latest submitted entry.

    An entry is a submitted plan that opened (or reversed into) a position. If that entry only partly
    filled, the next run tops the position up to this size instead of holding the partial amount.
    """
    out: dict[tuple[str, str], int] = {}
    if not journal or not journal.exists():
        return out
    for line in journal.read_text().splitlines():
        e = json.loads(line)
        if e.get("event") != "run" or not e.get("submitted"):
            continue
        for p in e.get("plans", []):
            key, side, cur = (p["hypothesis"], p["symbol"]), p["target_side"], p["current_qty"]
            if side == 0:
                out.pop(key, None)
            elif p.get("order_side") and np.sign(cur) != side:
                # Older journal lines lack target_qty: an entry from flat ordered exactly the target.
                tq = p.get("target_qty") or (side * p["order_qty"] if cur == 0 else 0)
                if tq:
                    out[key] = int(tq)
    return out


def plan_orders(broker, cfg: dict | None = None, bars: dict[str, pl.DataFrame] | None = None,
                journal: Path | None = None) -> list[Plan]:
    """Compute target positions and the orders needed. `bars` overrides data fetching (tests).

    `journal` (when given) is used to complete entries that only partly filled."""
    from lab.registry.db import Registry
    cfg = cfg or deployment()
    check_deployment(cfg)
    acct = broker.account()
    sizing_equity = min(acct.equity, float(cfg.get("capital", acct.equity)))
    held = broker.positions()
    plans = []
    reg = Registry()
    intended = intended_entry_sizes(journal)
    for d in cfg["strategies"]:
        status = reg.hypothesis(d["hypothesis"])["status"]
        if status not in ("VALIDATED", "PAPER"):
            raise SafetyError(f"{d['hypothesis']} is {status}: only VALIDATED strategies may be paper traded")
        strat = strategy_class(d["strategy"])(**d.get("params", {}))
        for sym in d["symbols"]:
            df = bars[sym] if bars and sym in bars else fetch_bars(sym, d.get("history_days", 600))
            _, target = replay_target(strat, df, sym, d.get("max_bars_held", 0))
            ref = float(df["close"][-1])
            date = str(df["ts"][-1].date())
            cur = held[sym].qty if sym in held else 0.0
            want_qty, note, tif = 0, "", "opg"
            if target != 0:
                if cur != 0 and np.sign(cur) == target:
                    want_qty = int(abs(cur))  # already positioned: hold, do not resize (as in the backtest)
                    meant = intended.get((d["hypothesis"], sym), 0)
                    # Never top up beyond what the current allocation buys (allocations shrink when
                    # strategies are added, D-027).
                    meant = int(np.sign(meant)) * min(abs(meant), int(math.floor(d["allocation"] * sizing_equity / ref)))
                    if np.sign(meant) == target and abs(meant) > want_qty:
                        # The entry only partly filled: complete it to the size the entry intended.
                        note = f"; entry partly filled ({want_qty} of {abs(meant)}), topping up"
                        want_qty = abs(meant)
                        tif = "day"  # D-024: opening-auction top-ups kept expiring unfilled on paper
                else:
                    want_qty = int(math.floor(d["allocation"] * sizing_equity / ref))
            delta = target * want_qty - cur
            side = "buy" if delta > 0 else ("sell" if delta < 0 else None)
            reason = {1: "long", -1: "short", 0: "flat"}[target]
            p = Plan(d["hypothesis"], sym, date, target, cur, side, int(abs(delta)), ref,
                     f"strategy wants {reason}; holding {cur:g}{note}", target_qty=int(target * want_qty),
                     time_in_force=tif)
            if side:
                p.client_order_id = f"{d['hypothesis']}-{sym}-{date}-{side}"
                notional = p.order_qty * ref
                cap = cfg.get("max_order_notional_pct", 1.05) * d["allocation"] * sizing_equity
                # Exits/reductions are always allowed; new exposure must respect the cap.
                if abs(target * want_qty) > abs(cur) and notional > cap + abs(cur) * ref:
                    raise SafetyError(f"order {p.client_order_id} notional {notional:,.0f} exceeds cap {cap:,.0f}")
            plans.append(p)
    return plans


def run(broker, submit: bool = False, cfg: dict | None = None, bars: dict | None = None,
        journal: Path = JOURNAL) -> dict:
    cfg = cfg or deployment()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if cfg.get("kill_switch"):
        if submit:
            broker.cancel_all()
        entry = {"ts": now, "event": "kill_switch", "submitted": submit}
        _journal(journal, entry)
        return entry
    acct = broker.account()
    plans = plan_orders(broker, cfg, bars, journal)
    orders = []
    for p in plans:
        if p.order_side and submit:
            o = broker.submit(p.symbol, p.order_qty, p.order_side, p.client_order_id, p.time_in_force)
            orders.append(asdict(o))
    if submit and orders:
        _mark_paper({p.hypothesis for p in plans if p.order_side})
    entry = {"ts": now, "event": "run", "submitted": submit, "account": asdict(acct),
             "plans": [asdict(p) for p in plans], "orders": orders}
    _journal(journal, entry)
    return entry


def _mark_paper(hypotheses: set[str]) -> None:
    """Protocol: a VALIDATED hypothesis becomes PAPER once its first paper order is submitted."""
    from lab.registry.db import Registry
    reg = Registry()
    changed = False
    for h in sorted(hypotheses):
        if reg.hypothesis(h)["status"] == "VALIDATED":
            reg.set_status(h, "PAPER", "first paper-trading order submitted (Alpaca paper account)")
            changed = True
    if changed:
        reg.export()
    reg.close()


def reconcile(broker, journal: Path = JOURNAL) -> list[dict]:
    """Record fills of orders this system submitted (fill price vs. the order's reference close)."""
    plans = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            e = json.loads(line)
            for p in e.get("plans", []):
                if p.get("client_order_id"):
                    plans[p["client_order_id"]] = p
    seen = {json.loads(line).get("client_order_id") for line in journal.read_text().splitlines()
            if '"event": "fill"' in line} if journal.exists() else set()
    out = []
    for o in broker.orders(status="closed"):
        if o.client_order_id in plans and o.client_order_id not in seen and o.filled_qty:
            p = plans[o.client_order_id]
            e = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": "fill",
                 "client_order_id": o.client_order_id, "symbol": o.symbol, "side": o.side, "qty": o.filled_qty,
                 "ordered_qty": p["order_qty"], "partial": o.filled_qty < p["order_qty"],
                 "fill_price": o.filled_avg_price, "filled_at": o.filled_at, "reference_close": p["reference_price"],
                 "gap_vs_close_bps": (o.filled_avg_price / p["reference_price"] - 1) * 1e4
                 if o.filled_avg_price else None}
            _journal(journal, e)
            out.append(e)
    return out


def snapshot(broker, journal: Path = JOURNAL) -> dict:
    acct = broker.account()
    e = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": "snapshot",
         "account": asdict(acct), "positions": {s: asdict(p) for s, p in broker.positions().items()}}
    _journal(journal, e)
    return e


def _journal(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
