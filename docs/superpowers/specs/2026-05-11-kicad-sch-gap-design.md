# KiCad-SCH Generation Gap — Design Spec (EU AI Act compatible)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this design.

**Date:** 2026-05-11
**Author:** Clément Saillant (LElectron Rare)
**Status:** Approved (brainstorm 2026-05-11 05:14-05:37 CEST)
**Goal:** Close the `.kicad_sch` v10 generation gap (parse_ok_cli=0 across 10 models, phase4/5 bench 2026-05-11) via two parallel tracks (C: LoRA training, D: hybrid DSL→compiler) with EU AI Act audit-grade methodology.

## Track A — Diagnostic (DONE)

Phase4/5 bench on macM1 (`~/ailiance-bench/bench-results/kicad_phase{4,5}{,_lora}.json`):
- All 10 models (7 base + 3 LoRA) score `parse_ok_kicad_rate = 0.0` via `kicad-cli sch erc` (rc=3, "Échec du chargement de la schématique").
- `parse_ok_any_rate = 1.0` via lenient py_partial parser — models DO emit balanced S-expressions.
- Per-sample `parse_ok_score` ranges 0.2-0.6 — partial schema present.
- **Root cause:** non-compliance with KiCad v10 strict schema (missing required `version`, `generator`, `paper`, `lib_symbols`, valid UUIDs, sheet metadata), NOT inability to generate S-expressions.

The widely-cited "P4/P5 ≤ 0.06" verdict is a metric-floor artifact: composite weight `0.30·parse_ok + 0.40·no_extra_errs + 0.30·no_extra_warns` yields ~0.06 when parse_ok=0 because ERC cannot run (err/warn counts default to 0).

## Architecture

```
Track A (DONE) → Diagnostic locked
       │
       ├──→ Track C (LoRA training, ~24h Studio)
       │      6 LoRAs = {qwen36, gemma-e4b} × {D1, D2, D3}
       │      Output: ~/ailiance/adapters/v3/kicad-sch-{model}-{dataset}/
       │
       ├──→ Track D (Hybrid DSL→compiler, ~4h inference)
       │      20 pipelines = 5 base models × {skidl, atopile, tscircuit, circuit-synth}
       │      Output: output/hybrid_kicad_sch_2026-05-11.json
       │
       └──→ Eval N3 5-axis (~12-16h, 5 seeds × 26 cells)
              parse_ok / erc_clean / sch_render / drc_clean / sem_equiv
              Composite: 0.3·parse + 0.3·erc + 0.15·render + 0.1·drc + 0.15·sem
```

## Track C — LoRA training

### Datasets (3 splits, ablation)

| Split | Source | Volume target | Path |
|---|---|---:|---|
| **D1 scraped** | GitHub `*.kicad_sch` (license-filtered MIT/Apache/CC0/GPL), `kicad-cli sch update` to v10 strict, hash-dedupe | 1k-10k | `~/ailiance-data/kicad-sch-scraped/` |
| **D2 synth** | 10k random circuit templates → {skidl + atopile + circuit-synth} compile → `.kicad_sch` v10 | 10k-30k | `~/ailiance-data/kicad-sch-synth/` |
| **D3 mixed** | 50/50 random sample from D1 + D2 | 10k-20k | `~/ailiance-data/kicad-sch-mixed/` |

Each split ships a `manifest.csv` (EU AI Act Annex IV §2.b lineage requirement):
```
source_type,source_url,commit_sha,license_spdx,dedup_hash,file_size_bytes,kicad_version_before,kicad_version_after
```

For D2/D3 synth rows, `source_url` is replaced by the generator config + seed pair.

### Pre-processing pipeline

- Strip `(lib_symbols ...)` block (10-50KB → external `(lib_id "...")` reference). Justified: kicad-cli resolves from system symbol libraries at load time. Reduces ctx from 5-50KB → 2-5KB per file.
- Validate post-strip via `kicad-cli sch erc` round-trip — files that fail this gate are excluded.
- Canonical UUID normalization (`00000000-0000-0000-0000-...` placeholder, regenerated at gen time).

### Training config

- Framework: MLX `mlx_lm.lora` on Studio M3 Ultra (cf. `feedback_mlx_not_pytorch_macos.md`).
- Hyperparameters: rank=16, alpha=32, scale=2.0 (cf. v2 patch from session 2026-05-11), lr=1e-4, batch=1, grad_accum=8.
- Context: 8K (qwen36) or 16K (gemma-e4b extended via YaRN if needed).
- Seeds: training run uses `seed=42` deterministic; eval uses 5-seed list (below).
- Adapter output: `~/ailiance/adapters/v3/kicad-sch-{model}-{dataset}/`.
- Configs versioned at `KIKI-Mac_tunner/configs/ailiance-v3-{model}-kicad-sch-{dataset}.yaml`.

### Models (M2 execution)

- **qwen36** : Qwen3.6-A3B (already v2-tuned on 18 cells, MLX infra rodée)
- **gemma-e4b** : lmstudio gemma-4-E4B-it MLX-4bit (already in prod via `ailiance-gemma4`)

Total: 2 models × 3 datasets = **6 LoRAs**.

### M3/M4 expansion (doc-only)

| Wave | Add | Total LoRAs | Compute |
|---|---|---:|---:|
| M2 (executed) | qwen36 + gemma-e4b | 6 | ~24h |
| M3 | + devstral-22b | 9 | +15h (~39h cum) |
| M4 | + apertus, eurollm, medium35 | 18 | +45h (~84h cum) |

Config templates pre-generated for M3/M4 but training **deferred** until M2 results known.

## Track D — Hybrid DSL→compiler

### Pipeline

For each (base model, compiler) pair:
1. **System prompt** : "You generate `{compiler}` source code for the requested circuit. Output only the code block."
2. **LLM gen** : base model (no LoRA), 5 seeds, temperature=0.2, max_tokens=2048.
3. **Compiler invoke** : Docker via iact-bench v0.2 validator OR local CLI fallback.
4. **`.kicad_sch` capture** : compiler output file.
5. **Eval N3** : 5-axis on captured file.

### Compilers (E5)

| Pipeline ID | Compiler | Validator | Local CLI |
|---|---|---|---|
| E1 | skidl | iact-bench-skidl | `python -c "from skidl import *; ..."` |
| E2 | atopile | iact-bench-atopile | `ato build` |
| E3 | tscircuit | iact-bench-tscircuit | `npx tsci build` |
| E4 | circuit-synth | iact-bench-circuit-synth | `python -m circuit_synth.build` |

### Base models (E5 × 5)

- apertus-8b, devstral-22b-4bit, eurollm-22b, qwen36-A3B, medium35

Total: 5 × 4 = **20 pipelines** (no training, inference-only).

### Failure modes tracked

- `dsl_parse_ok` : compiler accepts LLM-generated DSL (binary)
- `compile_ok` : compiler emits `.kicad_sch` (binary)
- `kicad_load_ok` : downstream parse_ok (binary)
- Pipelines failing at `dsl_parse_ok` mark `kicad_load_ok=0` and short-circuit the rest of N3.

## Eval N3 — 5-axis metric

| Axis | Definition | Tool | Range |
|---|---|---|---:|
| `parse_ok` | `kicad-cli sch erc <file>` rc==0 | kicad-cli 10.0.2 | {0,1} |
| `erc_clean` | erc errors_count==0 | kicad-cli | {0,1} |
| `sch_render` | `kicad-cli sch export svg <file>` rc==0 | kicad-cli | {0,1} |
| `drc_clean` | sch→pcb netlist + `pcbnew --drc` rc==0 | kicad-cli + pcbnew | {0,1} |
| `sem_equiv` | netlist graph isomorphism cosine sim vs reference | networkx + custom | [0,1] |

### Composite

```
score = 0.3·parse_ok + 0.3·erc_clean + 0.15·sch_render + 0.1·drc_clean + 0.15·sem_equiv
```

Weights rationale:
- `parse_ok` (0.3) and `erc_clean` (0.3) dominate because they are necessary gates.
- `sch_render` (0.15) and `sem_equiv` (0.15) capture quality beyond compliance.
- `drc_clean` (0.1) low weight because depends on PCB layout (downstream concern, partial credit).

### Reference set

5 baseline circuits from `~/ailiance-data/kicad-sch-refs/` (led_blinker, voltage_divider, ne555_astable, opamp_noninv, esp32_mini) + 10 additional templates to be added pre-run.

### Seed protocol

**Seed list (locked, 5 seeds for multi-seed-first-class compliance):**
`[42, 137, 1024, 8675309, 31415]`

Every cell evaluated at all 5 seeds. Bootstrap CI 95% reported on composite mean.

## EU AI Act mapping

| Article / Annex | Requirement | This design |
|---|---|---|
| Annex IV §2.b | Training data lineage | D1/D2/D3 `manifest.csv` with source URL, commit SHA, license SPDX |
| Annex IV §2.c | Validation methodology | This document + `iact-bench/docs/methodology.md` §8 |
| Annex IV §3 | Performance metrics | N3 5-axis × 5 seeds + bootstrap CI 95% |
| Annex IV §7 | Logging | NDJSON audit trail `~/ailiance/output/audit/kicad-sch-2026-05-11/*.ndjson`, sha256-signed at run end |
| Art 13 | Transparency | `model_card.md` per LoRA: config + manifest + perf + limitations |
| Art 15 | Accuracy / robustness | Adversarial subset (10% valid set), refusal/clarification check |
| Art 50 | Disclosure | Optional output watermark `;; generated by ailiance-v3-{model}-{dataset}-{adapter_sha}` (flag-gated; tested for parser compat) |

### Risk classification

- **Use case:** EDA copilot, productivity tool for hardware engineers
- **Annex III applicable:** No (not safety-critical / medical / transport / biometric / law enforcement)
- **Title III obligations:** Limited risk — transparency obligations recommended by prudence, not strictly mandated
- **Risk register:** `~/ailiance-bench/docs/superpowers/specs/risks/2026-05-11-kicad-sch-risks.md` (to be created during implementation)

## Pre-registration (OSF-style, hypothesis lock)

**Location:** `~/ailiance-bench/preregistrations/2026-05-11-kicad-sch-prereg.md` (committed BEFORE any training run).

**H1 (primary):** LoRA-C-D3-qwen36 > LoRA-C-D1-qwen36 > LoRA-C-D2-qwen36 on N3 composite.
- Test: one-sided paired t-test per pair, Bonferroni alpha=0.0167 (3 comparisons).
- Effect size threshold: Cohen d ≥ 0.5.

**H2:** Pipeline-D-skidl > Pipeline-D-tscircuit on `parse_ok` rate.
- Test: one-sided z-test on proportions, alpha=0.05.

**H3:** max(LoRA-C N3 composite) ≥ max(Pipeline-D N3 composite) on `sem_equiv` axis.
- Test: 5-seed bootstrap CI 95% non-overlap.

**Stopping rules:**
- If after 5 seeds, composite CI 95% overlaps 0 for any D1-LoRA cell → drop that cell from H1 (report as inconclusive).
- If `dsl_parse_ok` < 0.2 for any Track-D pipeline → drop pipeline from H2.

## Reproducibility envelope

- All configs YAML versioned in `KIKI-Mac_tunner/configs/` (commit SHA referenced from manifest).
- `requirements.lock` per run (uv), pinning MLX + mlx_lm + mlx-core versions (cf. Mistral 0.30.6 episode 2026-05-10).
- KiCad CLI version locked: `kicad-cli 10.0.2` (Homebrew installed on macM1, Docker images use `kicad/kicad:10.0.2` pinned by digest).
- Docker images pinned by sha256 digest (already done for 12 validators in iact-bench v0.2.0).
- Seeds: `[42, 137, 1024, 8675309, 31415]` (deterministic across all runs).
- NDJSON audit logs append-only, sha256-signed manifest at end of each run.

## Risks & mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| D1 scrape < 1k after license + dedup filter | Medium | Augment via D2 synth weighted-up; if D1 < 1k, ablation reports "D1 insufficient" |
| Ctx fenêtre saturée (lib_symbols inline) | High | Strip lib_symbols pre-training, lib_id reference resolution at load time |
| Track-D compilers crash on LLM DSL | High | Capture rc, mark pipeline failed:syntax, separate `dsl_parse_ok` metric |
| sem_equiv graph iso too slow on large refs | Low | Limit to refs with ≤15 components; skip if larger |
| License contamination in D1 | Medium | `licensecheck` + manual review top-100 repos before inclusion; reject if no LICENSE file |
| Watermark `;;` interferes with kicad-cli parse | Low | Smoke test before activation; fallback to no watermark |
| Studio compute contention (F1 still running) | Medium | Schedule Track C training after F1 completes (~07:30 CEST) |

## Implementation order (suggested for writing-plans)

1. **Phase 0** (~2h) : Pre-reg lock + risk register doc
2. **Phase 1** (~1-2 days) : D1 scraper + D2 synth generator + D3 mixer → manifests
3. **Phase 2** (~6h smoke + 24h full) : Train 6 LoRAs Track C (1 sample run first, then full)
4. **Phase 3** (~4h) : Run 20 pipelines Track D
5. **Phase 4** (~12-16h) : N3 5-axis eval × 5 seeds × 26 cells
6. **Phase 5** (~4h) : `bench_comparison.py` extension for `--metric-axes`, output table MD
7. **Phase 6** (~2h) : Model cards + audit trail signing + write-up

Total wall-time: ~4-5 days non-stop on Studio + macM1 + electron-server.

## References

- `ailiance-bench/docs/validators-mapping-2026-05-11.md` — 32 domains × 25 validators mapping
- `ailiance-bench/docs/comparison_v{1,2}_2026-05-11.md` — current PPL bench v1/v2 results
- `ailiance-bench/bench-results/kicad_phase{2,3,4,5}{,_lora}.{md,json}` — Track A source data
- `iact-bench/docs/methodology.md` §8 — audit walkthrough + AI Act mapping
- `ailiance-data/kicad-sch-refs/spi_bus_4devices.kicad_sch` — sample reference target
- ailiance PR #24 (`f01fa36`) — `bench_comparison.py` validator_lift 3rd axis
- ailiance PR #21 (`8118ec0`) — ChainOrchestrator + IactBenchValidator shim
- `feedback_multi_seed_first_class.md` — methodology requirement (5+ seeds)
- `feedback_mlx_not_pytorch_macos.md` — MLX over PyTorch on macOS
