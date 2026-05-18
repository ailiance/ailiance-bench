from mascarade_eval.aggregate import verdict


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
