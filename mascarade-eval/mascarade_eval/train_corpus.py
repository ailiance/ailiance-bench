"""Load the user prompts of a mascarade training dataset.

Datasets exist in two formats (recon 2026-05-18): ShareGPT
(`conversations`/`from`/`value`) and OpenAI (`messages`/`role`/`content`).
"""
from __future__ import annotations
import json
from huggingface_hub import hf_hub_download
from . import HF_ORG


def extract_prompts(jsonl_path: str) -> list[str]:
    """Return every user/human prompt in a chat JSONL file."""
    prompts: list[str] = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            msgs = d.get("messages") or d.get("conversations") or []
            for m in msgs:
                role = m.get("role") or m.get("from")
                if role in ("user", "human"):
                    prompts.append(m.get("content") or m.get("value") or "")
    return prompts


def load_train_prompts(domain: str) -> list[str]:
    """Download the domain training dataset from HF and extract its prompts."""
    path = hf_hub_download(
        repo_id=f"{HF_ORG}/mascarade-{domain}-dataset",
        filename=f"{domain}_chat.jsonl",
        repo_type="dataset",
    )
    return extract_prompts(path)
