# Mascarade LoRA Eval Harness — Design (sous-projet A)

## Context

L'audit + bench du volet-3 (2026-05-18) a montré que les 10 LoRA hardware
« mascarade » sont toutes réellement entraînées, mais de qualité inégale
(6 fortes, 3 faibles, 1 no-op). Problème : le bench qui a produit ce
verdict n'est **pas fiable** — perplexité mesurée sur la *queue du
train-set* (aucun vrai split held-out), N=25, perplexité = proxy faible.
On ne peut donc pas distinguer « LoRA faible » de « mesure faible ».

Ce sous-projet **A** construit l'instrument de mesure fiable. Il est le
premier d'une décomposition **A → B → C** : B (qualité des datasets) et
C (recette d'entraînement) sont tous deux conditionnés au verdict de A.
Sans instrument fiable, tout diagnostic data-vs-training est du bruit.

## Goal

Un **verdict par LoRA fiable** pour les 10 LoRA mascarade actuellement
déployées — `a appris` / `faible` / `domaine sans besoin de LoRA` /
`artefact de mesure` — qui aiguille chaque LoRA vers le sous-projet B
(corriger la donnée), C (ré-entraîner) ou « laisser tel quel ».

## Décisions de cadrage (issues du brainstorming)

1. **Portée** : juge les 10 LoRA *actuellement déployées* — pas seulement
   les futures. Conséquence : exige de la donnée held-out *fraîche* que
   ces LoRA n'ont jamais vue (elles ont été entraînées sur la totalité de
   leurs datasets).
2. **Métrique** : hybride — scorers fonctionnels (sorties structurées) +
   LLM-judge sur rubrique (domaines « mous ») + perplexité en signal
   secondaire (là où une réponse de référence existe).
3. **Source du held-out** : tranche minée de l'upstream Stack Exchange /
   KiCad, jamais incluse dans l'entraînement. *Révision 2026-05-18* : le
   trafic prod a été écarté après vérification — le trail NDJSON du
   gateway ne logue pas de prompts harvestables (steps de chaîne, output
   seul, policies non-DIRECT), et `LiteLLM_SpendLogs` n'a que 14 lignes.
4. **Modèle juge** : Mistral-Medium-3.5-128B maison (Studio `:9301`) en
   juge principal + spot-check externe ~10-15 % pour calibrer le biais.

## Must NOT (garde-fous)

- Ne PAS juger avec un modèle mascarade (auto-évaluation).
- Ne PAS découper le held-out dans les datasets d'entraînement existants
  (les LoRA ont tout vu) — le held-out doit être frais.
- A **mesure seulement** — il ne corrige pas la donnée (B) et ne
  ré-entraîne rien (C).
- Pas de verdict silencieux sur un domaine à held-out insuffisant : il
  est marqué *basse confiance*.

## Architecture

Vit dans le repo `ailiance-bench`, nouveau module `mascarade-eval/`
(réutilise le pattern Phase-N, les scorers `bench_kicad_functional`, les
références aux datasets HF). Pas de nouveau repo.

**5 composants :**

1. **Constructeur de held-out** — `mine_upstream.py` extrait, par
   domaine, une tranche de l'upstream Stack Exchange / KiCad jamais
   incluse dans l'entraînement (idéalement par coupe temporelle : des
   posts postérieurs à l'assemblage du corpus d'entraînement, donc
   garantis non vus). Paires (prompt, réponse de référence). Sortie :
   `heldout/<domain>.raw.jsonl`.
2. **Garde anti-fuite** (`leakage_check`) — cœur de l'intégrité.
3. **Runner** — génère les réponses sur chaque prompt held-out, pour
   2 configs : `base+LoRA` (bf16, via le serveur Studio `:9340` déjà en
   place) et `base` Qwen3-4B seul (servi via un endpoint dédié court ou
   chargé localement par le runner — choix tranché au plan d'implémentation).
4. **Scorers hybrides** — fonctionnels (`score_dsl/pcb/spice` réutilisés
   + étendus, ex. `platformio.ini`) ; LLM-judge Mistral-Medium-128B
   (`:9301`) sur rubrique par domaine + spot-check externe ~10-15 % ;
   perplexité en signal secondaire (items à réponse de référence).
5. **Agrégateur de verdict** — combine les scores en verdict par LoRA.

**Livrable** : `mascarade-eval-report.md` — un verdict par LoRA +
l'aiguillage vers B (data) ou C (training).

## Flux de données

```
upstream Stack Exchange / KiCad ─► mine_upstream.py ─► heldout/<dom>.raw.jsonl
                                                              │
                                                     garde anti-fuite
                                                              │
                                                 heldout/<dom>.clean.jsonl
                                                              │
                                 runner ── base ──┐           │
                                        └ base+LoRA ┴─► réponses ─► scorers
                                                                       │
                                                 (fonctionnel + judge + ppl)
                                                                       │
                                                       agrégateur ─► report.md
```

## Intégrité — garde anti-fuite

- Tout le held-out vient de l'upstream Stack Exchange / KiCad — **la même
  source dont la donnée d'entraînement a été dérivée**. Le risque de fuite
  est donc réel et permanent : la garde anti-fuite est l'élément central
  de l'intégrité (une coupe temporelle à la source réduit le risque mais
  ne le supprime pas — un même contenu peut être reposté/cité).
- La garde fait 2 passes contre `Ailiance-fr/mascarade-<domain>-dataset` :
  **hash exact** (prompt normalisé) + **quasi-duplication** (MinHash ou
  similarité d'embedding — un prompt paraphrasé d'un item d'entraînement
  est aussi une fuite). Tout item qui matche est rejeté et loggé.
- Si après filtrage un domaine passe sous un **plancher** (ex. 20 items
  propres), il est marqué *verdict basse confiance* ; on retombe sur
  l'upstream-mine pour compléter avant de produire un verdict.

## Logique de verdict

Comparaison LoRA vs base sur le held-out propre :

- LoRA ≫ base → `a appris`.
- LoRA ≈ base ET base déjà haut → `domaine sans besoin de LoRA`
  (cas stm32 : ppl de base déjà à 1,66).
- LoRA ≈ base ET base médiocre → `faible` → alimente B/C.
- Verdict honnête contredit l'ancien banc perplexité-train-tail →
  l'ancien était un `artefact de mesure`.

## Robustesse

- Isolation par domaine — un domaine qui plante n'avorte pas le run.
- Le spot-check externe est *best-effort* : API externe indisponible → le
  run finit avec le juge maison seul, en le notant dans le rapport.
- Échec de parse d'un scorer fonctionnel = un *score* (parse-fail est un
  signal), pas un crash.

## Tests

- **Scorers** : tests unitaires — sorties connues bonnes/mauvaises →
  plages de score attendues.
- **Garde anti-fuite** : test qui plante un item d'entraînement connu
  dans les candidats held-out → doit être attrapé.
- **Juge** : calibration sur un petit set noté à la main → le juge maison
  doit s'accorder dans une tolérance ; vérifier l'accord juge-maison vs
  spot-check externe.
- **Smoke end-to-end** : pipeline complet sur 1 domaine, petit N → un
  rapport avec verdict est produit.

## Verification (test bout-en-bout)

1. `pytest mascarade-eval/tests/` — scorers + garde anti-fuite verts.
2. Smoke : lancer le harnais sur 1 domaine (ex. `power`) → vérifier qu'un
   `mascarade-eval-report.md` avec un verdict est produit.
3. Run complet 10 domaines → le rapport contient 10 verdicts, et tout
   domaine à held-out insuffisant est marqué *basse confiance* (pas de
   verdict silencieux).

## Hors périmètre (sous-projets suivants)

- **B** — audit + refonte de la qualité des datasets que A désigne
  comme réellement faibles.
- **C** — revue de la recette d'entraînement et ré-entraînement de ce
  que B ne peut pas régler au niveau données.

Chacun aura son propre spec, conditionné au rapport de A.
