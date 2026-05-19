from mascarade_eval.leakage_check import normalize, is_leak, filter_leaks

def test_normalize_collapses_whitespace_and_case():
    assert normalize("  Hello   WORLD\n") == "hello world"

def test_exact_duplicate_is_a_leak():
    train = ["how do I route a differential pair"]
    assert is_leak("How do I route a differential pair?", train) is True

def test_near_duplicate_is_a_leak():
    train = ["what value decoupling capacitor for an stm32 vdd pin"]
    cand = "What value of decoupling capacitor should I use for an STM32 VDD pin?"
    assert is_leak(cand, train, overlap_threshold=0.6) is True

def test_distinct_prompt_is_not_a_leak():
    train = ["how to configure spi on stm32"]
    assert is_leak("explain aliasing in dsp", train) is False

def test_filter_leaks_drops_leaked_items_and_reports():
    items = [{"prompt": "configure spi on stm32"}, {"prompt": "explain fft windowing"}]
    train = ["how to configure spi on stm32"]
    clean, dropped = filter_leaks(items, train)
    assert len(clean) == 1 and clean[0]["prompt"] == "explain fft windowing"
    assert len(dropped) == 1

def test_long_prompt_not_leaked_by_short_generic_training():
    # Regression: a long held-out prompt must not be flagged just because
    # it covers a short training prompt's stopwords + generic vocabulary.
    # Unigram word sets over-flagged this (every long prompt covered 60%+
    # of some short instruction's words); content trigrams fix it.
    train = [
        "write a freecad python script to create a parametric box",
        "write an openscad script for a parametric gear with teeth",
        "write a cadquery script for a pcb standoff with a hex base",
    ]
    cand = (
        "I want to create a box in FreeCAD for a small PCB. I am new to "
        "the software and cannot work out how to add mounting holes to "
        "the base, or how to make the script parametric so the "
        "dimensions can change later. Any help would be appreciated."
    )
    assert is_leak(cand, train) is False

def test_punctuation_only_variant_is_a_leak():
    # "exact" duplicate must survive case + punctuation differences.
    train = ["set the via stitching pitch for a ground plane"]
    assert is_leak("Set the via-stitching pitch for a ground plane!!", train) is True

def test_paraphrased_near_duplicate_is_caught():
    # A genuine reword of a training prompt still shares content bigrams
    # ("decoupling capacitor", "stm32 vdd") -- it must count as a leak.
    train = ["set the decoupling capacitor value for the stm32 vdd pin"]
    cand = ("What decoupling capacitor value should I pick for an "
            "STM32 VDD pin on my board?")
    assert is_leak(cand, train) is True

def test_short_prompt_below_shingle_size_is_handled():
    # prompts shorter than k content words fall back to a joined shingle
    assert is_leak("kicad", ["kicad"]) is True
    assert is_leak("kicad", ["explain dsp aliasing fundamentals"]) is False
