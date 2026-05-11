# KiCad Phase 3 bench — sch -> JSON extraction

_Generated: 2026-05-11 02:45:31_

- Dataset    : `/Users/electron/ailiance-data/kicad-sch-extract/valid.jsonl` (6 samples)
- Models     : 7
- Max tokens : 2048

| Model | n | json_ok | comp_F1 | comp_recall | netname_F1 | netpins_F1 | netpins_recall | composite |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **gemma-e4b-ailiance-base** | 6 | 0.67 | 0.50 | 0.50 | 0.17 | 0.00 | 0.00 | 0.308 |
| **gemma-e2b** | 6 | 0.33 | 0.33 | 0.33 | 0.33 | 0.00 | 0.00 | 0.233 |
| **ministral-3b** | 6 | 1.00 | 1.00 | 1.00 | 0.93 | 0.00 | 0.00 | 0.687 |
| **ministral-3-8b** | 6 | 1.00 | 1.00 | 1.00 | 0.17 | 0.15 | 0.15 | 0.579 |
| **ministral-3-14b-instruct** | 6 | 1.00 | 1.00 | 1.00 | 0.17 | 0.15 | 0.13 | 0.578 |
| **ministral-3-14b-reasoning** | 6 | 0.17 | 0.17 | 0.17 | 0.00 | 0.00 | 0.00 | 0.083 |
| **granite-4.1-3b** | 6 | 1.00 | 1.00 | 1.00 | 0.83 | 0.12 | 0.12 | 0.702 |

## Models tested

- **gemma-e4b-ailiance-base** — `lmstudio-community/gemma-4-E4B-it-MLX-4bit`
- **gemma-e2b** — `lmstudio-community/gemma-4-E2B-it-MLX-4bit`
- **ministral-3b** — `mlx-community/Ministral-3-3B-Instruct-2512-4bit`
- **ministral-3-8b** — `mlx-community/Ministral-3-8B-Instruct-2512-4bit`
- **ministral-3-14b-instruct** — `mlx-community/Ministral-3-14B-Instruct-2512-4bit`
- **ministral-3-14b-reasoning** — `mlx-community/Ministral-3-14B-Reasoning-2512-4bit`
- **granite-4.1-3b** — `mlx-community/granite-4.1-3b-4bit`
