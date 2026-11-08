import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "src" / "lab" / "registry" / "schema.sql"


def test_registry_schema_applies():
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA.read_text())
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"hypotheses", "experiments", "trials", "stat_tests", "status_changes", "vault_access"} <= tables
