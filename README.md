# electron-bench — benchmarking MLX pour modèles open-source et fine-tunes electron-rare

Snapshot reproductible des benchmarks lancés sur Mac Apple Silicon (M1 Pro 32 Go RAM)
avec [`mlx-lm`](https://github.com/ml-explore/mlx-lm) + [`lm-eval-harness`](https://github.com/EleutherAI/lm-evaluation-harness).

## Modèles benchmarkés

Bases publiques : `gemma3-4b`, `ministral-3b`, `ministral-3-8b`, `qwen-coder-3b`,
`qwen3.5-9b`, `llama-3.2-3b`, `helium-1-2b`, `granite-4.1-3b`, `jackrong-9b-opus`.

Fine-tunes electron-rare (Gemma 3 4B SFT + LoRA sur les 5 niches) :
`base` (Gemma 3 4B vanilla, référence), `eu-kiki`, `mascarade`.

Voir `bench-results/BENCH_TABLE.md` pour la table consolidée.

## Tâches

- **Accuracy publique** (lm-eval-harness, 100 exemples, seed 0) :
  - `gsm8k_cot` (8-shot, ou 4-shot avec QuantizedKVCache pour les 8B+)
  - `arc_easy` (0-shot)
  - `mmlu_pro_computer_science` (0-shot)
- **Perplexité 5 niches** (`mlx_lm.perplexity`, 20 samples × 1024 seq) :
  `spice`, `stm32`, `kicad`, `embedded_iot`, `emc_power`.

## Reproduction

```bash
git clone https://github.com/electron-rare/electron-bench.git
cd electron-bench
python3.12 -m venv .venv && source .venv/bin/activate
pip install -U pip uv
uv pip install -r requirements.txt
python scripts/bench_new_models.py
```

Les résultats sont append-only dans `bench-results/all_models.txt`.
Régénérer la table markdown : `python scripts/regen_bench_table.py`.

## Prérequis

- Mac Apple Silicon (M1/M2/M3 — testé sur M1 Pro)
- Python 3.12+
- ≥ 16 Go de RAM unifiée recommandés (le bench tourne sur 32 Go ;
  en dessous, plusieurs tâches OOM — voir limitations)
- Xcode complet **uniquement** si tu veux builder le fork mlx custom
  (`metal-3x-buffer-limit`). Pour le bench, `mlx` pip suffit.

## Limitations connues

- **`ministral-3-8b` / `gsm8k_cot`** : OOM (rc=-6, [METAL] Insufficient Memory)
  en 8-shot sur 32 Go. Workaround : `python scripts/bench_oom_retry.py`
  qui patch `make_prompt_cache` → `QuantizedKVCache(bits=8, group_size=64)`
  + 4-shot + cap `max-tokens=1024`.
- **`qwen3.5-9b`** : timeout 600s sur les 3 tâches lm-eval. Le retry kvq8
  bump à 1500s.
- **`helium-1-2b`** : `_NO RESULT` (modèle bf16 brut, KV cache fp16
  + 8-shot prompt = crash silencieux). Retry kvq8 idem.
- Les sous-dossiers `bench-results/<model>-<task>/` produits par
  `--output-dir` sont volumineux et **gitignorés** ; seuls les extraits
  consolidés sont versionnés.

## Liens

- Fork MLX custom (cap Metal 3× pour modèles >7B, build Xcode requis,
  non utilisé ici) : https://github.com/L-electron-Rare/mlx
  (branche `metal-3x-buffer-limit`).
- Datasets HF org : `electron-rare/mascarade-*-dataset`
  (https://huggingface.co/electron-rare).

## Licence

MIT pour le code de bench. Les résultats sont publiés tels quels ;
chaque modèle benchmarké reste sous sa licence d'origine
(voir colonne *License* de `BENCH_TABLE.md`).
