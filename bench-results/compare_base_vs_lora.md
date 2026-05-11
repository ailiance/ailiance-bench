# Compare base vs LoRA — composite lift par phase / dataset

_Generated: 2026-05-11 05:16:37_

- Base ref     : `gemma-e4b-ailiance-base` (les 3 adapters LoRA sont sur cette meme base)
- Adapters     : gemma-e4b-eukiki-final, gemma-e4b-mascarade-final, gemma-e4b-aggro-test
- Lift         : `composite_lora - composite_base` (en pts ; +X.Xpts)

| Phase | Dataset | base | +ailiance | +mascarade | +aggro |
|---|---|---:|---:|---:|---:|
| P1| kicad-dsl| 0.090| 0.640 (+55.0pts)| 0.090 (+0.0pts)| 0.090 (+0.0pts) |
| P1| kicad-pcb| 0.010| 0.430 (+42.0pts)| 0.010 (+0.0pts)| 0.010 (+0.0pts) |
| P1| spice-sim| 0.425| 0.676 (+25.1pts)| 0.176 (-24.9pts)| 0.189 (-23.5pts) |
| P2| kicad-sch-gen| 0.420| 0.220 (-20.0pts)| 0.400 (-2.0pts)| 0.320 (-10.0pts) |
| P3| kicad-sch-extract| 0.308| 0.690 (+38.2pts)| 0.785 (+47.6pts)| 0.350 (+4.2pts) |
| P4| kicad-erc-abs| 0.060| 0.057 (-0.3pts)| 0.060 (+0.0pts)| 0.060 (+0.0pts) |
| P5| kicad-erc-delta| 0.060| 0.057 (-0.3pts)| 0.060 (+0.0pts)| 0.060 (+0.0pts) |
