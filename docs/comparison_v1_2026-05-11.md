# Bench comparison — base vs tuned

- Base: `perplexity_base_20260511_0405.json` (96 rows)
- Tuned: `perplexity_v1-only_20260510_2215.json` (30 rows)
- Joined cells: 30

## apertus (5/32 joined)

| domain | base_ppl | tuned_ppl | lift_pct | lift_log | base_n | tuned_n |
|---|---:|---:|---:|---:|---:|---:|
| chat-fr | 7.0481 | – | – | – | 50 | None |
| cpp | 3.0385 | – | – | – | 50 | None |
| docker-devops | 2.9566 | – | – | – | 50 | None |
| electronics | 3.1329 | 3.17 | -1.18 | -0.0118 | 50 | 50 |
| embedded | 13.267 | 10.32 | 22.21 | 0.2512 | 50 | 50 |
| emc-dsp-power | 11.385 | – | – | – | 50 | None |
| freecad | 3.528 | – | – | – | 3 | None |
| html-css | 2.9499 | – | – | – | 50 | None |
| iot | 14.4319 | – | – | – | 50 | None |
| kicad-dsl | 2.3915 | – | – | – | 50 | None |
| kicad-pcb | 1.5547 | – | – | – | 50 | None |
| llm-ops | 25.1843 | – | – | – | 50 | None |
| llm-orch | 7.495 | – | – | – | 50 | None |
| lua-upy | 4.2831 | – | – | – | 44 | None |
| math-gsm8k | 4.7497 | 4.19 | 11.78 | 0.1254 | 50 | 50 |
| math-reasoning | 2.0394 | 2.17 | -6.4 | -0.0621 | 50 | 50 |
| ml-training | 2.1838 | – | – | – | 50 | None |
| multilingual-eu | 7.2846 | – | – | – | 50 | None |
| music-audio | 3.597 | – | – | – | 25 | None |
| platformio | 4.0071 | – | – | – | 35 | None |
| python | 2.8396 | – | – | – | 50 | None |
| rust | 2.8207 | – | – | – | 50 | None |
| rust-embedded | 2.9861 | – | – | – | 50 | None |
| security-fenrir | 6.1666 | – | – | – | 50 | None |
| shell | 49.8794 | – | – | – | 50 | None |
| spice-sim | 5.1841 | 3.99 | 23.03 | 0.2618 | 25 | 25 |
| sql | 4.0137 | – | – | – | 50 | None |
| traduction-tech | 26.0059 | – | – | – | 50 | None |
| typescript | 2.7828 | – | – | – | 50 | None |
| web-backend | 3.6535 | – | – | – | 50 | None |
| web-frontend | 3.1581 | – | – | – | 50 | None |
| yaml-json | 3.1648 | – | – | – | 50 | None |

**apertus stats**: median lift = 11.78%, min = -6.40%, max = 23.03%, cells where adapter HURT (negative lift): 2

## devstral (22/32 joined)

| domain | base_ppl | tuned_ppl | lift_pct | lift_log | base_n | tuned_n |
|---|---:|---:|---:|---:|---:|---:|
| chat-fr | 6.4577 | – | – | – | 50 | None |
| cpp | 2.4355 | 1.94 | 20.34 | 0.2275 | 50 | 50 |
| docker-devops | 2.3794 | 2.06 | 13.42 | 0.1441 | 50 | 50 |
| electronics | 2.6021 | – | – | – | 50 | None |
| embedded | 9.806 | – | – | – | 50 | None |
| emc-dsp-power | 8.4449 | – | – | – | 50 | None |
| freecad | 2.6858 | 2.49 | 7.29 | 0.0757 | 3 | 3 |
| html-css | 2.3159 | 2.0 | 13.64 | 0.1467 | 50 | 50 |
| iot | 10.5029 | 6.15 | 41.44 | 0.5352 | 50 | 50 |
| kicad-dsl | 1.826 | 1.37 | 24.97 | 0.2873 | 50 | 50 |
| kicad-pcb | 1.3965 | 1.24 | 11.21 | 0.1189 | 50 | 50 |
| llm-ops | 9.9532 | 6.8 | 31.68 | 0.381 | 50 | 50 |
| llm-orch | 4.3541 | 3.53 | 18.93 | 0.2098 | 50 | 50 |
| lua-upy | 3.2904 | 2.67 | 18.85 | 0.2089 | 44 | 44 |
| math-gsm8k | 3.4253 | – | – | – | 50 | None |
| math-reasoning | 1.7502 | – | – | – | 50 | None |
| ml-training | 1.9076 | 1.78 | 6.69 | 0.0692 | 50 | 50 |
| multilingual-eu | 7.0474 | – | – | – | 50 | None |
| music-audio | 2.4385 | 1.73 | 29.05 | 0.3433 | 25 | 25 |
| platformio | 3.2229 | 1.56 | 51.6 | 0.7256 | 35 | 35 |
| python | 2.2769 | 2.04 | 10.4 | 0.1099 | 50 | 50 |
| rust | 2.2903 | 2.06 | 10.06 | 0.106 | 50 | 50 |
| rust-embedded | 2.335 | 2.0 | 14.35 | 0.1549 | 50 | 50 |
| security-fenrir | 4.0882 | – | – | – | 50 | None |
| shell | 14.4948 | 13.44 | 7.28 | 0.0756 | 50 | 50 |
| spice-sim | 3.8341 | – | – | – | 25 | None |
| sql | 2.7401 | 2.2 | 19.71 | 0.2195 | 50 | 50 |
| traduction-tech | 15.632 | – | – | – | 50 | None |
| typescript | 2.2345 | 1.96 | 12.28 | 0.1311 | 50 | 50 |
| web-backend | 2.6519 | 2.13 | 19.68 | 0.2192 | 50 | 50 |
| web-frontend | 2.4984 | 2.16 | 13.54 | 0.1455 | 50 | 50 |
| yaml-json | 2.4509 | 2.12 | 13.5 | 0.145 | 50 | 50 |

**devstral stats**: median lift = 14.00%, min = 6.69%, max = 51.60%, cells where adapter HURT (negative lift): 0

## eurollm (3/32 joined)

| domain | base_ppl | tuned_ppl | lift_pct | lift_log | base_n | tuned_n |
|---|---:|---:|---:|---:|---:|---:|
| chat-fr | 7.1409 | 5.12 | 28.3 | 0.3327 | 50 | 50 |
| cpp | 3.2736 | – | – | – | 50 | None |
| docker-devops | 3.0455 | – | – | – | 50 | None |
| electronics | 3.2062 | – | – | – | 50 | None |
| embedded | 13.8874 | – | – | – | 50 | None |
| emc-dsp-power | 9.5807 | – | – | – | 50 | None |
| freecad | 2.8383 | – | – | – | 3 | None |
| html-css | 2.7564 | – | – | – | 50 | None |
| iot | 15.0451 | – | – | – | 50 | None |
| kicad-dsl | 2.5925 | – | – | – | 50 | None |
| kicad-pcb | 1.5656 | – | – | – | 50 | None |
| llm-ops | 13.8565 | – | – | – | 50 | None |
| llm-orch | 4.8595 | – | – | – | 50 | None |
| lua-upy | 3.4673 | – | – | – | 44 | None |
| math-gsm8k | 3.2587 | – | – | – | 50 | None |
| math-reasoning | 1.9585 | – | – | – | 50 | None |
| ml-training | 2.1377 | – | – | – | 50 | None |
| multilingual-eu | 9.0867 | 6.63 | 27.04 | 0.3152 | 50 | 50 |
| music-audio | 2.9347 | – | – | – | 25 | None |
| platformio | 4.3107 | – | – | – | 35 | None |
| python | 3.0579 | – | – | – | 50 | None |
| rust | 2.9942 | – | – | – | 50 | None |
| rust-embedded | 3.3348 | – | – | – | 50 | None |
| security-fenrir | 4.7759 | – | – | – | 50 | None |
| shell | 45.7311 | – | – | – | 50 | None |
| spice-sim | 4.7247 | – | – | – | 25 | None |
| sql | 3.735 | – | – | – | 50 | None |
| traduction-tech | 29.3798 | 9.37 | 68.11 | 1.1428 | 50 | 50 |
| typescript | 2.8815 | – | – | – | 50 | None |
| web-backend | 2.9383 | – | – | – | 50 | None |
| web-frontend | 2.8502 | – | – | – | 50 | None |
| yaml-json | 2.908 | – | – | – | 50 | None |

**eurollm stats**: median lift = 28.30%, min = 27.04%, max = 68.11%, cells where adapter HURT (negative lift): 0
