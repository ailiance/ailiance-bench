# KiCad Phase 2 bench — generation .kicad_sch (KiCad 10 S-expr)

_Generated: 2026-05-11 02:16:41_

- Dataset    : `/Users/electron/eu-kiki-data/kicad-sch-gen/valid.jsonl` (6 samples, 5 evaluated)
- Models     : 7
- Max tokens : 4096
- Validation : pure-Python parser (kicad-cli not installed)

| Model | n | parse_ok | cli_proxy | comp_match | label_match | composite |
|---|---:|---:|---:|---:|---:|---:|
| **gemma-e4b-eu-kiki-base** | 5 | 1.00 | 0.05 | 0.00 | 0.00 | 0.420 |
| **gemma-e2b** | 5 | 1.00 | 0.00 | 0.00 | 0.00 | 0.400 |
| **ministral-3b** | 5 | 1.00 | 0.00 | 0.00 | 0.00 | 0.400 |
| **ministral-3-8b** | 5 | 1.00 | 0.00 | 0.00 | 0.00 | 0.400 |
| **ministral-3-14b-instruct** | 5 | 0.80 | 0.05 | 0.00 | 0.00 | 0.340 |
| **ministral-3-14b-reasoning** | 5 | 1.00 | 0.05 | 0.00 | 0.00 | 0.420 |
| **granite-4.1-3b** | 5 | 1.00 | 0.00 | 0.00 | 0.00 | 0.400 |

## Models tested

- **gemma-e4b-eu-kiki-base** — `lmstudio-community/gemma-4-E4B-it-MLX-4bit`
- **gemma-e2b** — `lmstudio-community/gemma-4-E2B-it-MLX-4bit`
- **ministral-3b** — `mlx-community/Ministral-3-3B-Instruct-2512-4bit`
- **ministral-3-8b** — `mlx-community/Ministral-3-8B-Instruct-2512-4bit`
- **ministral-3-14b-instruct** — `mlx-community/Ministral-3-14B-Instruct-2512-4bit`
- **ministral-3-14b-reasoning** — `mlx-community/Ministral-3-14B-Reasoning-2512-4bit`
- **granite-4.1-3b** — `mlx-community/granite-4.1-3b-4bit`
