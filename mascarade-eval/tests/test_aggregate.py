from mascarade_eval.aggregate import verdict, render_report


def test_verdict_learned_when_lora_clearly_beats_base():
    assert verdict(base_score=0.40, lora_score=0.72, n=30) == "a appris"


def test_verdict_no_lora_needed_when_base_already_high():
    assert verdict(base_score=0.93, lora_score=0.94, n=30) == "domaine sans besoin de LoRA"


def test_verdict_weak_when_lora_barely_beats_mediocre_base():
    assert verdict(base_score=0.45, lora_score=0.49, n=30) == "faible"


def test_verdict_low_confidence_when_too_few_items():
    assert verdict(base_score=0.40, lora_score=0.72, n=12) == "basse confiance"


def test_verdict_at_min_heldout_is_not_low_confidence():
    # n == MIN_HELDOUT (20) should not trigger basse confiance
    assert verdict(base_score=0.40, lora_score=0.72, n=20) == "a appris"


def test_verdict_at_learned_margin_boundary():
    # delta == _LEARNED_MARGIN (0.15) exactly => "a appris" (>= inclusive)
    assert verdict(base_score=0.50, lora_score=0.65, n=30) == "a appris"


def test_verdict_at_base_high_boundary_small_delta():
    # base == _BASE_HIGH (0.85) exactly, delta < margin => no LoRA needed
    assert verdict(base_score=0.85, lora_score=0.86, n=30) == "domaine sans besoin de LoRA"


def test_verdict_high_base_with_large_delta_learned():
    # base >= _BASE_HIGH but delta >= margin => "a appris" wins (branch order)
    assert verdict(base_score=0.85, lora_score=1.00, n=30) == "a appris"


def test_render_report_shapes_a_table_row_per_row():
    rows = [{"domain": "iot", "n": 3, "base_score": 0.700,
             "lora_score": 0.700, "verdict": "basse confiance",
             "routed_to": "re-miner du held-out", "scorer": "judge"}]
    out = render_report(rows)
    assert out.startswith("# Mascarade Eval")
    assert "| iot | 3 | 0.700 | 0.700 | judge | basse confiance |" in out
    assert out.endswith("\n")


def test_report_includes_scorer_column():
    """Header + per-row scorer label + verdict caveat must all be present."""
    rows = [
        {"domain": "kicad", "n": 25, "base_score": 0.30, "lora_score": 0.55,
         "verdict": "a appris", "routed_to": "-", "scorer": "functional"},
        {"domain": "iot", "n": 25, "base_score": 0.55, "lora_score": 0.62,
         "verdict": "faible", "routed_to": "B (data) -> C (training)",
         "scorer": "judge"},
    ]
    out = render_report(rows)
    # column header
    assert "| Scorer |" in out
    # per-row labels distinguishable
    assert "| kicad | 25 | 0.300 | 0.550 | functional | a appris |" in out
    assert "| iot | 25 | 0.550 | 0.620 | judge | faible |" in out
    # explicit non-comparability caveat
    assert "ne sont pas" in out and "comparables" in out
    assert "par domaine" in out


def test_report_defaults_scorer_to_judge_when_missing():
    """Back-compat: a row without 'scorer' key still renders, labelled judge."""
    rows = [{"domain": "iot", "n": 3, "base_score": 0.7, "lora_score": 0.7,
             "verdict": "basse confiance", "routed_to": "re-miner du held-out"}]
    out = render_report(rows)
    assert "| judge |" in out
