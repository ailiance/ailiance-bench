# Phase 7 — KiCad LoRA bench via `mlx_lm.server` HTTP

Bench KiCad cross-machine et parallele en reutilisant les `mlx_lm.server`
deja chauds (modele + adapter LoRA en RAM) au lieu de re-loader le tout
en subprocess a chaque combinaison (Phase 2 / 3 / 4 / 5 actuelles).

## Architecture

```
+-------------------+         HTTP POST /v1/chat/completions
| bench_kicad_      |  ---->  +------------------------+
| via_server.py     |         | mlx_lm.server (LoRA A) | port 8502 (macM1)
| ThreadPoolExecutor|  ---->  +------------------------+
| N concurrent      |         +------------------------+
| (LoRA x prompt)   |  ---->  | mlx_lm.server (LoRA B) | port 8503 (macM1)
|                   |         +------------------------+
|                   |  ---->  +------------------------+
|                   |         | mlx_lm.server (model)  | port 9301 (Studio)
|                   |         +------------------------+   via SSH tunnel
+-------------------+              (port forward sur 127.0.0.1:19301)

response chat-completion -> score_sch() (kicad_sch_parser.py + kicad-cli)
                         -> aggregate() (parse_ok_rate, cli_proxy_avg, ...)
                         -> ~/bench-results/kicad_phase7_http.{json,md}
```

Le script reutilise directement les helpers de `bench_kicad_phase2.py` :
`load_samples`, `score_sch`, `aggregate`, `BENCH_DIR`, `DEFAULT_MAX_TOKENS`,
`SPI_BUS_ID`. Donc **0 nouveau code de scoring** : meme parser, meme metriques.

## Gains vs subprocess Phase 2/3/4/5

| Aspect                    | Subprocess (Phase 2-5) | HTTP (Phase 7) |
| ---                       | ---                    | ---            |
| Load modele + adapter     | ~30-60 s / combo       | 0 (deja en RAM)|
| Parallelisme              | sequentiel             | N threads      |
| Cross-machine             | non (macM1 only)       | oui (SSH tunnel ou LAN) |
| Empreinte RAM totale      | 1 modele a la fois     | M modeles persistents |
| Latence/sample            | dominee par load       | dominee par gen|

Sur le POC (1 sample x 2 LoRA, gemma-4-E4B-it-MLX-4bit), on observe une
generation HTTP qui demarre **immediatement** (pas de load) — vs 30-45 s
de cold start cote subprocess pour le meme modele 4-bit.

## Servers actuels (snapshot 2026-05-12)

### macM1 (locaux, accessibles direct)

| port | model                                | adapter                              |
| ---  | ---                                  | ---                                  |
| 8502 | lmstudio-community/gemma-4-E4B-it-MLX-4bit | `~/lora-adapters/gemma4-e4b-eukiki/final` |
| 8503 | lmstudio-community/gemma-4-E4B-it-MLX-4bit | `~/lora-adapters/gemma4-e4b-mascarade/final` |

### Studio (distants, via SSH tunnel — voir plus bas)

| port | model                              | adapter             |
| ---  | ---                                | ---                 |
| 9301 | Mistral-Medium-3.5-128B-MLX-Q8     | —                   |
| 9305 | Qwen3.6-35B-A3B-MLX-BF16           | —                   |
| 9316 | Devstral-Small-2-24B-MLX-4bit      | —                   |
| 9334 | gemma-4-E4B-it-MLX-4bit            | `gemma4-eukiki`     |

## SSH tunnel vers Studio

A lancer **manuellement** depuis macM1 (l'utilisateur conserve le controle
des credentials et de la session SSH) :

```bash
ssh -fN \
    -L 19301:localhost:9301 \
    -L 19305:localhost:9305 \
    -L 19316:localhost:9316 \
    -L 19334:localhost:9334 \
    studio
```

Puis decommenter les entrees `LORA_SERVERS` correspondantes (URLs en
`http://127.0.0.1:19xxx/...`) dans `bench_kicad_via_server.py`, ou utiliser
`--include-discovered` (l'auto-discovery scanne aussi 19300-19400).

Verification :

```bash
curl -sS http://127.0.0.1:19334/v1/models | jq '.data[0].id'
```

## Ajouter un nouveau LoRA server

1. Lancer le server cote machine cible :

   ```bash
   mlx_lm.server \
     --model lmstudio-community/gemma-4-E4B-it-MLX-4bit \
     --adapter-path ~/lora-adapters/<adapter>/final \
     --host 127.0.0.1 --port <port-libre> --log-level INFO &
   ```

2. (Si distant) ajouter `-L <local-port>:localhost:<port-libre>` au tunnel.

3. Ajouter une entree dans `LORA_SERVERS` :

   ```python
   {"nick": "kicad-sch-v3",
    "url": "http://127.0.0.1:<local-port>/v1/chat/completions",
    "model": "lmstudio-community/gemma-4-E4B-it-MLX-4bit",
    "adapter_hint": "<adapter>"},
   ```

   Ou lancer le bench avec `--include-discovered` pour qu'il decouvre
   le port lui-meme (le nick sera `auto:<port>:<model>`).

## Usage

```bash
# POC : 1 sample x N servers preconfigures
python3 ~/scripts/bench_kicad_via_server.py --limit 1

# Sous-ensemble de servers
python3 ~/scripts/bench_kicad_via_server.py --servers eu-kiki kicad-sch-v3

# Full dataset, 4 workers, inclut auto-discovered
python3 ~/scripts/bench_kicad_via_server.py --include-discovered --workers 4

# Liste seulement (pas d'appel HTTP)
python3 ~/scripts/bench_kicad_via_server.py --dry-run
python3 ~/scripts/bench_kicad_via_server.py --discover
```

## Output

- `~/bench-results/kicad_phase7_http.json` : metadata + bench par server
- `~/bench-results/kicad_phase7_http.md`   : tableau resume

Structure JSON :

```json
{
  "metadata": {
    "timestamp": "2026-05-12 00:58:03",
    "servers": [...],
    "n_samples_eval": 4,
    "max_tokens": 4096,
    "max_workers": 4
  },
  "bench": {
    "eu-kiki":   {"composite_score": 0.42, "samples": [...]},
    "mascarade": {"composite_score": 0.31, "samples": [...]}
  }
}
```

## Contraintes / safety

- Le script **ne tue jamais de server** — seulement TCP-ping + POST.
- L'auto-discovery est best-effort, fail-graceful : un port qui timeout
  ou retourne 404 sur `/v1/models` n'arrete pas le bench.
- Compatible avec les bench v3 en cours (PID 33756 sur Studio) : on n'y
  touche pas, on ne fait que des requetes HTTP sur des ports differents.
- Format `chat/completions` compatible mlx_lm.server >= 0.21.

## Limitations connues (2026-05-12)

- **Concurrence GPU** : sur macM1 (M1 Max), si un `mlx_lm.lora` (training)
  est en cours, **toute** inference HTTP via `mlx_lm.server` sera serializee
  voire bloquee tant que le batch GPU est occupe (Metal n'a pas de
  preemption). Validation POC effectuee :
  - sockets HTTP **ouverts** (4 ESTABLISHED 8502/8503) ;
  - paylod chat/completions **envoye correctement** ;
  - servers **CPU 0%** parce que GPU monopolise par training v3 (PID 36136
    sur cette session) → reponses en attente.
  Recommandation : lancer Phase 7 quand aucun `mlx_lm.lora` ne tourne,
  ou cibler des servers Studio via SSH tunnel.

- **Pipeline scoring valide a part** (sans GPU) :
  ```
  $ python3 /tmp/test_phase7_scoring.py
  sample: led_blinker  expected_chars=990
  score(expected vs expected):
    parse_ok                 = True
    composite                = 1.0
    cli_proxy_score          = 1.0
    comp_count_match         = 1.0
    label_count_match        = 1.0
  score(stub vs expected):
    parse_ok                 = True
    composite                = 0.7
    cli_proxy_score          = 0.75
    comp_count_match         = 0.0
    label_count_match        = 0.0
  aggregate:
    n_samples                = 2
    parse_ok_rate            = 1.0
    cli_proxy_avg            = 0.875
    composite_score          = 0.85
  ```
  Confirme que `score_sch` + `aggregate` (importes depuis
  `bench_kicad_phase2.py`) fonctionnent inchanges dans le pipeline HTTP.

## Demarrage rapide d'un nouveau LoRA server

`scripts/start-gemma4-e4b-kicad-sch-v3.sh` :

```bash
# defaults : port 8504, adapter ~/lora-adapters/gemma4-e4b-kicad-sch-v3/final
./scripts/start-gemma4-e4b-kicad-sch-v3.sh

# override
PORT=8505 ADAPTER=~/lora-adapters/aggro-test/final \
  ./scripts/start-gemma4-e4b-kicad-sch-v3.sh
```

Refuse de demarrer si le port est deja occupe (safety vs OOM /
double-load du modele).
