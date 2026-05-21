# AGENTS.md

Guidance for AI coding agents (Claude Code, Aider, Cursor, etc.) working in this repo.

## Project

`ailiance-bench` — MLX benchmarking suite for open-source models and **Ailiance** fine-tunes on Apple Silicon. Evaluates via perplexity on 5 embedded niches (`spice`, `stm32`, `kicad`, `embedded_iot`, `emc_power`) and a Phase 6 LoRA scoreboard (7 KiCad/SPICE tasks × 4 adapters). Audit-grade for EU AI Act Art. 13/15/52/53. Repo `ailiance/ailiance-bench`, branch `main`.

## Tech stack

- Language: Python (Mac native, `requirements.txt`-driven)
- Runtime: pinned venv aligned with `KIKI-Mac_tunner` (MLX 0.31 stack — see that repo's requirements.txt)
- Test: `pytest` (under `tests/`)
- Bench artifacts: `bench-results/` (`BENCH_TABLE.md`, `compare_base_vs_lora.md` are sources of truth)
- Grist integration: schema `Bench_31_domains` (16 columns) on Ailiance Grist
- Companion: `vendored/iact-bench` submodule (audit-grade validators) — initialised in production gateway, optional locally
- LoRA curriculum + mascarade eval live in dedicated subtrees

## Commands

```bash
pip install -r requirements.txt
pytest tests/ -v
python scripts/<bench_script>.py                # run a niche bench
bash scripts/run_phase6_scoreboard.sh           # regenerate Phase 6 table
```

## Conventions

- Commits: subject ≤ 50 chars, body ≤ 72, no underscore in scope, no AI attribution, never `--no-verify`.
- Branches: `feat/<name>`, `fix/<name>`, `docs/<name>`, `bench/<name>`, `grist/<name>`.
- French in prose; English in code/commits.
- Bench results are append-only artifacts. Do not rewrite history of `bench-results/*.md` — produce a new dated snapshot and link from `README.md`.

## File layout

- `bench-results/` — `BENCH_TABLE.md` (12-model scoreboard), `compare_base_vs_lora.md` (Phase 6 LoRA table), per-task JSON
- `lora-curriculum/` — curriculum specs for the LoRA training cycles
- `mascarade-eval/` — eval harness for the mascarade adapters (kicad / spice / stm32 / emc / embedded / platformio / freecad / dsp / iot / power)
- `preregistrations/` — pre-registered evaluation protocols (audit-grade)
- `patches/` — local patches to lm-eval / mlx-lm / harnesses
- `ops/` — Grist population scripts, gateway ingestion glue
- `scripts/` — bench drivers, scoreboard generators
- `tests/` — unit/integration

## Domain-specific gotchas

- **Bench winners (Phase 6)**: `eu-kiki` is the generalist champion (4/7, peak P1-DSL +55); `mascarade` wins P3 extraction (+48); **`kicad9plus` causes catastrophic forgetting** (-31 on P3) — DO NOT recommend it as a default and add a warning if you write new cards/READMEs.
- **`parse_kicad=0` everywhere on P4/P5**: from-scratch `.kicad_sch` generation is unsolved — bottleneck is absence of KiCad 6+ S-expr in pre-training, **not** the chat mode. Don't fix by "tuning prompts".
- **Apple Silicon only** for the MLX benches; CPU fallback is not exercised.
- **Pin matters**: align with `KIKI-Mac_tunner` requirements.txt (`mlx==0.31.2`, `mlx-lm==0.31.3`, `lm-eval==0.4.11`). Bumping versions invalidates the historical scoreboard.
- **`vendored/iact-bench` submodule** is required to drop the StubValidator fallback in production. Locally, run `git submodule update --init --recursive` only if you actually need real validators (heavy).
- **Grist Bool gotcha**: `ModifyColumn Text→Bool` does NOT re-parse — values become ascii-byte Buffers and break SUM. Get typing right at column creation, or drop+recreate the table; never retype Bool post-hoc. (Memory: `feedback_grist_bool_retype_corruption.md`.)
- **Judge model**: production judge is `mistral-medium` via `gateway.ailiance.fr`; when that 500s, fall back to `mistral-small`. Document the judge used in any bench result you publish.
- **Mascarade routing reality (2026-05-18)**: production serves mascarade in MLX **bf16** on MacStudio `:9340` (PR #100), not Tower Q4. The Tower Q4 path is rollback only. Eval runs should target whichever surface they intend to validate and say so explicitly.
- **HF cards**: license `apache-2.0` for models, datasets keep upstream license (often CC-BY-SA-4.0 / GPL-3.0) — do not relicense datasets.

## When in doubt

- Read `README.md` and the latest `bench-results/*.md`.
- Recent commits: `git log --oneline -20`.
- Memory: `~/.claude/projects/-Users-electron/memory/project_ailiance_bench_phase6_2026_05_11.md`, `project_ailiance_eval_harness_2026_05_18.md`, `project_iact_bench_2026_05_10.md`.
- Cluster context: `~/CLAUDE.md` (Studio + Tower + macM1 inference surfaces).
- Run `pytest tests/ -v` before non-trivial commits.
