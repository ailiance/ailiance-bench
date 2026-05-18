"""End-to-end smoke test for run_eval.main().

Uses tmp_path isolation + monkeypatching so no real HTTP is needed.
The `iot` domain has no functional scorer, exercising the judge path.
Both base and lora receive the same mocked score (0.7), delta=0, n=3
which is below MIN_HELDOUT=20, so the expected verdict is
"basse confiance".
"""
from __future__ import annotations
import json
import importlib
import sys
import mascarade_eval.run_eval as run_eval


def test_run_eval_smoke_produces_report(tmp_path, monkeypatch):
    # -- redirect HELDOUT_DIR and RESULTS_DIR --
    heldout = tmp_path / "heldout"
    results = tmp_path / "results"
    heldout.mkdir()
    monkeypatch.setattr(run_eval, "HELDOUT_DIR", heldout)
    monkeypatch.setattr(run_eval, "RESULTS_DIR", results)

    # -- 3-item fixture for iot (no functional scorer → exercises judge path) --
    items = [
        {"domain": "iot", "prompt": f"q{i}", "reference": "", "source": "x"}
        for i in range(3)
    ]
    (heldout / "iot.clean.jsonl").write_text(
        "\n".join(json.dumps(it) for it in items)
    )

    # -- mock runner.chat_completion (used by run_config) --
    monkeypatch.setattr("mascarade_eval.runner.chat_completion",
                        lambda url, model, prompt, **kw: "an answer")

    # -- mock judge_one at the binding run_eval actually calls --
    monkeypatch.setattr("mascarade_eval.run_eval.judge_one",
                        lambda *a, **k: 7)  # both base+lora → 0.7

    # -- drive main() via sys.argv --
    monkeypatch.setattr(sys, "argv", ["run_eval", "--domains", "iot"])
    rc = run_eval.main()
    assert rc == 0

    # -- report file must exist --
    report_path = results / "mascarade-eval-report.md"
    assert report_path.exists(), "report file not created"

    report = report_path.read_text()
    assert "iot" in report
    assert "| iot |" in report, f"Expected '| iot |' row, got:\n{report}"
    assert "basse confiance" in report, (
        f"Expected 'basse confiance' verdict (n=3 < MIN_HELDOUT=20), got:\n{report}"
    )

    # -- JSON results file must exist and contain correct scores --
    json_path = results / "mascarade-eval.json"
    assert json_path.exists(), "JSON results file not created"
    rows = json.loads(json_path.read_text())
    assert len(rows) == 1
    assert rows[0]["domain"] == "iot"
    assert rows[0]["verdict"] == "basse confiance"
    assert abs(rows[0]["base_score"] - 0.7) < 1e-9, (
        f"Expected base_score=0.7, got {rows[0]['base_score']}"
    )
    assert abs(rows[0]["lora_score"] - 0.7) < 1e-9, (
        f"Expected lora_score=0.7, got {rows[0]['lora_score']}"
    )


def test_run_eval_handles_missing_heldout(tmp_path, monkeypatch):
    """Missing heldout/<domain>.clean.jsonl => fallback row, not abort."""
    from mascarade_eval import run_eval as _run_eval
    results = tmp_path / "results"
    monkeypatch.setattr(_run_eval, "HELDOUT_DIR", tmp_path / "missing")
    monkeypatch.setattr(_run_eval, "RESULTS_DIR", results)
    monkeypatch.setattr(sys, "argv", ["run_eval", "--domains", "iot"])
    rc = _run_eval.main()
    assert rc == 0
    rows = json.loads((results / "mascarade-eval.json").read_text())
    assert len(rows) == 1
    assert rows[0]["domain"] == "iot"
    assert rows[0]["n"] == 0
    assert rows[0]["verdict"] == "basse confiance"
