# KiCad + SPICE functional bench — Phase 1 (DSL + PCB + SPICE)

_Generated: 2026-05-10 23:42:32_

- Datasets: ['kicad-dsl', 'kicad-pcb', 'spice-sim']
- Samples / dataset: **20**
- Models: 7

## Dataset: `kicad-dsl`

| Model | n | parse_ok | composite | extras |
|---|---:|---:|---:|---|
| **gemma-e4b-eu-kiki-base** | 20 | 0.00 | 0.090 | fields_complete_rate=0.0, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |
| **gemma-e2b** | 20 | 0.00 | 0.090 | fields_complete_rate=0.0, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |
| **ministral-3b** | 20 | 0.00 | 0.114 | fields_complete_rate=0.0, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |
| **ministral-3-8b** | 20 | 0.00 | 0.090 | fields_complete_rate=0.0, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |
| **ministral-3-14b-instruct** | 20 | 0.00 | 0.130 | fields_complete_rate=0.15, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |
| **ministral-3-14b-reasoning** | 20 | 0.05 | 0.118 | fields_complete_rate=0.05, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |
| **granite-4.1-3b** | 20 | 0.00 | 0.090 | fields_complete_rate=0.0, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |

## Dataset: `kicad-pcb`

| Model | n | parse_ok | composite | extras |
|---|---:|---:|---:|---|
| **gemma-e4b-eu-kiki-base** | 20 | 0.00 | 0.010 | structure_ok_rate=0.0, pad_count_match_rate=0.05, has_at_rate=0.0 |
| **gemma-e2b** | 20 | 0.00 | 0.010 | structure_ok_rate=0.0, pad_count_match_rate=0.05, has_at_rate=0.0 |
| **ministral-3b** | 20 | 0.00 | 0.010 | structure_ok_rate=0.0, pad_count_match_rate=0.05, has_at_rate=0.0 |
| **ministral-3-8b** | 20 | 0.50 | 0.210 | structure_ok_rate=0.0, pad_count_match_rate=0.05, has_at_rate=0.0 |
| **ministral-3-14b-instruct** | 20 | 0.15 | 0.305 | structure_ok_rate=0.35, pad_count_match_rate=0.1, has_at_rate=0.8 |
| **ministral-3-14b-reasoning** | 20 | 0.05 | 0.075 | structure_ok_rate=0.05, pad_count_match_rate=0.05, has_at_rate=0.2 |
| **granite-4.1-3b** | 20 | 0.00 | 0.010 | structure_ok_rate=0.0, pad_count_match_rate=0.05, has_at_rate=0.0 |

## Dataset: `spice-sim`

| Model | n | parse_ok | composite | extras |
|---|---:|---:|---:|---|
| **gemma-e4b-eu-kiki-base** | 20 | 0.45 | 0.425 | has_end_rate=0.25, ground_present_rate=0.25, balanced_rate=0.75 |
| **gemma-e2b** | 20 | 0.85 | 0.580 | has_end_rate=0.35, ground_present_rate=0.65, balanced_rate=0.95 |
| **ministral-3b** | 20 | 0.75 | 0.641 | has_end_rate=0.25, ground_present_rate=0.75, balanced_rate=0.8 |
| **ministral-3-8b** | 20 | 0.90 | 0.853 | has_end_rate=1.0, ground_present_rate=1.0, balanced_rate=0.9 |
| **ministral-3-14b-instruct** | 20 | 0.90 | 0.821 | has_end_rate=0.8, ground_present_rate=0.85, balanced_rate=0.9 |
| **ministral-3-14b-reasoning** | 20 | 0.95 | 0.598 | has_end_rate=0.35, ground_present_rate=0.3, balanced_rate=0.95 |
| **granite-4.1-3b** | 20 | 0.85 | 0.739 | has_end_rate=0.5, ground_present_rate=0.75, balanced_rate=1.0 |

## Models tested

- **gemma-e4b-eu-kiki-base** — `lmstudio-community/gemma-4-E4B-it-MLX-4bit`
- **gemma-e2b** — `lmstudio-community/gemma-4-E2B-it-MLX-4bit`
- **ministral-3b** — `mlx-community/Ministral-3-3B-Instruct-2512-4bit`
- **ministral-3-8b** — `mlx-community/Ministral-3-8B-Instruct-2512-4bit`
- **ministral-3-14b-instruct** — `mlx-community/Ministral-3-14B-Instruct-2512-4bit`
- **ministral-3-14b-reasoning** — `mlx-community/Ministral-3-14B-Reasoning-2512-4bit`
- **granite-4.1-3b** — `mlx-community/granite-4.1-3b-4bit`
