from mascarade_eval.scorers import functional_score, DOMAIN_SCORER


def test_spice_functional_score_on_valid_netlist():
    netlist = "R1 1 0 1k\nV1 1 0 5\nC1 1 0 1u\n.end"
    s = functional_score("spice", netlist, netlist)
    assert 0.0 <= s["composite"] <= 1.0 and s["parse_ok"] is True


def test_domain_without_functional_scorer_returns_none():
    assert DOMAIN_SCORER.get("iot") is None  # judged by LLM only


from mascarade_eval.scorers import perplexity_score


def test_perplexity_is_none_when_no_logprob_provider():
    assert perplexity_score("some reference answer", logprob_fn=None) is None


def test_perplexity_computes_from_logprobs():
    ppl = perplexity_score("ref", logprob_fn=lambda t: [-1.0, -1.0])
    assert abs(ppl - 2.718281828) < 1e-3


def test_functional_score_returns_none_when_parse_ok_false():
    """Plain-text answer to a structured-output domain => fall through to judge."""
    plain_text = "This is just a paragraph, no SPICE here."
    s = functional_score("spice", plain_text, "irrelevant")
    assert s is None  # caller will use judge_one instead


def test_functional_score_returns_dict_when_parse_ok_true():
    """Real netlist scored functionally, no judge fallback needed."""
    netlist = "R1 1 0 1k\nV1 1 0 5\n.end"
    s = functional_score("spice", netlist, netlist)
    assert s is not None and s["parse_ok"] is True
