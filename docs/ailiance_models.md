# Ailiance models on Hugging Face

Ailiance (French AI org, EU AI Act context) publishes LoRA adapters
on Hugging Face fine-tuned on four base families:

- `swiss-ai/Apertus-70B-Instruct-2509` (Apache 2.0) — Swiss-AI flagship
- `mistralai/Devstral-Small-2-24B-Instruct-2512` (Apache 2.0) — code-tuned Mistral
- `utter-project/EuroLLM-22B-Instruct-2512` (Apache 2.0) — multilingual EU
- `lmstudio-community/gemma-4-E4B-it-MLX-4bit` (Gemma Terms) — light electronics specialists

All adapters are MLX-trained on Apple M3 Ultra 512 GB, packaged for downstream
use with **EU AI Act Template AI Office July 2025** alignment.

## Catalog — Gemma 4 E4B legacy (4 adapters)

| Repo                                              | Status                | License        | Adapter size | Iters | Rank | Scale | Primary data                                                  |
|---------------------------------------------------|-----------------------|----------------|-------------:|------:|-----:|------:|---------------------------------------------------------------|
| `Ailiance-fr/gemma-4-E4B-eukiki-lora`             | Champion general (4/7)| cc-by-sa-4.0   | 146 MB       | 2000  |   32 |   2.0 | `Ailiance-fr/kill-life-embedded-qa`                            |
| `Ailiance-fr/gemma-4-E4B-mascarade-lora`          | Champion extraction   | cc-by-sa-4.0   | 146 MB       | 1500  |   32 |   2.0 | `Ailiance-fr/mascarade-*` (stm32, spice, iot, embedded)        |
| `Ailiance-fr/gemma-4-E4B-aggro-test-lora`         | Sanity baseline       | cc-by-sa-4.0   | 146 MB       |   40  |   32 |   2.0 | curriculum phase-1 subset                                      |
| `Ailiance-fr/gemma-4-E4B-kicad9plus-lora`         | Negative result       | cc-by-sa-4.0   |  27 MB       | 1200  |    8 |  20.0 | `Ailiance-fr/kicad9plus-permissive`                            |

**Note**: weights of the Gemma base remain under the Gemma Terms of Use; the LoRA
adapters are re-licensed CC-BY-SA-4.0 because training data is CC-BY-SA-4.0 and the
share-alike clause propagates. Downstream users must comply with **both** licenses.

## Catalog — Apertus 70B Instruct (9 adapters)

| Repo                                                          | Domain              | License      | Status              |
|---------------------------------------------------------------|---------------------|--------------|---------------------|
| `Ailiance-fr/apertus-embedded-lora`                           | embedded systems    | cc-by-sa-4.0 | clean                |
| `Ailiance-fr/apertus-electronics-hw-lora`                     | electronics HW      | cc-by-sa-4.0 | clean                |
| `Ailiance-fr/apertus-emc-dsp-power-lora`                      | EMC + DSP + power   | cc-by-sa-4.0 | DISCLOSURE (SE)      |
| `Ailiance-fr/apertus-emc-dsp-power-curriculum-lora`           | EMC + DSP + power   | cc-by-sa-4.0 | DISCLOSURE (SE)      |
| `Ailiance-fr/apertus-spice-sim-lora`                          | SPICE simulation    | cc-by-sa-4.0 | clean                |
| `Ailiance-fr/apertus-math-lora`                               | math                | apache-2.0   | synthetic            |
| `Ailiance-fr/apertus-math-gsm8k-lora`                         | math (GSM8K)        | mit          | synthetic            |
| `Ailiance-fr/apertus-math-reasoning-lora`                     | math reasoning      | apache-2.0   | synthetic            |
| `Ailiance-fr/apertus-security-fenrir-lora`                    | security            | apache-2.0   | synthetic            |
| `Ailiance-fr/apertus-security-fenrir-curriculum-lora`         | security            | apache-2.0   | synthetic            |

## Catalog — Devstral Small 2 24B (28 adapters)

| Repo                                                          | Domain              | License      |
|---------------------------------------------------------------|---------------------|--------------|
| `Ailiance-fr/devstral-cpp-lora`                               | C++                 | apache-2.0   |
| `Ailiance-fr/devstral-cpp-bf16-lora`                          | C++ (bf16 base)     | apache-2.0   |
| `Ailiance-fr/devstral-cpp-curriculum-lora`                    | C++ (curriculum)    | apache-2.0   |
| `Ailiance-fr/devstral-python-lora`                            | Python              | apache-2.0   |
| `Ailiance-fr/devstral-python-bf16-lora`                       | Python (bf16)       | apache-2.0   |
| `Ailiance-fr/devstral-rust-lora`                              | Rust                | apache-2.0   |
| `Ailiance-fr/devstral-rust-bf16-lora`                         | Rust (bf16)         | apache-2.0   |
| `Ailiance-fr/devstral-rust-embedded-lora`                     | Rust embedded       | apache-2.0   |
| `Ailiance-fr/devstral-rust-embedded-bf16-lora`                | Rust embedded (bf16)| apache-2.0   |
| `Ailiance-fr/devstral-typescript-lora`                        | TypeScript          | apache-2.0   |
| `Ailiance-fr/devstral-typescript-bf16-lora`                   | TypeScript (bf16)   | apache-2.0   |
| `Ailiance-fr/devstral-shell-lora`                             | Shell               | apache-2.0   |
| `Ailiance-fr/devstral-shell-bf16-lora`                        | Shell (bf16)        | apache-2.0   |
| `Ailiance-fr/devstral-sql-lora`                               | SQL                 | apache-2.0   |
| `Ailiance-fr/devstral-sql-bf16-lora`                          | SQL (bf16)          | apache-2.0   |
| `Ailiance-fr/devstral-yaml-json-lora`                         | YAML / JSON         | apache-2.0   |
| `Ailiance-fr/devstral-html-css-lora`                          | HTML / CSS          | apache-2.0   |
| `Ailiance-fr/devstral-html-css-bf16-lora`                     | HTML / CSS (bf16)   | apache-2.0   |
| `Ailiance-fr/devstral-web-backend-lora`                       | Web backend         | apache-2.0   |
| `Ailiance-fr/devstral-web-frontend-lora`                      | Web frontend        | apache-2.0   |
| `Ailiance-fr/devstral-docker-devops-lora`                     | Docker / DevOps     | apache-2.0   |
| `Ailiance-fr/devstral-docker-devops-bf16-lora`                | Docker / DevOps (bf16) | apache-2.0|
| `Ailiance-fr/devstral-lua-upy-lora`                           | Lua / MicroPython   | apache-2.0   |
| `Ailiance-fr/devstral-llm-ops-lora`                           | LLM ops             | apache-2.0   |
| `Ailiance-fr/devstral-llm-ops-bf16-lora`                      | LLM ops (bf16)      | apache-2.0   |
| `Ailiance-fr/devstral-llm-orch-lora`                          | LLM orchestration   | apache-2.0   |
| `Ailiance-fr/devstral-ml-training-lora`                       | ML training         | apache-2.0   |
| `Ailiance-fr/devstral-ml-training-bf16-lora`                  | ML training (bf16)  | apache-2.0   |
| `Ailiance-fr/devstral-music-audio-lora`                       | Music / audio DSP   | apache-2.0   |
| `Ailiance-fr/devstral-platformio-lora`                        | PlatformIO          | cc-by-sa-4.0 |
| `Ailiance-fr/devstral-freecad-lora`                           | FreeCAD             | cc-by-sa-4.0 |
| `Ailiance-fr/devstral-iot-lora`                               | IoT                 | cc-by-sa-4.0 |
| `Ailiance-fr/devstral-kicad-dsl-lora`                         | KiCad DSL           | cc-by-sa-4.0 |
| `Ailiance-fr/devstral-kicad-dsl-curriculum-lora`              | KiCad DSL (curr.)   | cc-by-sa-4.0 |
| `Ailiance-fr/devstral-kicad-pcb-lora`                         | KiCad PCB           | cc-by-sa-4.0 |
| `Ailiance-fr/devstral-kicad-pcb-curriculum-lora`              | KiCad PCB (curr.)   | cc-by-sa-4.0 |
| `Ailiance-fr/devstral-kicad-pcb-fullseq-lora`                 | KiCad PCB (full-seq)| cc-by-sa-4.0 |

> `devstral-vlm-schematic-lora` was **NOT** uploaded: orphan `.safetensors`
> without an adapter directory (skipped intentionally).

## Catalog — EuroLLM 22B Instruct (3 adapters)

| Repo                                                          | Domain                 | License      |
|---------------------------------------------------------------|------------------------|--------------|
| `Ailiance-fr/eurollm-multilingual-eu-lora`                    | 24 EU languages         | apache-2.0   |
| `Ailiance-fr/eurollm-chat-fr-lora`                            | French chat             | apache-2.0   |
| `Ailiance-fr/eurollm-traduction-tech-lora`                    | Technical translation FR/EN | apache-2.0 |

## License chain (how licenses flow through the LoRA pipeline)

LoRA adapters are **derivatives of both** the base model **and** the training corpus.
The combined license is **the most restrictive** of the chain — this is enforced
explicitly in every model card.

| Base                                   | Base license       | Training data (typical)                             | Data license  | LoRA license       |
|----------------------------------------|--------------------|-----------------------------------------------------|---------------|--------------------|
| `swiss-ai/Apertus-70B-Instruct-2509`   | Apache 2.0         | `Ailiance-fr/mascarade-*-dataset`                   | CC-BY-SA-4.0  | **CC-BY-SA-4.0**   |
| `swiss-ai/Apertus-70B-Instruct-2509`   | Apache 2.0         | math reasoning / security (synthetic)               | Apache 2.0 / MIT | Apache 2.0 / MIT |
| `mistralai/Devstral-Small-2-24B-...`   | Apache 2.0         | code corpora (synthetic + permissive)               | Apache 2.0    | **Apache 2.0**     |
| `mistralai/Devstral-Small-2-24B-...`   | Apache 2.0         | `Ailiance-fr/mascarade-kicad-dataset`               | CC-BY-SA-4.0  | **CC-BY-SA-4.0**   |
| `utter-project/EuroLLM-22B-...`        | Apache 2.0         | EU-multilingual permissive corpora                  | Apache 2.0    | **Apache 2.0**     |
| `lmstudio-community/gemma-4-E4B-...`   | Gemma Terms of Use | `Ailiance-fr/mascarade-*` / `kicad9plus-permissive` | CC-BY-SA-4.0  | **CC-BY-SA-4.0** (weights still bound by Gemma Terms) |

**Rules applied (encoded in `scripts/push_ailiance_lora_v2.py`)**:

1. If training data is **CC-BY-SA-4.0**, the LoRA is **CC-BY-SA-4.0**
   (share-alike propagates).
2. If training data is **Apache 2.0 / MIT**, the LoRA inherits the base license
   (Apache 2.0 in all current cases).
3. Gemma base weights remain bound by the Gemma Terms of Use **in addition** to
   the LoRA's own license — downstream users must comply with **both**.
4. Domains with **partial Stack Exchange attribution** (`emc`, `dsp`, `power`)
   carry a `PARTIAL ATTRIBUTION DISCLOSURE` bandeau in their model card.
5. The `mascarade-kicad-dataset` chain carries an `ATTRIBUTION AUDIT COMPLETED`
   bandeau (audit completed 2026-05-11; report in
   [`docs/audit_mascarade_se_attribution.md`](./audit_mascarade_se_attribution.md)).

## Benchmark matrix (Gemma 4 E4B family, base vs LoRA)

Reference base: `lmstudio-community/gemma-4-E4B-it-MLX-4bit`. Full table at
[`bench-results/compare_base_vs_lora.md`](../bench-results/compare_base_vs_lora.md).

| Phase | Dataset            |  base | +eu-kiki        | +mascarade      | +aggro          | +kicad9plus      |
|------:|--------------------|------:|----------------:|----------------:|----------------:|-----------------:|
| P1    | kicad-dsl          | 0.090 | **0.640 (+55.0)** | 0.090 (+0.0)    | 0.090 (+0.0)    | 0.090 (+0.0)     |
| P1    | kicad-pcb          | 0.010 | **0.430 (+42.0)** | 0.010 (+0.0)    | 0.010 (+0.0)    | 0.015 (+0.5)     |
| P1    | spice-sim          | 0.425 | **0.676 (+25.1)** | 0.176 (-24.9)   | 0.189 (-23.5)   | 0.268 (-15.7)    |
| P2    | kicad-sch-gen      | 0.420 | 0.220 (-20.0)   | 0.400 (-2.0)    | 0.320 (-10.0)   | 0.180 (-24.0)    |
| P3    | kicad-sch-extract  | 0.308 | 0.690 (+38.2)   | **0.785 (+47.6)** | 0.350 (+4.2)    | 0.000 (-30.8)    |
| P4    | kicad-erc-abs      | 0.060 | 0.057 (-0.3)    | 0.060 (+0.0)    | 0.060 (+0.0)    | 0.033 (-2.7)     |
| P5    | kicad-erc-delta    | 0.060 | 0.057 (-0.3)    | 0.060 (+0.0)    | 0.060 (+0.0)    | 0.033 (-2.7)     |

**Reading guide**:

- `eukiki` wins **4 phases** (P1 DSL/PCB/SPICE, P3 extract) — pick for general use.
- `mascarade` wins **P3 extract** specifically — pick for schematic / netlist parsing tasks.
- `aggro-test` is roughly neutral — sanity baseline.
- `kicad9plus` is a documented failure (rank 8 + scale 20 on 98 samples).

Benchmarks for the Apertus / Devstral / EuroLLM families are not part of this
release and will appear in `bench-results/` as they become available.

## Benchmark status per family (as of 2026-05-11)

Each model card on HuggingFace now declares its own **Benchmark / Training
metrics** section. The pipeline status per family:

| Family   | # adapters | Functional bench (`electron-bench`) | Training metrics (val loss, ppl) | Notes                                                                                                          |
|----------|-----------:|-------------------------------------|----------------------------------|----------------------------------------------------------------------------------------------------------------|
| Gemma    | 4          | ✅ P1 → P6 (compare_base_vs_lora)   | ✅ embedded in card               | Reference base, full matrix above.                                                                             |
| Devstral | 38         | ⏳ roadmap                          | ✅ for adapters with persisted logs (cpp, chat-fr, docker-devops, *-curriculum variants) | Per-card metrics extracted from `batch_eu_kiki_v2.log` / `medium35-*-curriculum.log`. Bf16 variants share metrics with their fp counterparts. |
| Apertus  | 10         | ⏳ roadmap                          | ⏳ roadmap (training logs not persisted) | Cards carry a `Benchmark roadmap` section pointing at issue tracker.                                           |
| EuroLLM  | 3          | ⏳ roadmap                          | ⏳ roadmap (training logs not persisted) | Cards carry a `Benchmark roadmap` section.                                                                     |
| Qwen3-4B | 8          | ✅ already present (ailiance-bench v0.2 Phase 6) | n/a (managed separately)         | Existing `## Bench results` / `## Bench context` sections preserved (idempotency).                              |
| Router   | 2          | n/a (classifier, not LoRA)          | n/a                              | Excluded from bench script.                                                                                    |

Maintained by [`scripts/add_bench_section_to_cards.py`](../scripts/add_bench_section_to_cards.py)
— idempotent, drives off [`scripts/data/training_metrics.json`](../scripts/data/training_metrics.json).
Re-run with `--force-replace` when new metrics become available.

## Usage example (any of the 49 adapters)

```python
from mlx_lm import load, generate

# Example: KiCad DSL specialist on Devstral
model, tok = load(
    "mistralai/Devstral-Small-2-24B-Instruct-2512",
    adapter_path="Ailiance-fr/devstral-kicad-dsl-lora",
)

prompt = "Generate a KiCad symbol for a 10kOhm resistor"
print(generate(model, tok, prompt=prompt, max_tokens=512))
```

To switch to another adapter, change `adapter_path=` to one of the 49 repos
listed above. Each model card declares its own base, license, and training
data lineage.

## EU AI Act compliance

Each model card declares:

- **Article 53(1)(c)** copyright policy — training data licenses preserved
  upstream and re-declared in the License chain table of every card.
- **Article 53(1)(d)** training data summary — link to upstream dataset card.
- **GPAI Code of Practice (July 2025)** acknowledged.
- **No web scraping by Ailiance**, **no licensed data**, **no PII**.
- Where upstream Stack Exchange CC-BY-SA-4.0 content is used, share-alike
  is preserved on the LoRA derivative.

## Verification (one-liner)

```bash
TOKEN=$(cat ~/.cache/huggingface/token 2>/dev/null || cat ~/.huggingface/token)
for repo in apertus-embedded devstral-cpp eurollm-chat-fr gemma-4-E4B-eukiki; do
  echo "=== Ailiance-fr/${repo}-lora ==="
  curl -sH "Authorization: Bearer $TOKEN" \
    "https://huggingface.co/api/models/Ailiance-fr/${repo}-lora" \
    | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
cd = d.get('cardData', {})
print(' license   :', cd.get('license', 'NONE'))
print(' base_model:', cd.get('base_model', 'NONE'))
"
done
```

## Related

- [`ailiance_datasets.md`](./ailiance_datasets.md) — the Ailiance dataset catalog
  (13 datasets that feed these adapters).
- [`audit_mascarade_se_attribution.md`](./audit_mascarade_se_attribution.md)
  — Stack Exchange attribution audit (kicad domain, 2026-05-11).
- [`bench-results/compare_base_vs_lora.md`](../bench-results/compare_base_vs_lora.md)
  — Gemma 4 E4B benchmark matrix with per-task scores.
