"""End-to-end test for the leakage-filter pipeline.

Drives `filter_domain` against an isolated tmp_path with a stub
training-corpus provider so no network / HF round-trip is required.
"""
from __future__ import annotations

import json

from mascarade_eval.filter_heldout import filter_domain


def test_filter_heldout_pipeline_e2e(tmp_path):
    heldout = tmp_path / "heldout"
    heldout.mkdir()

    raw_items = [
        {"domain": "kicad", "prompt": "How to add a differential pair in KiCad?",
         "reference": "Use the pair routing tool.", "source": "se://a"},
        {"domain": "kicad", "prompt": "configure spi on stm32",
         "reference": "stub", "source": "se://b"},
        {"domain": "kicad", "prompt": "What is the best ESD diode for USB-C?",
         "reference": "TPD4S012.", "source": "se://c"},
    ]
    (heldout / "kicad.raw.jsonl").write_text(
        "\n".join(json.dumps(it) for it in raw_items)
    )

    training_prompts = [
        "how to configure spi on stm32",         # near-dup of item[1]
        "explain ground plane stitching",        # unrelated
    ]

    kept, dropped = filter_domain(
        "kicad",
        heldout_dir=heldout,
        train_prompts_provider=lambda _d: training_prompts,
    )

    assert kept == 2
    assert dropped == 1

    clean_path = heldout / "kicad.clean.jsonl"
    dropped_path = heldout / "kicad.dropped.jsonl"
    assert clean_path.exists() and dropped_path.exists()

    clean = [json.loads(line) for line in clean_path.read_text().splitlines() if line]
    drop = [json.loads(line) for line in dropped_path.read_text().splitlines() if line]
    assert {it["prompt"] for it in clean} == {
        "How to add a differential pair in KiCad?",
        "What is the best ESD diode for USB-C?",
    }
    assert drop[0]["prompt"] == "configure spi on stm32"
    assert "overlap" in drop[0]
    assert 0.6 <= drop[0]["overlap"] <= 1.0


def test_filter_heldout_missing_raw_is_noop(tmp_path):
    heldout = tmp_path / "heldout"
    heldout.mkdir()
    kept, dropped = filter_domain(
        "spice",
        heldout_dir=heldout,
        train_prompts_provider=lambda _d: [],
    )
    assert kept == 0 and dropped == 0
    assert not (heldout / "spice.clean.jsonl").exists()


def test_filter_heldout_empty_raw_writes_empty(tmp_path):
    heldout = tmp_path / "heldout"
    heldout.mkdir()
    (heldout / "iot.raw.jsonl").write_text("")
    kept, dropped = filter_domain(
        "iot",
        heldout_dir=heldout,
        train_prompts_provider=lambda _d: ["irrelevant"],
    )
    assert kept == 0 and dropped == 0
    assert (heldout / "iot.clean.jsonl").read_text() == ""
