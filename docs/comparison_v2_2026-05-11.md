# Bench comparison — base vs tuned

- Base: `perplexity_base_20260511_0049.json` (64 rows)
- Tuned: `perplexity_v2-only_20260511_0135.json` (18 rows)
- Joined cells: 18
- Headline metric: **lift_log** (scale-invariant); cells with n<25 flagged ⚠️ and excluded from median.

## medium35 (4/32 joined, 0 flagged n<25)

| flag | domain | base_ppl | tuned_ppl | lift_log | lift_pct | base_n | tuned_n |
|---|---|---:|---:|---:|---:|---:|---:|
| ⚠️ n<25 | chat-fr | 16.4362 | – | – | – | 50 | None |
| ⚠️ n<25 | cpp | 11.1603 | – | – | – | 50 | None |
| ⚠️ n<25 | docker-devops | 4.4293 | – | – | – | 50 | None |
| ⚠️ n<25 | electronics | 6.823 | – | – | – | 50 | None |
|  | embedded | 27.73 | 7.56 | 1.2996 | 72.74 | 50 | 50 |
|  | emc-dsp-power | 33.501 | 7.6 | 1.4834 | 77.31 | 50 | 50 |
| ⚠️ n<25 | freecad | 12.3239 | – | – | – | 3 | None |
| ⚠️ n<25 | html-css | 4.4612 | – | – | – | 50 | None |
| ⚠️ n<25 | iot | 33.1555 | – | – | – | 50 | None |
| ⚠️ n<25 | kicad-dsl | 2.7093 | – | – | – | 50 | None |
| ⚠️ n<25 | kicad-pcb | 2.0206 | – | – | – | 50 | None |
| ⚠️ n<25 | llm-ops | 27.1713 | – | – | – | 50 | None |
| ⚠️ n<25 | llm-orch | 10.0039 | – | – | – | 50 | None |
| ⚠️ n<25 | lua-upy | 7.0968 | – | – | – | 44 | None |
|  | math-gsm8k | 11.3267 | 3.28 | 1.2393 | 71.04 | 50 | 50 |
|  | math-reasoning | 3.3573 | 2.05 | 0.4933 | 38.94 | 50 | 50 |
| ⚠️ n<25 | ml-training | 6.6593 | – | – | – | 50 | None |
| ⚠️ n<25 | multilingual-eu | 23.2369 | – | – | – | 50 | None |
| ⚠️ n<25 | music-audio | 4.608 | – | – | – | 25 | None |
| ⚠️ n<25 | platformio | 5.7289 | – | – | – | 35 | None |
| ⚠️ n<25 | python | 3.9956 | – | – | – | 50 | None |
| ⚠️ n<25 | rust | 4.2414 | – | – | – | 50 | None |
| ⚠️ n<25 | rust-embedded | 15.1744 | – | – | – | 50 | None |
| ⚠️ n<25 | security-fenrir | 9.2697 | – | – | – | 50 | None |
| ⚠️ n<25 | shell | 60.7473 | – | – | – | 50 | None |
| ⚠️ n<25 | spice-sim | 11.479 | – | – | – | 25 | None |
| ⚠️ n<25 | sql | 6.6303 | – | – | – | 50 | None |
| ⚠️ n<25 | traduction-tech | 46.2529 | – | – | – | 50 | None |
| ⚠️ n<25 | typescript | 3.9749 | – | – | – | 50 | None |
| ⚠️ n<25 | web-backend | 5.4677 | – | – | – | 50 | None |
| ⚠️ n<25 | web-frontend | 5.0246 | – | – | – | 50 | None |
| ⚠️ n<25 | yaml-json | 5.2643 | – | – | – | 50 | None |

**medium35 stats** (n≥25, 4 cells): median log-lift = 1.2694 (e255.89% effective), min = 0.4933, max = 1.4834, median lift_pct (legacy) = 71.89%, cells where adapter HURT (negative log-lift): 0, flagged (n<25): 0

## qwen36 (14/32 joined, 0 flagged n<25)

| flag | domain | base_ppl | tuned_ppl | lift_log | lift_pct | base_n | tuned_n |
|---|---|---:|---:|---:|---:|---:|---:|
| ⚠️ n<25 | chat-fr | 6.9893 | – | – | – | 50 | None |
| ⚠️ n<25 | cpp | 2.9354 | – | – | – | 50 | None |
| ⚠️ n<25 | docker-devops | 2.9072 | – | – | – | 50 | None |
| ⚠️ n<25 | electronics | 3.4056 | – | – | – | 50 | None |
| ⚠️ n<25 | embedded | 14.5487 | – | – | – | 50 | None |
| ⚠️ n<25 | emc-dsp-power | 12.312 | – | – | – | 50 | None |
| ⚠️ n<25 | freecad | 3.6675 | – | – | – | 3 | None |
|  | html-css | 2.6096 | 1.76 | 0.3939 | 32.56 | 50 | 50 |
|  | iot | 16.2294 | 7.43 | 0.7813 | 54.22 | 50 | 50 |
| ⚠️ n<25 | kicad-dsl | 2.3753 | – | – | – | 50 | None |
| ⚠️ n<25 | kicad-pcb | 4.4189 | – | – | – | 50 | None |
|  | llm-ops | 10.5894 | 3.93 | 0.9912 | 62.89 | 50 | 50 |
|  | llm-orch | 5.0385 | 2.72 | 0.6165 | 46.02 | 50 | 50 |
| ⚠️ n<25 | lua-upy | 3.2515 | – | – | – | 44 | None |
| ⚠️ n<25 | math-gsm8k | 3.6319 | – | – | – | 50 | None |
| ⚠️ n<25 | math-reasoning | 2.0512 | – | – | – | 50 | None |
| ⚠️ n<25 | ml-training | 2.4106 | – | – | – | 50 | None |
| ⚠️ n<25 | multilingual-eu | 8.4504 | – | – | – | 50 | None |
|  | music-audio | 2.8016 | 1.65 | 0.5294 | 41.11 | 25 | 25 |
|  | platformio | 3.8629 | 1.44 | 0.9868 | 62.72 | 35 | 35 |
|  | python | 2.6771 | 1.91 | 0.3376 | 28.65 | 50 | 50 |
|  | rust | 2.6313 | 1.91 | 0.3204 | 27.41 | 50 | 50 |
| ⚠️ n<25 | rust-embedded | 2.7625 | – | – | – | 50 | None |
| ⚠️ n<25 | security-fenrir | 4.1017 | – | – | – | 50 | None |
|  | shell | 19.9935 | 7.25 | 1.0144 | 63.74 | 50 | 50 |
| ⚠️ n<25 | spice-sim | 4.2489 | – | – | – | 25 | None |
|  | sql | 3.9362 | 2.03 | 0.6622 | 48.43 | 50 | 50 |
| ⚠️ n<25 | traduction-tech | 19.7821 | – | – | – | 50 | None |
|  | typescript | 2.8373 | 1.88 | 0.4116 | 33.74 | 50 | 50 |
|  | web-backend | 3.4693 | 2.0 | 0.5508 | 42.35 | 50 | 50 |
|  | web-frontend | 3.0245 | 1.98 | 0.4236 | 34.53 | 50 | 50 |
|  | yaml-json | 2.9129 | 2.02 | 0.3661 | 30.65 | 50 | 50 |

**qwen36 stats** (n≥25, 14 cells): median log-lift = 0.5401 (e71.62% effective), min = 0.3204, max = 1.0144, median lift_pct (legacy) = 41.73%, cells where adapter HURT (negative log-lift): 0, flagged (n<25): 0
