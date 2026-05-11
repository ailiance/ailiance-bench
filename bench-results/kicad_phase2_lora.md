# KiCad Phase 2 LORA bench — generation .kicad_sch (adapters)

_Generated: 2026-05-11 04:37:30_

- Dataset    : `/Users/electron/eu-kiki-data/kicad-sch-gen/valid.jsonl` (6 samples, 5 evaluated)
- Combos     : 3
- Max tokens : 4096
- Validation : pure-Python parser (kicad-cli not used in P2)

| Combo | n | parse_ok | cli_proxy | comp_match | label_match | composite |
|---|---:|---:|---:|---:|---:|---:|
| **gemma-e4b-eukiki-final** | 5 | 0.40 | 0.15 | 0.00 | 0.00 | 0.220 |
| **gemma-e4b-mascarade-final** | 5 | 1.00 | 0.00 | 0.00 | 0.00 | 0.400 |
| **gemma-e4b-aggro-test** | 5 | 0.80 | 0.00 | 0.00 | 0.00 | 0.320 |

## Combos tested

- **gemma-e4b-eukiki-final** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/gemma4-e4b-eukiki/final`
- **gemma-e4b-mascarade-final** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/gemma4-e4b-mascarade/final`
- **gemma-e4b-aggro-test** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/aggro-test`
