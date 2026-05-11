#!/usr/bin/env python3
"""
Bench fonctionnel KiCad + SPICE — Phase 1 (kicad-dsl + kicad-pcb + spice-sim).

Va plus loin que la perplexite : on prompte chaque modele 4-bit MLX avec
un input du dataset, on genere via mlx_lm.generate (Python API), puis on
parse / score la sortie selon des regles de structure :

  - kicad-dsl  : .lib legacy (DEF...ENDDEF, F0/F1/F2, X pins, S/DRAW)
  - kicad-pcb  : .kicad_mod legacy S-expr (module, layer F.Cu, fp_text,
                 pad count, at/size)
  - spice-sim  : Berkeley SPICE / Ngspice netlist (.cir/.sp) — composants
                 R/C/L/V/I/Q/M/D/X, .model, .subckt/.ends, analyses
                 .dc/.ac/.tran/.op, .end final, ground node 0

Sortie :
  ~/bench-results/kicad_functional_phase1.json
  ~/bench-results/kicad_functional_phase1.md
  Save incremental apres chaque (modele, dataset).

Usage :
  python3 ~/scripts/bench_kicad_functional.py                  # 20 samples
  python3 ~/scripts/bench_kicad_functional.py --n-samples 50
  python3 ~/scripts/bench_kicad_functional.py --models gemma-e2b
  python3 ~/scripts/bench_kicad_functional.py --datasets kicad-dsl
  python3 ~/scripts/bench_kicad_functional.py --dry-run

Env :
  EUKIKI_DATA_DIR     : default ~/eu-kiki-data/hf-traced
  BENCH_RESULTS_DIR   : default ~/bench-results
  MLX_VENV_BIN        : default ~/mlx-stack/.venv/bin
  KICAD_MAX_TOKENS    : override max tokens (default per-dataset)
  KICAD_SKIP_HEAVY    : "1" pour skip granite-4.1-30b (default: 1, RAM)
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Paths & constants
# --------------------------------------------------------------------------- #

HOME = Path.home()
DATA_DIR = Path(os.environ.get("EUKIKI_DATA_DIR", HOME / "eu-kiki-data" / "hf-traced"))
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
PYBIN = Path(os.environ.get("MLX_VENV_BIN", HOME / "mlx-stack" / ".venv" / "bin"))

OUT_JSON = BENCH_DIR / "kicad_functional_phase1.json"
OUT_MD = BENCH_DIR / "kicad_functional_phase1.md"
LOG_DIR = HOME / "logs"

# Memory ceiling on M1 Max 32 GB : granite-4.1-30b en 4-bit pese ~16 GB,
# et la generation (vs perplexite) consomme bien plus de KV cache.
# On le SKIP par defaut en Phase 1, peut etre force via KICAD_SKIP_HEAVY=0.
SKIP_HEAVY = os.environ.get("KICAD_SKIP_HEAVY", "1") == "1"
HEAVY_NICKS = {"granite-4.1-30b"}

# Memes nicknames que bench_31_domains_base.py (reutilise tel quel).
MODELS: list[tuple[str, str]] = [
    ("gemma-e4b-eu-kiki-base",   "lmstudio-community/gemma-4-E4B-it-MLX-4bit"),
    ("gemma-e2b",                "lmstudio-community/gemma-4-E2B-it-MLX-4bit"),
    ("ministral-3b",             "mlx-community/Ministral-3-3B-Instruct-2512-4bit"),
    ("ministral-3-8b",           "mlx-community/Ministral-3-8B-Instruct-2512-4bit"),
    ("ministral-3-14b-instruct", "mlx-community/Ministral-3-14B-Instruct-2512-4bit"),
    ("ministral-3-14b-reasoning","mlx-community/Ministral-3-14B-Reasoning-2512-4bit"),
    ("granite-4.1-3b",           "mlx-community/granite-4.1-3b-4bit"),
    ("granite-4.1-30b",          "mlx-community/granite-4.1-30b-4bit"),
]

DATASETS = ["kicad-dsl", "kicad-pcb", "spice-sim"]

# Per-dataset gen params : DSL plus court, PCB plus long (max 33KB observe).
# SPICE : moyenne ~56 lignes / 1.4KB, max ~12KB sur valid -> 1024 suffit
# largement pour la majorite, on borde a 1280 pour les longs subckts.
GEN_PARAMS = {
    "kicad-dsl": {"max_tokens": 1024},
    "kicad-pcb": {"max_tokens": 1536},
    "spice-sim": {"max_tokens": 1280},
}

DEFAULT_N_SAMPLES = 20

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_functional-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
_log_fh = None


def _open_log() -> None:
    global _log_fh
    if _log_fh is None:
        _log_fh = LOG_PATH.open("a", buffering=1)


def log(msg: str) -> None:
    _open_log()
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")


# --------------------------------------------------------------------------- #
# Dataset loading
# --------------------------------------------------------------------------- #


def load_samples(dataset: str, n: int, seed: int = 0) -> list[dict[str, str]]:
    """Charge n samples (prompt user + reference assistant) du valid.jsonl."""
    p = DATA_DIR / dataset / "valid.jsonl"
    if not p.exists():
        raise FileNotFoundError(p)
    rows: list[dict[str, str]] = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            msgs = d.get("messages", [])
            user = next((m["content"] for m in msgs if m.get("role") == "user"), None)
            asst = next((m["content"] for m in msgs if m.get("role") == "assistant"), None)
            if user is None or asst is None:
                continue
            rows.append({
                "prompt": user,
                "expected": asst,
                "provenance": d.get("_provenance", {}),
            })
    # deterministic prefix slice — pas besoin de shuffle pour Phase 1
    return rows[:n]


# --------------------------------------------------------------------------- #
# Parsers / scoring
# --------------------------------------------------------------------------- #


def _balanced_parens(s: str) -> bool:
    depth = 0
    in_str = False
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _expected_pin_count_lib(expected: str) -> int:
    return len(re.findall(r"^X\s+\S+\s+\S+\s+", expected, flags=re.M))


def _gen_pin_count_lib(generated: str) -> int:
    return len(re.findall(r"^X\s+\S+\s+\S+\s+", generated, flags=re.M))


def _expected_pad_count_pcb(expected: str) -> int:
    return len(re.findall(r"\(pad\s+", expected))


def _gen_pad_count_pcb(generated: str) -> int:
    return len(re.findall(r"\(pad\s+", generated))


def _extract_def_block(text: str) -> str | None:
    """Extrait le bloc DEF...ENDDEF d'une sortie .lib (s'il existe)."""
    m = re.search(r"(DEF\s+\S+.*?ENDDEF)", text, flags=re.S)
    return m.group(1) if m else None


def _extract_module_block(text: str) -> str | None:
    """Extrait le 1er bloc (module ...) balance d'une sortie .kicad_mod."""
    idx = text.find("(module")
    if idx == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(idx, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[idx:i + 1]
    return None  # unbalanced


def score_dsl(generated: str, expected: str) -> dict[str, Any]:
    """Score .lib legacy KiCad 5."""
    block = _extract_def_block(generated)
    parse_ok = block is not None
    src = block if block else generated

    has_f0 = bool(re.search(r"^F0\s+", src, flags=re.M))
    has_f1 = bool(re.search(r"^F1\s+", src, flags=re.M))
    has_f2 = bool(re.search(r"^F2\s+", src, flags=re.M))
    fields_complete = has_f0 and has_f1 and has_f2

    has_draw = ("DRAW" in src and "ENDDRAW" in src)
    has_rect = bool(re.search(r"^S\s+", src, flags=re.M))
    structure_ok = has_draw or has_rect

    fplist_ok = (src.count("$FPLIST") == src.count("$ENDFPLIST"))

    exp_pins = _expected_pin_count_lib(expected)
    gen_pins = _gen_pin_count_lib(src)
    pin_count_match = (exp_pins > 0 and gen_pins == exp_pins)
    if exp_pins == 0:
        # rare ; on neutralise pour eviter de penaliser injustement
        pin_count_match = (gen_pins == 0)

    structure_score = (
        (1.0 if fields_complete else 0.0) * 0.4
        + (1.0 if structure_ok else 0.0) * 0.4
        + (1.0 if fplist_ok else 0.0) * 0.2
    )
    values_score = 1.0 if pin_count_match else 0.0
    composite = (
        (1.0 if parse_ok else 0.0) * 0.4
        + structure_score * 0.4
        + values_score * 0.2
    )

    return {
        "parse_ok": parse_ok,
        "fields_complete": fields_complete,
        "has_draw_or_rect": structure_ok,
        "fplist_balanced": fplist_ok,
        "expected_pin_count": exp_pins,
        "generated_pin_count": gen_pins,
        "pin_count_match": pin_count_match,
        "composite": round(composite, 4),
    }


def score_pcb(generated: str, expected: str) -> dict[str, Any]:
    """Score .kicad_mod legacy S-expr."""
    block = _extract_module_block(generated)
    parse_ok = block is not None and _balanced_parens(block)
    src = block if block else generated

    has_layer_fcu = bool(re.search(r"\(layer\s+F\.Cu\)", src))
    has_fp_text = bool(re.search(r"\(fp_text\s+", src))
    has_at = bool(re.search(r"\(at\s+-?\d", src))
    has_size = bool(re.search(r"\(size\s+\d", src))
    structure_ok = has_layer_fcu and has_fp_text

    exp_pads = _expected_pad_count_pcb(expected)
    gen_pads = _gen_pad_count_pcb(src)
    pad_count_match = (exp_pads > 0 and gen_pads == exp_pads)
    if exp_pads == 0:
        pad_count_match = (gen_pads == 0)

    structure_score = (
        (1.0 if structure_ok else 0.0) * 0.5
        + (1.0 if has_at else 0.0) * 0.25
        + (1.0 if has_size else 0.0) * 0.25
    )
    values_score = 1.0 if pad_count_match else 0.0
    composite = (
        (1.0 if parse_ok else 0.0) * 0.4
        + structure_score * 0.4
        + values_score * 0.2
    )

    return {
        "parse_ok": parse_ok,
        "layer_fcu": has_layer_fcu,
        "has_fp_text": has_fp_text,
        "has_at_coords": has_at,
        "has_size_dims": has_size,
        "expected_pad_count": exp_pads,
        "generated_pad_count": gen_pads,
        "pad_count_match": pad_count_match,
        "composite": round(composite, 4),
    }


# --------------------------------------------------------------------------- #
# SPICE parsing / scoring
# --------------------------------------------------------------------------- #

# Composant lines : la 1re lettre code le type. On ignore lignes commentaires
# (* en col 0) et directives (.). Les continuations '+' sont ignorees.
# On exige au moins 2 tokens "node-like" (alphanumeric/underscore) apres le
# nom de composant pour eviter de matcher de la prose ("Hello world").
# SPICE est case-insensitive, on accepte upper et lower.
_SPICE_COMP_RE = re.compile(
    r"^[ \t]*([RCLVIQMDXKEFGHTBSWJZUOAP])([A-Za-z0-9_]+)\s+"
    r"([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)",
    re.M | re.I,
)
_SPICE_MODEL_RE = re.compile(r"^\s*\.model\s+\S+", re.M | re.I)
_SPICE_SUBCKT_RE = re.compile(r"^\s*\.subckt\s+\S+", re.M | re.I)
_SPICE_ENDS_RE = re.compile(r"^\s*\.ends\b", re.M | re.I)
_SPICE_ANALYSIS_RE = re.compile(
    r"^\s*\.(dc|ac|tran|op|sens|noise|pss|pz|disto|sp|four)\b",
    re.M | re.I,
)
_SPICE_END_RE = re.compile(r"^\s*\.end\s*$", re.M | re.I)


def _spice_strip_fences(text: str) -> str:
    """Retire fences ```spice ... ``` si presents."""
    m = re.search(r"```(?:spice|cir|sp|net)?\s*\n(.*?)```", text, re.S | re.I)
    return m.group(1) if m else text


_SPICE_NODE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _looks_like_spice_token(tok: str) -> bool:
    """True si tok ressemble a un identifiant SPICE valide (pas de prose)."""
    return bool(_SPICE_NODE_RE.match(tok))


def _spice_referenced_nodes(text: str) -> dict[str, int]:
    """Compte la frequence de chaque noeud reference par les composants.

    Heuristique : pour les composants 2/3/4-pin, les 1ers tokens apres le
    nom de composant sont des noeuds (jusqu'au 1er token qui ressemble a une
    valeur ou un model name). On joue safe : pour R/C/L/V/I/D, on prend les
    2 1ers ; pour Q/M (BJT/MOSFET), 3-4 ; pour X (subckt), tout sauf le
    dernier (= subckt name). On ignore les lignes-titre (1re ligne non-vide
    ne commence par aucun token SPICE valide) — la 1re ligne d'une netlist
    SPICE est un titre arbitraire (Berkeley convention).
    """
    counts: dict[str, int] = {}
    lines = text.splitlines()
    seen_first_real = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("*") or line.startswith(".") or line.startswith("+"):
            continue
        toks = line.split()
        if not toks:
            continue
        head = toks[0]
        # 1re ligne non-commentaire = titre Berkeley SPICE, on l'ignore
        # SAUF si elle est clairement un composant (1 lettre + suffixe).
        if not seen_first_real:
            seen_first_real = True
            if not (len(head) >= 2 and head[0].isalpha() and head[1:].replace("_", "").isalnum()
                    and head[0].upper() in "RCLVIQMDXKEFGHTBSWJZUOAP"):
                continue
        if not head or not head[0].isalpha():
            continue
        c0 = head[0].upper()
        # Verif rapide : si head ne ressemble pas a un identifiant SPICE
        # propre (ex: "Hello,"), skip cette ligne.
        if not _looks_like_spice_token(head):
            continue
        nodes: list[str] = []
        if c0 in "RCLVIDH" and len(toks) >= 3:
            nodes = toks[1:3]
        elif c0 == "Q" and len(toks) >= 4:
            nodes = toks[1:4]
        elif c0 == "M" and len(toks) >= 5:
            nodes = toks[1:5]
        elif c0 == "X" and len(toks) >= 3:
            nodes = toks[1:-1]
        elif c0 in "EFG" and len(toks) >= 5:
            nodes = toks[1:5]
        elif c0 == "T" and len(toks) >= 5:
            nodes = toks[1:5]
        elif c0 == "O" and len(toks) >= 5:
            nodes = toks[1:5]
        elif c0 == "B" and len(toks) >= 3:
            nodes = toks[1:3]
        else:
            if len(toks) >= 3:
                nodes = toks[1:3]
        for n in nodes:
            if "=" in n:
                continue
            # Rejette les tokens qui ne sont pas des identifiants
            # SPICE valides (pas de prose comme "lossy" si fragmentaire).
            if not _looks_like_spice_token(n):
                continue
            counts[n] = counts.get(n, 0) + 1
    return counts


def parse_spice(text: str) -> dict[str, Any]:
    """Parse une netlist SPICE et extrait les metriques structurelles."""
    src = _spice_strip_fences(text)

    components = _SPICE_COMP_RE.findall(src)
    n_components = len(components)
    n_models = len(_SPICE_MODEL_RE.findall(src))
    n_subckts = len(_SPICE_SUBCKT_RE.findall(src))
    n_ends = len(_SPICE_ENDS_RE.findall(src))
    n_analyses = len(_SPICE_ANALYSIS_RE.findall(src))
    has_end = bool(_SPICE_END_RE.search(src))

    nodes = _spice_referenced_nodes(src)
    ground_node_present = "0" in nodes
    floating = [n for n, c in nodes.items() if c < 2]

    # balanced : chaque .subckt a un .ends ; au moins 1 composant ; .end
    # n'est pas obligatoire dans un sub-snippet mais on le note separement.
    balanced = (n_subckts == n_ends) and (n_components > 0)

    # parse_ok strict : >= 3 composants (vraie netlist) OU au moins 1
    # composant avec ground node 0 + soit .end soit .model/.subckt/.analyse
    # — un texte de prose peut matcher 1-2 lignes par hasard, mais une
    # vraie netlist a quasi-toujours ground + une analyse OU plusieurs
    # composants.
    has_spice_directive = (n_models + n_subckts + n_analyses) > 0
    parse_ok = balanced and (
        n_components >= 3
        or (n_components >= 1 and ground_node_present and (has_end or has_spice_directive))
    )

    return {
        "parse_ok": parse_ok,
        "has_end": has_end,
        "n_components": n_components,
        "n_models": n_models,
        "n_subckts": n_subckts,
        "n_analyses": n_analyses,
        "ground_node_present": ground_node_present,
        "floating_nodes": floating[:20],  # cap pour bornage JSON
        "n_floating_nodes": len(floating),
        "balanced": balanced,
    }


def _ratio_match(gen: int, exp: int) -> float:
    """1 - |gen-exp|/max(exp,1), borne a [0,1]."""
    denom = max(exp, 1)
    diff = abs(gen - exp)
    return max(0.0, min(1.0, 1.0 - diff / denom))


def score_spice(generated: str, expected: str) -> dict[str, Any]:
    """Score une netlist SPICE generee contre la reference."""
    g = parse_spice(generated)
    e = parse_spice(expected)

    parse_ok = 1.0 if g["parse_ok"] else 0.0
    # has_end : si la reference n'a PAS de .end (cas Berkeley legacy ou
    # snippet), on neutralise (= 1.0) pour ne pas penaliser injustement.
    if e["has_end"]:
        has_end = 1.0 if g["has_end"] else 0.0
    else:
        has_end = 1.0 if g["has_end"] else 0.5
    component_count_match = _ratio_match(g["n_components"], e["n_components"])
    analysis_count_match = _ratio_match(g["n_analyses"], e["n_analyses"])
    ground_present = 1.0 if g["ground_node_present"] else 0.0
    # floating_nodes_low : on compare a la reference. Si gen <= ref, full
    # credit. Sinon decroissance bornee.
    nf = g["n_floating_nodes"]
    ref_nf = e["n_floating_nodes"]
    if nf <= max(ref_nf, 1):
        floating_low = 1.0
    else:
        budget = max(ref_nf + 2, 4)
        floating_low = max(0.0, 1.0 - (nf - ref_nf) / budget)

    composite = (
        parse_ok * 0.30
        + has_end * 0.20
        + component_count_match * 0.10
        + analysis_count_match * 0.10
        + ground_present * 0.15
        + floating_low * 0.15
    )

    return {
        "parse_ok": bool(g["parse_ok"]),
        "has_end": bool(g["has_end"]),
        "ground_node_present": bool(g["ground_node_present"]),
        "balanced": bool(g["balanced"]),
        "expected_n_components": e["n_components"],
        "generated_n_components": g["n_components"],
        "component_count_match": round(component_count_match, 4),
        "expected_n_analyses": e["n_analyses"],
        "generated_n_analyses": g["n_analyses"],
        "analysis_count_match": round(analysis_count_match, 4),
        "n_models": g["n_models"],
        "n_subckts": g["n_subckts"],
        "n_floating_nodes": g["n_floating_nodes"],
        "floating_nodes_low": round(floating_low, 4),
        "composite": round(composite, 4),
    }


SCORERS = {
    "kicad-dsl": score_dsl,
    "kicad-pcb": score_pcb,
    "spice-sim": score_spice,
}


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def aggregate(samples: list[dict[str, Any]], dataset: str) -> dict[str, Any]:
    n = len(samples)
    if n == 0:
        return {"n_samples": 0}
    scores = [s["scores"] for s in samples]
    parse_ok_rate = sum(1 for s in scores if s.get("parse_ok")) / n
    composite_score = sum(s.get("composite", 0.0) for s in scores) / n

    out: dict[str, Any] = {
        "n_samples": n,
        "parse_ok_rate": round(parse_ok_rate, 4),
        "composite_score": round(composite_score, 4),
    }
    if dataset == "kicad-dsl":
        out["fields_complete_rate"] = round(
            sum(1 for s in scores if s.get("fields_complete")) / n, 4)
        out["pin_count_match_rate"] = round(
            sum(1 for s in scores if s.get("pin_count_match")) / n, 4)
        out["fplist_balanced_rate"] = round(
            sum(1 for s in scores if s.get("fplist_balanced")) / n, 4)
    elif dataset == "kicad-pcb":
        out["structure_ok_rate"] = round(
            sum(1 for s in scores if s.get("layer_fcu") and s.get("has_fp_text")) / n, 4)
        out["pad_count_match_rate"] = round(
            sum(1 for s in scores if s.get("pad_count_match")) / n, 4)
        out["has_at_rate"] = round(
            sum(1 for s in scores if s.get("has_at_coords")) / n, 4)
    elif dataset == "spice-sim":
        out["has_end_rate"] = round(
            sum(1 for s in scores if s.get("has_end")) / n, 4)
        out["ground_present_rate"] = round(
            sum(1 for s in scores if s.get("ground_node_present")) / n, 4)
        out["balanced_rate"] = round(
            sum(1 for s in scores if s.get("balanced")) / n, 4)
        out["component_count_match_avg"] = round(
            sum(s.get("component_count_match", 0.0) for s in scores) / n, 4)
        out["analysis_count_match_avg"] = round(
            sum(s.get("analysis_count_match", 0.0) for s in scores) / n, 4)
        out["floating_nodes_low_avg"] = round(
            sum(s.get("floating_nodes_low", 0.0) for s in scores) / n, 4)
    return out


# --------------------------------------------------------------------------- #
# Generation (Python API mlx_lm)
# --------------------------------------------------------------------------- #


def _format_prompt(tokenizer, user_msg: str) -> str:
    """Construit un prompt chat-template si possible, sinon plain text."""
    try:
        msgs = [{"role": "user", "content": user_msg}]
        prompt = tokenizer.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True
        )
        return prompt
    except Exception:
        return user_msg


def generate_for_model(
    nick: str,
    hf_id: str,
    datasets: list[str],
    n_samples: int,
    max_tokens_override: int | None,
) -> dict[str, dict[str, Any]]:
    """Charge le modele UNE FOIS, genere n_samples par dataset, score."""
    log(f"  loading model {nick} ({hf_id}) ...")
    t0 = time.time()
    # Imports locaux : evite de payer mlx_lm.load au dry-run / aux modeles skip
    from mlx_lm import load as mlx_load
    from mlx_lm import generate as mlx_generate
    try:
        model, tokenizer = mlx_load(hf_id)
    except Exception as exc:
        log(f"  LOAD FAILED for {nick}: {exc!r}")
        return {ds: {"error": f"load_failed: {exc!r}", "n_samples": 0} for ds in datasets}
    log(f"  loaded in {time.time()-t0:.1f}s")

    out: dict[str, dict[str, Any]] = {}
    for ds in datasets:
        log(f"  -> generating {n_samples} samples on {ds}")
        max_tokens = max_tokens_override or GEN_PARAMS[ds]["max_tokens"]
        try:
            samples = load_samples(ds, n_samples)
        except FileNotFoundError as exc:
            log(f"  dataset missing: {exc}")
            out[ds] = {"error": f"dataset_missing: {exc}", "n_samples": 0}
            continue

        records: list[dict[str, Any]] = []
        for i, sample in enumerate(samples):
            prompt_text = _format_prompt(tokenizer, sample["prompt"])
            t_gen = time.time()
            try:
                generated = mlx_generate(
                    model,
                    tokenizer,
                    prompt=prompt_text,
                    max_tokens=max_tokens,
                    verbose=False,
                )
            except Exception as exc:
                log(f"     [{i+1}/{n_samples}] GEN ERROR: {exc!r}")
                generated = ""
            dt_gen = time.time() - t_gen

            scores = SCORERS[ds](generated, sample["expected"])
            records.append({
                "prompt": sample["prompt"][:300],
                "expected": sample["expected"][:600],
                "generated": generated[:2000],
                "scores": scores,
                "gen_time_s": round(dt_gen, 2),
            })
            if (i + 1) % 5 == 0 or i == n_samples - 1:
                log(f"     [{i+1}/{n_samples}] composite={scores.get('composite')} "
                    f"parse_ok={scores.get('parse_ok')} t={dt_gen:.1f}s")
        agg = aggregate(records, ds)
        agg["samples"] = records
        out[ds] = agg
        log(f"  {ds} done: composite={agg.get('composite_score')} "
            f"parse_ok_rate={agg.get('parse_ok_rate')}")

    # Free memory before next model
    del model
    del tokenizer
    gc.collect()
    try:
        import mlx.core as mx  # type: ignore
        mx.metal.clear_cache()
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Markdown output
# --------------------------------------------------------------------------- #


def write_markdown(results: dict) -> None:
    lines: list[str] = []
    lines.append("# KiCad + SPICE functional bench — Phase 1 (DSL + PCB + SPICE)")
    lines.append("")
    md = results["metadata"]
    lines.append(f"_Generated: {md['timestamp']}_")
    lines.append("")
    lines.append(f"- Datasets: {md['datasets']}")
    lines.append(f"- Samples / dataset: **{md['n_samples']}**")
    lines.append(f"- Models: {len(md['models'])}")
    lines.append("")
    for ds in md["datasets"]:
        lines.append(f"## Dataset: `{ds}`")
        lines.append("")
        lines.append("| Model | n | parse_ok | composite | extras |")
        lines.append("|---|---:|---:|---:|---|")
        for m in md["models"]:
            nick = m["nickname"]
            entry = results["bench"].get(nick, {}).get(ds, {})
            if "error" in entry:
                lines.append(f"| **{nick}** | 0 | — | — | {entry['error']} |")
                continue
            n = entry.get("n_samples", 0)
            if n == 0:
                lines.append(f"| **{nick}** | 0 | — | — | skipped |")
                continue
            extras_keys = [k for k in entry if k.endswith("_rate") and k != "parse_ok_rate"]
            extras = ", ".join(f"{k}={entry[k]}" for k in extras_keys)
            lines.append(
                f"| **{nick}** | {n} | {entry.get('parse_ok_rate', 0):.2f} | "
                f"{entry.get('composite_score', 0):.3f} | {extras} |"
            )
        lines.append("")
    lines.append("## Models tested")
    lines.append("")
    for m in md["models"]:
        lines.append(f"- **{m['nickname']}** — `{m['hf_id']}`")
    lines.append("")
    OUT_MD.write_text("\n".join(lines))
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad functional bench Phase 1")
    ap.add_argument("--models", nargs="*", default=None,
                    help="Subset de nicknames")
    ap.add_argument("--datasets", nargs="*", default=None,
                    help=f"Subset parmi {DATASETS}")
    ap.add_argument("--n-samples", type=int, default=DEFAULT_N_SAMPLES,
                    help=f"Samples par dataset (default {DEFAULT_N_SAMPLES})")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override max_tokens (default per-dataset)")
    ap.add_argument("--include-heavy", action="store_true",
                    help="Inclut granite-4.1-30b (par defaut skip — RAM)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Liste modeles + datasets sans charger ni generer")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    # Resolve datasets
    if args.datasets:
        datasets = [d for d in args.datasets if d in DATASETS]
        missing = sorted(set(args.datasets) - set(DATASETS))
        if missing:
            log(f"WARN: datasets ignores (inconnus): {missing}")
    else:
        datasets = list(DATASETS)

    # Resolve models
    if args.models:
        models = [(n, h) for n, h in MODELS if n in args.models]
        missing = sorted(set(args.models) - {n for n, _ in MODELS})
        if missing:
            log(f"WARN: modeles ignores (inconnus): {missing}")
    else:
        models = list(MODELS)
        if SKIP_HEAVY and not args.include_heavy:
            before = len(models)
            models = [(n, h) for n, h in models if n not in HEAVY_NICKS]
            if len(models) < before:
                log(f"WARN: skip heavy models {sorted(HEAVY_NICKS)} "
                    f"(KICAD_SKIP_HEAVY=1 ; --include-heavy pour forcer)")

    log("=" * 70)
    log("KICAD + SPICE FUNCTIONAL BENCH — PHASE 1")
    log(f"  Models   : {len(models)} -> {[n for n, _ in models]}")
    log(f"  Datasets : {datasets}")
    log(f"  Samples  : {args.n_samples} per dataset")
    log(f"  Output   : {OUT_JSON}")
    log(f"  Output   : {OUT_MD}")
    log(f"  Log      : {LOG_PATH}")
    eta_min = len(models) * len(datasets) * args.n_samples * 15 / 60
    log(f"  ETA      : ~{eta_min:.0f} min (15s/gen rough)")
    log("=" * 70)

    if args.dry_run:
        log("DRY-RUN — datasets sample shape:")
        for ds in datasets:
            try:
                rows = load_samples(ds, 1)
                log(f"  {ds}: prompt[:80]={rows[0]['prompt'][:80]!r}")
                log(f"  {ds}: expected_chars={len(rows[0]['expected'])}")
            except Exception as exc:
                log(f"  {ds}: ERROR {exc!r}")
        log("DRY-RUN: imports test...")
        try:
            import mlx_lm  # noqa: F401
            from mlx_lm import load, generate  # noqa: F401
            log("  mlx_lm imports OK")
        except Exception as exc:
            log(f"  mlx_lm import FAILED: {exc!r}")
            return 2
        log("DRY-RUN done.")
        return 0

    results: dict[str, Any] = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_dir": str(DATA_DIR),
            "n_samples": args.n_samples,
            "max_tokens_override": args.max_tokens,
            "gen_params": GEN_PARAMS,
            "models": [{"nickname": n, "hf_id": h} for n, h in models],
            "datasets": datasets,
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick, hf_id in models:
        log(f"\n############ MODEL: {nick} ({hf_id}) ############")
        try:
            per_ds = generate_for_model(
                nick, hf_id, datasets, args.n_samples, args.max_tokens
            )
        except Exception as exc:
            log(f"  MODEL CRASHED: {exc!r}")
            log(traceback.format_exc())
            per_ds = {ds: {"error": f"model_crash: {exc!r}", "n_samples": 0}
                      for ds in datasets}

        results["bench"][nick] = per_ds
        # incremental save
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD FUNCTIONAL BENCH PHASE 1 COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
