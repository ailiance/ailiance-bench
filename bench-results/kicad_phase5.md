# KiCad Phase 5 — ERC delta vs reference (base)

_Generated: 2026-05-11 05:16:37_

- Source phase4   : `/Users/electron/bench-results/kicad_phase4.json`
- Refs            : `/Users/electron/eu-kiki-data/kicad-sch-gen/valid.jsonl`
- KiCad CLI       : `/opt/homebrew/bin/kicad-cli` (10.0.2)
- Score weights   : 0.30 parse_ok + 0.40 no_extra_errs + 0.30 no_extra_warns (caps 5/10)

## Reference ERC (per id)

| id | via | errs_ref | warns_ref |
|---|---|---:|---:|
| esp32_mini | kicad-cli | 7 | 16 |
| led_blinker | kicad-cli | 3 | 4 |
| ne555_astable | kicad-cli | 5 | 8 |
| opamp_noninv | kicad-cli | 5 | 6 |
| voltage_divider | kicad-cli | 3 | 4 |

## Re-score per model

| Model | n | composite_v1 | composite_v2 | avg errs_delta | avg warns_delta |
|---|---:|---:|---:|---:|---:|
| **gemma-e4b-eu-kiki-base** | 5 | 0.060 | 0.060 | 0.00 | 0.00 |
| **gemma-e2b** | 5 | 0.051 | 0.051 | 0.00 | 0.00 |
| **ministral-3b** | 5 | 0.042 | 0.042 | 0.00 | 0.00 |
| **ministral-3-8b** | 5 | 0.060 | 0.060 | 0.00 | 0.00 |
| **ministral-3-14b-instruct** | 5 | 0.051 | 0.051 | 0.00 | 0.00 |
| **ministral-3-14b-reasoning** | 5 | 0.060 | 0.060 | 0.00 | 0.00 |
| **granite-4.1-3b** | 5 | 0.060 | 0.060 | 0.00 | 0.00 |
