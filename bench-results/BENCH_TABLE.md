# Bench multi-modèles consolidé (final, 2026-05-10)

## Public benchs (% accuracy, ↑ better)

| Model | Provider | License | gsm-S | gsm-F | arc | arc-n | mmlu | mmluPro |
|---|---|---|---:|---:|---:|---:|---:|---:|
| **base** | Google | Gemma Terms | 23.0 | 31.0 | 62.0 | 63.0 | 56.8 | 0.0 |
| **eu-kiki** | electron-rare | CC-BY-SA-4.0 | 52.0 | 74.0 | 78.5 | 80.5 | — | 58.0 |
| **mascarade** | electron-rare | CC-BY-SA-4.0 | 29.0 | 73.0 | 77.0 | 78.0 | — | 40.0 |
| **gemma3-4b** | Google | Gemma Terms | — | — | 66.0 | 62.5 | — | 38.0 |
| **ministral-3b** | Mistral | Apache 2.0 | — | — | 64.0 | 35.0 | — | 16.0 |
| **qwen-coder-3b** | Alibaba | Apache 2.0 | 37.0 | 62.0 | 64.0 | 63.5 | — | 34.0 |
| **llama-3.2-3b** | Meta | Llama 3.2 | — | — | 65.5 | 63.5 | — | 36.0 |
| **qwen3.5-9b** | Alibaba | Apache 2.0 | TO | TO | TO | TO | — | TO |
| **jackrong-9b-opus** | Jackrong (distill Opus) | Apache 2.0 + Anthropic AUP? | 64.0 | 78.0 | 54.0 | 53.0 | — | 0.0 |
| **helium-1-2b** | Kyutai | CC-BY 4.0 | — | — | — | — | — | — |
| **ministral-3-8b** | Mistral | Apache 2.0 | — | — | — | — | — | — |
| **granite-4.1-3b** | IBM | Apache 2.0 | — | — | — | — | — | — |

## Niches perplexity (lower=better)

| Model | spice | stm32 | kicad | embedded_iot | emc_power |
|---|---:|---:|---:|---:|---:|
| **base** | 21.75 | 6.39 | 19.55 | 32.50 | 254.93 |
| **eu-kiki** | 9.53 | 3.56 | 9.54 | 10.80 | 42.26 |
| **mascarade** | 6.61 | 3.00 | 7.95 | 9.03 | 39.71 |
| **gemma3-4b** | — | — | — | — | — |
| **ministral-3b** | 6.18 | 2.54 | 3.94 | 8.73 | 18.30 |
| **qwen-coder-3b** | 4.75 | 2.18 | 2.89 | 5.67 | 20.02 |
| **llama-3.2-3b** | — | — | — | — | — |
| **qwen3.5-9b** | — | — | — | — | — |
| **jackrong-9b-opus** | 3.37 | 1.64 | 2.33 | 4.28 | 12.50 |
| **helium-1-2b** | — | — | — | — | — |
| **ministral-3-8b** | — | — | — | — | — |
| **granite-4.1-3b** | — | — | — | — | — |
