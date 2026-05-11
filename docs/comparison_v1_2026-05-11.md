# Bench comparison — base vs tuned

- Base: `perplexity_base_20260511_0405.json` (96 rows)
- Tuned: `perplexity_v1-only_20260510_2215.json` (30 rows)
- Joined cells: 30
- Headline metric: **lift_log** (scale-invariant); cells with n<25 flagged ⚠️ and excluded from median.

## apertus (5/32 joined, 0 flagged n<25)

| flag | domain | base_ppl | tuned_ppl | lift_log | lift_pct | base_n | tuned_n |
|---|---|---:|---:|---:|---:|---:|---:|
| ⚠️ n<25 | chat-fr | 7.0481 | – | – | – | 50 | None |
| ⚠️ n<25 | cpp | 3.0385 | – | – | – | 50 | None |
| ⚠️ n<25 | docker-devops | 2.9566 | – | – | – | 50 | None |
|  | electronics | 3.1329 | 3.17 | -0.0118 | -1.18 | 50 | 50 |
|  | embedded | 13.267 | 10.32 | 0.2512 | 22.21 | 50 | 50 |
| ⚠️ n<25 | emc-dsp-power | 11.385 | – | – | – | 50 | None |
| ⚠️ n<25 | freecad | 3.528 | – | – | – | 3 | None |
| ⚠️ n<25 | html-css | 2.9499 | – | – | – | 50 | None |
| ⚠️ n<25 | iot | 14.4319 | – | – | – | 50 | None |
| ⚠️ n<25 | kicad-dsl | 2.3915 | – | – | – | 50 | None |
| ⚠️ n<25 | kicad-pcb | 1.5547 | – | – | – | 50 | None |
| ⚠️ n<25 | llm-ops | 25.1843 | – | – | – | 50 | None |
| ⚠️ n<25 | llm-orch | 7.495 | – | – | – | 50 | None |
| ⚠️ n<25 | lua-upy | 4.2831 | – | – | – | 44 | None |
|  | math-gsm8k | 4.7497 | 4.19 | 0.1254 | 11.78 | 50 | 50 |
|  | math-reasoning | 2.0394 | 2.17 | -0.0621 | -6.4 | 50 | 50 |
| ⚠️ n<25 | ml-training | 2.1838 | – | – | – | 50 | None |
| ⚠️ n<25 | multilingual-eu | 7.2846 | – | – | – | 50 | None |
| ⚠️ n<25 | music-audio | 3.597 | – | – | – | 25 | None |
| ⚠️ n<25 | platformio | 4.0071 | – | – | – | 35 | None |
| ⚠️ n<25 | python | 2.8396 | – | – | – | 50 | None |
| ⚠️ n<25 | rust | 2.8207 | – | – | – | 50 | None |
| ⚠️ n<25 | rust-embedded | 2.9861 | – | – | – | 50 | None |
| ⚠️ n<25 | security-fenrir | 6.1666 | – | – | – | 50 | None |
| ⚠️ n<25 | shell | 49.8794 | – | – | – | 50 | None |
|  | spice-sim | 5.1841 | 3.99 | 0.2618 | 23.03 | 25 | 25 |
| ⚠️ n<25 | sql | 4.0137 | – | – | – | 50 | None |
| ⚠️ n<25 | traduction-tech | 26.0059 | – | – | – | 50 | None |
| ⚠️ n<25 | typescript | 2.7828 | – | – | – | 50 | None |
| ⚠️ n<25 | web-backend | 3.6535 | – | – | – | 50 | None |
| ⚠️ n<25 | web-frontend | 3.1581 | – | – | – | 50 | None |
| ⚠️ n<25 | yaml-json | 3.1648 | – | – | – | 50 | None |

**apertus stats** (n≥25, 5 cells): median log-lift = 0.1254 (e13.36% effective), min = -0.0621, max = 0.2618, median lift_pct (legacy) = 11.78%, cells where adapter HURT (negative log-lift): 2, flagged (n<25): 0

## devstral (22/32 joined, 1 flagged n<25)

| flag | domain | base_ppl | tuned_ppl | lift_log | lift_pct | base_n | tuned_n |
|---|---|---:|---:|---:|---:|---:|---:|
| ⚠️ n<25 | chat-fr | 6.4577 | – | – | – | 50 | None |
|  | cpp | 2.4355 | 1.94 | 0.2275 | 20.34 | 50 | 50 |
|  | docker-devops | 2.3794 | 2.06 | 0.1441 | 13.42 | 50 | 50 |
| ⚠️ n<25 | electronics | 2.6021 | – | – | – | 50 | None |
| ⚠️ n<25 | embedded | 9.806 | – | – | – | 50 | None |
| ⚠️ n<25 | emc-dsp-power | 8.4449 | – | – | – | 50 | None |
| ⚠️ n<25 | freecad | 2.6858 | 2.49 | 0.0757 | 7.29 | 3 | 3 |
|  | html-css | 2.3159 | 2.0 | 0.1467 | 13.64 | 50 | 50 |
|  | iot | 10.5029 | 6.15 | 0.5352 | 41.44 | 50 | 50 |
|  | kicad-dsl | 1.826 | 1.37 | 0.2873 | 24.97 | 50 | 50 |
|  | kicad-pcb | 1.3965 | 1.24 | 0.1189 | 11.21 | 50 | 50 |
|  | llm-ops | 9.9532 | 6.8 | 0.381 | 31.68 | 50 | 50 |
|  | llm-orch | 4.3541 | 3.53 | 0.2098 | 18.93 | 50 | 50 |
|  | lua-upy | 3.2904 | 2.67 | 0.2089 | 18.85 | 44 | 44 |
| ⚠️ n<25 | math-gsm8k | 3.4253 | – | – | – | 50 | None |
| ⚠️ n<25 | math-reasoning | 1.7502 | – | – | – | 50 | None |
|  | ml-training | 1.9076 | 1.78 | 0.0692 | 6.69 | 50 | 50 |
| ⚠️ n<25 | multilingual-eu | 7.0474 | – | – | – | 50 | None |
|  | music-audio | 2.4385 | 1.73 | 0.3433 | 29.05 | 25 | 25 |
|  | platformio | 3.2229 | 1.56 | 0.7256 | 51.6 | 35 | 35 |
|  | python | 2.2769 | 2.04 | 0.1099 | 10.4 | 50 | 50 |
|  | rust | 2.2903 | 2.06 | 0.106 | 10.06 | 50 | 50 |
|  | rust-embedded | 2.335 | 2.0 | 0.1549 | 14.35 | 50 | 50 |
| ⚠️ n<25 | security-fenrir | 4.0882 | – | – | – | 50 | None |
|  | shell | 14.4948 | 13.44 | 0.0756 | 7.28 | 50 | 50 |
| ⚠️ n<25 | spice-sim | 3.8341 | – | – | – | 25 | None |
|  | sql | 2.7401 | 2.2 | 0.2195 | 19.71 | 50 | 50 |
| ⚠️ n<25 | traduction-tech | 15.632 | – | – | – | 50 | None |
|  | typescript | 2.2345 | 1.96 | 0.1311 | 12.28 | 50 | 50 |
|  | web-backend | 2.6519 | 2.13 | 0.2192 | 19.68 | 50 | 50 |
|  | web-frontend | 2.4984 | 2.16 | 0.1455 | 13.54 | 50 | 50 |
|  | yaml-json | 2.4509 | 2.12 | 0.145 | 13.5 | 50 | 50 |

**devstral stats** (n≥25, 21 cells): median log-lift = 0.1549 (e16.75% effective), min = 0.0692, max = 0.7256, median lift_pct (legacy) = 14.35%, cells where adapter HURT (negative log-lift): 0, flagged (n<25): 1

## eurollm (3/32 joined, 0 flagged n<25)

| flag | domain | base_ppl | tuned_ppl | lift_log | lift_pct | base_n | tuned_n |
|---|---|---:|---:|---:|---:|---:|---:|
|  | chat-fr | 7.1409 | 5.12 | 0.3327 | 28.3 | 50 | 50 |
| ⚠️ n<25 | cpp | 3.2736 | – | – | – | 50 | None |
| ⚠️ n<25 | docker-devops | 3.0455 | – | – | – | 50 | None |
| ⚠️ n<25 | electronics | 3.2062 | – | – | – | 50 | None |
| ⚠️ n<25 | embedded | 13.8874 | – | – | – | 50 | None |
| ⚠️ n<25 | emc-dsp-power | 9.5807 | – | – | – | 50 | None |
| ⚠️ n<25 | freecad | 2.8383 | – | – | – | 3 | None |
| ⚠️ n<25 | html-css | 2.7564 | – | – | – | 50 | None |
| ⚠️ n<25 | iot | 15.0451 | – | – | – | 50 | None |
| ⚠️ n<25 | kicad-dsl | 2.5925 | – | – | – | 50 | None |
| ⚠️ n<25 | kicad-pcb | 1.5656 | – | – | – | 50 | None |
| ⚠️ n<25 | llm-ops | 13.8565 | – | – | – | 50 | None |
| ⚠️ n<25 | llm-orch | 4.8595 | – | – | – | 50 | None |
| ⚠️ n<25 | lua-upy | 3.4673 | – | – | – | 44 | None |
| ⚠️ n<25 | math-gsm8k | 3.2587 | – | – | – | 50 | None |
| ⚠️ n<25 | math-reasoning | 1.9585 | – | – | – | 50 | None |
| ⚠️ n<25 | ml-training | 2.1377 | – | – | – | 50 | None |
|  | multilingual-eu | 9.0867 | 6.63 | 0.3152 | 27.04 | 50 | 50 |
| ⚠️ n<25 | music-audio | 2.9347 | – | – | – | 25 | None |
| ⚠️ n<25 | platformio | 4.3107 | – | – | – | 35 | None |
| ⚠️ n<25 | python | 3.0579 | – | – | – | 50 | None |
| ⚠️ n<25 | rust | 2.9942 | – | – | – | 50 | None |
| ⚠️ n<25 | rust-embedded | 3.3348 | – | – | – | 50 | None |
| ⚠️ n<25 | security-fenrir | 4.7759 | – | – | – | 50 | None |
| ⚠️ n<25 | shell | 45.7311 | – | – | – | 50 | None |
| ⚠️ n<25 | spice-sim | 4.7247 | – | – | – | 25 | None |
| ⚠️ n<25 | sql | 3.735 | – | – | – | 50 | None |
|  | traduction-tech | 29.3798 | 9.37 | 1.1428 | 68.11 | 50 | 50 |
| ⚠️ n<25 | typescript | 2.8815 | – | – | – | 50 | None |
| ⚠️ n<25 | web-backend | 2.9383 | – | – | – | 50 | None |
| ⚠️ n<25 | web-frontend | 2.8502 | – | – | – | 50 | None |
| ⚠️ n<25 | yaml-json | 2.908 | – | – | – | 50 | None |

**eurollm stats** (n≥25, 3 cells): median log-lift = 0.3327 (e39.47% effective), min = 0.3152, max = 1.1428, median lift_pct (legacy) = 28.30%, cells where adapter HURT (negative log-lift): 0, flagged (n<25): 0
