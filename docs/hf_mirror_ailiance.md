# HuggingFace Mirror — Ailiance-fr

Public-facing mirror of selected `electron-rare/*` datasets onto `Ailiance-fr/*`
(French AI org, EU AI Act context). Mirrors preserve cardData, licenses, and
all sample/inventory files. Each mirror README carries a prominent provenance
note pointing back to the `electron-rare/*` canonical version.

## Mapping

| Source (canonical)                          | Mirror (Ailiance-fr)                          | Date mirror   | License       | Status compliance |
|---------------------------------------------|-----------------------------------------------|---------------|---------------|-------------------|
| `electron-rare/kicad9plus-permissive`       | `Ailiance-fr/kicad9plus-permissive`           | 2026-05-11    | CC-BY-SA-4.0  | Clean — permissive split (Apache/MIT/CC0/CERN-OHL-P), 98 samples, EU AI Act template July 2025 |
| `electron-rare/kicad9plus-copyleft`         | `Ailiance-fr/kicad9plus-copyleft`             | 2026-05-11    | GPL-3.0       | Clean — copyleft split (GPL-3/CERN-OHL-S/EUPL-1.2), 209 samples, EU AI Act template July 2025 |
| `electron-rare/kill-life-embedded-qa`       | `Ailiance-fr/kill-life-embedded-qa`           | 2026-05-11    | CC-BY-SA-4.0  | Clean — 100% original Kill_LIFE KB (≈30 samples aggregated, alpaca format) |

## URLs

- https://huggingface.co/datasets/Ailiance-fr/kicad9plus-permissive
- https://huggingface.co/datasets/Ailiance-fr/kicad9plus-copyleft
- https://huggingface.co/datasets/Ailiance-fr/kill-life-embedded-qa

## What is NOT mirrored (deliberately)

These remain `electron-rare/*` only until compliance audits land:

- `electron-rare/mascarade-{power,dsp,emc,kicad,...}` — pending Stack Exchange API
  attribution audit (PARTIAL ATTRIBUTION warning on some splits).
- `electron-rare/mascarade-{stm32,spice,iot,embedded}` — clean but waiting for the
  full mascarade compliance pass to be mirrored as a coherent family.
- `electron-rare/kicad9plus-sch-corpus` — deprecated (replaced by the two splits
  above after the CC-BY-SA-4.0 / GPL compatibility audit).

## Mirror procedure (reference)

```bash
HF=/Users/electron/mlx-stack/.venv/bin/hf
NAME=<dataset>
$HF repo create Ailiance-fr/$NAME --type dataset
$HF download electron-rare/$NAME --repo-type dataset --local-dir /tmp/mirror_$NAME
# Drop .cache/, add provenance note at top of README.md
$HF upload Ailiance-fr/$NAME /tmp/mirror_$NAME --repo-type dataset
```

Mirror READMEs carry this header (added by hand on the mirrored copy):

> **Mirror of `electron-rare/<name>`** — see original for canonical version and
> changelog. Maintained by Ailiance-fr (French AI org, EU AI Act context).

## Next steps

- Mirror clean `mascarade-{stm32,spice,iot,embedded}` once SE attribution audit
  is locked across the whole `mascarade-*` family (consistent provenance).
- Once SE API key arrives, complete the `mascarade-{power,dsp,emc,kicad}`
  attribution recovery (task #23), then mirror those too.
- Consider mirroring evaluation / bench-result artefacts on Ailiance-fr once the
  bench-kicad9plus full pipeline (task #27) lands stable numbers.
