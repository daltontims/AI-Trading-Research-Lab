"""End-to-end promotion pipeline on synthetic data with known truth."""

import numpy as np
import pytest

from lab.engine.backtest import ExecutionConfig, RiskConfig
from lab.registry.db import Registry
from lab.strategies.examples import RandomEntry, TimeSeriesMomentum
from lab.validation.evaluate import evaluate, param_grid
from lab.validation.synthetic import dev_val, path_bars


def synthetic(seed, n, phi=0.0, vol=0.004, symbol="BTCUSDT"):
    """Hourly bars from a continuous path with AR(1) bar returns: phi=0 is a pure random walk."""
    return dev_val(path_bars(seed, n, phi=phi, vol=vol), symbol)


@pytest.fixture
def reg(tmp_path):
    return Registry(tmp_path / "r.sqlite")


def _hyp(reg, family):
    return reg.register_hypothesis(family=family, title=family, question="?", source="manual",
                                   asset_classes=["crypto"], instruments=["BTCUSDT"], timeframe="1h", spec={"f": family})


LOW_COST = ExecutionConfig(cost_profile="crypto_perp", cost_multiplier=0.2)


def test_param_grid():
    assert param_grid({"a": [1, 2], "b": [3]}) == [{"a": 1, "b": 3}, {"a": 2, "b": 3}]


def test_pipeline_rejects_best_of_random_strategies(reg):
    dev, val = synthetic(0, 24 * 365 * 4)
    hid = _hyp(reg, "random")
    ev = evaluate(RandomEntry, {"seed": list(range(12))}, ["BTCUSDT"], "1h", hypothesis_id=hid, registry=reg,
                  dev_data=dev, val_data=val, execution=LOW_COST, fixed_params={"prob": 0.01},
                  risk=RiskConfig(max_bars_held=24), export=False, write_report=False, n_boot=200)
    assert ev.verdict == "REJECTED"
    assert reg.hypothesis(hid)["status"] == "REJECTED"
    assert ev.val_metrics is None  # validation data never touched for a rejected idea
    assert not reg.query("SELECT 1 FROM experiments WHERE stage='validation'")
    assert reg.trial_count(hypothesis_id=hid) >= 12


def test_pipeline_finds_planted_momentum_edge(reg, tmp_path, monkeypatch):
    import lab.validation.evaluate as E
    monkeypatch.setattr(E, "REPORT_DIR", tmp_path / "reports")
    dev, val = synthetic(1, 24 * 365 * 4, phi=0.15)
    hid = _hyp(reg, "momentum")
    ev = evaluate(TimeSeriesMomentum, {"lookback": [1, 2, 3, 4]}, ["BTCUSDT"], "1h", hypothesis_id=hid,
                  registry=reg, dev_data=dev, val_data=val, execution=LOW_COST,
                  risk=RiskConfig(sizing="pct_equity", position_pct=0.5), export=False, n_boot=200)
    assert ev.verdict == "CANDIDATE", ev.reasons
    assert ev.best_params["lookback"] == 1
    assert ev.val_metrics["total_return"] > 0
    assert reg.hypothesis(hid)["status"] == "CANDIDATE"
    assert ev.confidence in ("low", "moderate")
    text = open(ev.report_path).read()
    for field in ("Win rate", "Profit factor", "Max drawdown", "Validation", "Weaknesses", "Confidence"):
        assert field in text
    # The validation split can only be used once per hypothesis.
    with pytest.raises(PermissionError):
        evaluate(TimeSeriesMomentum, {"lookback": [1, 2, 3, 4]}, ["BTCUSDT"], "1h", hypothesis_id=hid,
                 registry=reg, dev_data=dev, val_data=val, execution=LOW_COST,
                 risk=RiskConfig(sizing="pct_equity", position_pct=0.5), export=False, write_report=False,
                 n_boot=100)


def test_pipeline_rejects_edge_destroyed_by_costs(reg):
    dev, val = synthetic(1, 24 * 365 * 4, phi=0.15)
    hid = _hyp(reg, "momentum_costly")
    ev = evaluate(TimeSeriesMomentum, {"lookback": [1, 2]}, ["BTCUSDT"], "1h", hypothesis_id=hid, registry=reg,
                  dev_data=dev, val_data=val, execution=ExecutionConfig(cost_profile="crypto_spot_us_retail",
                                                                       profile_by_symbol={}),
                  risk=RiskConfig(sizing="pct_equity", position_pct=0.5), export=False, write_report=False,
                  n_boot=100)
    assert ev.verdict == "REJECTED"
    assert any(r.startswith(("net_profit_after_costs", "profit_factor", "profitable_at_2x_costs")) for r in ev.reasons)


def test_pipeline_records_stat_tests(reg):
    dev, val = synthetic(2, 24 * 365 * 3)
    hid = _hyp(reg, "records")
    ev = evaluate(TimeSeriesMomentum, {"lookback": [6, 12, 24, 48]}, ["BTCUSDT"], "1h", hypothesis_id=hid,
                  registry=reg, dev_data=dev, val_data=val, execution=LOW_COST, export=False,
                  write_report=False, n_boot=100, risk=RiskConfig(sizing="pct_equity", position_pct=0.5))
    names = {r["test"] for r in reg.query("SELECT test FROM stat_tests WHERE experiment_id=?", (ev.experiments[0],))}
    assert {"deflated_sharpe", "pbo", "spa", "walk_forward_oos_sharpe", "parameter_plateau", "min_trades",
            "profitable_at_2x_costs", "lookahead_signal_causality"} <= names


def test_breakouts_with_stops_do_not_profit_on_random_walks():
    """Regression for D-016: stop fills must not create profits on a driftless random walk."""
    from lab.engine.backtest import run_backtest
    from lab.strategies.examples import DonchianBreakout
    from lab.validation.synthetic import market
    rets = []
    for i in range(24):
        d = market(path_bars(500 + i, 24 * 365))
        rets.append(run_backtest(DonchianBreakout(n=20), d, RiskConfig(sizing="pct_equity", position_pct=0.5),
                                 ExecutionConfig(cost_profile="crypto_perp", cost_multiplier=0.0)).metrics["total_return"])
    r = np.array(rets)
    t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
    assert t < 2.0, f"breakouts profit on random walks (t={t:.2f}): fill bias?"


def test_vault_test_requires_candidate_and_runs_once(reg, monkeypatch):
    import lab.validation.evaluate as E
    from lab.registry.db import VaultAlreadyOpenedError
    hid = _hyp(reg, "vault")
    with pytest.raises(PermissionError, match="only CANDIDATE"):
        E.vault_test(TimeSeriesMomentum, {"lookback": 1}, ["BTCUSDT"], "1h", hypothesis_id=hid, registry=reg)
    reg.set_status(hid, "CANDIDATE", "test")
    _, vault = synthetic(9, 24 * 365, phi=0.15)
    import lab.research as R
    monkeypatch.setattr(R, "load", lambda *a, **k: vault)
    out = E.vault_test(TimeSeriesMomentum, {"lookback": 1}, ["BTCUSDT"], "1h", hypothesis_id=hid, registry=reg,
                       execution=LOW_COST, risk=RiskConfig(sizing="pct_equity", position_pct=0.5), style="intraday")
    assert out["verdict"] == "VALIDATED" and reg.hypothesis(hid)["status"] == "VALIDATED"
    assert reg.vault_opened(hid)
    reg.set_status(hid, "CANDIDATE", "pretend")  # even if someone resets the status...
    with pytest.raises((PermissionError, VaultAlreadyOpenedError)):
        E.vault_test(TimeSeriesMomentum, {"lookback": 1}, ["BTCUSDT"], "1h", hypothesis_id=hid, registry=reg,
                     execution=LOW_COST)
