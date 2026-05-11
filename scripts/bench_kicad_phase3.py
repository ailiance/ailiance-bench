#!/usr/bin/env python3
"""
Bench Phase 3 — extraction inverse .kicad_sch -> JSON {components, nets}.

Le modele recoit un .kicad_sch + une instruction "extract components & nets,
output JSON" et doit produire :
  {"components": [{"ref","value","footprint"}, ...],
   "nets":       [{"name","pins": ["REF.PIN", ...]}, ...]}

Validation :
  1. JSON parsable (binaire)
  2. F1 sur composants (refs : recall + precision)
  3. F1 sur nets (label names : recall + precision)
  4. (info) F1 sur values composants si renseignes

Score composite :
  json_ok (0.20)  + components_f1 (0.40) + nets_f1 (0.40)

Sortie :
  ~/bench-results/kicad_phase3.{json,md}
  Save incremental.

Usage :
  python3 ~/scripts/bench_kicad_phase3.py
  python3 ~/scripts/bench_kicad_phase3.py --models gemma-e2b
  python3 ~/scripts/bench_kicad_phase3.py --dry-run
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

HOME = Path.home()
DATA_PATH = Path(os.environ.get(
    "KICAD_SCH_EXT_PATH",
    HOME / "ailiance-data" / "kicad-sch-extract" / "valid.jsonl",
))
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
LOG_DIR = HOME / "logs"

OUT_JSON = BENCH_DIR / "kicad_phase3.json"
OUT_MD = BENCH_DIR / "kicad_phase3.md"

SKIP_HEAVY = os.environ.get("KICAD_SKIP_HEAVY", "1") == "1"
HEAVY_NICKS = {"granite-4.1-30b"}

MODELS: list[tuple[str, str]] = [
    ("gemma-e4b-ailiance-base",   "lmstudio-community/gemma-4-E4B-it-MLX-4bit"),
    ("gemma-e2b",                "lmstudio-community/gemma-4-E2B-it-MLX-4bit"),
    ("ministral-3b",             "mlx-community/Ministral-3-3B-Instruct-2512-4bit"),
    ("ministral-3-8b",           "mlx-community/Ministral-3-8B-Instruct-2512-4bit"),
    ("ministral-3-14b-instruct", "mlx-community/Ministral-3-14B-Instruct-2512-4bit"),
    ("ministral-3-14b-reasoning","mlx-community/Ministral-3-14B-Reasoning-2512-4bit"),
    ("granite-4.1-3b",           "mlx-community/granite-4.1-3b-4bit"),
    ("granite-4.1-30b",          "mlx-community/granite-4.1-30b-4bit"),
]

# 2048 = ~ 8 KB d'output JSON, suffit largement sauf grosse esp32_mini ;
# spi_bus reste lourd cote prompt mais l'output JSON est borne, ok 2048.
DEFAULT_MAX_TOKENS = 2048

# --------------------------------------------------------------------------- #

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_phase3-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
_log_fh = None


def log(msg: str) -> None:
    global _log_fh
    if _log_fh is None:
        _log_fh = LOG_PATH.open("a", buffering=1)
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #


# --- pin enrichment ---------------------------------------------------------
# When the ground_truth_json in valid.jsonl lacks per-net pin lists (e.g. for
# realistic schematics like spi_bus), we try to enrich GT by re-parsing the
# .kicad_sch embedded in the user prompt with our pure-Python parser
# (kicad_sch_parser.parse_sch). We only fill in `pins` for nets that are
# currently empty — never overwrite hand-curated values.

try:
    sys.path.insert(0, str(HOME / "scripts"))
    from kicad_sch_parser import parse_sch as _parse_sch  # noqa: E402
except Exception as _exc:
    _parse_sch = None  # graceful fallback


def _extract_sch_from_prompt(prompt: str) -> str:
    """Best-effort extract the (kicad_sch ...) S-expression from the prompt."""
    if not prompt:
        return ""
    i = prompt.find("(kicad_sch")
    if i < 0:
        return ""
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(prompt)):
        ch = prompt[j]
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
                return prompt[i:j + 1]
    return ""


def _enrich_gt_with_pins(gt: dict, prompt: str) -> dict:
    """If GT has nets with empty `pins`, try to fill them from parse_sch(prompt_sch)."""
    if _parse_sch is None or not gt:
        return gt
    nets = gt.get("nets") or []
    if not nets:
        return gt
    needs = any(not (n.get("pins") or []) for n in nets if isinstance(n, dict))
    if not needs:
        return gt
    sch = _extract_sch_from_prompt(prompt)
    if not sch:
        return gt
    try:
        parsed = _parse_sch(sch)
    except Exception:
        return gt
    parsed_pins = {n["name"]: n.get("pins") or [] for n in parsed.get("nets", [])}
    enriched_nets = []
    for n in nets:
        if not isinstance(n, dict):
            enriched_nets.append(n)
            continue
        if not (n.get("pins") or []):
            extra = parsed_pins.get(n.get("name"), [])
            if extra:
                n = dict(n)
                n["pins"] = list(extra)
        enriched_nets.append(n)
    out = dict(gt)
    out["nets"] = enriched_nets
    return out


def load_samples() -> list[dict]:
    rows = []
    if not DATA_PATH.exists():
        raise FileNotFoundError(DATA_PATH)
    with DATA_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            msgs = d.get("messages", [])
            user = next((m["content"] for m in msgs if m.get("role") == "user"), None)
            asst = next((m["content"] for m in msgs if m.get("role") == "assistant"), None)
            gt = d.get("ground_truth_json")
            if user is None or asst is None or gt is None:
                continue
            gt = _enrich_gt_with_pins(gt, user)
            rows.append({
                "id": d.get("_id", ""),
                "source": d.get("_source", ""),
                "prompt": user,
                "expected": asst,
                "ground_truth": gt,
            })
    return rows


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.S | re.I)


def _strip_md(text: str) -> str:
    m = _JSON_FENCE_RE.search(text)
    return m.group(1) if m else text


def _try_parse_json(text: str) -> Any:
    src = _strip_md(text).strip()
    # Best-effort : trouver le 1er { equilibre
    if not src.startswith("{"):
        i = src.find("{")
        if i == -1:
            return None
        src = src[i:]
    # Strip trailing junk apres derniere accolade balanced
    depth = 0
    in_str = False
    esc = False
    end = None
    for j, ch in enumerate(src):
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
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is not None:
        src = src[:end]
    try:
        return json.loads(src)
    except Exception:
        return None


def _f1(true_set: set, pred_set: set) -> dict:
    tp = len(true_set & pred_set)
    fp = len(pred_set - true_set)
    fn = len(true_set - pred_set)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
    }


def _net_pins_map(nets_list) -> dict[str, frozenset]:
    """Build {net_name: frozenset(pins)} for pin-level F1 scoring."""
    out: dict[str, set] = {}
    for n in nets_list or []:
        if not isinstance(n, dict):
            continue
        name = n.get("name")
        if not name:
            continue
        pins = [p for p in (n.get("pins") or []) if isinstance(p, str)]
        out.setdefault(name, set()).update(pins)
    return {k: frozenset(v) for k, v in out.items()}


def _pins_pair_set(net_pins_map: dict[str, frozenset]) -> set:
    """Convert {net: pins} to a set of (net, pin) tuples for set-F1."""
    return {(name, pin) for name, pins in net_pins_map.items() for pin in pins}


def score_extract(generated: str, gt: dict) -> dict:
    parsed = _try_parse_json(generated)
    json_ok = isinstance(parsed, dict) and "components" in parsed and "nets" in parsed

    gt_refs = {c["ref"] for c in gt.get("components", []) if isinstance(c, dict) and "ref" in c}
    gt_nets = {n["name"] for n in gt.get("nets", []) if isinstance(n, dict) and "name" in n}
    gt_net_pins = _net_pins_map(gt.get("nets", []))
    gt_has_pins = any(len(v) > 0 for v in gt_net_pins.values())

    if json_ok:
        try:
            pred_refs = {
                c.get("ref", "") for c in parsed.get("components", [])
                if isinstance(c, dict) and c.get("ref")
            }
        except Exception:
            pred_refs = set()
        try:
            pred_nets = {
                n.get("name", "") for n in parsed.get("nets", [])
                if isinstance(n, dict) and n.get("name")
            }
        except Exception:
            pred_nets = set()
        try:
            pred_net_pins = _net_pins_map(parsed.get("nets", []))
        except Exception:
            pred_net_pins = {}
    else:
        pred_refs = set()
        pred_nets = set()
        pred_net_pins = {}

    comp_f1 = _f1(gt_refs, pred_refs)
    net_name_f1 = _f1(gt_nets, pred_nets)

    # Pin-level F1 over (net, pin) pairs. Backward-compat: when GT has no pins
    # at all for any net (legacy-name-only sample), pin F1 is N/A → reuse the
    # net-name F1 score so the composite degrades gracefully to the previous
    # scheme rather than dropping to zero.
    pred_has_pins = any(len(v) > 0 for v in pred_net_pins.values())
    if gt_has_pins:
        net_pins_f1 = _f1(_pins_pair_set(gt_net_pins), _pins_pair_set(pred_net_pins))
    else:
        # Degrade gracefully — pin grading not possible
        net_pins_f1 = dict(net_name_f1)
        net_pins_f1["note"] = "fallback_to_name_f1"

    # New composite : json_ok 0.15 + comp 0.35 + net_name 0.20 + net_pins 0.30
    composite = (
        (1.0 if json_ok else 0.0) * 0.15
        + comp_f1["f1"] * 0.35
        + net_name_f1["f1"] * 0.20
        + net_pins_f1["f1"] * 0.30
    )

    return {
        "json_ok": json_ok,
        "expected_n_components": len(gt_refs),
        "predicted_n_components": len(pred_refs),
        "components": comp_f1,
        "expected_n_nets": len(gt_nets),
        "predicted_n_nets": len(pred_nets),
        "nets": net_name_f1,           # legacy key -> NOW means net-NAMES F1
        "net_pins": net_pins_f1,       # NEW key -> per-pin F1
        "gt_has_pins": gt_has_pins,
        "pred_has_pins": pred_has_pins,
        "composite": round(composite, 4),
    }


def aggregate(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"n_samples": 0}
    sc = [r["scores"] for r in records]
    return {
        "n_samples": n,
        "json_ok_rate": round(sum(1 for s in sc if s["json_ok"]) / n, 4),
        "components_f1_avg": round(sum(s["components"]["f1"] for s in sc) / n, 4),
        "components_recall_avg": round(sum(s["components"]["recall"] for s in sc) / n, 4),
        "components_precision_avg": round(sum(s["components"]["precision"] for s in sc) / n, 4),
        "nets_f1_avg": round(sum(s["nets"]["f1"] for s in sc) / n, 4),
        "nets_recall_avg": round(sum(s["nets"]["recall"] for s in sc) / n, 4),
        "nets_precision_avg": round(sum(s["nets"]["precision"] for s in sc) / n, 4),
        "net_pins_f1_avg": round(sum(s.get("net_pins", {}).get("f1", 0.0) for s in sc) / n, 4),
        "net_pins_recall_avg": round(sum(s.get("net_pins", {}).get("recall", 0.0) for s in sc) / n, 4),
        "composite_score": round(sum(s["composite"] for s in sc) / n, 4),
    }


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


def _format_prompt(tokenizer, user_msg: str) -> str:
    try:
        return tokenizer.apply_chat_template(
            [{"role": "user", "content": user_msg}],
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        return user_msg


def generate_for_model(nick: str, hf_id: str, samples: list[dict],
                       max_tokens: int) -> dict:
    log(f"  loading {nick} ({hf_id}) ...")
    t0 = time.time()
    from mlx_lm import load as mlx_load
    from mlx_lm import generate as mlx_generate
    try:
        model, tokenizer = mlx_load(hf_id)
    except Exception as exc:
        log(f"  LOAD FAILED for {nick}: {exc!r}")
        return {"error": f"load_failed: {exc!r}", "n_samples": 0}
    log(f"  loaded in {time.time()-t0:.1f}s")

    records = []
    for i, sample in enumerate(samples):
        sid = sample["id"]
        prompt_text = _format_prompt(tokenizer, sample["prompt"])
        t_g = time.time()
        try:
            generated = mlx_generate(
                model, tokenizer,
                prompt=prompt_text,
                max_tokens=max_tokens,
                verbose=False,
            )
        except Exception as exc:
            log(f"     [{i+1}/{len(samples)}] GEN ERROR ({sid}): {exc!r}")
            generated = ""
        dt_g = time.time() - t_g
        scores = score_extract(generated, sample["ground_truth"])
        records.append({
            "id": sid,
            "source": sample["source"],
            "expected_chars": len(sample["expected"]),
            "generated_chars": len(generated),
            "generated": generated[:2500],
            "scores": scores,
            "gen_time_s": round(dt_g, 2),
        })
        log(f"     [{i+1}/{len(samples)}] {sid} composite={scores['composite']} "
            f"json_ok={scores['json_ok']} compF1={scores['components']['f1']} "
            f"netNameF1={scores['nets']['f1']} netPinsF1={scores.get('net_pins',{}).get('f1',0)} "
            f"t={dt_g:.1f}s")

    agg = aggregate(records)
    agg["samples"] = records

    del model
    del tokenizer
    gc.collect()
    try:
        import mlx.core as mx  # type: ignore
        mx.metal.clear_cache()
    except Exception:
        pass
    return agg


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #


def write_markdown(results: dict) -> None:
    md = results["metadata"]
    lines = [
        "# KiCad Phase 3 bench — sch -> JSON extraction",
        "",
        f"_Generated: {md['timestamp']}_",
        "",
        f"- Dataset    : `{md['data_path']}` ({md['n_samples']} samples)",
        f"- Models     : {len(md['models'])}",
        f"- Max tokens : {md['max_tokens']}",
        "",
        "| Model | n | json_ok | comp_F1 | comp_recall | netname_F1 | netpins_F1 | netpins_recall | composite |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in md["models"]:
        nick = m["nickname"]
        e = results["bench"].get(nick, {})
        if "error" in e:
            lines.append(f"| **{nick}** | 0 | — | — | — | — | — | — | err: {e['error'][:30]} |")
            continue
        n = e.get("n_samples", 0)
        if n == 0:
            lines.append(f"| **{nick}** | 0 | — | — | — | — | — | — | skipped |")
            continue
        lines.append(
            f"| **{nick}** | {n} | "
            f"{e.get('json_ok_rate', 0):.2f} | "
            f"{e.get('components_f1_avg', 0):.2f} | "
            f"{e.get('components_recall_avg', 0):.2f} | "
            f"{e.get('nets_f1_avg', 0):.2f} | "
            f"{e.get('net_pins_f1_avg', 0):.2f} | "
            f"{e.get('net_pins_recall_avg', 0):.2f} | "
            f"{e.get('composite_score', 0):.3f} |"
        )
    lines += ["", "## Models tested", ""]
    for m in md["models"]:
        lines.append(f"- **{m['nickname']}** — `{m['hf_id']}`")
    OUT_MD.write_text("\n".join(lines) + "\n")
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad Phase 3 — sch->JSON extraction bench")
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--include-heavy", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    samples = load_samples()
    n_samples = len(samples)

    if args.models:
        models = [(n, h) for n, h in MODELS if n in args.models]
        miss = sorted(set(args.models) - {n for n, _ in MODELS})
        if miss:
            log(f"WARN: unknown models: {miss}")
    else:
        models = list(MODELS)
        if SKIP_HEAVY and not args.include_heavy:
            before = len(models)
            models = [(n, h) for n, h in models if n not in HEAVY_NICKS]
            if len(models) < before:
                log(f"WARN: skipping heavy {sorted(HEAVY_NICKS)}")

    log("=" * 70)
    log("KICAD PHASE 3 BENCH — sch -> JSON extraction")
    log(f"  Models    : {len(models)} -> {[n for n, _ in models]}")
    log(f"  Samples   : {n_samples}")
    log(f"  MaxTokens : {args.max_tokens}")
    log(f"  Output    : {OUT_JSON}")
    log(f"  Output    : {OUT_MD}")
    log(f"  Log       : {LOG_PATH}")
    eta_min = len(models) * n_samples * 30 / 60
    log(f"  ETA       : ~{eta_min:.0f} min")
    log("=" * 70)

    if args.dry_run:
        log("DRY-RUN — sample shapes:")
        for s in samples:
            log(f"  {s['id']}: prompt_chars={len(s['prompt'])} "
                f"gt_components={len(s['ground_truth'].get('components', []))} "
                f"gt_nets={len(s['ground_truth'].get('nets', []))}")
        log("DRY-RUN — running scorer on expected (sanity):")
        for s in samples:
            sc = score_extract(s["expected"], s["ground_truth"])
            log(f"  {s['id']}: composite={sc['composite']} json_ok={sc['json_ok']} "
                f"compF1={sc['components']['f1']} netNameF1={sc['nets']['f1']} "
                f"netPinsF1={sc.get('net_pins',{}).get('f1',0)} "
                f"gt_has_pins={sc.get('gt_has_pins')} pred_has_pins={sc.get('pred_has_pins')}")
        try:
            import mlx_lm  # noqa: F401
            log("  mlx_lm import OK")
        except Exception as exc:
            log(f"  mlx_lm import FAILED: {exc!r}")
        log("DRY-RUN done.")
        return 0

    results = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_path": str(DATA_PATH),
            "n_samples": n_samples,
            "max_tokens": args.max_tokens,
            "models": [{"nickname": n, "hf_id": h} for n, h in models],
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick, hf_id in models:
        log(f"\n############ MODEL: {nick} ({hf_id}) ############")
        try:
            per = generate_for_model(nick, hf_id, samples, args.max_tokens)
        except Exception as exc:
            log(f"  MODEL CRASHED: {exc!r}")
            log(traceback.format_exc())
            per = {"error": f"model_crash: {exc!r}", "n_samples": 0}
        results["bench"][nick] = per
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD PHASE 3 BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
