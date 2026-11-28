"""Automatic promotion: discovery CANDIDATE -> one-time vault test -> VALIDATED -> paper account (D-027).

For every discovery candidate that has not opened the vault:
  1. Run its frozen rules once on the vault (most recent, never-seen data). The result is final.
  2. If VALIDATED and it trades a supported market whose symbol is not already used by another
     paper strategy, add it to configs/deployment.yaml and split the account equally between all
     deployed strategies (allocations sum to 1: no leverage).
Every outcome is appended to research/discovery/promotions.jsonl. The paper runner picks up the new
deployment at its next daily run; its first order also moves the hypothesis to PAPER.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import yaml

from lab import instruments
from lab.discovery import templates as T
from lab.engine.backtest import ExecutionConfig, RiskConfig
from lab.paper import runner
from lab.registry.db import Registry

ROOT = Path(__file__).resolve().parents[3]
LOG = ROOT / "research" / "discovery" / "promotions.jsonl"

HEADER = """# Strategies deployed to PAPER trading. Only VALIDATED hypotheses may be listed.
# Changing this file changes what the paper account trades: commit every change.
# Discovery winners are added automatically by lab.discovery.promote after passing the vault test (D-027).
"""


def best_params(hid: str, source: str) -> dict:
    batch = source.split(":", 1)[1]
    path = ROOT / "research" / "discovery" / batch / "evaluations.jsonl"
    for line in path.read_text().splitlines():
        r = json.loads(line)
        if r["id"] == hid:
            return r["best_params"]
    raise KeyError(f"{hid}: no evaluation in {path}")


def write_deployment(cfg: dict, path: Path = runner.CONFIG) -> None:
    runner.check_deployment(cfg)
    path.write_text(HEADER + yaml.safe_dump(cfg, sort_keys=False, default_flow_style=None))


def add_to_deployment(cfg: dict, hid: str, strategy: str, params: dict, symbol: str) -> tuple[dict, str]:
    """Return (new config, note). Equal allocation across all strategies after adding this one."""
    used = {s for d in cfg["strategies"] for s in d["symbols"]}
    if symbol in used:
        return cfg, f"not deployed: {symbol} already traded by another paper strategy (one per symbol)"
    if instruments.get(symbol).asset_class not in runner.PAPER_ASSET_CLASSES:
        return cfg, f"not deployed: {instruments.get(symbol).asset_class} paper trading not supported yet"
    new = {**cfg, "strategies": [dict(d) for d in cfg["strategies"]]}
    new["strategies"].append({"hypothesis": hid, "strategy": strategy, "params": params, "symbols": [symbol],
                              "timeframe": "1d", "allocation": 1.0, "history_days": 600})
    w = round(1.0 / len(new["strategies"]), 4)
    for d in new["strategies"]:
        d["allocation"] = w
    return new, f"deployed to paper; {len(new['strategies'])} strategies at {w:.0%} of the account each"


def promote(reg: Registry | None = None, deploy: bool = True, config: Path = runner.CONFIG) -> list[dict]:
    from lab.validation.evaluate import vault_test
    reg = reg or Registry()
    rows = reg.query("SELECT * FROM hypotheses WHERE status='CANDIDATE' AND source LIKE 'discovery:%' ORDER BY id")
    out = []
    for h in rows:
        if reg.vault_opened(h["id"]):
            continue
        spec = json.loads(h["spec"])
        cls = T.strategy_from_name(spec["strategy"])
        params = best_params(h["id"], h["source"])
        sym = json.loads(h["instruments"])[0]
        res = vault_test(cls, params, [sym], h["timeframe"], hypothesis_id=h["id"], registry=reg,
                         risk=RiskConfig(**spec["risk"]), execution=ExecutionConfig(cost_profile=spec["profile"]),
                         style="swing", notes="discovery auto-promotion (D-027)")
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hypothesis": h["id"], "symbol": sym,
               "strategy": spec["strategy"], "params": params, "verdict": res["verdict"], "reasons": res["reasons"],
               "vault_return": res["metrics"]["total_return"], "vault_sharpe": res["metrics"]["sharpe"],
               "period": res["period"]}
        if res["verdict"] == "VALIDATED" and deploy:
            cfg = runner.deployment(config)
            cfg, rec["deployment"] = add_to_deployment(cfg, h["id"], spec["strategy"], params, sym)
            write_deployment(cfg, config)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        out.append(rec)
        print(f"{h['id']} {sym}: vault {res['verdict']} {rec.get('deployment', '')}")
    reg.export()
    return out
