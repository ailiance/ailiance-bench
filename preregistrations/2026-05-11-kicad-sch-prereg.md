# KiCad-SCH Generation Gap — Pre-registration

**Date locked:** 2026-05-11
**Author:** Clément Saillant (LElectron Rare)
**Spec:** `docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md`
**Status:** Locked BEFORE any Track C training run or Track D inference run.

This pre-registration follows OSF conventions. Any deviation from the
hypotheses, stopping rules, or seed list below must be documented as an
amendment commit referencing this file.

## Hypotheses

### H1 (primary) — LoRA dataset ordering

LoRA-C-D3-qwen36 > LoRA-C-D1-qwen36 > LoRA-C-D2-qwen36 on N3 composite.

- Test: one-sided paired t-test per pair.
- Multiple-comparison correction: Bonferroni, alpha = 0.0167 (3 comparisons).
- Effect-size threshold: Cohen d >= 0.5.

### H2 — DSL pipeline ordering

Pipeline-D-skidl > Pipeline-D-tscircuit on `parse_ok` rate.

- Test: one-sided z-test on proportions, alpha = 0.05.

### H3 — Track C vs Track D semantic equivalence

max(LoRA-C N3 composite) >= max(Pipeline-D N3 composite) on the
`sem_equiv` axis.

- Test: 5-seed bootstrap CI 95% non-overlap.

## Stopping rules

- If after 5 seeds the composite CI 95% overlaps 0 for any D1-LoRA cell,
  that cell is dropped from H1 and reported as inconclusive.
- If `dsl_parse_ok` < 0.2 for any Track-D pipeline, that pipeline is
  dropped from H2.

## Seed list (locked)

```
[42, 137, 1024, 8675309, 31415]
```

Every cell (Track C LoRA, Track D pipeline) is evaluated at all 5 seeds.
Bootstrap CI 95% is reported on the composite mean.

## Reproducibility envelope

- All configs YAML versioned in `KIKI-Mac_tunner/configs/`.
- `requirements.lock` per run (uv).
- KiCad CLI pinned: `kicad-cli 10.0.2`.
- Docker images pinned by sha256 digest (iact-bench v0.2.0).
- NDJSON audit logs append-only, sha256-signed manifest at run end.

## Amendments

(none yet)
