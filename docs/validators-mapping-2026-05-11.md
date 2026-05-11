# Bench domains → iact-bench validators mapping (2026-05-11)

Cross-reference between the 32 bench domains we evaluate (PPL matrix v1+v2)
and the 25 functional validators in `electron-rare/iact-bench` v0.2.0.

## Coverage summary

- **13/32 domains** have at least one direct functional validator (41%).
- **19/32 domains** are pure NLP/semantic — no programmatic validator fits.
- **2 gaps** in iact-bench: `compile-python` and `compile-rust` (filed as PR — link TBD).

## Domains with functional validators (13)

| Bench domain | Validator(s) | Validator type |
|---|---|---|
| `cpp` | `compile-cpp` | compile (gcc/clang) |
| `html-css` | `parse-html-css` | parse |
| `typescript` | `compile-typescript` | compile (tsc) |
| `shell` | `compile-shell` | shellcheck/bash -n |
| `yaml-json` | `compile-yaml-json` | parse (yaml.safe_load / json.loads) |
| `sql` | `parse-sql` | parse (sqlparse) |
| `rust-embedded` | `compile-rust-embedded` | compile (rustc --target thumbv7em-…) |
| `platformio` | `compile-platformio` | build (pio run) |
| `embedded` | `idf-build` | build (ESP-IDF idf.py build) |
| `kicad-dsl` | `atopile-build`, `skidl-erc`, `tscircuit-build`, `circuit-synth-build` | DSL→SCH compilers |
| `kicad-pcb` | `kicad-drc`, `kicad-erc` | DRC/ERC checkers |
| `spice-sim` | `ngspice-converge`, `xyce-converge`, `lcapy-analyze` | simulators |
| `freecad` | `freecad-script`, `cadquery-build`, `build123d-build`, `openscad-render`, `jscad-build`, `implicit-build` | CAD execution |

## Domains without direct validators (19)

| Bench domain | Reason | Possible future validator |
|---|---|---|
| `chat-fr` | NLP/semantic | LLM-as-judge (out of iact-bench scope) |
| `docker-devops` | infra config | `docker build --check` possible |
| `electronics` | knowledge domain | none direct; could re-use `kicad-erc` for circuits |
| `emc-dsp-power` | analog/EE knowledge | none direct |
| `iot` | architectural | could re-use `idf-build` for ESP32 IoT code |
| `llm-ops` | infra/devops | none direct |
| `llm-orch` | architectural | none direct |
| `lua-upy` | embedded scripting | `compile-lua-upy` would be ideal (gap) |
| `math-gsm8k` | math/reasoning | symbolic solver as judge |
| `math-reasoning` | math/reasoning | idem |
| `ml-training` | infra/code | indirect via `compile-python` (PR) |
| `multilingual-eu` | translation | LLM-as-judge |
| `music-audio` | creative/audio | none direct |
| `python` | code-gen | **`compile-python` (PR)** |
| `rust` | code-gen | **`compile-rust` (PR)** |
| `security-fenrir` | semi-formal | none direct |
| `traduction-tech` | translation | LLM-as-judge |
| `web-backend` | code-gen | could re-use `compile-typescript` |
| `web-frontend` | code-gen | idem |

## 3-axis matrix opportunity

For the 13 covered domains × 5 models × tuned/base = 130 cells where we
*could* add a third axis to the existing PPL + accuracy comparison:

| Axis | Source | Coverage |
|---|---|---|
| `ppl` | `eval_framework.py` + `bench_base.py` | 96+30+64+18 = 208 cells (all 32 domains) |
| `accuracy` | `lm_eval_base_2026-05-11.sh` (Studio) | 15 runs (5 models × 3 tasks), in progress |
| **`validator_pass_rate`** | iact-bench `chain_policy=deliberate` via PR #21 orchestrator | **TBD — 130 cells if F1 fires** |

The validator axis catches **catastrophic forgetting silencieux** : cells where
PPL says "improvement" but the generated code doesn't compile/parse. Our PPL
matrix can't see this; lm-eval-harness catches it on standard benchs but not
on our domain-specific niches.

## References

- iact-bench v0.2.0: `electron-rare/iact-bench:configs/domain_validators.yaml`
- Orchestrator wire-up: `ailiance/ailiance#21` (merged 2026-05-11 02:42), uses `IactBenchValidator` shim with lazy import.
- PPL matrix: `ailiance/ailiance-bench:docs/comparison_v{1,2}_2026-05-11.md`
- lm-eval-harness in-progress: Studio `~/ailiance/output/lm-eval-base-2026-05-11/`
