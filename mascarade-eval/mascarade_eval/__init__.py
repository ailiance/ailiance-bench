"""Trustworthy eval harness for the 10 mascarade hardware LoRAs."""
from pathlib import Path

DOMAINS: tuple[str, ...] = (
    "kicad", "spice", "stm32", "emc", "embedded",
    "platformio", "freecad", "dsp", "iot", "power",
)
BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
HF_ORG = "Ailiance-fr"

_ROOT = Path(__file__).resolve().parent.parent
HELDOUT_DIR = _ROOT / "heldout"
RESULTS_DIR = _ROOT / "results"
MIN_HELDOUT = 20  # below this, a domain verdict is flagged low-confidence
