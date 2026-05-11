# Bench comparison — base vs tuned

- Base: `perplexity_base_20260511_0049.json` (64 rows)
- Tuned: `perplexity_v2-only_20260511_0135.json` (18 rows)
- Joined cells: 18

## medium35 (4/32 joined)

| domain | base_ppl | tuned_ppl | lift_pct | lift_log | base_n | tuned_n |
|---|---:|---:|---:|---:|---:|---:|
| chat-fr | 16.4362 | – | – | – | 50 | None |
| cpp | 11.1603 | – | – | – | 50 | None |
| docker-devops | 4.4293 | – | – | – | 50 | None |
| electronics | 6.823 | – | – | – | 50 | None |
| embedded | 27.73 | 7.56 | 72.74 | 1.2996 | 50 | 50 |
| emc-dsp-power | 33.501 | 7.6 | 77.31 | 1.4834 | 50 | 50 |
| freecad | 12.3239 | – | – | – | 3 | None |
| html-css | 4.4612 | – | – | – | 50 | None |
| iot | 33.1555 | – | – | – | 50 | None |
| kicad-dsl | 2.7093 | – | – | – | 50 | None |
| kicad-pcb | 2.0206 | – | – | – | 50 | None |
| llm-ops | 27.1713 | – | – | – | 50 | None |
| llm-orch | 10.0039 | – | – | – | 50 | None |
| lua-upy | 7.0968 | – | – | – | 44 | None |
| math-gsm8k | 11.3267 | 3.28 | 71.04 | 1.2393 | 50 | 50 |
| math-reasoning | 3.3573 | 2.05 | 38.94 | 0.4933 | 50 | 50 |
| ml-training | 6.6593 | – | – | – | 50 | None |
| multilingual-eu | 23.2369 | – | – | – | 50 | None |
| music-audio | 4.608 | – | – | – | 25 | None |
| platformio | 5.7289 | – | – | – | 35 | None |
| python | 3.9956 | – | – | – | 50 | None |
| rust | 4.2414 | – | – | – | 50 | None |
| rust-embedded | 15.1744 | – | – | – | 50 | None |
| security-fenrir | 9.2697 | – | – | – | 50 | None |
| shell | 60.7473 | – | – | – | 50 | None |
| spice-sim | 11.479 | – | – | – | 25 | None |
| sql | 6.6303 | – | – | – | 50 | None |
| traduction-tech | 46.2529 | – | – | – | 50 | None |
| typescript | 3.9749 | – | – | – | 50 | None |
| web-backend | 5.4677 | – | – | – | 50 | None |
| web-frontend | 5.0246 | – | – | – | 50 | None |
| yaml-json | 5.2643 | – | – | – | 50 | None |

**medium35 stats**: median lift = 71.89%, min = 38.94%, max = 77.31%, cells where adapter HURT (negative lift): 0

## qwen36 (14/32 joined)

| domain | base_ppl | tuned_ppl | lift_pct | lift_log | base_n | tuned_n |
|---|---:|---:|---:|---:|---:|---:|
| chat-fr | 6.9893 | – | – | – | 50 | None |
| cpp | 2.9354 | – | – | – | 50 | None |
| docker-devops | 2.9072 | – | – | – | 50 | None |
| electronics | 3.4056 | – | – | – | 50 | None |
| embedded | 14.5487 | – | – | – | 50 | None |
| emc-dsp-power | 12.312 | – | – | – | 50 | None |
| freecad | 3.6675 | – | – | – | 3 | None |
| html-css | 2.6096 | 1.76 | 32.56 | 0.3939 | 50 | 50 |
| iot | 16.2294 | 7.43 | 54.22 | 0.7813 | 50 | 50 |
| kicad-dsl | 2.3753 | – | – | – | 50 | None |
| kicad-pcb | 4.4189 | – | – | – | 50 | None |
| llm-ops | 10.5894 | 3.93 | 62.89 | 0.9912 | 50 | 50 |
| llm-orch | 5.0385 | 2.72 | 46.02 | 0.6165 | 50 | 50 |
| lua-upy | 3.2515 | – | – | – | 44 | None |
| math-gsm8k | 3.6319 | – | – | – | 50 | None |
| math-reasoning | 2.0512 | – | – | – | 50 | None |
| ml-training | 2.4106 | – | – | – | 50 | None |
| multilingual-eu | 8.4504 | – | – | – | 50 | None |
| music-audio | 2.8016 | 1.65 | 41.11 | 0.5294 | 25 | 25 |
| platformio | 3.8629 | 1.44 | 62.72 | 0.9868 | 35 | 35 |
| python | 2.6771 | 1.91 | 28.65 | 0.3376 | 50 | 50 |
| rust | 2.6313 | 1.91 | 27.41 | 0.3204 | 50 | 50 |
| rust-embedded | 2.7625 | – | – | – | 50 | None |
| security-fenrir | 4.1017 | – | – | – | 50 | None |
| shell | 19.9935 | 7.25 | 63.74 | 1.0144 | 50 | 50 |
| spice-sim | 4.2489 | – | – | – | 25 | None |
| sql | 3.9362 | 2.03 | 48.43 | 0.6622 | 50 | 50 |
| traduction-tech | 19.7821 | – | – | – | 50 | None |
| typescript | 2.8373 | 1.88 | 33.74 | 0.4116 | 50 | 50 |
| web-backend | 3.4693 | 2.0 | 42.35 | 0.5508 | 50 | 50 |
| web-frontend | 3.0245 | 1.98 | 34.53 | 0.4236 | 50 | 50 |
| yaml-json | 2.9129 | 2.02 | 30.65 | 0.3661 | 50 | 50 |

**qwen36 stats**: median lift = 41.73%, min = 27.41%, max = 63.74%, cells where adapter HURT (negative lift): 0
