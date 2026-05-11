# Compare base vs LoRA — composite lift par phase / dataset

_Generated: 2026-05-11 18:23:01_

- Base ref     : `gemma-e4b-eu-kiki-base` (les 3 adapters LoRA sont sur cette meme base)
- Adapters     : gemma-e4b-eukiki-final, gemma-e4b-mascarade-final, gemma-e4b-aggro-test, gemma-e4b-kicad9plus-final
- Lift         : `composite_lora - composite_base` (en pts ; +X.Xpts)

| Phase | Dataset | base | +eu-kiki | +mascarade | +aggro | +kicad9plus |
|---|---|---:|---:|---:|---:|---:|
| P1| kicad-dsl| 0.090| 0.640 (+55.0pts)| 0.090 (+0.0pts)| 0.090 (+0.0pts)| 0.090 (+0.0pts) |
| P1| kicad-pcb| 0.010| 0.430 (+42.0pts)| 0.010 (+0.0pts)| 0.010 (+0.0pts)| 0.015 (+0.5pts) |
| P1| spice-sim| 0.425| 0.676 (+25.1pts)| 0.176 (-24.9pts)| 0.189 (-23.5pts)| 0.268 (-15.7pts) |
| P2| kicad-sch-gen| 0.420| 0.220 (-20.0pts)| 0.400 (-2.0pts)| 0.320 (-10.0pts)| 0.180 (-24.0pts) |
| P3| kicad-sch-extract| 0.308| 0.690 (+38.2pts)| 0.785 (+47.6pts)| 0.350 (+4.2pts)| 0.000 (-30.8pts) |
| P4| kicad-erc-abs| 0.060| 0.057 (-0.3pts)| 0.060 (+0.0pts)| 0.060 (+0.0pts)| 0.033 (-2.7pts) |
| P5| kicad-erc-delta| 0.060| 0.057 (-0.3pts)| 0.060 (+0.0pts)| 0.060 (+0.0pts)| 0.033 (-2.7pts) |
