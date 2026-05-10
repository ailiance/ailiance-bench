# electron-bench

Benchmarking MLX pour modèles open-source et fine-tunes electron-rare sur Mac Apple Silicon.
Évaluation via perplexité sur 5 niches embarquées (spice, stm32, kicad, embedded_iot, emc_power).

## Modèles benchmarkés

| Modèle | Provider | Notes |
|--------|----------|-------|
| `eu-kiki` | electron-rare | Fine-tune custom ; 52% gsm-S / 78.5% arc / 58% mmluPro |
| `mascarade` | electron-rare | Fine-tune custom |
| `base` | electron-rare | Gemma 3 4B vanilla (référence pré-fine-tune) |
| `gemma3-4b` | Google | Gemma 3 4B |
| `ministral-3b` | Mistral | Ministral 3B |
| `ministral-3-8b` | Mistral | Ministral 3-8B |
| `qwen-coder-3b` | Alibaba | Qwen Coder 3B |
| `qwen3.5-9b` | Alibaba | Qwen 3.5 9B |
| `llama-3.2-3b` | Meta | Llama 3.2 3B |
| `helium-1-2b` | Helium | Helium 1 2B |
| `granite-4.1-3b` | IBM | Granite 4.1 3B |
| `jackrong-9b-opus` | Jackrong | Jackrong 9B Opus |

Scores complets : voir [`bench-results/BENCH_TABLE.md`](bench-results/BENCH_TABLE.md).

## Tâches d'évaluation

**lm-eval-harness** (100 exemples, seed 0) :
- `gsm8k_cot` (8-shot par défaut)
- `arc_easy` (0-shot)
- `mmlu_pro_computer_science` (0-shot)

**Perplexité MLX** (20 samples × 1024 seq) :
- Niches : `spice`, `stm32`, `kicad`, `embedded_iot`, `emc_power`
- Datasets HF : [`electron-rare/mascarade-*-dataset`](https://huggingface.co/electron-rare)

## Reproduction sur autre Mac

```bash
git clone https://github.com/electron-rare/electron-bench.git
cd electron-bench
python3.12 -m venv .venv && source .venv/bin/activate
pip install -U uv
uv pip install -r requirements.txt
python scripts/bench_new_models.py
```

Résultats append-only : `bench-results/all_models.txt`.
Régénérer table markdown : `python scripts/regen_bench_table.py`.

## Prérequis

- **Mac Apple Silicon** (M1/M2/M3+)
- **Python 3.12+**
- **≥16 Go RAM** (32 Go recommandé — modèles 8-9B peuvent OOM sur 16 Go)
- **Xcode complet + Metal Toolchain** (optionnel, pour wheel mlx fork) :
  `xcodebuild -downloadComponent MetalToolchain` (~688 Mo)

## Limitations connues (2026-05-10)

- **`ministral-3-8b` / `gsm8k_cot` 8-shot** : OOM Metal (cap GPU ~499K handles).
  Fork mlx branche `metal-3x-buffer-limit` : ×1.5 cap (748K) suffit qwen3.5-9b/helium, ×3 (1497K) pour ministral-3-8b.
- **`qwen3.5-9b`** : timeout 600s standard ; nécessite 1200-1500s ou fork mlx.
- **`helium-1-2b`** : NO_RESULT (template chat/tokenizer) ; test avec fork.
- **QuantizedKVCache 8-bit** : bloqué upstream mlx_lm 0.31.3 (pas `.merge()`).
  Voir `scripts/bench_oom_retry.py` (workaround patché, inutilisable jusqu'à ajout méthode).

## Liens

- Fork MLX : https://github.com/L-electron-Rare/mlx (branche `metal-3x-buffer-limit`)
- Build wheels CI : https://github.com/L-electron-Rare/mlx/actions/workflows/build-wheels.yml
- Datasets HF : https://huggingface.co/electron-rare

## Licence

MIT (code). Résultats publiés tels quels ; modèles sous licence d'origine.

## Gateway HTTP bench (2026-05-10)

`scripts/bench_gateway.py` — stdlib-only OpenAI-compat client to bench any
`/v1/chat/completions` endpoint. Configurable via `--endpoint`, `--models`,
`--rounds`, `--max-tokens`, optional `--out` JSON dump. Used to characterize
the eu-kiki/ailiance gateway (`electron-server:9300`) and direct workers
(Tower `:9304`, kxkm-ai tunnel `:8002`).

```bash
# Bench all 11 ailiance routes via the gateway
python3 scripts/bench_gateway.py --rounds 3 --max-tokens 64

# Bench a worker directly
python3 scripts/bench_gateway.py \
  --endpoint http://tower:9304/v1/chat/completions \
  --models eu-kiki-gemma --rounds 3
```

Results: `bench-results/gateway-*.json` (per-route p50 latency, tps, errors).

## Cross-machine aggregation (2026-05-10)

`docs/SYNTHESIS_2026-05-10.md` consolidates bench artefacts from macM1,
Studio, electron-server (124-cell `31_domains_baseline.json` + 12-model
`BENCH_TABLE.md` + 11-route gateway + Phase 1 quick eval).

`bench-results/aggregated/synthesis_31_domains.{csv,json}` — 124 rows
flattened (model, domain, ppl, stderr, status) for the 4-of-8 v2-baseline
matrix on macM1 (gemma E2B/E4B + ministral 3B/3-8B).

Also pushed to `grist.saillant.cc` (`dhyrySCayizD1PNqCNhCPN`) as 4 tables:
`Bench_31_domains` (124), `Bench_public` (12), `Bench_niches_ppl` (8),
`Bench_gateway` (11).

See `docs/SYNTHESIS_2026-05-10.md` and
`docs/2026-05-10-phase2-training-gaps.md` for the gap analysis and the
follow-up training plan.
