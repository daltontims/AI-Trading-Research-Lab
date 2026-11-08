"""Research registry and experiment recording."""

import numpy as np
import pytest

from engine_helpers import bars, market
from lab.engine.backtest import ExecutionConfig, RiskConfig
from lab.registry.db import Registry, VaultAlreadyOpenedError
from lab.research import cost_sensitivity, run_experiment
from lab.strategies.examples import DonchianBreakout, SmaCross


@pytest.fixture
def reg(tmp_path):
    return Registry(tmp_path / "registry.sqlite")


def _hyp(reg, **kw):
    base = dict(family="demo", title="demo", question="does it work?", source="manual",
                asset_classes=["crypto"], instruments=["BTCUSDT"], timeframe="1m", spec={"rule": "x"})
    return reg.register_hypothesis(**{**base, **kw})


def _data():
    rng = np.random.default_rng(0)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, 5000)))
    return market({"BTCUSDT": bars(np.concatenate([[100], c[:-1]]), c=c, v=np.full(5000, 1e6))})


def test_hypothesis_preregistration_is_immutable(reg):
    hid = _hyp(reg, id="H-TEST-1")
    assert _hyp(reg, id="H-TEST-1") == hid  # identical re-registration is fine
    with pytest.raises(ValueError, match="different rules"):
        _hyp(reg, id="H-TEST-1", spec={"rule": "changed"})
    child = _hyp(reg, spec={"rule": "changed"}, parent_id=hid)
    assert reg.hypothesis(child)["parent_id"] == hid


def test_experiment_records_everything(reg):
    hid = _hyp(reg)
    res, eid = run_experiment(DonchianBreakout(n=20), "BTCUSDT", "1m", hypothesis_id=hid, registry=reg,
                              data=_data(), export=False, execution=ExecutionConfig(cost_profile="crypto_perp"))
    e = reg.query("SELECT * FROM experiments WHERE id=?", (eid,))[0]
    for col in ("strategy_id", "strategy_version", "git_commit", "data_fingerprint", "config", "cost_models",
                "market", "timeframe", "started_at", "finished_at", "validation_status"):
        assert e[col], col
    assert e["strategy_id"] == "donchian_breakout" and e["outcome"] == "complete"
    assert e["validation_status"] == "IDEA"
    t = reg.query("SELECT * FROM trials WHERE experiment_id=?", (eid,))
    assert len(t) == 1 and t[0]["n_trades"] == res.metrics["trades"]
    tests = reg.query("SELECT * FROM stat_tests WHERE experiment_id=?", (eid,))
    assert tests[0]["test"] == "lookahead_signal_causality" and tests[0]["passed"] == 1
    assert reg.trial_count(hypothesis_id=hid) == 1 and reg.trial_count(family="demo") == 1


def test_strategy_version_changes_with_params_not_code(reg):
    a, b = SmaCross(fast=10), SmaCross(fast=20)
    assert a.strategy_version == b.strategy_version and a.params != b.params


def test_cost_sensitivity_records_each_multiplier(reg):
    hid = _hyp(reg)
    rows, eid = cost_sensitivity(DonchianBreakout(n=20), "BTCUSDT", "1m", hypothesis_id=hid, registry=reg,
                                 data=_data(), export=False, multipliers=(1, 2, 3))
    assert [r["cost_multiplier"] for r in rows] == [1, 2, 3]
    nets = [r["net_return"] for r in rows]
    assert nets == sorted(nets, reverse=True)
    assert reg.trial_count(hypothesis_id=hid) == 3  # stress runs count as trials


def test_vault_can_be_opened_once(reg):
    hid = _hyp(reg)
    eid = reg.start_experiment(hypothesis_id=hid, strategy_id="x", strategy_version="1", stage="vault",
                               market="crypto", instruments=["BTCUSDT"], timeframe="1m", data_split="vault",
                               data_versions={}, config={})
    reg.record_vault_access(hid, eid)
    with pytest.raises(VaultAlreadyOpenedError):
        reg.record_vault_access(hid, eid)
    with pytest.raises(PermissionError):
        run_experiment(SmaCross(), "BTCUSDT", "1m", hypothesis_id=hid, split="vault", stage="vault",
                       registry=reg, data=_data(), export=False)


def test_export_import_roundtrip(tmp_path, reg):
    hid = _hyp(reg)
    run_experiment(SmaCross(fast=5, slow=20), "BTCUSDT", "1m", hypothesis_id=hid, registry=reg, data=_data(),
                   export=False, risk=RiskConfig(sizing="pct_equity"))
    out = reg.export(tmp_path / "export")
    fresh = Registry(tmp_path / "new.sqlite", export_dir=out)
    for t in ("hypotheses", "experiments", "trials", "stat_tests"):
        assert fresh.query(f"SELECT COUNT(*) n FROM {t}")[0]["n"] == reg.query(f"SELECT COUNT(*) n FROM {t}")[0]["n"]


def test_failed_experiment_is_recorded(reg):
    hid = _hyp(reg)
    with pytest.raises(Exception):
        run_experiment(SmaCross(), ["NOT_A_SYMBOL"], "1m", hypothesis_id=hid, registry=reg, export=False)
    row = reg.query("SELECT outcome, error FROM experiments ORDER BY rowid DESC LIMIT 1")[0]
    assert row["outcome"] == "error" and row["error"]
