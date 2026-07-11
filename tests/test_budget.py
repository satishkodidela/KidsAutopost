import datetime as dt
import json

import pytest

from budget import Budget, BudgetExceeded, RATES


def make_budget(tmp_path, max_run=10.0, max_month=100.0):
    b = Budget(path=tmp_path / "costs.json", now=dt.date(2026, 7, 15))
    b.max_run, b.max_month = max_run, max_month
    return b


def test_precheck_within_budget(tmp_path):
    b = make_budget(tmp_path)
    estimate = b.precheck(n_clips=6, clip_seconds=8, backend="veo")
    assert estimate == pytest.approx(6 * 8 * RATES["veo"] * 1.3)


def test_precheck_exceeds_run_cap(tmp_path):
    b = make_budget(tmp_path, max_run=1.0)
    with pytest.raises(BudgetExceeded):
        b.precheck(n_clips=6, clip_seconds=8, backend="veo")


def test_charge_accumulates_and_persists(tmp_path):
    b = make_budget(tmp_path)
    b.charge(8, "veo", note="clip1")
    b.charge(8, "veo", note="clip2")
    assert b.run_spent == pytest.approx(16 * RATES["veo"])
    ledger = json.loads((tmp_path / "costs.json").read_text())
    assert ledger["months"]["2026-07"] == pytest.approx(16 * RATES["veo"])
    assert len(ledger["entries"]) == 2


def test_run_cap_enforced_on_charge(tmp_path):
    b = make_budget(tmp_path, max_run=1.0)
    with pytest.raises(BudgetExceeded):
        b.charge(60, "veo")
    assert b.run_spent == 0.0  # failed charge must not be recorded


def test_month_cap_spans_runs(tmp_path):
    make_budget(tmp_path, max_month=2.0).charge(8, "veo")
    b2 = make_budget(tmp_path, max_month=2.0)  # same ledger file, new run
    with pytest.raises(BudgetExceeded):
        b2.charge(8, "veo")
