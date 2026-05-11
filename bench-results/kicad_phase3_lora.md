# KiCad Phase 3 LORA bench — sch -> JSON extraction (adapters)

_Generated: 2026-05-11 04:49:30_

- Dataset    : `/Users/electron/ailiance-data/kicad-sch-extract/valid.jsonl` (6 samples)
- Combos     : 3
- Max tokens : 2048

| Combo | n | json_ok | comp_F1 | comp_recall | netname_F1 | netpins_F1 | netpins_recall | composite |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **gemma-e4b-eukiki-final** | 6 | 0.83 | 0.83 | 0.83 | 0.80 | 0.38 | 0.38 | 0.690 |
| **gemma-e4b-mascarade-final** | 6 | 1.00 | 1.00 | 1.00 | 0.94 | 0.32 | 0.35 | 0.785 |
| **gemma-e4b-aggro-test** | 6 | 0.50 | 0.50 | 0.50 | 0.50 | 0.00 | 0.00 | 0.350 |

## Combos tested

- **gemma-e4b-eukiki-final** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/gemma4-e4b-eukiki/final`
- **gemma-e4b-mascarade-final** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/gemma4-e4b-mascarade/final`
- **gemma-e4b-aggro-test** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/aggro-test`
