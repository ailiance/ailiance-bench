#!/usr/bin/env python3
"""
Rebrand Ailiance-fr/* dataset READMEs.

Transforme les "mirrors" simples de electron-rare/* en datasets Ailiance proprement
brandés : Ailiance = curator/maintainer principal, electron-rare = upstream contributor.

Preserve TOUTES les obligations légales (attribution upstream, opt-out, licenses,
EU AI Act sections, sample formats, source repos).

Usage:
    HF=/Users/electron/mlx-stack/.venv/bin/hf python3 rebrand_ailiance_readmes.py [--dry-run] [--only NAME]

Idempotent : on regénère toujours depuis la spec interne, donc relancer écrase l'ancien.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import urllib.request
import urllib.error


HF_BIN = os.environ.get("HF", "/Users/electron/mlx-stack/.venv/bin/hf")
ORG = "Ailiance-fr"
UPSTREAM_ORG = "electron-rare"
AUDIT_URL = "https://github.com/electron-rare/electron-bench/blob/main/docs/audit_kicad9plus.md"
SCRIPTS_URL = "https://github.com/electron-rare/electron-bench/tree/main/scripts"

ALL_NAMES = [
    "kicad9plus-permissive",
    "kicad9plus-copyleft",
    "kill-life-embedded-qa",
    "mascarade-stm32-dataset",
    "mascarade-spice-dataset",
    "mascarade-iot-dataset",
    "mascarade-embedded-dataset",
]


@dataclass
class DatasetSpec:
    name: str
    license_yaml: str  # cc-by-sa-4.0 / gpl-3.0
    license_display: str  # CC-BY-SA-4.0 / GPL-3.0-or-later
    pretty_name: str
    short_desc_fr: str  # 1-2 sentences French
    tags: list[str]
    size_category: str
    languages: list[str]
    task_categories: list[str]
    sample_count: str
    size_human: str
    format_desc: str
    citation_short: str  # for bibtex key (ailiance_<short>_2026)
    body_blocks: list[str] = field(default_factory=list)  # ordered content sections


# ---- Per-dataset content blocks (preserve legal/technical content) -----------

SAMPLE_KICAD_PERMISSIVE = """```json
{
  "messages": [
    {"role": "user", "content": "Generate a KiCad 9 schematic (titled '...', by ..., N components, libraries: ...). Use the standard S-expression format starting with `(kicad_sch ...)`."},
    {"role": "assistant", "content": "(kicad_sch\\n\\t(version 20250114)\\n\\t..."}
  ],
  "metadata": {
    "repo": "owner/name",
    "rel_path": "path/to/file.kicad_sch",
    "source_url": "https://github.com/owner/name/blob/<sha>/path/to/file.kicad_sch",
    "commit_sha": "<git sha>",
    "license_spdx": "Apache-2.0",
    "kicad_version": "20250114",
    "file_sha256": "<content sha>",
    "file_size_bytes": 12345,
    "downloaded_at": "2026-05-11T...",
    "compliance_notes": "...",
    "ia_act_status": "requires_review"
  }
}
```"""

SAMPLE_KICAD_COPYLEFT = SAMPLE_KICAD_PERMISSIVE.replace('"Apache-2.0"', '"GPL-3.0"')

SAMPLE_STM32 = '''```json
{
  "conversations": [
    {
      "from": "system",
      "value": "You are an expert STM32 and ARM Cortex-M embedded systems engineer. You write production-ready C firmware using STM32 HAL/LL drivers, CMSIS, FreeRTOS, and bare-metal register-level programming."
    },
    {
      "from": "human",
      "value": "Configure UART2 on STM32F4 at 115200 baud with DMA reception."
    },
    {
      "from": "gpt",
      "value": "Here's a complete UART2 + DMA setup for STM32F4: ..."
    }
  ]
}
```'''

SAMPLE_SPICE = '''```json
{
  "conversations": [
    {
      "from": "system",
      "value": "You are an expert analog circuit designer and SPICE simulation engineer. You write correct ngspice/LTspice netlists, debug convergence issues, perform AC/DC/transient analysis."
    },
    {
      "from": "human",
      "value": "Write a SPICE netlist for a common-emitter amplifier with voltage divider bias. Include AC analysis from 10Hz to 10MHz."
    },
    {
      "from": "gpt",
      "value": "Common-emitter amplifier with voltage divider bias: ..."
    }
  ]
}
```'''

SAMPLE_IOT = '''```json
{
  "conversations": [
    {
      "from": "system",
      "value": "You are an expert IoT and embedded systems engineer specializing in MQTT protocols, ESP32/ESP8266 with ESP-IDF, FreeRTOS, Home Assistant integration."
    },
    {
      "from": "human",
      "value": "Write ESP-IDF code for an MQTT client that publishes sensor data to a broker with TLS and auto-reconnection."
    },
    {
      "from": "gpt",
      "value": "ESP-IDF MQTT client with TLS and auto-reconnect: ..."
    }
  ]
}
```'''

SAMPLE_EMBEDDED = '''```json
{
  "conversations": [
    {
      "from": "system",
      "value": "You are an expert embedded systems engineer specializing in ARM Cortex-M, ESP32/ESP-IDF, and RISC-V architectures. You write production-grade firmware in C/C++."
    },
    {
      "from": "human",
      "value": "Write bare-metal ARM Cortex-M4 startup code in assembly with vector table and Reset_Handler."
    },
    {
      "from": "gpt",
      "value": "ARM Cortex-M4 bare-metal startup (GNU AS syntax): ..."
    }
  ]
}
```'''

SAMPLE_KILLLIFE = '''```json
{
  "instruction": "What is the ESP32-S3-WROOM-1-N16R8 module?",
  "input": "",
  "output": "The ESP32-S3-WROOM-1-N16R8 is the main MCU module of the Kill_LIFE board: ESP32-S3 dual-core LX7 + 16 MB flash + 8 MB PSRAM, used for the voice-companion pipeline and the LCD/audio peripherals.",
  "source": "rag:kb-components",
  "generated_at": "2026-03-27T05:11:28.145507+00:00"
}
```'''


# Per-dataset specifications (data sources + license/copyright sections preserved
# from the upstream electron-rare READMEs).

SPECS: dict[str, DatasetSpec] = {}


SPECS["kicad9plus-permissive"] = DatasetSpec(
    name="kicad9plus-permissive",
    license_yaml="cc-by-sa-4.0",
    license_display="CC-BY-SA-4.0",
    pretty_name="Ailiance — KiCad 9+ Schematic Corpus (Permissive)",
    short_desc_fr=(
        "Corpus de 98 schémas KiCad 9+ (`.kicad_sch`, format S-expression, "
        "version ≥ 20240722) collectés sous licences **permissives uniquement** "
        "(Apache-2.0, MIT, CC0-1.0, CERN-OHL-P-2.0). Pensé pour l'entraînement "
        "et le fine-tuning de modèles de génération de schémas EDA."
    ),
    tags=["kicad", "eda", "schematic", "s-expression", "electronics", "hardware", "ailiance"],
    size_category="n<1K",
    languages=["en", "fr"],
    task_categories=["text-generation"],
    sample_count="98",
    size_human="~1.2 MB JSONL (raw `.kicad_sch` ≈ 21 MB before chat-format wrapping)",
    format_desc="JSONL chat format (`messages` array, user/assistant)",
    citation_short="kicad9plus_permissive",
    body_blocks=[
        # --- Composition / split rationale ---
        """## Composition

**Permissive licenses only**: Apache-2.0 (74), MIT (20), CC0-1.0 (3), CERN-OHL-P-2.0 (1).

Permissive split of the original `electron-rare/kicad9plus-sch-corpus` (now deprecated). Le split a été réalisé après audit légal montrant l'incompatibilité CC-BY-SA-4.0 avec les entrées GPL-3 / CERN-OHL-S (compatibilité à sens unique : CC-BY-SA-4.0 → GPLv3, jamais l'inverse).

Pour les samples copyleft (GPL-3.0, CERN-OHL-S-2.0, EUPL-1.2) : voir [`Ailiance-fr/kicad9plus-copyleft`](https://huggingface.co/datasets/Ailiance-fr/kicad9plus-copyleft).""",
        # --- EU AI Act section ---
        """## EU AI Act compliance (Template AI Office, July 2025)

### General information
- **Name**: kicad9plus-sch-corpus (permissive subset)
- **Modality**: text (KiCad S-expression source)
- **Languages**: English (technical), French (some title-block descriptions)
- **Intended use**: entraînement / fine-tuning de modèles de génération de schémas KiCad 9 / KiCad 10

### Data sources

**Publicly available datasets**: None.

**Web scraping**: Yes — public GitHub repositories.
- Discovery method: `gh search code "(kicad_sch (version 202X)" extension:kicad_sch`
- Filtering: SPDX license whitelist (Apache-2.0, MIT, CC0-1.0, CERN-OHL-P-2.0)
- Per-sample provenance: see `metadata.source_url`, `metadata.commit_sha`, `metadata.repo`

**Licensed data**: None (no commercial / proprietary licenses).

### Data processing
- Sparse-clone with `gh repo clone --depth 1`
- Per-file `.meta.json` sidecar with `source_url`, `commit_sha`, `license_spdx`, `kicad_version`
- Deduplication via SHA-256 of file contents
- Truncation at 8 KB to fit training context (marked in metadata when applicable)
- Validation via `kicad-cli sch erc --format json --severity-all` (99.6% pass rate on tested subset)
- All processing scripts available at """ + SCRIPTS_URL + """

### Data characteristics
- **Size**: 98 samples, ~1.2 MB JSONL (raw `.kicad_sch` totals ~21 MB before chat-format wrapping)
- **License mix (input)**:
  - Apache-2.0: 74 samples (75.5%)
  - MIT: 20 (20.4%)
  - CC0-1.0: 3 (3.1%)
  - CERN-OHL-P-2.0: 1 (1.0%)
- **KiCad version mix**: 20250114 (KiCad 9 stable), 20250316, 20250610 (KiCad 9.0.1), 20260101 / 20260301 / 20260306 (KiCad 10)
- **Source repos**: 9 distinct upstream projects (full list in `LICENSE_INVENTORY.md`)""",
        # --- Sample format ---
        """## Sample format

Each line is a chat-format JSON object:

""" + SAMPLE_KICAD_PERMISSIVE,
        # --- Licenses ---
        """## Licenses applied

This dataset (the aggregated work) is released under **CC-BY-SA-4.0**.

Per-sample original licenses are **preserved in `metadata.license_spdx`** and listed in `LICENSE_INVENTORY.md`. Downstream users MUST preserve attribution per sample.

Apache-2.0 patent grant (§3) does NOT transfer through CC-BY-SA-4.0 — downstream users wishing to claim those grants must refer to the original sources.""",
        # --- Copyright ---
        """## Copyright considerations
- All sources are public GitHub repositories under permissive licenses.
- The `.kicad_sch` files are treated as software source under their original licenses.
- **Opt-out mechanism**: contact `c.saillant@gmail.com` (Ailiance) to remove specific samples; nous respectons l'Article 4(3) de la directive DSM (TDM reservations).
- **Reservations of rights**: nous honorons `robots.txt`, les meta tags HTML `noai` / `noimageai`, et le protocole TDM Reservation Protocol (TDMRep) quand discoverable sur les repos sources.""",
        # --- Pipeline ---
        """## Pipeline reproducibility
See """ + SCRIPTS_URL + """:
- `kicad9plus_pipeline.sh`, `build_kicad9plus_dataset.py`
- Original audit: """ + AUDIT_URL,
    ],
)


SPECS["kicad9plus-copyleft"] = DatasetSpec(
    name="kicad9plus-copyleft",
    license_yaml="gpl-3.0",
    license_display="GPL-3.0-or-later",
    pretty_name="Ailiance — KiCad 9+ Schematic Corpus (Copyleft)",
    short_desc_fr=(
        "Corpus de 209 schémas KiCad 9+ (`.kicad_sch`, format S-expression, "
        "version ≥ 20240722) collectés sous licences **copyleft / réciproques fortes** "
        "(GPL-3.0, CERN-OHL-S-2.0, EUPL-1.2). Compatible GPL-3.0-or-later au niveau "
        "aggregé. Pensé pour l'entraînement de modèles open-source soumis aux mêmes "
        "obligations de réciprocité."
    ),
    tags=["kicad", "eda", "schematic", "s-expression", "electronics", "hardware", "copyleft", "ailiance"],
    size_category="n<1K",
    languages=["en", "fr"],
    task_categories=["text-generation"],
    sample_count="209",
    size_human="~2.1 MB JSONL (raw `.kicad_sch` ≈ 38 MB before chat-format wrapping)",
    format_desc="JSONL chat format (`messages` array, user/assistant)",
    citation_short="kicad9plus_copyleft",
    body_blocks=[
        """## Composition

**Copyleft / strong reciprocal licenses only**: GPL-3.0 (169), CERN-OHL-S-2.0 (36), EUPL-1.2 (4).

Copyleft split of the original `electron-rare/kicad9plus-sch-corpus` (now deprecated). L'aggregé est re-licencié sous **GPL-3.0-or-later**, le plus restrictif des inputs (CERN-OHL-S-2.0 et EUPL-1.2 sont explicitement compatibles avec GPL-3.0+ via FSF / EUPL appendix interoperability).

Pour les samples permissifs (Apache-2.0, MIT, CC0-1.0, CERN-OHL-P-2.0) : voir [`Ailiance-fr/kicad9plus-permissive`](https://huggingface.co/datasets/Ailiance-fr/kicad9plus-permissive).""",
        """## EU AI Act compliance (Template AI Office, July 2025)

### General information
- **Name**: kicad9plus-sch-corpus (copyleft subset)
- **Modality**: text (KiCad S-expression source)
- **Languages**: English (technical), French (some title-block descriptions)
- **Intended use**: entraînement / fine-tuning de modèles de génération de schémas KiCad 9 / KiCad 10. **Les modèles entraînés sur ce dataset doivent respecter les obligations GPL-3.0-or-later** (disclosure des poids, des données dérivées d'entraînement, et du code d'inférence si redistribué).

### Data sources

**Publicly available datasets**: None.

**Web scraping**: Yes — public GitHub repositories.
- Discovery method: `gh search code "(kicad_sch (version 202X)" extension:kicad_sch`
- Filtering: SPDX license detection of GPL-3.0, CERN-OHL-S-2.0, EUPL-1.2
- Per-sample provenance: see `metadata.source_url`, `metadata.commit_sha`, `metadata.repo`

**Licensed data**: None (no commercial / proprietary licenses).

### Data processing
- Sparse-clone with `gh repo clone --depth 1`
- Per-file `.meta.json` sidecar with `source_url`, `commit_sha`, `license_spdx`, `kicad_version`
- Deduplication via SHA-256 of file contents
- Truncation at 8 KB to fit training context (marked in metadata when applicable)
- Validation via `kicad-cli sch erc --format json --severity-all` (99.6% pass rate on tested subset)
- All processing scripts available at """ + SCRIPTS_URL + """

### Data characteristics
- **Size**: 209 samples, ~2.1 MB JSONL (raw `.kicad_sch` totals ~38 MB before chat-format wrapping)
- **License mix (input)**:
  - GPL-3.0: 169 samples (80.9%)
  - CERN-OHL-S-2.0: 36 (17.2%)
  - EUPL-1.2: 4 (1.9%)
- **KiCad version mix**: 20240819 / 20240910 / 20241004 / 20241209 (KiCad 9 dev), 20250114 (KiCad 9 stable), 20250227 / 20250318 / 20250610 / 20250829 / 20250901 / 20250922 / 20251012 / 20251028 (later 9.x), 20260101 / 20260306 (KiCad 10)
- **Source repos**: 9 distinct upstream projects (full list in `LICENSE_INVENTORY.md`); largest contributors are `jaguilar/kicad` (133) and `flaviens/kicad` (34) — both KiCad demo / fork repositories under GPL-3.0.""",
        """## Sample format

Each line is a chat-format JSON object:

""" + SAMPLE_KICAD_COPYLEFT,
        """## Licenses applied
This dataset (the aggregated work) is released under **GPL-3.0-or-later**.

Per-sample original licenses are **preserved in `metadata.license_spdx`** and listed in `LICENSE_INVENTORY.md`. Downstream users MUST preserve attribution per sample and comply with the strongest applicable copyleft term (GPL-3.0-or-later for the aggregate).

Compatibility notes:
- **CERN-OHL-S-2.0 -> GPL-3.0+**: explicitly compatible (CERN-OHL-S §7 allows redistribution under GPL when combining with GPL works).
- **EUPL-1.2 -> GPL-3.0+**: compatible via the EUPL §5 / Appendix list (GPL-3.0 is a listed compatible licence).
- **GPL-3.0 -> GPL-3.0+**: trivially compatible.""",
        """## Copyright considerations
- All sources are public GitHub repositories under copyleft licenses.
- The `.kicad_sch` files are treated as software source under their original licenses.
- **Opt-out mechanism**: contact `c.saillant@gmail.com` (Ailiance) to remove specific samples; nous respectons l'Article 4(3) de la directive DSM (TDM reservations).
- **Reservations of rights**: nous honorons `robots.txt`, les meta tags HTML `noai` / `noimageai`, et le protocole TDM Reservation Protocol (TDMRep) quand discoverable sur les repos sources.""",
        """## Pipeline reproducibility
See """ + SCRIPTS_URL + """:
- `kicad9plus_pipeline.sh`, `build_kicad9plus_dataset.py`
- Original audit: """ + AUDIT_URL,
    ],
)


SPECS["kill-life-embedded-qa"] = DatasetSpec(
    name="kill-life-embedded-qa",
    license_yaml="cc-by-sa-4.0",
    license_display="CC-BY-SA-4.0",
    pretty_name="Ailiance — Kill-LIFE Embedded Knowledge Base",
    short_desc_fr=(
        "Knowledge-base Q&A spécifique au projet **Kill_LIFE** (compagnon vocal "
        "embarqué ESP32-S3 + Mascarade) : composants matériels, schémas KiCad "
        "du board minimal, simulations SPICE de l'alimentation/I2C/I2S/audio, "
        "et architecture du firmware C++ (pipeline voix, contrôleur vocal, "
        "intégration backend). Sert d'ancre factuelle pour le fine-tuning."
    ),
    tags=["electronics", "embedded", "kill-life", "esp32-s3", "kicad-10", "spice", "firmware", "knowledge-base", "voice-assistant", "ailiance"],
    size_category="n<1K",
    languages=["fr", "en"],
    task_categories=["text-generation", "question-answering"],
    sample_count="30",
    size_human="~66.4 KB JSONL (split agrégé)",
    format_desc="JSONL alpaca-style (`instruction` / `input` / `output`)",
    citation_short="kill_life_kb",
    body_blocks=[
        """## Splits

| Fichier | Samples | Domaine |
|---------|---------|---------|
| `kb_components_qa.jsonl` | 5 | Composants hardware (modules, capteurs, ICs) |
| `kb_kicad_qa.jsonl` | 10 | Schémas KiCad du board ESP32-S3 minimal (BOM, nets, footprints) |
| `kb_spice_qa.jsonl` | 5 | Simulations SPICE (alimentation, découplage, I2C pull-ups, I2S) |
| `kb_firmware_qa.jsonl` | 10 | Firmware C++ (VoiceController, pipeline audio, backend Mascarade) |

Un fichier consolidé `data/kill_life_embedded_qa.jsonl` agrège l'ensemble (**30 samples**, ~66.4 KB).""",
        """## Sample format

```python
from datasets import load_dataset

# Split agrégé
ds = load_dataset("Ailiance-fr/kill-life-embedded-qa", data_files="data/kill_life_embedded_qa.jsonl")

# Ou split spécifique (ex: composants seuls)
ds_components = load_dataset("Ailiance-fr/kill-life-embedded-qa", data_files="data/kb_components_qa.jsonl")
```

Exemple d'un sample (alpaca-style) :

""" + SAMPLE_KILLLIFE,
        """## Contexte projet

Le projet **Kill_LIFE** est un compagnon vocal embarqué construit autour :

- **Hardware** : ESP32-S3-WROOM-1-N16R8 + DAC PCM5101A + micro ICS-43434 + LCD Waveshare 1.85"
- **Firmware** : C++ avec `VoiceController`, pipeline push-to-talk, intégration backend Mascarade
- **Backend** : modèle Mascarade (Gemma-3n-E4B fine-tuné sur la famille `Ailiance-fr/mascarade-*` / `electron-rare/mascarade-*`)

Ce dataset sert à ancrer factuellement le LLM sur les détails du projet (BOM, nets, GPIO, simulations) plutôt que d'avoir des hallucinations sur la configuration exacte du board.""",
        """## Licenses applied

Aggregated dataset released under **CC-BY-SA-4.0** (attribution + sharealike).

100% original content collected from the internal Kill_LIFE knowledge base (no third-party datasets / no web scraping / no licensed inputs).""",
        """## Copyright considerations
- 100% original content (Ailiance / electron-rare team).
- **Opt-out mechanism**: contact `c.saillant@gmail.com` (Ailiance). We respect TDMRep, robots.txt, and `noai` / `noimageai` signals. We honor [Article 4(3) DSM Directive](https://eur-lex.europa.eu/eli/dir/2019/790/oj) opt-outs.""",
    ],
)


def _mascarade_spec(
    name: str,
    pretty_short: str,
    short_desc_fr: str,
    tags: list[str],
    sample_count: str,
    size_human: str,
    file_name: str,
    citation_short: str,
    sample_block: str,
    extra_data_sources_md: str,
    extra_copyright_md: str,
) -> DatasetSpec:
    return DatasetSpec(
        name=name,
        license_yaml="cc-by-sa-4.0",
        license_display="CC-BY-SA-4.0",
        pretty_name=f"Ailiance — {pretty_short}",
        short_desc_fr=short_desc_fr,
        tags=tags + ["ailiance"],
        size_category="1K<n<10K",
        languages=["fr", "en"],
        task_categories=["text-generation", "question-answering"],
        sample_count=sample_count,
        size_human=size_human,
        format_desc="JSONL « ShareGPT-style » (`conversations` array : system / human / gpt)",
        citation_short=citation_short,
        body_blocks=[
            f"""## Description longue

{short_desc_fr}

Ce dataset fait partie de la famille **Mascarade**, un corpus thématique destiné au fine-tuning LoRA de modèles compacts (cible : Gemma-3n-E4B et équivalents) pour des assistants spécialisés en électronique embarquée.

Format : JSONL « ShareGPT-style » avec un tour `system` (rôle d'expert), un tour `human` (question) et un tour `gpt` (réponse complète, code compilable, schémas ASCII si pertinent).""",
            f"""## Data sources (EU AI Act Template — AI Office, July 2025)

{extra_data_sources_md}

### Licensed data
None.""",
            f"""## Sample format

{sample_block}""",
            f"""## Usage

```python
from datasets import load_dataset

ds = load_dataset("Ailiance-fr/{name}")
print(ds["train"][0]["conversations"])
```

Pour un fine-tuning ShareGPT-style direct (axolotl, unsloth, mlx-lm) :

```yaml
# axolotl config
datasets:
  - path: Ailiance-fr/{name}
    type: sharegpt
    conversation: chatml
```

Fichier principal : `{file_name}`.""",
            f"""## Licenses applied

Aggregated dataset released under **CC-BY-SA-4.0**. Per-sample original licenses preserved in `metadata.license` when known.""",
            f"""## Copyright considerations

{extra_copyright_md}

**Opt-out**: contact `c.saillant@gmail.com` (Ailiance). We respect TDMRep, robots.txt, and noai/noimageai signals. We honor [Article 4(3) DSM Directive](https://eur-lex.europa.eu/eli/dir/2019/790/oj) opt-outs.""",
        ],
    )


SPECS["mascarade-stm32-dataset"] = _mascarade_spec(
    name="mascarade-stm32-dataset",
    pretty_short="STM32 & ARM Cortex-M Q&A",
    short_desc_fr=(
        "Q&A bilingue (FR/EN) sur le firmware STM32 et ARM Cortex-M : drivers "
        "HAL/LL, CMSIS, FreeRTOS, peripherals (UART, SPI, I2C, DMA, ADC, timers), "
        "bare-metal register-level, et assembleur ARM Thumb-2. Couvre les familles "
        "STM32F0/F1/F4/F7/G0/G4/H7/L0/L4."
    ),
    tags=["electronics", "embedded", "stm32", "arm", "cortex-m", "firmware", "hal", "cmsis", "freertos", "bare-metal"],
    sample_count="2,012",
    size_human="3.08 MB",
    file_name="stm32_chat.jsonl",
    citation_short="stm32",
    sample_block=SAMPLE_STM32,
    extra_data_sources_md=(
        "### Publicly available datasets\nNone (no third-party datasets reused).\n\n"
        "### Web scraping\nNone.\n\n"
        "### Synthetically generated\n"
        "- **100% generated by LLM** dans le pipeline d'entraînement *electron-rare*. "
        "Generator details preserved per-sample in `metadata.generator` when present; "
        "otherwise consult the original training pipeline."
    ),
    extra_copyright_md=(
        "- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS."
    ),
)


SPECS["mascarade-spice-dataset"] = _mascarade_spec(
    name="mascarade-spice-dataset",
    pretty_short="SPICE & Analog Simulation Q&A",
    short_desc_fr=(
        "Q&A bilingue (FR/EN) sur la simulation SPICE et l'analyse de circuits "
        "analogiques : ngspice, LTspice, modèles MOSFET/BJT, topologies analogiques, "
        "ampli-op, filtres actifs, sources de courant, polarisation."
    ),
    tags=["electronics", "spice", "simulation", "analog", "ngspice", "ltspice", "circuit-analysis", "masala-chai"],
    sample_count="3,091",
    size_human="4.00 MB",
    file_name="spice_chat.jsonl",
    citation_short="spice",
    sample_block=SAMPLE_SPICE,
    extra_data_sources_md=(
        "### Publicly available datasets\n"
        "- **Derived from [Masala-CHAI dataset](https://github.com/jitendra-bhandari/Masala-CHAI)** "
        "([arXiv:2411.14299](https://arxiv.org/abs/2411.14299), CC-BY-4.0). "
        "Original Masala-CHAI is itself derived from textbooks — verify upstream "
        "copyright before commercial use.\n\n"
        "### Web scraping\nNone directly performed by this dataset; upstream Masala-CHAI used textbook sources.\n\n"
        "### Synthetically generated\n"
        "- Light LLM augmentation (rephrasing, FR translation) on top of the Masala-CHAI base."
    ),
    extra_copyright_md=(
        "- Masala-CHAI base content: CC-BY-4.0 (attribution preserved above).\n"
        "- Synthetic LLM augmentations: belong to dataset author per OpenAI/Anthropic ToS.\n"
        "- Verify upstream textbook copyright before commercial use."
    ),
)


SPECS["mascarade-iot-dataset"] = _mascarade_spec(
    name="mascarade-iot-dataset",
    pretty_short="IoT & Connected Devices Q&A",
    short_desc_fr=(
        "Q&A bilingue (FR/EN) sur l'IoT et les objets connectés : ESP32, Wi-Fi, "
        "BLE, LoRaWAN, MQTT, intégration Home Assistant, drivers de capteurs, "
        "et gestion d'énergie pour devices battery-powered."
    ),
    tags=["electronics", "embedded", "iot", "esp32", "wifi", "ble", "mqtt", "lorawan", "home-assistant"],
    sample_count="6,005",
    size_human="11.04 MB",
    file_name="iot_chat.jsonl",
    citation_short="iot",
    sample_block=SAMPLE_IOT,
    extra_data_sources_md=(
        "### Publicly available datasets\n"
        "- **~33% from [acon96/Home-Assistant-Requests](https://huggingface.co/datasets/acon96/Home-Assistant-Requests) (MIT License)**.\n\n"
        "### Web scraping\nNone.\n\n"
        "### Synthetically generated\n"
        "- **~67%** generated by LLM in the *electron-rare* training pipeline (ESP32 / BLE / MQTT / LoRaWAN scenarios)."
    ),
    extra_copyright_md=(
        "- acon96/Home-Assistant-Requests samples: MIT License (attribution preserved above).\n"
        "- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS."
    ),
)


SPECS["mascarade-embedded-dataset"] = _mascarade_spec(
    name="mascarade-embedded-dataset",
    pretty_short="Embedded Systems & Linux Q&A",
    short_desc_fr=(
        "Q&A bilingue (FR/EN) sur les systèmes embarqués génériques : RTOS "
        "(FreeRTOS, Zephyr), Linux embarqué (Yocto, Buildroot), device tree, "
        "bootloaders (U-Boot, BL31), drivers noyau, et toolchains croisées."
    ),
    tags=["electronics", "embedded", "rtos", "drivers", "linux", "yocto", "buildroot", "device-tree", "bootloader"],
    sample_count="8,344",
    size_human="16.72 MB",
    file_name="embedded_chat.jsonl",
    citation_short="embedded",
    sample_block=SAMPLE_EMBEDDED,
    extra_data_sources_md=(
        "### Publicly available datasets\nNone.\n\n"
        "### Web scraping\n"
        "- **~10–15% scraped from Stack Exchange Electronics (CC-BY-SA-4.0) and EEVblog Forum (public domain)** "
        "— per-sample URL + author attribution **incomplete** for the Stack Exchange portion (legacy collection, "
        "see warning on the `mascarade-power`/`-dsp`/`-emc`/`-kicad` companions).\n\n"
        "### Synthetically generated\n"
        "- **~85%** generated by LLM (RTOS, device tree, drivers, bootloader scenarios)."
    ),
    extra_copyright_md=(
        "- Stack Exchange content: CC-BY-SA-4.0 (compatible upgrade ; full attribution remediation in progress for the ~10–15% scraped portion).\n"
        "- EEVblog content: public domain per forum rules.\n"
        "- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS."
    ),
)


# ---- README template assembly ------------------------------------------------

ABOUT_AILIANCE = """## About Ailiance

🇫🇷 **Ailiance** is a French AI organisation building EU-compliant resources for embedded systems and electronics design. Ailiance curates open datasets and fine-tuned models targeting:

- 🇪🇺 EU AI Act compliance (aligned with the GPAI Code of Practice signatories: Anthropic, Mistral, Google)
- ⚡ Electronics, embedded systems, hardware design
- 🔬 SPICE simulation, KiCad PCB / schematic, EDA workflows
- 🇫🇷 French + English technical content

Maintainer contact: `c.saillant@gmail.com` — see also the public bench/audit repo: [electron-bench](https://github.com/electron-rare/electron-bench)."""


PROVENANCE_TEMPLATE = """## Provenance & upstream attribution

This dataset is co-published with [`electron-rare/{name}`](https://huggingface.co/datasets/electron-rare/{name}) under the same **{license_display}** license. Original collection, curation, and pipeline tooling: **electron-rare** (upstream contributor). Production maintenance, EU AI Act packaging, and downstream support: **Ailiance** (this org).

Audit log (legal attribution, EU AI Act July 2025 template alignment): see [`docs/audit_kicad9plus.md`](""" + AUDIT_URL + """) and the companion [`docs/audit_mascarade_se_attribution.md`](https://github.com/electron-rare/electron-bench/blob/main/docs/audit_mascarade_se_attribution.md) on GitHub."""


RELATED_DATASETS = """## Related datasets

Ailiance dataset family (co-published with `electron-rare/*`):

- [Ailiance-fr/kicad9plus-permissive](https://huggingface.co/datasets/Ailiance-fr/kicad9plus-permissive) — KiCad 9+ schematics, permissive subset
- [Ailiance-fr/kicad9plus-copyleft](https://huggingface.co/datasets/Ailiance-fr/kicad9plus-copyleft) — KiCad 9+ schematics, copyleft subset
- [Ailiance-fr/kill-life-embedded-qa](https://huggingface.co/datasets/Ailiance-fr/kill-life-embedded-qa) — Kill_LIFE embedded knowledge base
- [Ailiance-fr/mascarade-stm32-dataset](https://huggingface.co/datasets/Ailiance-fr/mascarade-stm32-dataset) — STM32 & ARM Cortex-M Q&A
- [Ailiance-fr/mascarade-spice-dataset](https://huggingface.co/datasets/Ailiance-fr/mascarade-spice-dataset) — SPICE & analog simulation Q&A
- [Ailiance-fr/mascarade-iot-dataset](https://huggingface.co/datasets/Ailiance-fr/mascarade-iot-dataset) — IoT & connected devices Q&A
- [Ailiance-fr/mascarade-embedded-dataset](https://huggingface.co/datasets/Ailiance-fr/mascarade-embedded-dataset) — embedded systems generic Q&A"""


def _yaml_list(values: list[str]) -> str:
    return "\n".join(f"- {v}" for v in values)


def build_readme(spec: DatasetSpec) -> str:
    front = f"""---
license: {spec.license_yaml}
language:
{_yaml_list(spec.languages)}
pretty_name: "{spec.pretty_name}"
task_categories:
{_yaml_list(spec.task_categories)}
tags:
{_yaml_list(spec.tags)}
size_categories:
- {spec.size_category}
---"""

    header = f"""# {spec.pretty_name}

> 🇫🇷 **Ailiance** — curated by Ailiance for production deployment ; co-published with the upstream [`electron-rare/{spec.name}`](https://huggingface.co/datasets/electron-rare/{spec.name}). 🇪🇺 Compatible EU AI Act (Template AI Office, July 2025).

{spec.short_desc_fr}

## Statistics

| Métrique         | Valeur            |
|------------------|-------------------|
| Total samples    | **{spec.sample_count}** |
| Size             | {spec.size_human} |
| Format           | {spec.format_desc} |
| Languages        | French + English |
| Aggregate license| **{spec.license_display}** |"""

    body = "\n\n".join(spec.body_blocks)

    provenance = PROVENANCE_TEMPLATE.format(name=spec.name, license_display=spec.license_display)

    citation = f"""## Citation

```bibtex
@dataset{{ailiance_{spec.citation_short}_2026,
  author       = {{Ailiance}},
  title        = {{{{{spec.pretty_name}}}}},
  year         = {{2026}},
  publisher    = {{Hugging Face}},
  license      = {{{spec.license_display}}},
  url          = {{https://huggingface.co/datasets/Ailiance-fr/{spec.name}}},
  note         = {{Co-published with upstream electron-rare/{spec.name}}}
}}

@dataset{{electron_rare_{spec.citation_short}_2026,
  author       = {{electron-rare}},
  title        = {{{{Upstream: {spec.name}}}}},
  year         = {{2026}},
  publisher    = {{Hugging Face}},
  url          = {{https://huggingface.co/datasets/electron-rare/{spec.name}}}
}}
```"""

    license_eu = f"""## License & EU AI Act

**{spec.license_display}**. Données collectées et curées dans le cadre du projet **electron-rare**, packagées et maintenues par **Ailiance** pour déploiement production aligné EU AI Act.

Compatible **EU AI Act** : voir les signataires du *GPAI Code of Practice* (Anthropic, Mistral, Google) et la documentation transparence : [electron-bench](https://github.com/electron-rare/electron-bench).

Audit log: [`docs/audit_kicad9plus.md`]({AUDIT_URL})."""

    parts = [
        front,
        "",
        header,
        "",
        body,
        "",
        provenance,
        "",
        ABOUT_AILIANCE,
        "",
        license_eu,
        "",
        citation,
        "",
        RELATED_DATASETS,
        "",
    ]
    return "\n".join(parts)


# ---- HF upload ---------------------------------------------------------------

def hf_upload_readme(name: str, content: str, dry_run: bool) -> tuple[bool, str]:
    """Upload README.md to Ailiance-fr/<name>. Returns (ok, message)."""
    tmpdir = tempfile.mkdtemp(prefix=f"rebrand_{name}_")
    try:
        readme_path = Path(tmpdir) / "README.md"
        readme_path.write_text(content, encoding="utf-8")
        target = f"{ORG}/{name}"
        if dry_run:
            return True, f"[dry-run] would upload {len(content)} bytes to {target}"
        cmd = [
            HF_BIN,
            "upload",
            target,
            str(readme_path),
            "README.md",
            "--repo-type",
            "dataset",
            "--commit-message",
            "Ailiance rebrand: refresh README (pretty_name, About Ailiance, citation, upstream attribution preserved)",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            return False, f"FAIL ({res.returncode}): {res.stderr.strip()[:300]}"
        return True, res.stdout.strip()[-200:] or "ok"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def verify_readme(name: str) -> tuple[bool, str]:
    url = f"https://huggingface.co/datasets/{ORG}/{name}/raw/main/README.md"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            text = r.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return False, f"fetch failed: {e}"
    has_ailiance = "Ailiance" in text and "About Ailiance" in text
    has_upstream = "electron-rare" in text and "Provenance" in text
    has_audit = "audit_kicad9plus.md" in text
    new_pretty = "pretty_name:" in text and "Ailiance —" in text
    ok = has_ailiance and has_upstream and has_audit and new_pretty
    flags = []
    if not has_ailiance:
        flags.append("no-About-Ailiance")
    if not has_upstream:
        flags.append("no-upstream-block")
    if not has_audit:
        flags.append("no-audit-url")
    if not new_pretty:
        flags.append("pretty_name-not-updated")
    return ok, ",".join(flags) if flags else "ok"


# ---- main --------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Don't upload, write to /tmp/rebrand_output/ and verify only.")
    ap.add_argument("--only", help="Process only this dataset name.")
    ap.add_argument("--write-local", action="store_true", help="Always write rendered README to /tmp/rebrand_output/<name>.md")
    ap.add_argument("--skip-verify", action="store_true")
    args = ap.parse_args()

    names = ALL_NAMES if not args.only else [args.only]
    outdir = Path("/tmp/rebrand_output")
    outdir.mkdir(exist_ok=True)

    results: list[tuple[str, str, str]] = []  # (name, upload_status, verify_status)

    for i, name in enumerate(names):
        if name not in SPECS:
            print(f"[{name}] SKIP — no spec defined", file=sys.stderr)
            continue
        spec = SPECS[name]
        content = build_readme(spec)

        if args.dry_run or args.write_local:
            (outdir / f"{name}.md").write_text(content, encoding="utf-8")

        ok, msg = hf_upload_readme(name, content, dry_run=args.dry_run)
        upload_status = "OK" if ok else "FAIL"
        print(f"[{name}] upload={upload_status} ({msg})")
        if not ok and not args.dry_run:
            results.append((name, upload_status, "skipped"))
            continue

        # Rate limit politeness
        if not args.dry_run and i < len(names) - 1:
            time.sleep(2)

        verify_status = "skipped"
        if not args.skip_verify and not args.dry_run:
            time.sleep(1)
            v_ok, v_msg = verify_readme(name)
            verify_status = "OK" if v_ok else f"FAIL({v_msg})"
            print(f"[{name}] verify={verify_status}")

        results.append((name, upload_status, verify_status))

    print("\n=== Summary ===")
    for name, up, ver in results:
        print(f"  {name:40s} upload={up:6s} verify={ver}")

    any_fail = any(up != "OK" for _, up, _ in results)
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
