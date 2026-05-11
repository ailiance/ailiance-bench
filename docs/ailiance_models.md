# Ailiance models on Hugging Face

Ailiance (French AI org, EU AI Act context) publishes a family of LoRA adapters
on Hugging Face, fine-tuned on `lmstudio-community/gemma-4-E4B-it-MLX-4bit` for
electronics, embedded systems, KiCad, and SPICE tasks.

The same person owns the upstream `electron-bench` benchmark and curriculum; the
Ailiance org is the **publication / branding** side and packages the artifacts
for downstream users with EU AI Act Template AI Office July 2025 alignment.

## Catalog (4 LoRA adapters on `gemma-4-E4B-it-MLX-4bit`)

| Ailiance-fr name                                       | Status                | License | Adapter size | Iters | Rank | Scale | Curriculum                                                     |
|--------------------------------------------------------|-----------------------|---------|-------------:|------:|-----:|------:|----------------------------------------------------------------|
| `Ailiance-fr/gemma-4-E4B-eukiki-lora`                  | Champion general (4/7)| gemma   | 146 MB       | 2000  |   32 |   2.0 | 4-phase curriculum on eu-kiki (512 -> 1024 -> 2048 -> 3072)    |
| `Ailiance-fr/gemma-4-E4B-mascarade-lora`               | Champion extraction   | gemma   | 146 MB       | 1500  |   32 |   2.0 | 4-phase generic curriculum on Mascarade corpus                 |
| `Ailiance-fr/gemma-4-E4B-aggro-test-lora`              | Sanity baseline       | gemma   | 146 MB       |   40  |   32 |   2.0 | none (single-pass sanity check at LR 1e-4)                     |
| `Ailiance-fr/gemma-4-E4B-kicad9plus-lora`              | Negative result       | gemma   |  27 MB       | 1200  |    8 |  20.0 | none (98 samples, single dataset, catastrophic forgetting)     |

URLs:

- https://huggingface.co/Ailiance-fr/gemma-4-E4B-eukiki-lora
- https://huggingface.co/Ailiance-fr/gemma-4-E4B-mascarade-lora
- https://huggingface.co/Ailiance-fr/gemma-4-E4B-aggro-test-lora
- https://huggingface.co/Ailiance-fr/gemma-4-E4B-kicad9plus-lora

## Benchmark matrix (composite lift vs base)

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
- `aggro-test` is roughly neutral — the sanity baseline confirming that the training
  pipeline works without contaminating the benchmark.
- `kicad9plus` is a documented failure (rank 8 + scale 20 on 98 samples). Published
  for transparency; do not use in production.

## Usage example

```python
from mlx_lm import load, generate

# Champion general
model, tok = load(
    "lmstudio-community/gemma-4-E4B-it-MLX-4bit",
    adapter_path="Ailiance-fr/gemma-4-E4B-eukiki-lora",
)

prompt = "Generate a KiCad symbol for a 10kOhm resistor"
print(generate(model, tok, prompt=prompt, max_tokens=512))
```

To switch adapter, change `adapter_path=` to one of the other three repos.

## Training data lineage

Each adapter's model card declares the upstream datasets used. The Ailiance
dataset catalog (see [`ailiance_datasets.md`](./ailiance_datasets.md)) is the
canonical source:

| Adapter        | Primary training datasets                                                                                                                                                                                                                  |
|----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| eukiki         | internal eu-kiki curation over `Ailiance-fr/kicad9plus-permissive`, `Ailiance-fr/mascarade-spice-dataset`, `Ailiance-fr/mascarade-embedded-dataset`                                                                                          |
| mascarade      | `Ailiance-fr/mascarade-stm32-dataset`, `Ailiance-fr/mascarade-spice-dataset`, `Ailiance-fr/mascarade-iot-dataset`, `Ailiance-fr/mascarade-embedded-dataset`                                                                                  |
| aggro-test     | curriculum phase-1 subset (sanity check)                                                                                                                                                                                                    |
| kicad9plus     | `Ailiance-fr/kicad9plus-permissive` only (98 samples, CC-BY-SA-4.0)                                                                                                                                                                         |

## License

All four adapter weights are released under the **Gemma Terms of Use**
(inheritance from `lmstudio-community/gemma-4-E4B-it-MLX-4bit`).

- Terms: https://ai.google.dev/gemma/terms
- Each repo declares `license: gemma` in its `cardData`.

## EU AI Act compliance

Each model card declares:

- **Article 53(1)(c)** copyright policy (training data licenses preserved upstream).
- **Article 53(1)(d)** training data summary (publicly available datasets only;
  no web scraping; no licensed data).
- **GPAI Code of Practice (July 2025)** acknowledged (base model Gemma, Google
  is a signatory).

## Verification (one-liner)

```bash
TOKEN=$(cat ~/.cache/huggingface/token 2>/dev/null || cat ~/.huggingface/token)
for name in eukiki mascarade aggro-test kicad9plus; do
  echo "=== Ailiance-fr/gemma-4-E4B-${name}-lora ==="
  curl -sH "Authorization: Bearer $TOKEN" \
    "https://huggingface.co/api/models/Ailiance-fr/gemma-4-E4B-${name}-lora" \
    | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
cd = d.get('cardData', {})
files = [f.get('rfilename') for f in d.get('siblings', [])]
print(' files     :', files)
print(' license   :', cd.get('license', 'NONE'))
print(' base_model:', cd.get('base_model', 'NONE'))
"
done
```

## Related

- [`ailiance_datasets.md`](./ailiance_datasets.md) — the Ailiance dataset catalog
  (7 datasets that feed these models).
- [`bench-results/compare_base_vs_lora.md`](../bench-results/compare_base_vs_lora.md)
  — full benchmark matrix with per-task scores.
