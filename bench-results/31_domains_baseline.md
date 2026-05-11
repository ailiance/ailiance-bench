# 31-domains baseline (perplexity, lower=better)

_Generated: 2026-05-10 15:45:07_

- Samples / domain: **25**, seq-len: **1024**
- Data: `/Users/electron/eu-kiki-data/hf-traced`
- Models: 8 (4-bit MLX only — fits in 32 GB RAM)

| Model | chat-fr | cpp | docker-devops | embedded | emc-dsp-power | freecad | html-css | iot | kicad-dsl | kicad-pcb | llm-ops | llm-orch | lua-upy | math-gsm8k | math-reasoning | ml-training | multilingual-eu | music-audio | platformio | python | rust | rust-embedded | security-fenrir | shell | spice-sim | sql | traduction-tech | typescript | web-backend | web-frontend | yaml-json |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **gemma-e4b-eu-kiki-base** | 115.54 | 23.71 | 12.84 | 198.96 | 170.16 | 21.93 | 16.14 | 175.16 | 11.01 | 5.44 | 41.15 | 29.51 | 24.22 | 22.11 | 9.54 | 20.93 | 196.98 | 18.23 | 15.85 | 12.42 | 12.16 | 20.95 | 98.28 | 373.05 | 33.62 | 19.77 | 334.51 | 11.78 | 16.02 | 14.37 | 17.63 |
| **gemma-e2b** | 201.56 | 42.13 | 13.77 | 150.31 | 316.08 | 35.80 | 17.97 | 141.11 | 16.03 | 7.35 | 26.33 | 24.96 | 35.48 | 24.30 | 10.68 | 32.72 | 270.78 | 16.09 | 16.33 | 12.87 | 13.26 | 32.05 | 220.88 | 126.06 | 42.40 | 14.41 | 328.38 | 13.34 | 16.84 | 15.32 | 18.42 |
| **ministral-3b** | 7.12 | 5.39 | 6.26 | 8.64 | 10.15 | 5.56 | 6.08 | 8.98 | 4.29 | 2.94 | 6.74 | 6.65 | 6.67 | 6.28 | 5.61 | 5.42 | 7.78 | 5.91 | 6.92 | 6.38 | 6.15 | 7.15 | 10.48 | 5.78 | 6.81 | 6.05 | 6.48 | 6.34 | 6.21 | 6.07 | 6.47 |
| **ministral-3-8b** | 7.56 | 4.85 | 6.14 | 10.42 | 10.36 | 5.01 | 6.19 | 10.91 | 4.02 | 2.61 | 6.47 | 6.40 | 6.74 | 6.16 | 4.99 | 4.99 | 7.90 | 6.06 | 7.60 | 6.09 | 6.22 | 6.38 | 9.31 | 6.29 | 7.61 | 6.09 | 6.19 | 6.23 | 6.38 | 6.03 | 6.63 |
| **ministral-3-14b-instruct** | 5.39 | 3.83 | 4.83 | 6.13 | 7.52 | 4.23 | 4.58 | 6.36 | 3.39 | 2.31 | 4.70 | 4.72 | 5.24 | 4.71 | 4.10 | 4.36 | 5.61 | 4.45 | 5.59 | 4.80 | 4.80 | 5.21 | 7.34 | 4.28 | 5.08 | 4.59 | 4.80 | 4.82 | 4.85 | 4.56 | 4.90 |
| **ministral-3-14b-reasoning** | 6.79 | 3.35 | 3.90 | 7.72 | 9.98 | 3.96 | 3.68 | 8.12 | 2.87 | 1.96 | 4.51 | 4.66 | 4.87 | 4.18 | 3.21 | 3.81 | 7.37 | 3.96 | 3.84 | 3.83 | 3.80 | 5.13 | 7.42 | 4.65 | 5.23 | 3.98 | 5.96 | 3.83 | 4.08 | 3.96 | 4.14 |
| **granite-4.1-3b** | 22.66 | 36.70 | 19.38 | 73.58 | 26.23 | 26.21 | 72.91 | 70.59 | 6.70 | 4.87 | 132.85 | 145.49 | 46.56 | 24.73 | 9.90 | 37.72 | 29.05 | 59.13 | 17.75 | 20.19 | 17.69 | 50.37 | 17.69 | 883.12 | 19.58 | 26.33 | 89.17 | 17.56 | 64.66 | 76.76 | 78.13 |
| **granite-4.1-30b** | 12.84 | 41.73 | 16.11 | 37.48 | 20.32 | 27.65 | 41.59 | 38.63 | 5.66 | 3.76 | 52.71 | 75.89 | 39.19 | 5.72 | 6.40 | 45.12 | 13.55 | 43.47 | 12.65 | 18.05 | 14.92 | 74.47 | 16.46 | 75.66 | 17.92 | 16.27 | 18.35 | 15.28 | 52.17 | 52.78 | 62.94 |

## Models tested

- **gemma-e4b-eu-kiki-base** — `lmstudio-community/gemma-4-E4B-it-MLX-4bit`
- **gemma-e2b** — `lmstudio-community/gemma-4-E2B-it-MLX-4bit`
- **ministral-3b** — `mlx-community/Ministral-3-3B-Instruct-2512-4bit`
- **ministral-3-8b** — `mlx-community/Ministral-3-8B-Instruct-2512-4bit`
- **ministral-3-14b-instruct** — `mlx-community/Ministral-3-14B-Instruct-2512-4bit`
- **ministral-3-14b-reasoning** — `mlx-community/Ministral-3-14B-Reasoning-2512-4bit`
- **granite-4.1-3b** — `mlx-community/granite-4.1-3b-4bit`
- **granite-4.1-30b** — `mlx-community/granite-4.1-30b-4bit`
