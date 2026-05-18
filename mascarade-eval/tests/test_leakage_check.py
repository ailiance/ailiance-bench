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
