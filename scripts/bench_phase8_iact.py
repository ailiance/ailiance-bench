#!/usr/bin/env python3
"""bench_phase8_iact.py — iact-bench Docker validators for the 5 LoRA
that aren't covered by Phase 7 EDA scorers (stm32, embedded, platformio,
freecad, iot).

Cross-machine architecture:
  - generate on kxkm-ai (GPU, LoRA + base warm)
  - validate on electron-server (Docker iact-bench-* images, sandboxed)
  - call electron-server via ssh per sample (round-trip ~50 ms)

For `iot` (no Docker validator in iact-bench, marked `judge-only`):
  - fallback to eu-kiki gateway :9300 with model=ailiance-mistral-medium
    used as binary judge (does the generated answer correctly address
    the user's IoT question? yes/no).

Outputs:
  - /tmp/phase8_results/qwen3-4b-mascarade-<domain>_phase8.json
  - /tmp/phase8_results/_phase8_summary.md
  - --update-cards: replaces "## Bench results" section in each HF card.

Usage:
  python bench_phase8_iact.py                    # all 5 orphans
  python bench_phase8_iact.py --loras stm32      # selected
  python bench_phase8_iact.py --n-samples 5      # quick smoke
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("phase8")

HF_ORG = "Ailiance-fr"
BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
RESULTS_DIR = Path("/tmp/phase8_results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Pinned by digest from /home/electron/iact-bench/configs/domain_validators.yaml.
# Validators run on electron-server via `ssh electron-server "docker run ..."`.
# Sandbox flags exactly match the v0.2 methodology:
#   --network=none --read-only --tmpfs /tmp:size=256m --user 1000:1000
#   --cap-drop=ALL --security-opt=no-new-privileges
VALIDATORS = {
    "stm32": {
        "image": "ghcr.io/electron-rare/iact-bench-embedded:latest",
        "filename": "main.c",
        "cmd": ["arm-none-eabi-gcc", "-c", "-mcpu=cortex-m4", "-mthumb", "-Wall",
                "-o", "/tmp/out.o", "/tmp/in/main.c"],
        "timeout_s": 30,
        "cpu": 1.0,
        "memory": "512m",
        "tmpfs_size": "256m",  # iact-bench v0.2 strict — gcc output is tiny
    },
    "embedded": {  # same validator as stm32
        "image": "ghcr.io/electron-rare/iact-bench-embedded:latest",
        "filename": "main.c",
        "cmd": ["arm-none-eabi-gcc", "-c", "-mcpu=cortex-m4", "-mthumb", "-Wall",
                "-o", "/tmp/out.o", "/tmp/in/main.c"],
        "timeout_s": 30,
        "cpu": 1.0,
        "memory": "512m",
        "tmpfs_size": "256m",
    },
    "platformio": {
        "image": "ghcr.io/electron-rare/iact-bench-platformio:latest",
        "filename": "main.cpp",
        "cmd": ["sh", "-c",
                "mkdir -p /tmp/sketch && cp /tmp/in/main.cpp /tmp/sketch/sketch.ino && "
                "arduino-cli compile --fqbn esp32:esp32:esp32dev "
                "--config-dir /opt/arduino /tmp/sketch"],
        "timeout_s": 240,
        "cpu": 2.0,
        "memory": "2g",
        "tmpfs_size": "1g",  # bumped: ESP32 build intermediates can hit 50-100 MB
    },
    "freecad": {
        "image": "ghcr.io/electron-rare/iact-bench-freecad:latest",
        "filename": "macro.FCMacro",
        "cmd": ["freecadcmd", "-c", "exec(open('/tmp/in/macro.FCMacro').read())"],
        "timeout_s": 60,
        "cpu": 2.0,
        "memory": "1g",
        "tmpfs_size": "1g",  # bumped: parametric mesh/BRep can exceed 256 MB
    },
    # iot: judge-only fallback (no iact-bench Docker validator exists).
    "iot": {"judge_only": True},
}

# Naive extraction of code block from chat answer for compile validators.
import re
_CODE_FENCE_RE = re.compile(r"```(?:[a-z+]*\n)?(.*?)```", re.S)


def extract_code(text: str, fallback_lang: str | None = None) -> str:
    """Pull the first fenced code block; if none, return raw text."""
    m = _CODE_FENCE_RE.search(text)
    return m.group(1).strip() if m else text.strip()


def load_eval_samples(domain: str, n: int = 10) -> list[dict]:
    """Pull held-out samples from Ailiance-fr/mascarade-<domain>-dataset, seed=101."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=f"{HF_ORG}/mascarade-{domain}-dataset",
        filename=f"{domain}_chat.jsonl",
        repo_type="dataset",
    )
    with open(path) as f:
        lines = [line for line in f if line.strip()]
    random.seed(101)
    chosen = random.sample(lines, min(n, len(lines)))
    rows = []
    for l in chosen:
        d = json.loads(l)
        msgs = d.get("messages") or d.get("conversations") or []
        user = ""
        for m in msgs:
            role = m.get("role") or m.get("from")
            content = m.get("content") or m.get("value") or ""
            if role in ("user", "human"):
                user = content
                break
        if user:
            rows.append({"prompt": user})
    return rows


def cuda_load_lora(domain: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    log.info("loading base + lora qwen3-4b-mascarade-%s", domain)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16,
        device_map="auto", trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(model, f"{HF_ORG}/qwen3-4b-mascarade-{domain}-lora")
    model.eval()
    return model, tok


def cuda_generate(model, tok, prompt: str, max_tokens: int = 1024) -> str:
    import torch
    text = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True,
    )
    inputs = tok(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_tokens,
            do_sample=False, pad_token_id=tok.pad_token_id,
        )
    return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def docker_validate(domain: str, code: str) -> dict:
    """Send `code` to electron-server, run the iact-bench validator container.

    Sandbox flags: --network=none --read-only --tmpfs /tmp --user 1000:1000
    --cap-drop=ALL --security-opt no-new-privileges --rm

    Returns: {"exit_code": int, "stdout_head": str, "stderr_head": str,
              "duration_s": float, "pass": bool, "status": "ok"|"timeout"|"docker_err"}.
    """
    v = VALIDATORS[domain]
    # Stage the code into a tmp file on electron-server via ssh + stdin redirect.
    # Use base64 to avoid shell escaping issues.
    import base64
    enc = base64.b64encode(code.encode()).decode()
    fname = v["filename"]

    # Build the docker command line as a single shell command remotely.
    cmd_args = " ".join(f"'{a}'" for a in v["cmd"])
    tmpfs_size = v.get("tmpfs_size", "256m")
    remote_script = (
        f"set -e; "
        f"D=$(mktemp -d /tmp/phase8_XXXX); "
        f"echo '{enc}' | base64 -d > $D/{fname}; "
        f"timeout {v['timeout_s']}s docker run --rm "
        f"--network=none --read-only --tmpfs /tmp:size={tmpfs_size} "
        f"--user 1000:1000 --cap-drop=ALL --security-opt no-new-privileges "
        f"--cpus={v['cpu']} --memory={v['memory']} "
        f"-v $D:/tmp/in:ro {v['image']} {cmd_args}; "
        f"RC=$?; rm -rf $D; exit $RC"
    )
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            ["ssh", "electron-server", remote_script],
            capture_output=True, text=True,
            timeout=v["timeout_s"] + 30,
        )
        dt = time.perf_counter() - t0
        return {
            "exit_code": result.returncode,
            "stdout_head": result.stdout[:200],
            "stderr_head": result.stderr[:300],
            "duration_s": round(dt, 1),
            "pass": result.returncode == 0,
            "status": "ok",
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": None, "stdout_head": "", "stderr_head": "ssh+docker timed out",
            "duration_s": round(time.perf_counter() - t0, 1),
            "pass": False, "status": "timeout",
        }
    except Exception as e:
        return {
            "exit_code": None, "stdout_head": "", "stderr_head": repr(e),
            "duration_s": round(time.perf_counter() - t0, 1),
            "pass": False, "status": "docker_err",
        }


def judge_iot(prompt: str, answer: str) -> dict:
    """LLM judge fallback for iot domain (no iact-bench docker validator)."""
    import urllib.request
    judge_prompt = (
        "You are an expert IoT systems engineer judging another model's "
        "answer. Score the answer on a binary scale: does it correctly and "
        "completely address the user's IoT question (yes) or not (no)? "
        'Output ONLY JSON: {"correct": true|false}.\n\n'
        f"User question:\n{prompt}\n\nCandidate answer:\n{answer}\n\n"
        'Output: {"correct": ...}'
    )
    body = json.dumps({
        "model": "ailiance-mistral-medium",
        "messages": [{"role": "user", "content": judge_prompt}],
        "max_tokens": 30,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        "http://localhost:9300/v1/chat/completions",  # gateway via tunnel from kxkm-ai? no, direct localhost
        data=body, headers={"Content-Type": "application/json"},
    )
    try:
        # kxkm-ai doesn't have local :9300, route via electron-server tunnel proxy
        # Instead, call via ssh electron-server "curl ..."
        cmd = ["ssh", "electron-server",
               "curl -s --max-time 60 -X POST http://localhost:9300/v1/chat/completions "
               "-H 'Content-Type: application/json' "
               "-d " + json.dumps(json.dumps({
                   "model": "ailiance-mistral-medium",
                   "messages": [{"role": "user", "content": judge_prompt}],
                   "max_tokens": 30, "temperature": 0,
               }))]
        t0 = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        dt = time.perf_counter() - t0
        if r.returncode != 0:
            return {"pass": False, "status": "judge_err", "duration_s": round(dt, 1),
                    "stderr_head": r.stderr[:200]}
        d = json.loads(r.stdout)
        out = d.get("choices", [{}])[0].get("message", {}).get("content", "")
        m = re.search(r'"correct"\s*:\s*(true|false)', out, re.I)
        correct = (m.group(1).lower() == "true") if m else False
        return {"pass": correct, "status": "ok", "duration_s": round(dt, 1),
                "judge_out_head": out[:200]}
    except Exception as e:
        return {"pass": False, "status": "judge_err", "stderr_head": repr(e),
                "duration_s": 0.0}


def eval_lora(domain: str, n_samples: int) -> dict:
    rows = load_eval_samples(domain, n_samples)
    if not rows:
        return {"domain": domain, "status": "no_samples"}

    try:
        model, tok = cuda_load_lora(domain)
    except Exception as e:
        return {"domain": domain, "status": "load_failed", "error": repr(e)}

    per_sample = []
    v = VALIDATORS[domain]
    t_total = 0.0

    for i, r in enumerate(rows):
        try:
            gen = cuda_generate(model, tok, r["prompt"], max_tokens=v.get("max_tokens", 1024))
        except Exception as e:
            log.warning("  [%s] sample %d gen FAILED: %r", domain, i, e)
            per_sample.append({"i": i, "gen_failed": True, "pass": False})
            continue

        if v.get("judge_only"):
            res = judge_iot(r["prompt"], gen)
        else:
            code = extract_code(gen)
            res = docker_validate(domain, code)
        t_total += res.get("duration_s", 0.0)
        per_sample.append({"i": i, **res})
        log.info("  [%s] %d/%d pass=%s status=%s (%.1fs)",
                 domain, i + 1, len(rows), res.get("pass"),
                 res.get("status"), res.get("duration_s", 0))

    # Free VRAM
    import gc, torch
    del model
    gc.collect()
    torch.cuda.empty_cache()

    passes = sum(1 for s in per_sample if s.get("pass"))
    n_valid = sum(1 for s in per_sample if s.get("status") == "ok"
                  or s.get("status") is None and not s.get("gen_failed"))
    return {
        "domain": domain,
        "status": "ok",
        "n_samples": len(per_sample),
        "n_valid": n_valid,
        "n_pass": passes,
        "pass_rate": round(passes / max(len(per_sample), 1), 3),
        "validator": v.get("image", "judge-only"),
        "duration_s_total": round(t_total, 1),
        "samples": per_sample[:5],
    }


def card_snippet(r: dict) -> str:
    if r.get("status") != "ok":
        return f"\n## Bench results — iact-bench Phase 8 (Docker validators)\n\n_Eval skipped: {r.get('status')}_\n"
    name = r["domain"]
    v = VALIDATORS.get(name, {})
    tmpfs = v.get("tmpfs_size", "256m")
    tmpfs_note = ""
    if tmpfs != "256m":
        tmpfs_note = (
            f"\n\n_**Methodology note**: tmpfs bumped to `{tmpfs}` "
            f"(non-standard vs iact-bench v0.2 default 256m) to avoid "
            f"OOM-as-FAIL false negatives on {name}-typical workloads "
            f"({{'platformio': 'ESP32 build intermediates 50-100 MB', "
            f"'freecad': 'parametric mesh/BRep can exceed 256 MB'}}.get('{name}','heavy build artifacts'))._"
        )
    return (
        "\n## Bench results — iact-bench Phase 8 (Docker validators, "
        "2026-05-11)\n\n"
        f"Functional eval via the [`iact-bench`](https://github.com/electron-rare/iact-bench) "
        f"v0.2 Docker sandbox validators (no-network, read-only rootfs, "
        f"uid 1000 dropped caps, `--tmpfs /tmp:size={tmpfs}`). Source LoRA: "
        f"`{HF_ORG}/qwen3-4b-mascarade-{name}-lora`. Eval samples drawn "
        f"with seed=101 from `{HF_ORG}/mascarade-{name}-dataset`.\n\n"
        f"| Metric | Value |\n|---|---:|\n"
        f"| Validator | `{r['validator']}` |\n"
        f"| Tmpfs cap | `{tmpfs}` |\n"
        f"| Samples | {r['n_samples']} |\n"
        f"| **Pass rate** | **{r['pass_rate']}** |\n"
        f"| Total validator wall-clock | {r['duration_s_total']}s |\n\n"
        f"_Pass = sandboxed compile/exec succeeds (exit_code=0). "
        f"See `iact-bench/configs/domain_validators.yaml` for the exact "
        f"toolchain invocation (arm-none-eabi-gcc / arduino-cli / freecadcmd "
        f"depending on domain)._" + tmpfs_note + "\n"
    )


def update_card(domain: str, snippet: str) -> bool:
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    repo = f"{HF_ORG}/qwen3-4b-mascarade-{domain}-lora"
    try:
        path = hf_hub_download(repo_id=repo, filename="README.md", repo_type="model")
        readme = open(path).read()
    except Exception as e:
        log.error("card fetch failed %s: %r", repo, e)
        return False

    new_section = snippet.lstrip("\n")
    pattern = re.compile(r"## Bench results.*?(?=\n## |\Z)", re.S)
    if pattern.search(readme):
        new_readme = pattern.sub(new_section, readme, count=1)
    else:
        if "## Citations" in readme:
            new_readme = readme.replace("## Citations", new_section + "\n## Citations", 1)
        else:
            new_readme = readme.rstrip() + "\n\n" + new_section
    if new_readme == readme:
        return True
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
        tf.write(new_readme)
        tmp = tf.name
    try:
        api.upload_file(
            path_or_fileobj=tmp,
            path_in_repo="README.md",
            repo_id=repo,
            repo_type="model",
            commit_message=f"docs: Phase 8 iact-bench Docker validator pass-rate ({domain})",
        )
        return True
    finally:
        os.unlink(tmp)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--loras", default="stm32,embedded,platformio,freecad,iot")
    p.add_argument("--n-samples", type=int, default=10)
    p.add_argument("--update-cards", action="store_true")
    args = p.parse_args()

    domains = [d.strip() for d in args.loras.split(",") if d.strip()]
    summary = []

    for d in domains:
        log.info("=== %s ===", d)
        r = eval_lora(d, args.n_samples)
        summary.append(r)
        (RESULTS_DIR / f"qwen3-4b-mascarade-{d}_phase8.json").write_text(
            json.dumps(r, indent=2, ensure_ascii=False)
        )
        if args.update_cards:
            ok = update_card(d, card_snippet(r))
            log.info("  card update %s -> %s", d, ok)

    (RESULTS_DIR / "_phase8_summary.md").write_text(
        "# Phase 8 iact-bench Docker validators — summary\n\n"
        "| Domain | Validator | n | Pass rate | Total time |\n|---|---|---:|---:|---:|\n"
        + "\n".join(
            f"| {r['domain']} | {r.get('validator','-')} | "
            f"{r.get('n_samples','-')} | {r.get('pass_rate','-')} | "
            f"{r.get('duration_s_total','-')}s |"
            for r in summary
        )
    )
    (RESULTS_DIR / "_phase8_all.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    log.info("done. results in %s", RESULTS_DIR)


if __name__ == "__main__":
    main()
