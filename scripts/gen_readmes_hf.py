#!/usr/bin/env python3
"""Generate enriched READMEs for the 9 electron-rare datasets."""
import json
import os
from pathlib import Path

CACHE = Path.home() / ".cache/huggingface/hub"

# Dataset specs: short_name -> (full_repo_id, jsonl_filename, pretty_name, topic_fr, tags, system_keywords)
SPECS = {
    "stm32": {
        "repo": "electron-rare/mascarade-stm32-dataset",
        "file": "stm32_chat.jsonl",
        "pretty": "Mascarade — STM32 & ARM Cortex-M Q&A",
        "topic_fr": "Q&A bilingue (FR/EN) sur le firmware STM32 et ARM Cortex-M : drivers HAL/LL, CMSIS, FreeRTOS, peripherals (UART, SPI, I2C, DMA, ADC, timers), bare-metal register-level, et assembleur ARM Thumb-2.",
        "scope_fr": "Couvre les familles STM32F0/F1/F4/F7/G0/G4/H7/L0/L4 ainsi que les concepts génériques Cortex-M0/M3/M4/M7. Chaque exemple inclut du code C compilable, les adresses de registres correctes, la configuration d'horloge, et l'explication technique associée.",
        "tags": ["stm32", "arm", "cortex-m", "firmware", "hal", "cmsis", "freertos", "bare-metal"],
    },
    "spice": {
        "repo": "electron-rare/mascarade-spice-dataset",
        "file": "spice_chat.jsonl",
        "pretty": "Mascarade — SPICE Simulation Q&A",
        "topic_fr": "Q&A bilingue (FR/EN) sur la simulation SPICE de circuits analogiques : netlists ngspice/LTspice, analyses DC/AC/transient, débogage de convergence, modèles de composants, et automatisation via PySpice.",
        "scope_fr": "Couvre les amplificateurs (CE, op-amp, classe AB), les filtres actifs/passifs, les régulateurs, les oscillateurs, les modèles de transistors (BJT, MOSFET, JFET), et les directives d'analyse (`.tran`, `.ac`, `.dc`, `.noise`, `.tf`).",
        "tags": ["spice", "ngspice", "ltspice", "analog", "simulation", "circuit-design", "pyspice"],
    },
    "iot": {
        "repo": "electron-rare/mascarade-iot-dataset",
        "file": "iot_chat.jsonl",
        "pretty": "Mascarade — IoT & ESP32 Q&A",
        "topic_fr": "Q&A bilingue (FR/EN) sur l'IoT et les microcontrôleurs connectés : ESP32/ESP8266 avec ESP-IDF, MQTT (incluant TLS/mTLS), LoRaWAN, BLE, Wi-Fi, Home Assistant, PlatformIO, et conception d'objets battery-powered.",
        "scope_fr": "Inclut des designs production-ready avec gestion d'erreurs, sécurité TLS, optimisation énergétique (deep sleep, ULP), provisionnement (BLE, SmartConfig), OTA, et intégration de capteurs courants (BME280, SHT3x, ADS1115, INA219).",
        "tags": ["iot", "esp32", "esp-idf", "mqtt", "lorawan", "ble", "home-assistant", "platformio"],
    },
    "power": {
        "repo": "electron-rare/mascarade-power-dataset",
        "file": "power_chat.jsonl",
        "pretty": "Mascarade — Power Electronics Q&A",
        "topic_fr": "Q&A bilingue (FR/EN) sur l'électronique de puissance : convertisseurs DC-DC (buck, boost, buck-boost, flyback), commande moteur (FOC, DTC, BLDC/PMSM), onduleurs, drivers de grille, gestion de batterie, et correction du facteur de puissance.",
        "scope_fr": "Inclut les calculs complets de composants (inductances, capacités, MOSFETs, diodes), la sélection d'IC (TPS, LTC, LM, LM3886), le dimensionnement thermique, les compensations boucle de courant/tension, et le firmware de contrôle numérique sur STM32/DSP.",
        "tags": ["power-electronics", "dc-dc", "buck", "boost", "motor-control", "foc", "battery", "regulator"],
    },
    "dsp": {
        "repo": "electron-rare/mascarade-dsp-dataset",
        "file": "dsp_chat.jsonl",
        "pretty": "Mascarade — DSP & CMSIS-DSP Q&A",
        "topic_fr": "Q&A bilingue (FR/EN) sur le traitement du signal numérique embarqué : filtres FIR/IIR, FFT, analyse spectrale, traitement audio temps-réel, et implémentation sur ARM Cortex-M avec CMSIS-DSP.",
        "scope_fr": "Couvre la conception de filtres (Butterworth, Chebyshev, elliptique, design par fenêtrage), les optimisations point-fixe (Q15, Q31), les fenêtres (Hanning, Hamming, Blackman), la convolution, la corrélation, et les algorithmes audio (compression, EQ, reverb).",
        "tags": ["dsp", "cmsis-dsp", "fft", "fir", "iir", "audio", "signal-processing", "fixed-point"],
    },
    "emc": {
        "repo": "electron-rare/mascarade-emc-dataset",
        "file": "emc_chat.jsonl",
        "pretty": "Mascarade — EMC, EMI & RF Q&A",
        "topic_fr": "Q&A bilingue (FR/EN) sur la compatibilité électromagnétique (CEM) et la RF : filtrage EMI, protection ESD, adaptation d'impédance RF, design d'antennes, layout PCB pour la conformité CEM, et tests réglementaires (CE, FCC, CISPR).",
        "scope_fr": "Couvre les normes CISPR 32/35, EN 55032/35, FCC Part 15, IEC 61000-4-x (ESD, surge, burst), le calcul de filtres LC/π, le choix de selfs de mode commun (Würth, TDK, Coilcraft), les MOV, TVS, ferrite beads, le routing différentiel, et les techniques de blindage.",
        "tags": ["emc", "emi", "esd", "rf", "antenna", "cispr", "fcc", "compliance"],
    },
    "kicad": {
        "repo": "electron-rare/mascarade-kicad-dataset",
        "file": "kicad_chat.jsonl",
        "pretty": "Mascarade — KiCad PCB Design Q&A",
        "topic_fr": "Q&A bilingue (FR/EN) sur la conception PCB avec KiCad 8/9 : capture de schéma (Eeschema), assignation d'empreintes, placement, routing manuel et interactif, plans de masse/alimentation, vias, paires différentielles, contrôle d'impédance, DRC, génération Gerber/drill et BOM.",
        "scope_fr": "Couvre les standards IPC (IPC-2221, IPC-A-610, IPC-J-STD-001, IPC-7351, IPC-2581), les calculs d'impédance microstrip/stripline, les recommandations de stackup, les guidelines EMC, l'analyse thermique, les scripts Python KiCad, et les formats `.kicad_sch`/`.kicad_pcb`/`.kicad_mod`.",
        "tags": ["kicad", "pcb", "eda", "schematic", "routing", "ipc", "gerber", "footprint"],
    },
    "embedded": {
        "repo": "electron-rare/mascarade-embedded-dataset",
        "file": "embedded_chat.jsonl",
        "pretty": "Mascarade — Embedded Systems Q&A (general)",
        "topic_fr": "Q&A bilingue (FR/EN) généraliste sur les systèmes embarqués : ARM Cortex-M (STM32, nRF52, Teensy, SAMD), ESP32/ESP-IDF, RISC-V, firmware bare-metal et RTOS, registres, DMA, interruptions, modes basse consommation, bootloaders.",
        "scope_fr": "Couvre CMSIS, HAL, LL drivers, linker scripts, startup code, assembleur ARM/RISC-V, Raspberry Pi bare-metal, embedded Linux (device trees, modules kernel, GPIO/SPI/I2C). Le plus volumineux des datasets Mascarade — couverture transversale qui complète les datasets thématiques.",
        "tags": ["embedded", "arm", "cortex-m", "risc-v", "esp32", "rtos", "bare-metal", "bootloader"],
    },
}

# kill-life-embedded-qa is a special multi-file dataset
KILL_LIFE = {
    "repo": "electron-rare/kill-life-embedded-qa",
    "pretty": "Kill_LIFE — Embedded Knowledge-Base Q&A",
    "topic_fr": "Q&A spécifique au projet Kill_LIFE (compagnon vocal embarqué basé sur ESP32-S3 + Mascarade) : composants matériels du board, schémas KiCad du board ESP32-S3 minimal, simulations SPICE de l'alimentation/I2C/I2S/audio, et architecture du firmware (pipeline voix, contrôleur vocal, intégration backend).",
    "scope_fr": "Issu de la knowledge-base interne du projet electron-rare/kill-life. Sert d'ancre factuelle pour le fine-tuning : permet au modèle de répondre précisément sur la BOM, les nets, les rails d'alimentation, les empreintes, et le code firmware C++ du compagnon.",
    "tags": ["kill-life", "esp32-s3", "kicad-10", "spice", "firmware", "knowledge-base", "voice-assistant"],
    "splits": {
        "kb_components_qa": "Composants hardware (modules, capteurs, ICs)",
        "kb_kicad_qa": "Schémas KiCad du board ESP32-S3 minimal (BOM, nets, footprints)",
        "kb_spice_qa": "Simulations SPICE (alimentation, découplage, I2C pull-ups, I2S)",
        "kb_firmware_qa": "Firmware C++ (VoiceController, pipeline audio, backend Mascarade)",
    },
}


def find_jsonl(repo_short, filename):
    """Find a jsonl file in the cache snapshots."""
    repo_dir = CACHE / f"datasets--{repo_short.replace('/', '--')}"
    snaps = list((repo_dir / "snapshots").iterdir())
    if not snaps:
        return None
    return snaps[0] / filename


def file_size_mb(path):
    """Return real file size in MB (resolve symlink)."""
    real = os.path.realpath(path)
    return os.path.getsize(real) / 1024 / 1024


def count_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def first_sample(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.readline())


def size_category(n):
    if n < 1000:
        return "n<1K"
    if n < 10_000:
        return "1K<n<10K"
    if n < 100_000:
        return "10K<n<100K"
    return "100K<n<1M"


def render_yaml_tags(tags):
    return "\n".join(f"- {t}" for t in tags)


def render_mascarade_readme(short, spec, count, size_mb, sample):
    pretty = spec["pretty"]
    tags = ["electronics", "embedded"] + spec["tags"]
    sample_json = json.dumps(sample, ensure_ascii=False, indent=2)
    # Truncate big samples for readability
    if len(sample_json) > 3500:
        sample_json = sample_json[:3500] + "\n  ... (sample truncated for README — full content in JSONL)"
    yaml_tags = render_yaml_tags(tags)
    sz_cat = size_category(count)
    return f"""---
license: cc-by-sa-4.0
language:
- fr
- en
pretty_name: "{pretty}"
task_categories:
- text-generation
- question-answering
tags:
{yaml_tags}
size_categories:
- {sz_cat}
---

# {pretty}

{spec['topic_fr']}

## Description

{spec['scope_fr']}

Ce dataset fait partie de la famille **Mascarade**, un corpus thématique destiné au fine-tuning LoRA de modèles compacts (cible : Gemma-3n-E4B et équivalents) pour des assistants spécialisés en électronique embarquée.

Format : JSONL « ShareGPT-style » avec un tour `system` (rôle d'expert), un tour `human` (question) et un tour `gpt` (réponse complète, code compilable, schémas ASCII si pertinent).

## Statistiques

| Métrique     | Valeur            |
|--------------|-------------------|
| Total samples | **{count:,}** |
| Taille       | **{size_mb:.2f} MB** |
| Format       | `jsonl` (ShareGPT conversations) |
| Langues      | français + anglais |
| Fichier      | `{spec['file']}` |

## Format d'un sample

```json
{sample_json}
```

## Usage

```python
from datasets import load_dataset

ds = load_dataset("{spec['repo']}")
print(ds["train"][0]["conversations"])
```

Pour un fine-tuning ShareGPT-style direct (axolotl, unsloth, mlx-lm) :

```yaml
# axolotl config
datasets:
  - path: {spec['repo']}
    type: sharegpt
    conversation: chatml
```

## License & EU AI Act

**CC-BY-SA-4.0** (attribution + sharealike).

Données collectées et générées dans le cadre du projet **electron-rare** (fine-tuning LoRA sur Gemma-3n-E4B pour applications électronique embarquée).

Compatible **EU AI Act** : voir les signataires du *GPAI Code of Practice* (Anthropic, Mistral, Google) et la documentation transparence du projet : [electron-bench](https://github.com/electron-rare/electron-bench).

## Citation

```bibtex
@dataset{{electron_rare_{short}_2026,
  author    = {{electron-rare}},
  title     = {{ {pretty} }},
  year      = {{2026}},
  publisher = {{Hugging Face}},
  license   = {{CC-BY-SA-4.0}},
  url       = {{https://huggingface.co/datasets/{spec['repo']}}}
}}
```

## Related datasets

Famille `electron-rare/mascarade-*` couvrant : STM32, SPICE, KiCad, IoT, Power, DSP, EMC, embedded.

- [mascarade-stm32-dataset](https://huggingface.co/datasets/electron-rare/mascarade-stm32-dataset)
- [mascarade-spice-dataset](https://huggingface.co/datasets/electron-rare/mascarade-spice-dataset)
- [mascarade-kicad-dataset](https://huggingface.co/datasets/electron-rare/mascarade-kicad-dataset)
- [mascarade-iot-dataset](https://huggingface.co/datasets/electron-rare/mascarade-iot-dataset)
- [mascarade-power-dataset](https://huggingface.co/datasets/electron-rare/mascarade-power-dataset)
- [mascarade-dsp-dataset](https://huggingface.co/datasets/electron-rare/mascarade-dsp-dataset)
- [mascarade-emc-dataset](https://huggingface.co/datasets/electron-rare/mascarade-emc-dataset)
- [mascarade-embedded-dataset](https://huggingface.co/datasets/electron-rare/mascarade-embedded-dataset)
- [kill-life-embedded-qa](https://huggingface.co/datasets/electron-rare/kill-life-embedded-qa) — Q&A spécifique au projet Kill_LIFE
- [kicad9plus-sch-corpus](https://huggingface.co/datasets/electron-rare/kicad9plus-sch-corpus) — corpus de schémas KiCad 9+
"""


def render_kill_life_readme(spec, splits_info, total_count, total_size_mb, sample):
    pretty = spec["pretty"]
    tags = ["electronics", "embedded"] + spec["tags"]
    sample_json = json.dumps(sample, ensure_ascii=False, indent=2)
    if len(sample_json) > 2500:
        sample_json = sample_json[:2500] + "\n  ... (sample truncated for README)"
    yaml_tags = render_yaml_tags(tags)
    sz_cat = size_category(total_count)

    splits_table = "\n".join(
        f"| `{name}.jsonl` | {info['count']} | {spec['splits'][name]} |"
        for name, info in splits_info.items()
    )

    return f"""---
license: cc-by-sa-4.0
language:
- fr
- en
pretty_name: "{pretty}"
task_categories:
- text-generation
- question-answering
tags:
{yaml_tags}
size_categories:
- {sz_cat}
---

# {pretty}

{spec['topic_fr']}

## Description

{spec['scope_fr']}

Format : JSONL au format **alpaca-style** (`instruction` / `input` / `output`). Le contenu `output` contient des extraits bruts de fichiers source du repo Kill_LIFE (YAML de standards, schémas KiCad, netlists SPICE, code C++ firmware).

## Splits

| Fichier | Samples | Domaine |
|---------|---------|---------|
{splits_table}

Un fichier consolidé `data/kill_life_embedded_qa.jsonl` agrège l'ensemble (**{total_count} samples**, ~{total_size_mb*1024:.1f} KB).

## Statistiques

| Métrique     | Valeur            |
|--------------|-------------------|
| Total samples | **{total_count}** (split agrégé) |
| Taille       | **{total_size_mb*1024:.1f} KB** (tous fichiers) |
| Format       | `jsonl` (alpaca instruction/input/output) |
| Langues      | français + anglais |

## Format d'un sample

```json
{sample_json}
```

## Usage

```python
from datasets import load_dataset

# Split agrégé
ds = load_dataset("{spec['repo']}", data_files="data/kill_life_embedded_qa.jsonl")

# Ou split spécifique (ex: composants seuls)
ds_components = load_dataset("{spec['repo']}", data_files="data/kb_components_qa.jsonl")
```

## Contexte projet

Le projet **Kill_LIFE** est un compagnon vocal embarqué construit autour :

- **Hardware** : ESP32-S3-WROOM-1-N16R8 + DAC PCM5101A + micro ICS-43434 + LCD Waveshare 1.85"
- **Firmware** : C++ avec `VoiceController`, pipeline push-to-talk, intégration backend Mascarade
- **Backend** : modèle Mascarade (Gemma-3n-E4B fine-tuné sur la famille `electron-rare/mascarade-*`)

Ce dataset sert à ancrer factuellement le LLM sur les détails du projet (BOM, nets, GPIO, simulations) plutôt que d'avoir des hallucinations sur la configuration exacte du board.

## License & EU AI Act

**CC-BY-SA-4.0** (attribution + sharealike).

Compatible **EU AI Act** : voir les signataires du *GPAI Code of Practice* (Anthropic, Mistral, Google) et la documentation transparence du projet : [electron-bench](https://github.com/electron-rare/electron-bench).

## Citation

```bibtex
@dataset{{electron_rare_kill_life_qa_2026,
  author    = {{electron-rare}},
  title     = {{ {pretty} }},
  year      = {{2026}},
  publisher = {{Hugging Face}},
  license   = {{CC-BY-SA-4.0}},
  url       = {{https://huggingface.co/datasets/{spec['repo']}}}
}}
```

## Related datasets

- Famille [`electron-rare/mascarade-*`](https://huggingface.co/electron-rare) : STM32, SPICE, KiCad, IoT, Power, DSP, EMC, embedded
- [kicad9plus-sch-corpus](https://huggingface.co/datasets/electron-rare/kicad9plus-sch-corpus) — corpus de schémas KiCad 9+
"""


def main():
    print("=== Generating Mascarade READMEs ===")
    for short, spec in SPECS.items():
        path = find_jsonl(spec["repo"], spec["file"])
        if path is None or not path.exists():
            print(f"SKIP {short}: no file found")
            continue
        count = count_lines(path)
        size_mb = file_size_mb(path)
        sample = first_sample(path)
        readme = render_mascarade_readme(short, spec, count, size_mb, sample)
        out = Path(f"/tmp/mascarade_{short}_README.md")
        out.write_text(readme, encoding="utf-8")
        print(f"  {short}: {count} samples, {size_mb:.2f}MB -> {out}")

    print("\n=== Generating kill-life-embedded-qa README ===")
    repo_dir = CACHE / "datasets--electron-rare--kill-life-embedded-qa"
    snap = next((repo_dir / "snapshots").iterdir())
    splits_info = {}
    total_size_bytes = 0
    for name in ["kb_components_qa", "kb_kicad_qa", "kb_spice_qa", "kb_firmware_qa"]:
        p = snap / f"{name}.jsonl"
        if p.exists():
            cnt = count_lines(p)
            real = os.path.realpath(p)
            sz = os.path.getsize(real)
            splits_info[name] = {"count": cnt, "size": sz}
            total_size_bytes += sz
    # also include data/ aggregated file size only once for total
    agg_path = snap / "data" / "kill_life_embedded_qa.jsonl"
    total_count = count_lines(agg_path)
    sample = first_sample(agg_path)
    readme = render_kill_life_readme(KILL_LIFE, splits_info, total_count, total_size_bytes / 1024 / 1024, sample)
    out = Path("/tmp/kill_life_embedded_qa_README.md")
    out.write_text(readme, encoding="utf-8")
    print(f"  kill-life-embedded-qa: {total_count} aggregated samples, {total_size_bytes/1024:.1f}KB -> {out}")


if __name__ == "__main__":
    main()
