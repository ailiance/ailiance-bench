# KiCad-SCH Generation Gap — Risk Register

**Date:** 2026-05-11
**Spec:** `docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md`

| Risk | Probability | Mitigation |
|---|---|---|
| D1 scrape < 1k after license + dedup filter | Medium | Augment via D2 synth weighted-up; if D1 < 1k, ablation reports "D1 insufficient" |
| Ctx fenetre saturee (lib_symbols inline) | High | Strip lib_symbols pre-training, lib_id reference resolution at load time |
| Track-D compilers crash on LLM DSL | High | Capture rc, mark pipeline failed:syntax, separate `dsl_parse_ok` metric |
| sem_equiv graph iso too slow on large refs | Low | Limit to refs with <=15 components; skip if larger |
| License contamination in D1 | Medium | `licensecheck` + manual review top-100 repos before inclusion; reject if no LICENSE file |
| Watermark `;;` interferes with kicad-cli parse | Low | Smoke test before activation; fallback to no watermark |
| Studio compute contention (F1 still running) | Medium | Schedule Track C training after F1 completes (~07:30 CEST) |

## Tracking

Risks are revisited at the end of each phase (0/1/2/3/4/5/6) listed in
the spec §"Implementation order". Probability updates and observed
materialisations are appended below as dated entries.

## Materialisations

(none yet)
