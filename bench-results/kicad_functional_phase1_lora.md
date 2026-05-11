# KiCad + SPICE functional bench — Phase 1 LORA (adapters)

_Generated: 2026-05-11 03:24:10_

- Datasets : ['kicad-dsl', 'kicad-pcb', 'spice-sim']
- Samples / dataset : **20**
- Combos base+adapter : 3

## Combos tested

- **gemma-e4b-eukiki-final** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/gemma4-e4b-eukiki/final`
- **gemma-e4b-mascarade-final** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/gemma4-e4b-mascarade/final`
- **gemma-e4b-aggro-test** — base `lmstudio-community/gemma-4-E4B-it-MLX-4bit` + adapter `/Users/electron/lora-adapters/aggro-test`

## Dataset: `kicad-dsl`

| Combo | n | parse_ok | composite | extras |
|---|---:|---:|---:|---|
| **gemma-e4b-eukiki-final** | 20 | 0.50 | 0.640 | fields_complete_rate=0.95, pin_count_match_rate=0.4, fplist_balanced_rate=1.0 |
| **gemma-e4b-mascarade-final** | 20 | 0.00 | 0.090 | fields_complete_rate=0.0, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |
| **gemma-e4b-aggro-test** | 20 | 0.00 | 0.090 | fields_complete_rate=0.0, pin_count_match_rate=0.05, fplist_balanced_rate=1.0 |

## Dataset: `kicad-pcb`

| Combo | n | parse_ok | composite | extras |
|---|---:|---:|---:|---|
| **gemma-e4b-eukiki-final** | 20 | 0.05 | 0.430 | structure_ok_rate=1.0, pad_count_match_rate=0.05, has_at_rate=1.0 |
| **gemma-e4b-mascarade-final** | 20 | 0.00 | 0.010 | structure_ok_rate=0.0, pad_count_match_rate=0.05, has_at_rate=0.0 |
| **gemma-e4b-aggro-test** | 20 | 0.00 | 0.010 | structure_ok_rate=0.0, pad_count_match_rate=0.05, has_at_rate=0.0 |

## Dataset: `spice-sim`

| Combo | n | parse_ok | composite | extras |
|---|---:|---:|---:|---|
| **gemma-e4b-eukiki-final** | 20 | 0.65 | 0.676 | has_end_rate=0.5, ground_present_rate=0.75, balanced_rate=0.65 |
| **gemma-e4b-mascarade-final** | 20 | 0.00 | 0.176 | has_end_rate=0.0, ground_present_rate=0.05, balanced_rate=0.0 |
| **gemma-e4b-aggro-test** | 20 | 0.00 | 0.189 | has_end_rate=0.0, ground_present_rate=0.0, balanced_rate=0.0 |
