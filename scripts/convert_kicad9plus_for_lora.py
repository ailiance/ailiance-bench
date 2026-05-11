#!/usr/bin/env python3
"""
Convert HF dataset 'electron-rare/kicad9plus-permissive' (chat MLX format) en
{train,valid,test}.jsonl format `{"text": "<prompt>\n<assistant_content>"}`
pour mlx_lm.lora.

Split deterministe 90/5/5 via hash modulo (reproductible, pas de seed RNG).

Sortie : ~/lora-data-kicad9plus/{train,valid,test}.jsonl

Strategie de chargement :
  1. Essayer copie locale ~/ailiance-data/kicad9plus-corpus/dataset_permissive.jsonl
     (98 samples, format identique uploaded sur HF).
  2. Si absent, telecharger via huggingface_hub.snapshot_download
     'electron-rare/kicad9plus-permissive' (token deja configure).

Format mlx_lm.lora attendu : ligne JSONL `{"text": "..."}`.
On concatene user.content + "\n" + assistant.content. Pas de tokens speciaux.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
LOCAL_PERMISSIVE = HOME / "ailiance-data" / "kicad9plus-corpus" / "dataset_permissive.jsonl"
OUT_DIR = HOME / "lora-data-kicad9plus"
HF_DATASET_ID = "electron-rare/kicad9plus-permissive"


def log(msg: str) -> None:
    print(f"[convert] {msg}", flush=True)


def load_local_or_hf(prefer_local: bool = True) -> list[dict]:
    if prefer_local and LOCAL_PERMISSIVE.exists():
        log(f"loading LOCAL {LOCAL_PERMISSIVE}")
        rows = []
        with LOCAL_PERMISSIVE.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        log(f"  loaded {len(rows)} rows from local")
        return rows
    log(f"local missing, downloading {HF_DATASET_ID} from HF Hub ...")
    try:
        from huggingface_hub import snapshot_download
        local = snapshot_download(repo_id=HF_DATASET_ID, repo_type="dataset")
    except Exception as exc:
        log(f"  HF snapshot_download FAILED: {exc!r}")
        sys.exit(2)
    snap = Path(local)
    cand = list(snap.glob("**/dataset.jsonl")) + list(snap.glob("**/dataset_permissive.jsonl"))
    if not cand:
        log(f"  no dataset jsonl found in {snap}; ls={list(snap.iterdir())}")
        sys.exit(3)
    log(f"  found {cand[0]}")
    rows = []
    with cand[0].open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    log(f"  loaded {len(rows)} rows from HF cache")
    return rows


def to_text(row: dict) -> str | None:
    msgs = row.get("messages") or []
    user = next((m["content"] for m in msgs if m.get("role") == "user"), None)
    asst = next((m["content"] for m in msgs if m.get("role") == "assistant"), None)
    if not user or not asst:
        return None
    return f"{user}\n{asst}"


def split_idx(idx: int, total: int) -> str:
    """Split deterministe 90/5/5 via index modulo 20.
       - 18/20 = 90% train
       -  1/20 = 5% valid
       -  1/20 = 5% test
    """
    bucket = idx % 20
    if bucket < 18:
        return "train"
    if bucket < 19:
        return "valid"
    return "test"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--no-local", action="store_true",
                    help="Force HF download au lieu de copie locale")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = load_local_or_hf(prefer_local=not args.no_local)

    splits = {"train": [], "valid": [], "test": []}
    skipped = 0
    for idx, row in enumerate(rows):
        text = to_text(row)
        if text is None:
            skipped += 1
            continue
        splits[split_idx(idx, len(rows))].append({"text": text})

    for name, items in splits.items():
        path = args.out_dir / f"{name}.jsonl"
        with path.open("w") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        log(f"  wrote {path}: {len(items)} samples")

    log(f"done. total={len(rows)} skipped={skipped} "
        f"split=(train={len(splits['train'])}, valid={len(splits['valid'])}, "
        f"test={len(splits['test'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
