# Architecture Grist `ailiance-llm-*` — 4 documents

**Date :** 2026-05-19
**Statut :** design validé, prêt pour planification d'implémentation

## Problème

Les données ailiance/mascarade sont éparpillées dans des documents Grist
hétéroclites et mal nommés : `eGbbrpzN3TeLq3sUd2YFA2` (étiqueté
`ailiance-llm-workflow` — `Datasets`, `Heldout_Items`, `Exports`),
`dhyrySCayizD1PNqCNhCPN` (`mascarade-data` — `Mascarade_Eval`,
`Mascarade_Eval_Items`, `Bench_31_domains`, `Bench_mascarade_heldout`),
et le doc de training (`Mascarade_Training`, `Datasets_Registry`,
`Exports`). Aucune cohérence de nommage, aucune frontière claire entre
les étapes du cycle de vie des modèles.

## Objectif

Réorganiser toute la donnée Grist ailiance-llm en **4 documents séparés**
nommés selon les 4 étapes du pipeline, et migrer les tables existantes
dans la bonne cible.

## Le pipeline en 4 étapes

`domain` (données sources) → `training` (données figées → LoRA) →
`bench` (évaluation) → `workflow` (pilotage + audit).

## Décision d'architecture : 4 documents séparés

**4 documents Grist distincts**, pas un document unique. Conséquence
assumée : Grist ne fait de références/formules croisées qu'à l'intérieur
d'un document — donc la tour de contrôle de `workflow` ne peut pas
agréger nativement les 3 autres docs ; elle est alimentée par un
**script de synchro** (voir plus bas). L'isolation (sauvegardes,
permissions, taille de doc) prime sur la commodité des références
croisées.

## Les 4 documents

### `ailiance-llm-domain` — données sources, par domaine

| Table | Contenu |
|-------|---------|
| `Sourcing` | 1 ligne par domaine : tags Stack Exchange, sources Reddit, quotas de mining, état du mining. |
| `Dataset_Items` | Le contenu des datasets ; colonne `domain` + colonne `review_status` (`pending`/`validated`/`rejected`/`needs_fix`). |

**Pages Grist** : une page par domaine (kicad, spice, stm32, …), chacune
= vue filtrée de `Sourcing` + `Dataset_Items` sur ce domaine.

### `ailiance-llm-training` — données figées → LoRA

| Table | Contenu |
|-------|---------|
| `Exports` | Snapshots de datasets : `export_id`, date, `content_hash`, `n_items`, domaine, fichier, `hf_dataset_id`. |
| `Training_Runs` | 1 ligne par run : modèle de base, export consommé (hash), hyperparamètres, checkpoints, durée, statut, LoRA produit. |

### `ailiance-llm-bench` — évaluation

| Table | Contenu |
|-------|---------|
| `Bench_Results` | Résultats agrégés par domaine/modèle (consolide `Bench_31_domains`, `Mascarade_Eval`). |
| `Eval_Items` | 1 ligne par item évalué : score, raisonnement du juge (consolide `Mascarade_Eval_Items`, `Bench_mascarade_heldout`, `Heldout_Items`). |

### `ailiance-llm-workflow` — pilotage + audit

| Table | Contenu |
|-------|---------|
| `Pipeline_Status` | 1 ligne par domaine : sourcé ? entraîné ? évalué ? servi ? — **alimentée par le script de synchro**. |
| `Audit_Log` | Traces de l'agent, journal d'audit EU AI Act, décisions de routing logées. |

## Le script de synchro

Module Python réutilisant le `GristClient` déjà livré
(`mascarade_eval/grist/client.py`). Il lit un résumé d'état des docs
`domain`, `training`, `bench` et **upsert** les lignes de
`Pipeline_Status` du doc `workflow` (clé : `domain`). Exécuté à la
demande ou en cron. C'est le seul pont entre documents — il remplace les
références croisées que Grist n'offre pas entre documents séparés.

## Migration de l'existant

| Tables actuelles | Document cible |
|------------------|----------------|
| Contenu des datasets de training (`Mascarade_Training`) | `domain` → `Dataset_Items` |
| `Heldout_Items` (eval) | `bench` → `Eval_Items` |
| `Exports`, `Datasets_Registry` (doc training) | `training` → `Exports` |
| `Mascarade_Eval`, `Mascarade_Eval_Items`, `Bench_31_domains`, `Bench_mascarade_heldout` | `bench` → `Bench_Results` / `Eval_Items` |
| (nouveau) | `workflow` → `Pipeline_Status`, `Audit_Log` |

Les anciens documents `eGbbrpzN3TeLq3sUd2YFA2` et `mascarade-data` sont
conservés en lecture seule le temps de valider la migration, puis
archivés.

## Impact sur le code livré

Le sous-package `mascarade_eval/grist/` livré cette session cible
`Mascarade_Training` (doc training) et `Heldout_Items` (doc `eGbbrpzN`).
Cette réorganisation déplace ces tables : le ciblage doc/table du code
doit être recâblé — items de training → `domain`/`Dataset_Items`,
heldout → `bench`/`Eval_Items`, exports → `training`/`Exports`. À traiter
dans le plan d'implémentation.

## Découpage en sous-projets

Chacun reçoit son propre plan.

1. **Création + schémas des 4 docs** — créer les 4 documents Grist et
   leurs tables vides.
2. **Migration des données** — déplacer les tables existantes vers les
   4 cibles ; recâbler `mascarade_eval/grist/`.
3. **Script de synchro `Pipeline_Status`** — le pont vers `workflow`.
4. **Pages Grist par domaine** — runbook UI pour `ailiance-llm-domain`.

## Critères de succès

- Les 4 documents existent, nommés `ailiance-llm-{domain,training,bench,
  workflow}`, avec leurs tables.
- Toute donnée Grist ailiance-llm existante est migrée sans perte dans
  la bonne cible ; les anciens docs sont archivés.
- `Pipeline_Status` reflète l'état réel des 3 autres docs après un run
  du script de synchro.
- `mascarade_eval/grist/` fonctionne contre la nouvelle topologie
  (tests verts).

## Hors périmètre

- Refonte du contenu des datasets eux-mêmes.
- La surface de revue `admin.ailiance.fr` (spec dédiée
  `2026-05-19-grist-review-surface-design.md`).
