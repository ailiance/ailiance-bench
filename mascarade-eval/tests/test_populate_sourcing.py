import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import populate_sourcing as p  # noqa: E402


def _write_train(d: Path, records: list[dict]) -> None:
    d.mkdir()
    (d / "train.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )


def test_compute_sourcing_counts_records_licenses_sources(tmp_path):
    _write_train(tmp_path / "kicad", [
        {"messages": [{"role": "user", "content": "q1"}],
         "_provenance": {"license": "CC-BY-SA-4.0", "source": "KiCad/x"}},
        {"messages": [{"role": "user", "content": "q2"}],
         "_provenance": {"license": "CC-BY-SA-4.0", "source": "KiCad/y"}},
        {"messages": [{"role": "user", "content": "q3"}],
         "_provenance": {"license": "Apache-2.0", "source": "KiCad/x"}},
    ])
    row = p.compute_sourcing(tmp_path / "kicad")
    assert row["domain"] == "kicad"
    assert row["n_records"] == 3
    assert row["n_licenses"] == 2  # CC-BY-SA-4.0 + Apache-2.0
    assert row["n_sources"] == 2  # KiCad/x + KiCad/y
    assert json.loads(row["licenses"]) == {"CC-BY-SA-4.0": 2, "Apache-2.0": 1}
    assert sorted(json.loads(row["sources"])) == ["KiCad/x", "KiCad/y"]


def test_compute_sourcing_no_train_returns_none(tmp_path):
    d = tmp_path / "electronics"
    d.mkdir()
    (d / "pdf_supplement.jsonl").write_text("{}\n")
    assert p.compute_sourcing(d) is None


def test_compute_sourcing_lists_extra_files(tmp_path):
    _write_train(tmp_path / "cpp", [
        {"_provenance": {"license": "BSD-3-Clause", "source": "X/y"}},
    ])
    (tmp_path / "cpp" / "valid.jsonl").write_text("{}\n")
    (tmp_path / "cpp" / "train_curriculum.jsonl").write_text("{}\n")
    row = p.compute_sourcing(tmp_path / "cpp")
    assert "valid.jsonl" in row["extra_files"]
    assert "train_curriculum.jsonl" in row["extra_files"]


def test_compute_sourcing_skips_malformed_lines(tmp_path):
    d = tmp_path / "freecad"
    d.mkdir()
    (d / "train.jsonl").write_text(
        '{"_provenance":{"license":"LGPL","source":"FreeCAD/x"}}\n'
        'this is not json\n'
        '{"_provenance":{"license":"LGPL","source":"FreeCAD/y"}}\n')
    row = p.compute_sourcing(d)
    assert row["n_records"] == 2
