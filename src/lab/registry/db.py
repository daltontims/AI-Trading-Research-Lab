"""Research registry: SQLite database of hypotheses, experiments and trials.

Nothing is ever deleted. The database file (research/registry.sqlite) is not committed;
instead `export()` writes every table to JSONL under research/registry/ (committed to git),
and opening a registry whose database is missing rebuilds it from that export. This keeps
the full research history across ephemeral cloud machines.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = Path(__file__).with_name("schema.sql")
TABLES = ["hypotheses", "experiments", "trials", "stat_tests", "status_changes", "vault_access"]
STATUSES = ["IDEA", "EFFECT", "SCREENED", "CANDIDATE", "VALIDATED", "PAPER", "PAPER_PASSED", "REJECTED"]


def _default_path() -> Path:
    return Path(os.environ.get("LAB_REGISTRY", PROJECT_ROOT / "research" / "registry.sqlite"))


def _json(v) -> str:
    def clean(x):
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None if math.isnan(x) else ("inf" if x > 0 else "-inf")
        if isinstance(x, dict):
            return {str(k): clean(val) for k, val in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(i) for i in x]
        if hasattr(x, "item"):  # numpy scalars
            return clean(x.item())
        return x
    return json.dumps(clean(v), sort_keys=True, default=str)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def git_version() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=PROJECT_ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("+dirty" if dirty else "")
    except Exception:
        return "unknown"


class VaultAlreadyOpenedError(PermissionError):
    pass


class Registry:
    def __init__(self, path: Path | str | None = None, export_dir: Path | str | None = None):
        self.path = Path(path) if path else _default_path()
        self.export_dir = Path(export_dir) if export_dir else self.path.parent / "registry"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not self.path.exists()
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA.read_text())
        if fresh and self.export_dir.exists():
            self.import_export(self.export_dir)

    # ------------------------------------------------------------ helpers
    def _next_id(self, table: str, prefix: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        like = f"{prefix}-{day}-%"
        n = self.con.execute(f"SELECT COUNT(*) FROM {table} WHERE id LIKE ?", (like,)).fetchone()[0]
        return f"{prefix}-{day}-{n + 1:04d}"

    def query(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.con.execute(sql, params).fetchall()]

    # ------------------------------------------------------------ hypotheses
    def register_hypothesis(self, *, family: str, title: str, question: str, source: str,
                            asset_classes: list[str], instruments: list[str], timeframe: str, spec: dict,
                            rationale: str = "", style: str = "", param_space: dict | None = None,
                            trial_budget: int = 50, id: str | None = None, parent_id: str | None = None) -> str:
        """Pre-register a hypothesis. Re-registering the same id with a different spec is refused:
        changed rules must become a new hypothesis (with parent_id) so earlier trials still count."""
        if id is not None:
            row = self.con.execute("SELECT spec, param_space FROM hypotheses WHERE id=?", (id,)).fetchone()
            if row is not None:
                if row["spec"] != _json(spec) or row["param_space"] != _json(param_space or {}):
                    raise ValueError(f"{id} already registered with different rules; register a new "
                                     f"hypothesis with parent_id={id!r}")
                return id
        hid = id or self._next_id("hypotheses", "H")
        self.con.execute(
            """INSERT INTO hypotheses (id, parent_id, family, title, question, rationale, source, asset_classes,
               instruments, timeframe, style, spec, param_space, trial_budget, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'IDEA', ?, ?)""",
            (hid, parent_id, family, title, question, rationale, source, _json(asset_classes), _json(instruments),
             timeframe, style, _json(spec), _json(param_space or {}), trial_budget, now(), now()))
        self.con.commit()
        return hid

    def hypothesis(self, hid: str) -> dict:
        row = self.con.execute("SELECT * FROM hypotheses WHERE id=?", (hid,)).fetchone()
        if row is None:
            raise KeyError(f"unknown hypothesis {hid}")
        return dict(row)

    def set_status(self, hid: str, status: str, reason: str, experiment_id: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status}")
        old = self.hypothesis(hid)["status"]
        self.con.execute("UPDATE hypotheses SET status=?, updated_at=?, rejection_reason=? WHERE id=?",
                         (status, now(), reason if status == "REJECTED" else None, hid))
        self.con.execute("INSERT INTO status_changes (hypothesis_id, from_status, to_status, reason, experiment_id, "
                         "changed_at) VALUES (?,?,?,?,?,?)", (hid, old, status, reason, experiment_id, now()))
        self.con.commit()

    # ------------------------------------------------------------ experiments
    def start_experiment(self, *, hypothesis_id: str, strategy_id: str, strategy_version: str, stage: str,
                         market: str, instruments: list[str], timeframe: str, data_split: str,
                         data_versions: dict, config: dict, cost_models: dict | None = None,
                         data_start: str | None = None, data_end: str | None = None,
                         seed: int | None = None, notes: str = "") -> str:
        h = self.hypothesis(hypothesis_id)
        eid = self._next_id("experiments", "E")
        import hashlib
        fp = hashlib.sha256(_json(data_versions).encode()).hexdigest()[:16]
        self.con.execute(
            """INSERT INTO experiments (id, hypothesis_id, strategy_id, strategy_version, stage, market, instruments,
               timeframe, data_split, data_start, data_end, git_commit, data_fingerprint, data_versions, config,
               cost_models, seed, validation_status, started_at, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, hypothesis_id, strategy_id, strategy_version, stage, market, _json(instruments), timeframe,
             data_split, data_start, data_end, git_version(), fp, _json(data_versions), _json(config),
             _json(cost_models or {}), seed, h["status"], now(), notes))
        self.con.commit()
        return eid

    def finish_experiment(self, eid: str, outcome: str, warnings: list[str] | None = None,
                          error: str | None = None) -> None:
        self.con.execute("UPDATE experiments SET finished_at=?, outcome=?, warnings=?, error=? WHERE id=?",
                         (now(), outcome, _json(warnings or []), error, eid))
        self.con.commit()

    def add_trial(self, eid: str, params: dict, metrics: dict, cost_multiplier: float = 1.0,
                  monthly: list | None = None, regimes: list | None = None) -> int:
        cur = self.con.execute(
            """INSERT INTO trials (experiment_id, params, n_trades, win_rate, profit_factor, expectancy, net_return,
               max_drawdown, sharpe, sortino, cost_share, cost_multiplier, metrics, monthly, regimes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, _json(params), metrics.get("trades"), _num(metrics.get("win_rate")),
             _num(metrics.get("profit_factor")), _num(metrics.get("expectancy")), _num(metrics.get("total_return")),
             _num(metrics.get("max_drawdown")), _num(metrics.get("sharpe")), _num(metrics.get("sortino")),
             _num(metrics.get("cost_share_of_gross")), cost_multiplier, _json(metrics), _json(monthly or []),
             _json(regimes or []), now()))
        self.con.commit()
        return cur.lastrowid

    def add_stat_test(self, eid: str, test: str, statistic=None, p_value=None, passed=None, details=None):
        self.con.execute("INSERT INTO stat_tests (experiment_id, test, statistic, p_value, passed, details) "
                         "VALUES (?,?,?,?,?,?)", (eid, test, _num(statistic), _num(p_value),
                                                 None if passed is None else int(bool(passed)), _json(details or {})))
        self.con.commit()

    def trial_count(self, *, hypothesis_id: str | None = None, family: str | None = None) -> int:
        """Number of trials run so far (the input to multiple-testing corrections)."""
        if hypothesis_id:
            sql, p = ("SELECT COUNT(*) FROM trials t JOIN experiments e ON t.experiment_id=e.id "
                      "WHERE e.hypothesis_id=?", (hypothesis_id,))
        elif family:
            sql, p = ("SELECT COUNT(*) FROM trials t JOIN experiments e ON t.experiment_id=e.id "
                      "JOIN hypotheses h ON e.hypothesis_id=h.id WHERE h.family=?", (family,))
        else:
            sql, p = "SELECT COUNT(*) FROM trials", ()
        return self.con.execute(sql, p).fetchone()[0]

    # ------------------------------------------------------------ vault
    def record_vault_access(self, hypothesis_id: str, experiment_id: str) -> None:
        try:
            self.con.execute("INSERT INTO vault_access (hypothesis_id, experiment_id, opened_at) VALUES (?,?,?)",
                             (hypothesis_id, experiment_id, now()))
            self.con.commit()
        except sqlite3.IntegrityError:
            raise VaultAlreadyOpenedError(f"the vault was already opened for {hypothesis_id}; "
                                          "its vault result is final") from None

    def vault_opened(self, hypothesis_id: str) -> bool:
        return self.con.execute("SELECT 1 FROM vault_access WHERE hypothesis_id=?", (hypothesis_id,)).fetchone() \
            is not None

    # ------------------------------------------------------------ export / import
    def export(self, out_dir: Path | str | None = None) -> Path:
        out = Path(out_dir) if out_dir else self.export_dir
        out.mkdir(parents=True, exist_ok=True)
        for t in TABLES:
            rows = self.query(f"SELECT * FROM {t} ORDER BY rowid")
            with open(out / f"{t}.jsonl", "w") as f:
                for r in rows:
                    f.write(json.dumps(r, sort_keys=True) + "\n")
        return out

    def import_export(self, src: Path | str) -> None:
        src = Path(src)
        for t in TABLES:
            p = src / f"{t}.jsonl"
            if not p.exists():
                continue
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                cols = ",".join(r)
                self.con.execute(f"INSERT OR IGNORE INTO {t} ({cols}) VALUES ({','.join('?' * len(r))})",
                                 tuple(r.values()))
        self.con.commit()

    def close(self):
        self.con.close()


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else (1e300 if math.isinf(f) and f > 0 else (-1e300 if math.isinf(f) else f))
