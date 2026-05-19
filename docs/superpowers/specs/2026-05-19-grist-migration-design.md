# Migration des données Grist vers les 4 documents `ailiance-llm-*`

**Date :** 2026-05-19
**Statut :** design validé, prêt pour planification d'implémentation

## Problème

Le sous-projet 1 a provisionné les schémas des 4 documents
`ailiance-llm-{domain,training,bench,workflow}`. Les données réelles
vivent encore dans les anciens documents (`eGbbrpzN3TeLq3sUd2YFA2`,
`mascarade-data`, doc training). Elles contiennent des **éditions
humaines non reproductibles** (`review_status`, corrections, notes) :
une copie fidèle est requise. Et le code `mascarade_eval/grist/` cible
encore l'ancienne topologie.

## Objectif

Migrer fidèlement toutes les tables existantes vers les 4 nouveaux
documents, vérifier ligne par ligne l'absence de perte, puis recâbler
`mascarade_eval/grist/` sur la nouvelle topologie.

## Carte de migration

| Table source (doc) | Cible | Mapping de colonnes |
|--------------------|-------|---------------------|
| `Mascarade_Training` (training) | `domain` / `Dataset_Items` | identique (1:1) |
| `Heldout_Items` (eGbbrpzN) | `bench` / `Eval_Items` | `prompt`/`reference`/`source` mappés ; `response`/`score`/`judge_reasoning` laissés vides |
| `Exports` (training) | `training` / `Exports` | identique (1:1) |
| `Datasets_Registry` (training) | `training` / `Datasets` | identique (1:1) — **nouvelle table, voir ci-dessous** |
| `Mascarade_Eval`, `Bench_31_domains` (mascarade-data) | `bench` / `Bench_Results` | mappés vers `result_id`/`domain`/`model`/`score`/`n_items`/`created_at`/`notes` |
| `Mascarade_Eval_Items`, `Bench_mascarade_heldout` (mascarade-data) | `bench` / `Eval_Items` | mappés vers les colonnes `Eval_Items` ; champs absents laissés vides |

### Ajout de schéma : table `Datasets`

`Datasets_Registry` n'avait pas de cible. On ajoute une **3ᵉ table
`Datasets`** au document `training`, colonnes identiques au registre :
`name`, `family`, `domain`, `hf_dataset_id`, `license`, `n_items`,
`notes`. `LLM_DOCS["training"]` de `mascarade_eval/grist/llm_schema.py`
est étendu en conséquence.

## Architecture

### Script de migration

`scripts/migrate_grist_docs.py`, réutilisant `GristClient`. Une
**carte de migration** (structure de données) déclare chaque
`(doc source, table source) → (doc cible, table cible)` avec sa
fonction de mapping de colonnes. Pour chaque entrée : lit les lignes
source via `fetch_records`, applique le mapping, écrit en cible via
`add_records`. Les doc IDs source et cible viennent de `grist.env`
(`load_doc_id`).

### Vérification ligne par ligne

Après écriture d'une table, chaque ligne source est réduite à un hash
de son contenu canonique (JSON trié, mêmes colonnes que la cible) ; on
calcule de même les hashes des lignes cibles ; on assert que chaque
hash source figure dans l'ensemble cible. Une ligne manquante ou
altérée fait échouer la migration de cette table (échec net, pas de
poursuite silencieuse).

### Recâblage de `mascarade_eval/grist/`

Les constantes de `mascarade_eval/grist/__init__.py` (`DOC_HELDOUT`,
`TRAINING_TABLE`, etc.) sont repointées vers la nouvelle topologie :
les items de training → `ailiance-llm-domain` / `Dataset_Items`, les
heldout → `ailiance-llm-bench` / `Eval_Items`, les exports →
`ailiance-llm-training` / `Exports`. Les modules `ingest`, `export`,
`migrate`, `cli` et leurs tests suivent ce repointage.

### Séquencement

1. Étendre `llm_schema.py` avec la table `Datasets` ; provisionner.
2. Exécuter le script de migration (donnée copiée).
3. Vérification ligne par ligne — bloquante.
4. Recâbler `mascarade_eval/grist/` ; suite de tests verte sur la
   nouvelle topologie.
5. Passer les anciens documents en lecture seule.
6. Après une période de validation, archiver les anciens documents
   (action UI Grist — runbook).

## Critères de succès

- Toute ligne de toute table source existe à l'identique dans sa table
  cible (vérification ligne par ligne verte).
- `mascarade_eval/grist/` fonctionne contre les 4 docs `ailiance-llm-*`
  (suite de tests verte).
- Les anciens documents sont en lecture seule puis archivés ; aucune
  écriture ne leur est plus adressée.

## Hors périmètre

- Le script de synchro `Pipeline_Status` (sous-projet 3).
- Les pages Grist par domaine (sous-projet 4).
- La surface de revue `admin.ailiance.fr`.
