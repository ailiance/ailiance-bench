# Bench cluster — synthèse 2026-05-10

Aggregated from all machines (macM1, Studio, Tower, kxkm-ai, electron-server) at 18:15 CEST.

## Sources

| Fichier | Origine | Date | Cellules |
|---|---|---|---:|
| `31_domains_baseline.json` | macM1 `~/bench-results/` | 2026-05-10 15:45 | 124 (4×31) |
| `BENCH_TABLE.md` | macM1 + Studio `~/ailiance-bench/bench-results/` | 2026-05-10 13:12 | 72 (12×6) public + 60 (12×5) niches PPL |
| `perplexity_v1-only_*.json` | Studio `~/ailiance/output/eval/raw/` | 2026-05-10 16:25 | 3 (Phase 1 quick eval) |
| `gateway-2026-05-10-1730-final.json` | ailiance-bench | 2026-05-10 17:30 | 11 (gateway HTTP) |
| `tower-direct-2026-05-10-1535.json` | ailiance-bench | 2026-05-10 15:35 | 1 |
| `bench-complete.json` (older) | Studio `~/KIKI-Mac_tunner/output/micro-kiki/eval/` | 2026-04-19 | (Brainstacks v3) |

## Public benchmarks (% accuracy, ↑ better)

12 modèles × 6 datasets (gsm8k strict/flex, arc, arc_n, mmlu, mmlu_pro). Source: `BENCH_TABLE.md`.

| Model | Provider | Lic | gsm-S | gsm-F | arc | arc-n | mmlu | mmluPro |
|---|---|---|---:|---:|---:|---:|---:|---:|
| **base (gemma3-4b)** | Google | Gemma | 23.0 | 31.0 | 62.0 | 63.0 | 56.8 | 0.0 |
| **ailiance** | electron-rare | CC-BY-SA-4.0 | **52.0** | **74.0** | **78.5** | **80.5** | — | **58.0** |
| **mascarade** | electron-rare | CC-BY-SA-4.0 | 29.0 | 73.0 | 77.0 | 78.0 | — | 40.0 |
| **gemma3-4b** | Google | Gemma | — | — | 66.0 | 62.5 | — | 38.0 |
| **ministral-3b** | Mistral | Apache 2.0 | — | — | 64.0 | 35.0 | — | 16.0 |
| **ministral-3-8b** | Mistral | Apache 2.0 | — | — | 64.0 | 60.0 | — | — |
| **qwen-coder-3b** | Alibaba | Apache 2.0 | 37.0 | 62.0 | 64.0 | 63.5 | — | 34.0 |
| **llama-3.2-3b** | Meta | Llama 3.2 | — | — | 65.5 | 63.5 | — | 36.0 |
| **qwen3.5-9b** | Alibaba | Apache 2.0 | TO | TO | TO | TO | — | TO |
| **jackrong-9b-opus** | Jackrong (distill) | Apache 2.0 | **64.0** | **78.0** | 54.0 | 53.0 | — | 0.0 |
| **granite-4.1-3b** | IBM | Apache 2.0 | 36.0 | 73.0 | 56.0 | 57.0 | — | 51.0 |
| **helium-1-2b** | Kyutai | CC-BY 4.0 | — | — | — | — | — | — |

**Best per benchmark** (parmi les modèles testés) :
- gsm-S: jackrong-9b-opus 64% (ailiance 52%)
- gsm-F: jackrong-9b-opus 78% (ailiance 74%)
- arc: **ailiance 78.5%**
- arc-n: **ailiance 80.5%**
- mmlu: base 56.8%
- mmluPro: **ailiance 58%**

## Niches perplexity (lower=better) — 5 niches métier

12 modèles × 5 niches (spice, stm32, kicad, embedded_iot, emc_power). Source: `BENCH_TABLE.md`.

| Model | spice | stm32 | kicad | embedded_iot | emc_power |
|---|---:|---:|---:|---:|---:|
| **base** | 21.75 | 6.39 | 19.55 | 32.50 | 254.93 |
| **ailiance** | 9.53 | 3.56 | 9.54 | 10.80 | 42.26 |
| **mascarade** | 6.61 | 3.00 | 7.95 | 9.03 | 39.71 |
| **ministral-3b** | 6.18 | 2.54 | 3.94 | 8.73 | 18.30 |
| **ministral-3-8b** | 4.48 | 2.67 | 1.82 | 5.93 | 18.98 |
| **qwen-coder-3b** | 4.75 | 2.18 | 2.89 | 5.67 | 20.02 |
| **jackrong-9b-opus** | **3.37** | **1.64** | 2.33 | **4.28** | **12.50** |
| **granite-4.1-3b** | 9.84 | 41.43 | 2.85 | 33.46 | 35.75 |

**Best per niche** : jackrong-9b-opus dominate spice/stm32/embedded_iot/emc_power; ministral-3-8b best sur kicad (1.82). ailiance et mascarade meilleurs que base mais battus par ministral-3-8b et jackrong-9b-opus sur niches.

## 31-domains MLX baseline (2026-05-10 15:45, 4/8 modèles complets)

Source: `31_domains_baseline.json` (124 cells). Models en cours : ministral-3-14b-instruct, ministral-3-14b-reasoning, granite-4.1-3b, granite-4.1-30b (status `0` à 14:53 — bench fini ou en panne).

Domaines couverts (31) : chat-fr, cpp, docker-devops, embedded, emc-dsp-power, freecad, html-css, iot, kicad-dsl, kicad-pcb, llm-ops, llm-orch, lua-upy, math, math-gsm8k, math-reasoning, ml-training, multilingual-eu, music-audio, platformio, python, redaction-multilingue, rust, rust-embedded, security-fenrir, shell, spice-sim, sql, stm32, traduction-tech, typescript, web-backend, web-frontend, yaml-json.

PPL résumé per modèle (mean / max sur les 31 domaines) :

| Modèle | mean PPL | min | max | best domain |
|---|---:|---:|---:|---|
| gemma-e4b-ailiance-base | (cf JSON détail) | — | — | — |
| gemma-e2b | — | — | — | — |
| ministral-3b | — | — | — | — |
| ministral-3-8b | — | — | — | — |

(Détails : `synthesis_31_domains.csv` — 124 lignes (model, domain, ppl, stderr, status, samples, date, source))

## Phase 1 quick eval EU AI Act stack (Apertus 70B / Devstral 24B / EuroLLM 22B)

Source: `perplexity_v1-only_20260510_1625.json` (Studio MLX). 3 cellules pilote.

| Modèle | Domaine | Loss | PPL | Verdict |
|---|---|---:|---:|---|
| apertus | math-gsm8k | 1.47 | **4.35** | ✅ adapter math fonctionne |
| eurollm | chat-fr | 1.77 | **5.89** | ✅ adapter chat-fr fonctionne |
| devstral | python | 12.78 | 355 379 | ⚠️ base Devstral broken (template/tokenizer issue) |

## Gateway end-to-end HTTP bench (electron-server :9300)

Source: `gateway-2026-05-10-1730-final.json`. Mesure latency + tps via OpenAI-compat API.

| Route | p50 latence | p50 tps | Backend |
|---|---:|---:|---|
| `ailiance-qwen` | **0.77s** | **20.1** | kxkm-ai Qwen 80B MoE |
| `ailiance` (default) | 0.79s | 20.2 | router fallback |
| `ailiance-gemma` | 1.04s | 15.4 | Tower Gemma 3 4B |
| `ailiance-gemma2` | 2.96s | 5.4 | macM1 Gemma 4 E2B |
| `ailiance-ministral` | 3.37s | 4.7 | macM1 Ministral 14B Instruct |
| `ailiance-ministral-reasoning` | 3.37s | 4.7 | macM1 Ministral 14B Reasoning |
| `ailiance-gemma4` | 3.92s | 4.1 | macM1 Gemma 4 E4B + LoRA |
| `ailiance-eurollm` | 4.16s | 0 (bug #10) | Studio EuroLLM 22B |
| `ailiance-granite` | 6.85s | 2.3 | kxkm-ai Granite 30B Q4 |
| `ailiance-apertus` | — | — | ❌ Studio :9301 down |
| `ailiance-mistral` | — | — | ❌ Studio :9301 down |

## Older artefacts (Brainstacks 35B-A3B, avril 2026)

| Fichier | Date | Type | Notes |
|---|---|---|---|
| `bench-complete.json` | 2026-04-19 | Brainstacks v3 r=16 fleet eval | DEAD adapters (lora_B = 0) |
| `base_model_comparison.json` | 2026-04-18 | Base model PPL baseline | |
| `quality-test-35b.json` | 2026-04-19 | 35B-A3B quality test | |
| `fused_eval_results.json` | 2026-04-17 | Fused stacks eval | V2/V3 PPL identiques bit-à-bit (bug d'éval) |

Pour analyse plus profonde, voir `KIKI-Mac_tunner/output/micro-kiki/eval/`.

## Lacunes identifiées

1. **31_domains_baseline.json incomplet** : 4/8 modèles complets, 4 manquants (ministral-14B×2, granite-3B + 30B)
2. **EU AI Act stack** : Phase 1 quick eval = 3/49 cellules (1 par modèle). Le full eval Phase 3 (--compare) crashe Killed:9 OOM.
3. **Devstral broken** : base model retourne quasi random tokens (PPL 355k). À investiguer (tokenizer/template).
4. **Apertus + Mistral down** : Studio :9301 worker pas démarré.
5. **EuroLLM content empty** : issue #10, double bug runtime.py.
6. **Niches PPL** ne couvre que 5 domaines. 26 autres dans le 31_domains track.

## Prochaines actions concrètes

1. Compléter 31_domains_baseline (4 modèles restants → 248 cellules)
2. Démarrer Studio :9301 worker → bench Apertus + Mistral 128B
3. Patcher eval_framework.py pour mode séquentiel-strict (un modèle à la fois) → Phase 3 full eval sans OOM
4. Investiguer Devstral base model (anomalie PPL)
5. Re-train chat-fr/traduction-tech adapters (issue #10 dépendance)
