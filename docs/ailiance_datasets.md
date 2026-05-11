# Ailiance datasets on Hugging Face

Ailiance (French AI org, EU AI Act context) co-publishes a family of electronics /
embedded-systems datasets on Hugging Face. Each Ailiance dataset is **co-published**
with the corresponding `electron-rare/*` upstream version — same license, same
sample/inventory files, but rebranded README putting Ailiance forward as the
production curator/maintainer while preserving full upstream attribution.

Previously framed as plain "mirrors" (see git history of `docs/hf_mirror_ailiance.md`),
the Ailiance copies are now treated as **Ailiance's official datasets** — same
content, but with branding, citation, and EU AI Act packaging aligned to Ailiance
as the curator of record.

## Branding strategy (co-publishing)

| Aspect                     | Ailiance role                                              | electron-rare role                                    |
|----------------------------|------------------------------------------------------------|-------------------------------------------------------|
| Repository ownership       | Owner of `Ailiance-fr/*`                                   | Owner of `electron-rare/*` (canonical)                |
| README branding            | Primary curator (pretty_name `Ailiance — ...`)             | Upstream contributor (cited, linked)                  |
| Citation (bibtex)          | Primary `@dataset{ailiance_<short>_2026, ...}`             | Secondary `@dataset{electron_rare_<short>_2026, ...}` |
| EU AI Act packaging        | Maintains Template AI Office July 2025 alignment           | Provides source pipeline + audit logs                 |
| Contact / opt-out          | `c.saillant@gmail.com` (Ailiance)                          | Same person, ailiance-bench repo for audit logs       |
| Data files (`.jsonl`)      | Identical to upstream — never re-edited                    | Source of truth                                       |
| Pipeline scripts           | Referenced (linked to ailiance-bench)                      | Lives at ailiance-bench/scripts/                      |

**No fork divergence**: data files are bit-identical to electron-rare/*. Only the
README differs (branding + citation + about-Ailiance + related-datasets sections).
A future re-pull / re-build of an electron-rare dataset would propagate to the
matching Ailiance-fr/* via the rebrand script (`~/scripts/rebrand_ailiance_readmes.py`).

## Catalog (11 datasets)

| Ailiance-fr name                                    | Upstream (electron-rare)              | License        | Samples | Pretty name (Ailiance)                                       |
|-----------------------------------------------------|---------------------------------------|----------------|---------|--------------------------------------------------------------|
| `Ailiance-fr/kicad9plus-permissive`                 | `kicad9plus-permissive`               | CC-BY-SA-4.0   |   98    | Ailiance — KiCad 9+ Schematic Corpus (Permissive)            |
| `Ailiance-fr/kicad9plus-copyleft`                   | `kicad9plus-copyleft`                 | GPL-3.0        |  209    | Ailiance — KiCad 9+ Schematic Corpus (Copyleft)              |
| `Ailiance-fr/kill-life-embedded-qa`                 | `kill-life-embedded-qa`               | CC-BY-SA-4.0   |   30    | Ailiance — Kill-LIFE Embedded Knowledge Base                 |
| `Ailiance-fr/mascarade-stm32-dataset`               | `mascarade-stm32-dataset`             | CC-BY-SA-4.0   | 2,012   | Ailiance — STM32 & ARM Cortex-M Q&A                          |
| `Ailiance-fr/mascarade-spice-dataset`               | `mascarade-spice-dataset`             | CC-BY-SA-4.0   | 3,091   | Ailiance — SPICE & Analog Simulation Q&A                     |
| `Ailiance-fr/mascarade-iot-dataset`                 | `mascarade-iot-dataset`               | CC-BY-SA-4.0   | 6,005   | Ailiance — IoT & Connected Devices Q&A                       |
| `Ailiance-fr/mascarade-embedded-dataset`            | `mascarade-embedded-dataset`          | CC-BY-SA-4.0   | 8,344   | Ailiance — Embedded Systems & Linux Q&A                      |
| `Ailiance-fr/mascarade-power-dataset`               | `mascarade-power-dataset`             | CC-BY-SA-4.0   | 3,267   | Mascarade — Power Electronics Q&A (✅ AUDITED — 4.87 % SE)   |
| `Ailiance-fr/mascarade-dsp-dataset`                 | `mascarade-dsp-dataset`               | CC-BY-SA-4.0   | 3,160   | Mascarade — DSP & Signal Processing Q&A (✅ AUDITED — 5.35 % SE) |
| `Ailiance-fr/mascarade-emc-dataset`                 | `mascarade-emc-dataset`               | CC-BY-SA-4.0   | 3,360   | Mascarade — EMC & EMI Q&A (✅ AUDITED — 4.05 % SE)           |
| `Ailiance-fr/mascarade-kicad-dataset`               | `mascarade-kicad-dataset`             | CC-BY-SA-4.0   | 2,645   | Mascarade — KiCad EDA Q&A (✅ AUDITED — 5.52 % SE)            |

URLs:

- https://huggingface.co/datasets/Ailiance-fr/kicad9plus-permissive
- https://huggingface.co/datasets/Ailiance-fr/kicad9plus-copyleft
- https://huggingface.co/datasets/Ailiance-fr/kill-life-embedded-qa
- https://huggingface.co/datasets/Ailiance-fr/mascarade-stm32-dataset
- https://huggingface.co/datasets/Ailiance-fr/mascarade-spice-dataset
- https://huggingface.co/datasets/Ailiance-fr/mascarade-iot-dataset
- https://huggingface.co/datasets/Ailiance-fr/mascarade-embedded-dataset
- https://huggingface.co/datasets/Ailiance-fr/mascarade-power-dataset
- https://huggingface.co/datasets/Ailiance-fr/mascarade-dsp-dataset
- https://huggingface.co/datasets/Ailiance-fr/mascarade-emc-dataset
- https://huggingface.co/datasets/Ailiance-fr/mascarade-kicad-dataset

## SE attribution audit (2026-05-11) — `mascarade-{power,dsp,emc,kicad}`

All four datasets carry per-sample Stack Exchange Electronics attribution after the
2026-05-11 audit (see [`audit_mascarade_se_attribution.md`](./audit_mascarade_se_attribution.md)).
The previous PARTIAL ATTRIBUTION DISCLOSURE bandeau ("~30 % SE") is replaced on all
4 × 2 = 8 dataset cards (electron-rare canonical + Ailiance-fr mirror) by the audited
numbers:

| Dataset                       | Total | SE confirmed | %     | Not-found-on-API | Synthetic | Over-count |
|-------------------------------|------:|-------------:|------:|-----------------:|----------:|-----------:|
| `mascarade-power-dataset`     | 3 267 |          159 | 4.87 %|              424 |     2 682 |     ~6.4×  |
| `mascarade-dsp-dataset`       | 3 160 |          169 | 5.35 %|              535 |     2 453 |     ~5.7×  |
| `mascarade-emc-dataset`       | 3 360 |          136 | 4.05 %|              482 |     2 740 |     ~7.6×  |
| `mascarade-kicad-dataset`     | 2 645 |          146 | 5.52 %|              386 |     2 108 |     ~5.6×  |

All 8 dataset cards now display ✅ **ATTRIBUTION AUDIT COMPLETED (2026-05-11)** as the
header bandeau, with per-sample `metadata.stack_exchange_attribution` for the 610
confirmed samples and `metadata.attribution_recovery` markers for the 1 827
not-found-on-API and 12 low-confidence samples.

## What is NOT co-published yet

- `electron-rare/kicad9plus-sch-corpus` — deprecated (replaced by `kicad9plus-permissive`
  / `kicad9plus-copyleft` after the CC-BY-SA-4.0 / GPL compatibility audit).

## Rebrand procedure

The rebrand is fully scripted and idempotent:

```bash
HF=/Users/electron/mlx-stack/.venv/bin/hf python3 ~/scripts/rebrand_ailiance_readmes.py
```

Per-dataset, the script:

1. Renders the README from the in-script spec (pretty_name, statistics,
   data-sources block, copyright block, sample format).
2. Wraps it with the shared blocks: header banner, **About Ailiance**,
   **Provenance & upstream attribution**, **License & EU AI Act**,
   **Citation** (dual: Ailiance primary + electron-rare upstream),
   **Related datasets**.
3. Uploads `README.md` only (never `.jsonl` / data files) via
   `hf upload Ailiance-fr/<name> ...`.
4. Verifies the published README contains the expected branding markers
   (`About Ailiance`, `Provenance`, audit URL, updated pretty_name).

Options:

- `--dry-run` — write rendered READMEs to `/tmp/rebrand_output/` and skip upload.
- `--only NAME` — process a single dataset.
- `--write-local` — additionally save the rendered README to `/tmp/rebrand_output/`.

## Verification (one-liner)

```bash
for name in kicad9plus-permissive kicad9plus-copyleft kill-life-embedded-qa \
            mascarade-stm32-dataset mascarade-spice-dataset \
            mascarade-iot-dataset mascarade-embedded-dataset \
            mascarade-power-dataset mascarade-dsp-dataset \
            mascarade-emc-dataset mascarade-kicad-dataset; do
  echo "=== $name ==="
  curl -sL "https://huggingface.co/api/datasets/Ailiance-fr/$name" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
cd = d.get('cardData', {})
print(' pretty_name:', cd.get('pretty_name', 'NONE'))
print(' license    :', cd.get('license', 'NONE'))
"
done
```

## Compliance preservation

All Ailiance READMEs preserve the legally-load-bearing sections from the upstream
electron-rare versions:

- EU AI Act Template AI Office July 2025 (data sources, processing, characteristics)
- Per-sample license metadata pointer (`metadata.license_spdx` for KiCad,
  `metadata.license` for Mascarade)
- Opt-out mechanism (Article 4(3) DSM Directive)
- TDM Reservation Protocol acknowledgement
- Upstream dataset attribution (Masala-CHAI, acon96/Home-Assistant-Requests,
  Stack Exchange, EEVblog)
- Audit log URL: `docs/audit_kicad9plus.md` (and the SE-specific
  `docs/audit_mascarade_se_attribution.md` referenced in the Provenance block).

## Scraping methodology

Future collections feeding any Ailiance dataset MUST go through the
EU-AI-Act-compliant pipeline documented in
[`scraping_compliance.md`](./scraping_compliance.md). The pipeline:

- runs `check_robots_txt` and `check_tdmrep` before every HTTP GET,
- uses the contactable User-Agent `Ailiance-Compliance-Crawler/1.0`,
- honors HTTP 429 + `Retry-After` and Stack Exchange `backoff`,
- persists a per-sample `compliance` block in every `.meta.json` sidecar,
- appends a JSONL audit trail to `~/eu-kiki-data/scraping_logs/`.

Source files: `scripts/scraping_compliant/lib_compliance.py`,
`scripts/scraping_compliant/scrape_kicad9plus.py`,
`scripts/scraping_compliant/scrape_se_attribution.py`.

## Models trained on these datasets

The Ailiance org also publishes 4 LoRA adapters on
`lmstudio-community/gemma-4-E4B-it-MLX-4bit` that use this dataset catalog as
training data. See [`ailiance_models.md`](./ailiance_models.md) for the full
catalog and benchmark matrix.

| Model                                                  | Status                | Primary training data                                                                                       |
|--------------------------------------------------------|-----------------------|-------------------------------------------------------------------------------------------------------------|
| `Ailiance-fr/gemma-4-E4B-eukiki-lora`                  | Champion general (4/7)| eu-kiki curation over kicad9plus-permissive + mascarade-spice + mascarade-embedded                          |
| `Ailiance-fr/gemma-4-E4B-mascarade-lora`               | Champion extraction   | mascarade-{stm32,spice,iot,embedded}                                                                        |
| `Ailiance-fr/gemma-4-E4B-aggro-test-lora`              | Sanity baseline       | curriculum phase-1 subset                                                                                   |
| `Ailiance-fr/gemma-4-E4B-kicad9plus-lora`              | Negative result       | kicad9plus-permissive only (98 samples)                                                                     |

## Future direction

- **Ailiance Hub** — Ailiance org page on HF surfaces these 11 datasets as the
  official catalog ; electron-rare/* stays as the canonical source / changelog
  reference.
- Audit récurrent : re-run `audit_remaining.py` every quarter (or before any
  major release) to verify new samples respect the per-sample attribution
  invariant.
- Ailiance fine-tuned models (e.g. Gemma-3n-E4B trained on this corpus) will
  cite the `Ailiance-fr/*` URLs as primary training data, with cross-links
  to `electron-rare/*` for archive.
