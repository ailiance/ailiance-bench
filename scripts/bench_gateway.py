#!/usr/bin/env python3
"""Bench ailiance gateway via OpenAI-compatible API on :9300.

Per model: N rounds, fixed prompt set, capture latency + token throughput.
Marks broken backends as ERROR with first error message.
"""
import json
import time
import urllib.request
from statistics import median

import argparse

DEFAULT_ENDPOINT = "http://localhost:9300/v1/chat/completions"
DEFAULT_MODELS = [
    "ailiance",
    "ailiance-apertus",
    "ailiance-mistral",
    "ailiance-gemma4",
    "ailiance-eurollm",
    "ailiance-gemma",
    "ailiance-qwen",
]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT,
                    help="OpenAI-compatible /v1/chat/completions URL")
parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS,
                    help="model ids to benchmark")
parser.add_argument("--rounds", type=int, default=3)
parser.add_argument("--max-tokens", type=int, default=64)
parser.add_argument("--out", default=None,
                    help="optional JSON path to write the summary")
args = parser.parse_args()
GATEWAY = args.endpoint
MODELS = args.models
PROMPTS = [
    "Explain in one sentence what a transformer is in deep learning.",
    "Give the boiling point of water in Celsius.",
    "Write a one-line bash command to count files in a dir.",
]
MAX_TOKENS = args.max_tokens
ROUNDS = args.rounds


def call(model, prompt):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        GATEWAY, data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        dt = time.time() - t0
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "") or ""
        usage = data.get("usage", {})
        out_tok = usage.get("completion_tokens", len(content.split()))
        return {
            "ok": True,
            "dt": dt,
            "tok": out_tok,
            "tps": out_tok / dt if dt > 0 else 0,
            "preview": content[:60].replace("\n", " "),
        }
    except Exception as e:
        return {"ok": False, "dt": time.time() - t0, "err": str(e)[:80]}


results = {}
for m in MODELS:
    print("=== " + m + " ===", flush=True)
    runs = []
    for i in range(ROUNDS):
        for p in PROMPTS:
            r = call(m, p)
            runs.append(r)
            if r["ok"]:
                line = "  r{} [OK]  {:.2f}s tok={} tps={:.1f}".format(
                    i + 1, r["dt"], r["tok"], r["tps"]
                )
            else:
                line = "  r{} [ERR] {:.2f}s err={}".format(
                    i + 1, r["dt"], r["err"][:50]
                )
            print(line, flush=True)
    ok = [r for r in runs if r["ok"]]
    if ok:
        results[m] = {
            "n_ok": len(ok),
            "n_err": len(runs) - len(ok),
            "median_latency_s": round(median(r["dt"] for r in ok), 3),
            "median_tps": round(median(r["tps"] for r in ok), 2),
            "median_tokens": int(median(r["tok"] for r in ok)),
        }
    else:
        first_err = next((r.get("err") for r in runs if not r["ok"]), "unknown")
        results[m] = {
            "n_ok": 0,
            "n_err": len(runs),
            "error_sample": first_err,
        }

print()
print(json.dumps(results, indent=2))
if args.out:
    with open(args.out, "w") as f:
        json.dump({"endpoint": GATEWAY, "models": MODELS,
                   "rounds": ROUNDS, "max_tokens": MAX_TOKENS,
                   "results": results}, f, indent=2)
    print(f"\nwrote {args.out}")
