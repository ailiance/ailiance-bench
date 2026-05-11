#!/usr/bin/env python3
"""
Phase 7 — KiCad LoRA bench via mlx_lm.server HTTP (chat-completions).

Reuse les mlx_lm.server deja chauds (eu-kiki, mascarade, kicad9plus, kicad-sch-v3, ...)
au lieu de re-loader le modele/adapter en subprocess a chaque combo.

Avantages vs subprocess Phase 2/3 :
  - Plus de load 30-60s par combo : les modeles sont deja en RAM
  - Parallelisable cross-machine (macM1 + Studio via SSH tunnel)
  - 1 ThreadPoolExecutor lance N (LoRA x prompt) en concurrent
  - Reutilise score_sch / parse_summary / load_samples (DRY)

Usage :
  python3 ~/scripts/bench_kicad_via_server.py                       # full LORA_SERVERS x dataset
  python3 ~/scripts/bench_kicad_via_server.py --servers eu-kiki mascarade
  python3 ~/scripts/bench_kicad_via_server.py --limit 1             # POC : 1 sample
  python3 ~/scripts/bench_kicad_via_server.py --discover            # auto-discover seulement
  python3 ~/scripts/bench_kicad_via_server.py --dry-run             # liste servers/samples

Configuration manuelle des LoRA servers : editer LORA_SERVERS ci-dessous.
Auto-discovery (option --discover) scan les ports 8500-8550 (macM1)
et 19300-19400 (tunnel SSH vers Studio, voir docs/phase7_http_bench.md).

SSH tunnel Studio (a lancer MANUELLEMENT cote user, pas par ce script) :
  ssh -fN -L 19301:localhost:9301 -L 19305:localhost:9305 \\
         -L 19316:localhost:9316 -L 19334:localhost:9334 studio
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import socket
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Reuse scoring/dataset utilities from existing Phase 2 base
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bench_kicad_phase2 import (  # noqa: E402
    BENCH_DIR,
    DEFAULT_MAX_TOKENS,
    SPI_BUS_ID,
    aggregate,
    load_samples,
    score_sch,
)

HOME = Path.home()
OUT_JSON = BENCH_DIR / "kicad_phase7_http.json"
OUT_MD = BENCH_DIR / "kicad_phase7_http.md"
LOG_DIR = HOME / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_phase7_http-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

_log_fh = None


def log(msg: str) -> None:
    global _log_fh
    if _log_fh is None:
        _log_fh = LOG_PATH.open("a", buffering=1)
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    _log_fh.write(line + "\n")


# --------------------------------------------------------------------------- #
# Static LoRA -> server map. Edit here to add/remove endpoints.
# nick = label libre, url = OpenAI-compatible /v1/chat/completions endpoint
# model = id du modele a passer dans le payload (mlx_lm.server l'accepte ;
#         souvent le path ou repo HF du modele, ou simplement "default")
# --------------------------------------------------------------------------- #

LORA_SERVERS: list[dict[str, str]] = [
    # --- macM1 local ---
    {"nick": "eu-kiki",   "url": "http://127.0.0.1:8502/v1/chat/completions",
     "model": "lmstudio-community/gemma-4-E4B-it-MLX-4bit",
     "adapter_hint": "gemma4-e4b-eukiki/final"},
    {"nick": "mascarade", "url": "http://127.0.0.1:8503/v1/chat/completions",
     "model": "lmstudio-community/gemma-4-E4B-it-MLX-4bit",
     "adapter_hint": "gemma4-e4b-mascarade/final"},
    # --- Studio direct (si reseau local accessible) ---
    # {"nick": "eu-kiki-studio", "url": "http://studio.local:9334/v1/chat/completions",
    #  "model": "gemma-4-E4B-it-MLX-4bit",
    #  "adapter_hint": "gemma4-eukiki"},
    # --- Studio via SSH tunnel (recommande) : decommenter une fois le tunnel lance ---
    # {"nick": "eu-kiki-studio",   "url": "http://127.0.0.1:19334/v1/chat/completions",
    #  "model": "gemma-4-E4B-it-MLX-4bit", "adapter_hint": "gemma4-eukiki"},
    # {"nick": "mistral-medium",   "url": "http://127.0.0.1:19301/v1/chat/completions",
    #  "model": "Mistral-Medium-3.5-128B-MLX-Q8", "adapter_hint": None},
    # {"nick": "qwen3.6-35b",      "url": "http://127.0.0.1:19305/v1/chat/completions",
    #  "model": "Qwen3.6-35B-A3B-MLX-BF16",       "adapter_hint": None},
    # {"nick": "devstral-2-24b",   "url": "http://127.0.0.1:19316/v1/chat/completions",
    #  "model": "Devstral-Small-2-24B-MLX-4bit",  "adapter_hint": None},
]


# --------------------------------------------------------------------------- #
# Auto-discovery (best-effort, graceful)
# --------------------------------------------------------------------------- #

LOCAL_PORT_RANGE = (8500, 8550)
TUNNEL_PORT_RANGE = (19300, 19400)


def _tcp_alive(host: str, port: int, timeout: float = 0.25) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _probe_models(url_base: str, timeout: float = 1.5) -> dict | None:
    """Best-effort /v1/models probe. Returns parsed JSON or None."""
    try:
        req = urllib.request.Request(url_base.rstrip("/") + "/v1/models")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def discover_servers(host: str = "127.0.0.1") -> list[dict[str, Any]]:
    """Scan LOCAL + TUNNEL port ranges. Returns list of {nick, url, model}.
    Fails GRACEFULLY (never raises, never kills servers).
    """
    found: list[dict[str, Any]] = []
    for low, high in (LOCAL_PORT_RANGE, TUNNEL_PORT_RANGE):
        for p in range(low, high + 1):
            if not _tcp_alive(host, p):
                continue
            base = f"http://{host}:{p}"
            info = _probe_models(base)
            if not info:
                # alive but maybe HTTP 404 on /v1/models : still mark as candidate
                found.append({
                    "nick": f"unknown:{p}",
                    "url": f"{base}/v1/chat/completions",
                    "model": "default",
                    "adapter_hint": None,
                    "probe": "no-models-endpoint",
                })
                continue
            model_id = "default"
            try:
                data = info.get("data") or []
                if data:
                    model_id = data[0].get("id") or data[0].get("name") or "default"
            except Exception:
                pass
            found.append({
                "nick": f"auto:{p}:{Path(str(model_id)).name[:24]}",
                "url": f"{base}/v1/chat/completions",
                "model": model_id,
                "adapter_hint": None,
                "probe": "ok",
            })
    return found


# --------------------------------------------------------------------------- #
# HTTP chat-completion call
# --------------------------------------------------------------------------- #


def call_chat(srv: dict[str, str], prompt: str, max_tokens: int,
              temperature: float = 0.0, timeout: float = 600.0) -> dict[str, Any]:
    body = json.dumps({
        "model": srv.get("model", "default"),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        srv["url"], data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        dt_call = time.time() - t0
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        return {
            "ok": True,
            "dt": dt_call,
            "content": content,
            "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"),
        }
    except urllib.error.HTTPError as e:
        return {"ok": False, "dt": time.time() - t0,
                "error": f"http_{e.code}: {e.reason}"}
    except Exception as e:  # network / decode
        return {"ok": False, "dt": time.time() - t0,
                "error": f"{type(e).__name__}: {str(e)[:120]}"}


# --------------------------------------------------------------------------- #
# Parallel bench
# --------------------------------------------------------------------------- #


def bench_one(srv: dict[str, str], sample: dict, max_tokens: int) -> dict:
    res = call_chat(srv, sample["prompt"], max_tokens)
    if res["ok"]:
        try:
            scores = score_sch(res["content"], sample["expected"])
        except Exception as exc:
            scores = {"parse_ok": False, "composite": 0.0,
                      "score_error": repr(exc)}
        return {
            "server": srv["nick"],
            "id": sample["id"],
            "source": sample["source"],
            "ok": True,
            "gen_time_s": round(res["dt"], 2),
            "generated_chars": len(res["content"]),
            "expected_chars": len(sample["expected"]),
            "completion_tokens": res.get("completion_tokens"),
            "prompt_tokens": res.get("prompt_tokens"),
            "generated": res["content"][:3000],
            "scores": scores,
        }
    return {
        "server": srv["nick"],
        "id": sample["id"],
        "source": sample["source"],
        "ok": False,
        "gen_time_s": round(res["dt"], 2),
        "error": res["error"],
        "scores": {"parse_ok": False, "composite": 0.0,
                   "comp_count_match": 0.0, "label_count_match": 0.0,
                   "cli_proxy_score": 0.0, "structure_score": 0.0,
                   "starts_with_kicad_sch": False, "has_version": False,
                   "has_lib_symbols": False, "has_uuid": False,
                   "expected_n_components": 0, "generated_n_components": 0,
                   "expected_n_labels": 0, "generated_n_labels": 0},
    }


def run_parallel(servers: list[dict], samples: list[dict],
                 max_tokens: int, max_workers: int) -> dict:
    tasks: list[tuple[dict, dict]] = []
    for srv in servers:
        for s in samples:
            if s["id"] == SPI_BUS_ID:
                continue
            tasks.append((srv, s))

    n_samples_eff = sum(1 for s in samples if s["id"] != SPI_BUS_ID)
    log(f"  scheduling {len(tasks)} HTTP tasks "
        f"({len(servers)} servers x {n_samples_eff} samples) "
        f"with {max_workers} workers")

    results: dict[str, list[dict]] = {srv["nick"]: [] for srv in servers}

    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut2tag = {
            ex.submit(bench_one, srv, s, max_tokens): (srv["nick"], s["id"])
            for srv, s in tasks
        }
        done = 0
        for fut in cf.as_completed(fut2tag):
            nick, sid = fut2tag[fut]
            done += 1
            try:
                rec = fut.result()
            except Exception as exc:
                rec = {"server": nick, "id": sid, "ok": False,
                       "error": f"task_crash: {exc!r}",
                       "scores": {"parse_ok": False, "composite": 0.0}}
            results[nick].append(rec)
            ok = rec.get("ok")
            comp = rec.get("scores", {}).get("composite", 0.0)
            t_ = rec.get("gen_time_s", 0.0)
            log(f"  [{done}/{len(tasks)}] {nick}/{sid} ok={ok} "
                f"composite={comp} t={t_}s")

    # aggregate per server
    bench: dict[str, dict] = {}
    for srv in servers:
        recs = results[srv["nick"]]
        # build records compatible with aggregate()
        compat = []
        for r in recs:
            compat.append({
                "id": r["id"],
                "scores": r.get("scores", {"parse_ok": False, "composite": 0.0,
                                           "comp_count_match": 0.0,
                                           "label_count_match": 0.0,
                                           "cli_proxy_score": 0.0,
                                           "structure_score": 0.0,
                                           "starts_with_kicad_sch": False,
                                           "has_lib_symbols": False}),
            })
        try:
            agg = aggregate(compat)
        except Exception as exc:
            agg = {"n_samples": len(recs), "aggregate_error": repr(exc)}
        agg["samples"] = recs
        bench[srv["nick"]] = agg
    return bench


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #


def write_markdown(results: dict) -> None:
    md = results["metadata"]
    lines = [
        "# KiCad Phase 7 HTTP bench — mlx_lm.server reuse",
        "",
        f"_Generated: {md['timestamp']}_",
        "",
        f"- Servers   : {len(md['servers'])}",
        f"- Samples   : {md['n_samples_eval']}/{md['n_samples_total']} "
        f"(skipped: {md['skipped_ids']})",
        f"- MaxTokens : {md['max_tokens']}",
        f"- Workers   : {md['max_workers']}",
        f"- Dataset   : `{md['data_path']}`",
        "",
        "| Server | n | parse_ok | cli_proxy | comp_match | label_match | composite |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for srv in md["servers"]:
        nick = srv["nick"]
        e = results["bench"].get(nick, {})
        if "aggregate_error" in e:
            lines.append(f"| **{nick}** | 0 | — | — | — | — | err |")
            continue
        n = e.get("n_samples", 0)
        if n == 0:
            lines.append(f"| **{nick}** | 0 | — | — | — | — | skipped |")
            continue
        lines.append(
            f"| **{nick}** | {n} | "
            f"{e.get('parse_ok_rate', 0):.2f} | "
            f"{e.get('cli_proxy_avg', 0):.2f} | "
            f"{e.get('comp_count_match_avg', 0):.2f} | "
            f"{e.get('label_count_match_avg', 0):.2f} | "
            f"{e.get('composite_score', 0):.3f} |"
        )
    lines += ["", "## Servers", ""]
    for srv in md["servers"]:
        ad = srv.get("adapter_hint") or "—"
        lines.append(f"- **{srv['nick']}** → `{srv['url']}` (model `{srv.get('model','?')}`, "
                     f"adapter `{ad}`)")
    OUT_MD.write_text("\n".join(lines) + "\n")
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 7 HTTP bench (mlx_lm.server)")
    ap.add_argument("--servers", nargs="*", default=None,
                    help="subset de nicks LORA_SERVERS")
    ap.add_argument("--discover", action="store_true",
                    help="auto-discovery des servers (ne lance pas le bench)")
    ap.add_argument("--include-discovered", action="store_true",
                    help="merge auto-discovered avec LORA_SERVERS")
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--workers", type=int, default=4,
                    help="thread workers (parallelisme = LoRA x sample concurrents)")
    ap.add_argument("--limit", type=int, default=None,
                    help="limit N samples (POC). Default = all")
    ap.add_argument("--dry-run", action="store_true",
                    help="liste servers + samples sans appel HTTP")
    ap.add_argument("--out", default=str(OUT_JSON),
                    help=f"override out JSON (default {OUT_JSON})")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    out_json = Path(args.out)

    log("=" * 70)
    log("PHASE 7 — KICAD HTTP BENCH via mlx_lm.server (chat-completions)")
    log("=" * 70)

    # Discovery
    if args.discover or args.include_discovered:
        log("auto-discovering active servers ...")
        discovered = discover_servers()
        if discovered:
            for d in discovered:
                log(f"  found: {d['nick']} -> {d['url']} probe={d.get('probe')}")
        else:
            log("  none found")
        if args.discover and not args.include_discovered:
            log("--discover only : exit")
            return 0
    else:
        discovered = []

    servers = list(LORA_SERVERS)
    if args.include_discovered:
        existing_urls = {s["url"] for s in servers}
        for d in discovered:
            if d["url"] not in existing_urls:
                servers.append(d)

    if args.servers:
        servers = [s for s in servers if s["nick"] in args.servers]
        miss = sorted(set(args.servers) - {s["nick"] for s in servers})
        if miss:
            log(f"  WARN: unknown server nicks: {miss}")
    if not servers:
        log("ERROR: no servers selected. Edit LORA_SERVERS or pass --include-discovered.")
        return 2

    log(f"servers selected ({len(servers)}):")
    for s in servers:
        log(f"  - {s['nick']:24s} {s['url']}")

    # Quick TCP ping pre-flight (does NOT kill anything)
    for s in servers:
        try:
            from urllib.parse import urlparse
            u = urlparse(s["url"])
            alive = _tcp_alive(u.hostname or "127.0.0.1", u.port or 80, timeout=1.0)
            s["_alive"] = alive
            log(f"    ping {s['nick']}: {'OK' if alive else 'DOWN'}")
        except Exception as exc:
            s["_alive"] = False
            log(f"    ping {s['nick']}: ERR {exc!r}")

    samples = load_samples()
    n_total = len(samples)
    if args.limit:
        # On garde l'ordre, on prend les premiers non-SPI
        kept = []
        for s in samples:
            if s["id"] == SPI_BUS_ID:
                continue
            kept.append(s)
            if len(kept) >= args.limit:
                break
        samples = kept
    n_eval = sum(1 for s in samples if s["id"] != SPI_BUS_ID)

    log(f"samples: {n_eval} eval / {n_total} total (limit={args.limit})")
    for s in samples:
        log(f"  - {s['id']} ({s['source']})  expected_chars={len(s['expected'])}")

    if args.dry_run:
        log("dry-run done.")
        return 0

    # Run
    metadata = {
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_path": str(Path(os.environ.get(
            "KICAD_SCH_GEN_PATH",
            HOME / "eu-kiki-data" / "kicad-sch-gen" / "valid.jsonl",
        ))),
        "n_samples_total": n_total,
        "n_samples_eval": n_eval,
        "max_tokens": args.max_tokens,
        "max_workers": args.workers,
        "skipped_ids": [SPI_BUS_ID],
        "servers": [{k: v for k, v in s.items() if not k.startswith("_")}
                    for s in servers],
    }
    bench = run_parallel(servers, samples, args.max_tokens, args.workers)
    results = {"metadata": metadata, "bench": bench}
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    log(f"JSON saved to {out_json}")

    # Markdown only when default location used
    if Path(args.out) == OUT_JSON:
        write_markdown(results)
    else:
        # still write a sibling .md
        global OUT_MD
        OUT_MD = out_json.with_suffix(".md")
        write_markdown(results)

    log("PHASE 7 HTTP BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("Interrupted by user.")
        sys.exit(130)
    except Exception:
        log("FATAL:")
        log(traceback.format_exc())
        sys.exit(1)
