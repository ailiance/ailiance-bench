# tests/test_mine_upstream.py
"""Unit tests for mine_upstream.shape_item — network-free."""
from mascarade_eval.mine_upstream import shape_item


def test_shape_item_builds_prompt_reference_pair():
    """SE API returns 'title' + 'body' (HTML) + answer 'body' — standard mapping."""
    raw = {
        "title": "How to route DDR3",
        "body": "<p>details...</p>",
        "accepted_answer_body": "route it like this",
        "link": "https://electronics.stackexchange.com/questions/1/how-to-route-ddr3",
    }
    item = shape_item(raw, domain="kicad")
    assert item["domain"] == "kicad"
    assert "How to route DDR3" in item["prompt"]
    assert item["reference"] == "route it like this"
    assert item["source"]  # provenance recorded


def test_shape_item_title_only_when_no_body():
    """When body is absent, prompt is just the title."""
    raw = {"title": "Decoupling cap placement", "accepted_answer_body": "Place near VCC pin."}
    item = shape_item(raw, domain="emc")
    assert item["prompt"] == "Decoupling cap placement"
    assert item["reference"] == "Place near VCC pin."
    assert item["domain"] == "emc"


def test_shape_item_falls_back_to_link_as_source():
    """'link' field used as source provenance."""
    raw = {
        "title": "FFT window choice",
        "body": "<p>Which window?</p>",
        "accepted_answer_body": "Use Hann.",
        "link": "https://dsp.stackexchange.com/questions/99/fft-window",
    }
    item = shape_item(raw, domain="dsp")
    assert item["source"] == "https://dsp.stackexchange.com/questions/99/fft-window"


def test_shape_item_source_fallback_when_no_link():
    """Falls back gracefully when neither 'link' nor 'source' key is present."""
    raw = {"title": "ESP32 BLE pairing", "accepted_answer_body": "Use NimBLE."}
    item = shape_item(raw, domain="iot")
    assert item["source"] == "upstream"


def test_shape_item_empty_reference_allowed():
    """Items with no accepted_answer_body produce an empty reference (caller filters)."""
    raw = {"title": "STM32 clock config", "body": "<p>help</p>"}
    item = shape_item(raw, domain="stm32")
    assert item["reference"] == ""
    assert item["domain"] == "stm32"
