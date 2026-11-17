"""Broker interfaces for PAPER trading only.

`AlpacaPaperBroker` talks to Alpaca's paper-trading API. It is hard-wired to the paper endpoint:
any other base URL (in particular the live endpoint) is refused. There is no live-trading code
in this project; adding it requires the owner's explicit permission (CLAUDE.md).

Credentials: the key id is read from the ALPACA_KEY_ID environment variable; the secret key is
injected by the cloud environment's network proxy as the `APCA-API-SECRET-KEY` header (never stored
in code, files or the repository). On a personal computer, ALPACA_SECRET_KEY may be set instead.

`SimBroker` is an in-memory broker used for dry runs and tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

PAPER_URL = "https://paper-api.alpaca.markets"


class LiveTradingRefused(PermissionError):
    pass


@dataclass
class Account:
    equity: float
    cash: float
    buying_power: float
    status: str


@dataclass
class Position:
    symbol: str
    qty: float
    avg_entry_price: float
    market_value: float


@dataclass
class Order:
    id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    status: str
    time_in_force: str
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    submitted_at: str | None = None
    filled_at: str | None = None


class AlpacaPaperBroker:
    """Minimal Alpaca v2 REST client restricted to paper trading."""

    def __init__(self, base_url: str | None = None, key_id: str | None = None, timeout: float = 30.0):
        base = (base_url or os.environ.get("ALPACA_BASE_URL") or PAPER_URL).rstrip("/")
        if base != PAPER_URL:
            raise LiveTradingRefused(f"refusing non-paper endpoint {base!r}: only {PAPER_URL} is allowed")
        key_id = key_id or os.environ.get("ALPACA_KEY_ID")
        if not key_id:
            raise RuntimeError("ALPACA_KEY_ID is not set (see docs/PAPER_TRADING.md)")
        headers = {"APCA-API-KEY-ID": key_id,
                   # Placeholder replaced by the environment's proxy with the real secret.
                   "APCA-API-SECRET-KEY": os.environ.get("ALPACA_SECRET_KEY", "injected-by-proxy")}
        self.base = base
        self.http = httpx.Client(base_url=base + "/v2", headers=headers, timeout=timeout)

    def _get(self, path, **params):
        r = self.http.get(path, params=params or None)
        r.raise_for_status()
        return r.json()

    def account(self) -> Account:
        a = self._get("/account")
        return Account(float(a["equity"]), float(a["cash"]), float(a["buying_power"]), a["status"])

    def positions(self) -> dict[str, Position]:
        return {p["symbol"]: Position(p["symbol"], float(p["qty"]), float(p["avg_entry_price"]),
                                      float(p["market_value"])) for p in self._get("/positions")}

    def clock(self) -> dict:
        return self._get("/clock")

    def orders(self, status: str = "all", after: str | None = None, limit: int = 200) -> list[Order]:
        params = {"status": status, "limit": limit, "direction": "desc"}
        if after:
            params["after"] = after
        return [_order(o) for o in self._get("/orders", **params)]

    def submit(self, symbol: str, qty: int, side: str, client_order_id: str, time_in_force: str = "opg") -> Order:
        body = {"symbol": symbol, "qty": str(int(qty)), "side": side, "type": "market",
                "time_in_force": time_in_force, "client_order_id": client_order_id}
        r = self.http.post("/orders", json=body)
        if r.status_code == 422 and "client_order_id" in r.text:
            # Already submitted (idempotent re-run): return the existing order.
            return _order(self._get(f"/orders:by_client_order_id", client_order_id=client_order_id))
        r.raise_for_status()
        return _order(r.json())

    def cancel_all(self) -> None:
        self.http.delete("/orders").raise_for_status()


def _order(o: dict) -> Order:
    f = o.get("filled_avg_price")
    return Order(o["id"], o.get("client_order_id", ""), o["symbol"], o["side"], float(o.get("qty") or 0), o["status"],
                 o.get("time_in_force", ""), float(o.get("filled_qty") or 0), float(f) if f else None,
                 o.get("submitted_at"), o.get("filled_at"))


@dataclass
class SimBroker:
    """In-memory broker for dry runs and tests. Orders fill at a given open price via `fill_open`."""

    cash: float = 5000.0
    held: dict = field(default_factory=dict)          # symbol -> qty
    last_price: dict = field(default_factory=dict)
    submitted: list = field(default_factory=list)

    def account(self) -> Account:
        eq = self.cash + sum(q * self.last_price.get(s, 0.0) for s, q in self.held.items())
        return Account(eq, self.cash, self.cash, "ACTIVE")

    def positions(self) -> dict[str, Position]:
        return {s: Position(s, q, 0.0, q * self.last_price.get(s, 0.0)) for s, q in self.held.items() if q}

    def clock(self) -> dict:
        return {"is_open": False}

    def orders(self, status: str = "all", after: str | None = None, limit: int = 200) -> list[Order]:
        return list(self.submitted)

    def submit(self, symbol, qty, side, client_order_id, time_in_force="opg") -> Order:
        if any(o.client_order_id == client_order_id for o in self.submitted):
            return next(o for o in self.submitted if o.client_order_id == client_order_id)
        o = Order(f"sim-{len(self.submitted)}", client_order_id, symbol, side, float(qty), "accepted", time_in_force)
        self.submitted.append(o)
        return o

    def fill_open(self, prices: dict[str, float]) -> None:
        for o in self.submitted:
            if o.status == "accepted" and o.symbol in prices:
                px = prices[o.symbol]
                sign = 1 if o.side == "buy" else -1
                self.held[o.symbol] = self.held.get(o.symbol, 0.0) + sign * o.qty
                self.cash -= sign * o.qty * px
                o.status, o.filled_qty, o.filled_avg_price = "filled", o.qty, px
        self.last_price.update(prices)

    def cancel_all(self) -> None:
        for o in self.submitted:
            if o.status == "accepted":
                o.status = "canceled"
