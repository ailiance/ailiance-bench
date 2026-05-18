"""Generate answers for base and base+LoRA over a held-out file.

Two configs are supported:
- ``lora``  — mascarade Studio MLX multi-LoRA server at localhost:9340,
  which serves the fused Qwen3-4B + domain LoRA (hot-swapped per alias).
- ``base``  — plain Qwen3-4B without any LoRA at localhost:9341.
  At execution time, spin up a second ``mlx_lm.server`` on Studio using
  the same base model (``mlx-community/Qwen3-4B-4bit`` or the bf16 merged
  weights) but with *no* adapter flag, then bind it to port 9341 via the
  existing autossh tunnel from electron-server.  A local ``mlx_lm.server``
  on GrosMac is an acceptable alternative for smoke runs.
"""
from __future__ import annotations
import json
import time
import urllib.request

# base+LoRA: Studio :9340 mascarade server (via the gateway tunnel
# localhost:9340). base: a plain Qwen3-4B endpoint — see CONFIGS.
CONFIGS = {
    "lora": "http://localhost:9340/v1/chat/completions",
    "base": "http://localhost:9341/v1/chat/completions",  # see Step 5 note
}


def chat_completion(url: str, model: str, prompt: str,
                    max_tokens: int = 1024, timeout: int = 90) -> str:
    """One OpenAI-compatible chat call; returns the assistant content."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""


def run_config(heldout_items: list[dict], config: str, model: str) -> list[dict]:
    """Generate an answer per held-out item for one config."""
    url = CONFIGS[config]
    out = []
    for item in heldout_items:
        t0 = time.perf_counter()
        try:
            answer = chat_completion(url, model, item["prompt"])
            err = None
        except Exception as e:  # noqa: BLE001
            answer, err = "", repr(e)
        out.append({**item, "config": config, "answer": answer,
                    "error": err, "gen_s": round(time.perf_counter() - t0, 2)})
    return out
