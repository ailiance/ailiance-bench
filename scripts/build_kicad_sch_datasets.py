#!/usr/bin/env python3
"""
Construit les datasets jsonl Phase 2 et Phase 3 a partir des templates
hand-crafted + schemas locaux references.

Phase 2 (~/eu-kiki-data/kicad-sch-gen/valid.jsonl) :
  {"messages": [
     {"role": "user", "content": "<prompt>"},
     {"role": "assistant", "content": "<.kicad_sch>"}
   ],
   "_id": "...", "_source": "template|local"}

Phase 3 (~/eu-kiki-data/kicad-sch-extract/valid.jsonl) :
  {"messages": [
     {"role": "user", "content": "Extract components & nets from this KiCad schematic. Output JSON ...\\n\\n<.kicad_sch>"},
     {"role": "assistant", "content": "<json ground truth>"}
   ],
   "ground_truth_json": {...}, "_id": "...", "_source": "..."}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kicad_sch_templates import all_templates  # noqa: E402

OUT_GEN = Path.home() / "eu-kiki-data" / "kicad-sch-gen" / "valid.jsonl"
OUT_EXT = Path.home() / "eu-kiki-data" / "kicad-sch-extract" / "valid.jsonl"

EXTRACT_INSTRUCTION = (
    "You are a KiCad schematic parser. Read the .kicad_sch S-expression below "
    "and output ONLY a JSON object with two keys: \"components\" and \"nets\".\n"
    "  components: list of {ref, value, footprint} for every instance symbol.\n"
    "  nets: list of {name, pins} where each pin is \"REF.PIN\".\n"
    "Output VALID JSON, no markdown fences, no commentary.\n\n"
    "Schematic:\n"
)


def main() -> int:
    OUT_GEN.parent.mkdir(parents=True, exist_ok=True)
    OUT_EXT.parent.mkdir(parents=True, exist_ok=True)

    templates = all_templates()
    n_gen = 0
    n_ext = 0
    with OUT_GEN.open("w") as fg, OUT_EXT.open("w") as fe:
        for t in templates:
            tid = t["id"]
            src = "local" if tid == "spi_bus_4devices" else "template"

            # Phase 2 : prompt -> sch
            fg.write(json.dumps({
                "_id": tid,
                "_source": src,
                "messages": [
                    {"role": "user", "content": t["prompt"]},
                    {"role": "assistant", "content": t["sch"]},
                ],
            }, ensure_ascii=False) + "\n")
            n_gen += 1

            # Phase 3 : sch -> JSON
            user_msg = EXTRACT_INSTRUCTION + t["sch"]
            asst_msg = json.dumps(t["ground_truth"], ensure_ascii=False)
            fe.write(json.dumps({
                "_id": tid,
                "_source": src,
                "messages": [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": asst_msg},
                ],
                "ground_truth_json": t["ground_truth"],
            }, ensure_ascii=False) + "\n")
            n_ext += 1

    print(f"Phase 2 : {n_gen} samples -> {OUT_GEN}")
    print(f"Phase 3 : {n_ext} samples -> {OUT_EXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
