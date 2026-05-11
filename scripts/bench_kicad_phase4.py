#!/usr/bin/env python3
"""
Bench Phase 4 — ERC reel via kicad-cli sur les .kicad_sch generes en Phase 2.

Pour chaque (modele, sample) de ~/bench-results/kicad_phase2.json :
  1. Recupere le contenu `generated` (peut etre tronque a 3000 chars en Phase 2).
  2. Decode tout markdown fence (```...```), ecrit dans /tmp/kicad_phase4_<m>_<s>.kicad_sch.
  3. Lance `kicad-cli sch erc <file> --format json --severity-all
                                  --output <report.json>` (timeout 30s).
  4. Parse le rapport JSON :
       - errors_count, warnings_count
       - violations_by_type (dict type -> count)
       - parse_ok = True si rapport genere (rc==0).
     Si kicad-cli echoue (rc!=0) -> fallback parser pure-Python (balanced_parens
     + extract_components) pour parse_ok ; errors/warnings = N/A (mis a None).
  5. Score composite :
       parse_ok        (0.30)  : 1.0 si rapport JSON ERC genere, sinon
                                 0.5 si parser pure-Python OK, sinon 0.
       erc_no_errors   (0.40)  : si parse_ok via kicad-cli :
                                   1.0 si 0 errors, sinon max(0, 1 - errors/10).
                                 Sinon : 0 (no kicad-cli report).
       erc_low_warns   (0.30)  : si parse_ok via kicad-cli :
                                   max(0, 1 - warnings/20).
                                 Sinon : 0.

Sortie :
  ~/bench-results/kicad_phase4.{json,md}
  Save incremental apres chaque modele.

Usage :
  python3 ~/scripts/bench_kicad_phase4.py
  python3 ~/scripts/bench_kicad_phase4.py --models gemma-e2b
  python3 ~/scripts/bench_kicad_phase4.py --dry-run
  python3 ~/scripts/bench_kicad_phase4.py --phase2 /path/to/kicad_phase2.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from kicad_sch_parser import balanced_parens, extract_components, extract_labels  # noqa: E402

# --------------------------------------------------------------------------- #

HOME = Path.home()
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
LOG_DIR = HOME / "logs"

PHASE2_JSON = BENCH_DIR / "kicad_phase2.json"
OUT_JSON = BENCH_DIR / "kicad_phase4.json"
OUT_MD = BENCH_DIR / "kicad_phase4.md"

KICAD_CLI = os.environ.get("KICAD_CLI", "/opt/homebrew/bin/kicad-cli")
ERC_TIMEOUT_S = int(os.environ.get("KICAD_ERC_TIMEOUT", "30"))

# Plafonds pour le scoring (cf. mission)
ERR_CAP = 10
WARN_CAP = 20

# --------------------------------------------------------------------------- #

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_phase4-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
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
# Utilitaires
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(
    r"```(?:lisp|scheme|kicad|sexp|sch|kicad_sch)?\s*\n(.*?)```",
    re.S | re.I,
)


def _strip_md_fence(text: str) -> str:
    m = _FENCE_RE.search(text)
    return m.group(1) if m else text


def _safe_token(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:60] or "x"


# --------------------------------------------------------------------------- #
# kicad-cli ERC runner
# --------------------------------------------------------------------------- #


def run_erc(sch_text: str, model_nick: str, sample_id: str) -> dict[str, Any]:
    """Ecrit `sch_text` dans /tmp et lance kicad-cli ERC. Retourne :
       {parse_ok, parse_via, errors_count, warnings_count, violations_by_type,
        rc, stderr, report_path}.
    Si kicad-cli plante -> fallback pure-Python pour parse_ok partiel.
    """
    safe_m = _safe_token(model_nick)
    safe_s = _safe_token(sample_id)
    sch_path = Path(tempfile.gettempdir()) / f"kicad_phase4_{safe_m}_{safe_s}.kicad_sch"
    rpt_path = Path(tempfile.gettempdir()) / f"kicad_phase4_{safe_m}_{safe_s}.erc.json"

    # nettoie d'eventuels artefacts d'une run precedente
    for p in (sch_path, rpt_path):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    try:
        sch_path.write_text(sch_text, encoding="utf-8")
    except Exception as exc:
        return {
            "parse_ok": 0.0,
            "parse_via": "write_failed",
            "errors_count": None,
            "warnings_count": None,
            "violations_by_type": {},
            "rc": -1,
            "stderr": f"write: {exc!r}",
            "report_path": None,
        }

    cmd = [
        KICAD_CLI, "sch", "erc", str(sch_path),
        "--format", "json",
        "--severity-all",
        "--output", str(rpt_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=ERC_TIMEOUT_S,
            check=False,
        )
        rc = proc.returncode
        stderr = proc.stderr.decode("utf-8", errors="replace")[:500]
    except subprocess.TimeoutExpired:
        rc = -2
        stderr = f"timeout>{ERC_TIMEOUT_S}s"
    except FileNotFoundError as exc:
        rc = -3
        stderr = f"kicad-cli not found: {exc!r}"
    except Exception as exc:
        rc = -4
        stderr = f"subprocess: {exc!r}"

    # Cas nominal : rapport JSON ecrit
    if rc == 0 and rpt_path.exists():
        try:
            with rpt_path.open("r", encoding="utf-8") as f:
                rep = json.load(f)
        except Exception as exc:
            rep = None
            stderr = (stderr + f" | json_parse: {exc!r}")[:500]
        if rep is not None:
            errs = 0
            warns = 0
            by_type: Counter[str] = Counter()
            for sheet in rep.get("sheets", []):
                for v in sheet.get("violations", []):
                    sev = v.get("severity", "")
                    typ = v.get("type", "?")
                    by_type[typ] += 1
                    if sev == "error":
                        errs += 1
                    elif sev == "warning":
                        warns += 1
            return {
                "parse_ok": 1.0,
                "parse_via": "kicad-cli",
                "errors_count": errs,
                "warnings_count": warns,
                "violations_by_type": dict(by_type.most_common()),
                "rc": rc,
                "stderr": stderr,
                "report_path": str(rpt_path),
            }

    # Fallback : parser pure-Python pour parse_ok partiel
    try:
        comps = extract_components(sch_text)
        labs = extract_labels(sch_text)
        balanced = balanced_parens(sch_text)
        starts_ok = sch_text.lstrip().startswith("(kicad_sch")
        # on accorde 0.5 si la structure haut-niveau est plausible
        py_ok = balanced and starts_ok and (len(comps) >= 1 or len(labs) >= 1)
    except Exception:
        py_ok = False

    return {
        "parse_ok": 0.5 if py_ok else 0.0,
        "parse_via": "py_fallback" if py_ok else "failed",
        "errors_count": None,
        "warnings_count": None,
        "violations_by_type": {},
        "rc": rc,
        "stderr": stderr,
        "report_path": None,
    }


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def composite_score(erc: dict[str, Any]) -> dict[str, float]:
    parse_ok = float(erc.get("parse_ok", 0.0))
    errs = erc.get("errors_count")
    warns = erc.get("warnings_count")

    if erc.get("parse_via") == "kicad-cli" and errs is not None and warns is not None:
        no_err = 1.0 if errs == 0 else max(0.0, 1.0 - errs / float(ERR_CAP))
        low_w = max(0.0, 1.0 - warns / float(WARN_CAP))
    else:
        no_err = 0.0
        low_w = 0.0

    composite = 0.30 * parse_ok + 0.40 * no_err + 0.30 * low_w
    return {
        "parse_ok_score": round(parse_ok, 4),
        "erc_no_errors": round(no_err, 4),
        "erc_low_warnings": round(low_w, 4),
        "composite": round(composite, 4),
    }


def aggregate(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"n_samples": 0}
    parse_ok_full = sum(1 for r in records if r["erc"]["parse_via"] == "kicad-cli")
    parse_ok_any = sum(1 for r in records if r["erc"]["parse_ok"] > 0)
    errs = [r["erc"]["errors_count"] for r in records if r["erc"]["errors_count"] is not None]
    warns = [r["erc"]["warnings_count"] for r in records if r["erc"]["warnings_count"] is not None]
    composites = [r["scores"]["composite"] for r in records]
    return {
        "n_samples": n,
        "parse_ok_kicad_rate": round(parse_ok_full / n, 4),
        "parse_ok_any_rate": round(parse_ok_any / n, 4),
        "avg_errors": round(sum(errs) / len(errs), 2) if errs else None,
        "avg_warnings": round(sum(warns) / len(warns), 2) if warns else None,
        "max_errors": max(errs) if errs else None,
        "max_warnings": max(warns) if warns else None,
        "composite_avg": round(sum(composites) / n, 4),
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def load_phase2(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open() as f:
        return json.load(f)


def run_for_model(nick: str, model_block: dict) -> dict:
    samples = model_block.get("samples", [])
    log(f"  {nick}: {len(samples)} samples to evaluate")
    records = []
    for i, s in enumerate(samples):
        sid = s.get("id", f"sample_{i}")
        gen = s.get("generated", "") or ""
        gen_chars = s.get("generated_chars", len(gen))
        sch_text = _strip_md_fence(gen)
        if not sch_text.strip():
            erc = {
                "parse_ok": 0.0, "parse_via": "empty",
                "errors_count": None, "warnings_count": None,
                "violations_by_type": {}, "rc": 0, "stderr": "empty",
                "report_path": None,
            }
        else:
            erc = run_erc(sch_text, nick, sid)
        scores = composite_score(erc)
        # On ne stocke pas le sch complet (deja dans phase2.json),
        # juste les violations resumees + composite.
        records.append({
            "id": sid,
            "source": s.get("source", ""),
            "prompt": s.get("prompt", "")[:200],
            "generated_chars_phase2": gen_chars,
            "generated_truncated_in_phase2": gen_chars > len(gen),
            "erc": {
                "parse_ok": erc["parse_ok"],
                "parse_via": erc["parse_via"],
                "errors_count": erc["errors_count"],
                "warnings_count": erc["warnings_count"],
                "violations_by_type": erc["violations_by_type"],
                "rc": erc["rc"],
                "stderr": erc["stderr"][:200] if erc.get("stderr") else "",
            },
            "scores": scores,
        })
        log(f"     [{i+1}/{len(samples)}] {sid} via={erc['parse_via']} "
            f"errs={erc['errors_count']} warns={erc['warnings_count']} "
            f"composite={scores['composite']}")
    agg = aggregate(records)
    agg["samples"] = records
    return agg


def write_markdown(results: dict) -> None:
    md = results["metadata"]
    lines = [
        "# KiCad Phase 4 bench — ERC reel via kicad-cli",
        "",
        f"_Generated: {md['timestamp']}_",
        "",
        f"- KiCad CLI    : `{md['kicad_cli']}` (v{md.get('kicad_version','?')})",
        f"- Phase 2 src  : `{md['phase2_path']}`",
        f"- Models       : {len(md['models'])}",
        f"- Timeout ERC  : {md['erc_timeout_s']}s",
        f"- Score weights: parse_ok 0.30 + erc_no_errors 0.40 + erc_low_warnings 0.30",
        "",
        "| Model | n | parse_ok_cli | avg_err | avg_warn | composite |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for nick in md["models"]:
        e = results["bench"].get(nick, {})
        if "error" in e:
            lines.append(f"| **{nick}** | 0 | — | — | — | err: {e['error'][:40]} |")
            continue
        n = e.get("n_samples", 0)
        if n == 0:
            lines.append(f"| **{nick}** | 0 | — | — | — | skipped |")
            continue
        avg_e = e.get("avg_errors")
        avg_w = e.get("avg_warnings")
        lines.append(
            f"| **{nick}** | {n} | "
            f"{e.get('parse_ok_kicad_rate', 0):.2f} | "
            f"{(avg_e if avg_e is not None else 0):.2f} | "
            f"{(avg_w if avg_w is not None else 0):.2f} | "
            f"{e.get('composite_avg', 0):.3f} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n")
    log(f"Markdown saved to {OUT_MD}")


def detect_kicad_version() -> str:
    try:
        proc = subprocess.run(
            [KICAD_CLI, "version"], capture_output=True, timeout=10, check=False,
        )
        return proc.stdout.decode().strip().splitlines()[0] if proc.stdout else "?"
    except Exception:
        return "?"


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad Phase 4 — ERC bench")
    ap.add_argument("--phase2", type=Path, default=PHASE2_JSON,
                    help=f"Path to kicad_phase2.json (default: {PHASE2_JSON})")
    ap.add_argument("--models", nargs="*", default=None,
                    help="Subset of model nicknames to score")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=None)
    args = ap.parse_args()

    global ERC_TIMEOUT_S
    if args.timeout is not None:
        ERC_TIMEOUT_S = args.timeout

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 70)
    log("KICAD PHASE 4 BENCH — ERC reel via kicad-cli")
    log(f"  KICAD_CLI : {KICAD_CLI} (v{detect_kicad_version()})")
    log(f"  Phase 2   : {args.phase2}")
    log(f"  Output    : {OUT_JSON}")
    log(f"  Output    : {OUT_MD}")
    log(f"  Log       : {LOG_PATH}")
    log(f"  Timeout   : {ERC_TIMEOUT_S}s/sample")
    log("=" * 70)

    # --- dry-run : tolere phase2.json absent (Phase 2 pas encore finie) ---
    if args.dry_run:
        log("DRY-RUN — checking environment...")
        if not Path(KICAD_CLI).exists():
            log(f"  WARN: kicad-cli not found at {KICAD_CLI}")
        else:
            log(f"  OK : kicad-cli at {KICAD_CLI} (v{detect_kicad_version()})")
        ref = HOME / "eu-kiki-data" / "kicad-sch-refs" / "spi_bus_4devices.kicad_sch"
        if ref.exists():
            log(f"  testing ERC on reference {ref.name} ...")
            txt = ref.read_text()
            erc = run_erc(txt, "dryrun", "spi_bus_4devices")
            sc = composite_score(erc)
            log(f"  result: via={erc['parse_via']} errs={erc['errors_count']} "
                f"warns={erc['warnings_count']} composite={sc['composite']}")
            tops = list(erc["violations_by_type"].items())[:5]
            log(f"  top violation types: {tops}")
        if not args.phase2.exists():
            log(f"  WARN: phase2 source absent yet: {args.phase2}")
            log("  -> Phase 4 ready ; will run once Phase 2 produces this file.")
            log("DRY-RUN done.")
            return 0
        # Si phase2 existe deja en dry-run, on n'evalue pas, on resume.
        try:
            ph2 = load_phase2(args.phase2)
            for nick, blk in ph2.get("bench", {}).items():
                n = blk.get("n_samples", 0)
                log(f"  phase2 model {nick}: n_samples={n}")
        except Exception as exc:
            log(f"  WARN: cannot read phase2: {exc!r}")
        log("DRY-RUN done.")
        return 0

    # --- run reel ---
    try:
        ph2 = load_phase2(args.phase2)
    except FileNotFoundError:
        log(f"FATAL: phase2 source not found: {args.phase2}")
        return 2
    except Exception as exc:
        log(f"FATAL: cannot load phase2: {exc!r}")
        return 2

    bench_in = ph2.get("bench", {}) or {}
    if not bench_in:
        log("FATAL: phase2.bench is empty — nothing to evaluate")
        return 3

    if args.models:
        wanted = set(args.models)
        models_order = [n for n in bench_in if n in wanted]
        miss = sorted(wanted - set(bench_in))
        if miss:
            log(f"WARN: unknown models in phase2: {miss}")
    else:
        models_order = list(bench_in.keys())

    results = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kicad_cli": KICAD_CLI,
            "kicad_version": detect_kicad_version(),
            "phase2_path": str(args.phase2),
            "phase2_metadata": ph2.get("metadata", {}),
            "erc_timeout_s": ERC_TIMEOUT_S,
            "score_weights": {
                "parse_ok": 0.30,
                "erc_no_errors": 0.40,
                "erc_low_warnings": 0.30,
                "err_cap": ERR_CAP,
                "warn_cap": WARN_CAP,
            },
            "models": models_order,
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick in models_order:
        log(f"\n############ MODEL: {nick} ############")
        blk = bench_in.get(nick, {}) or {}
        if "error" in blk:
            log(f"  Phase 2 had error for {nick}: {blk['error']!r} — skipping ERC")
            results["bench"][nick] = {"error": blk["error"], "n_samples": 0}
            OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
            continue
        try:
            per = run_for_model(nick, blk)
        except Exception as exc:
            log(f"  MODEL ERC CRASHED: {exc!r}")
            log(traceback.format_exc())
            per = {"error": f"erc_crash: {exc!r}", "n_samples": 0}
        results["bench"][nick] = per
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD PHASE 4 BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
