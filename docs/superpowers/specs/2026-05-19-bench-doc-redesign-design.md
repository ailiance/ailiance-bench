# Redesign du doc `ailiance-llm-bench` — une table par source

**Date :** 2026-05-19
**Statut :** design validé, prêt pour planification d'implémentation

## Problème

L'architecture 4-docs (`2026-05-19-ailiance-llm-grist-docs-design.md`)
a défini le doc `bench` avec deux tables consolidées : `Bench_Results`
(7 colonnes) et `Eval_Items` (9 colonnes). La migration réelle (dry-run
2026-05-19) a révélé que les 4 tables source sont **4 formes de données
distinctes** qui ne se consolident pas — la migration perdrait
quasiment toutes les colonnes :

| Table source (doc) | Lignes | Colonnes |
|--------------------|--------|----------|
| `Heldout_Items` (ailiance-llm-heldout-legacy) | 400 | 10 |
| `Mascarade_Eval` (mascarade-data) | 9 | 12 |
| `Mascarade_Eval_Items` (mascarade-data) | 323 | 20 |
| `Bench_31_domains` (mascarade-data) | 124 | 23 |

Avec les schémas consolidés, le dry-run a montré 5 à 21 colonnes
perdues par table — perte quasi-totale.

## Objectif

Redéfinir le doc `bench` en **une table cible par table source**, chaque
table reprenant verbatim les colonnes de sa source. La migration devient
une copie fidèle (`rename` vide, `dropped_columns` vide, vérifiée).

## Schéma cible — doc `bench`, 4 tables

Colonnes relevées sur l'instance Grist live le 2026-05-19 :

- **`Heldout_Items`** : `item_key, domain, prompt, reference, source,
  dataset, review_status, reviewer, reviewed_at, review_note`
- **`Mascarade_Eval`** : `run_domain, run_id, domain, n, base_score,
  lora_score, delta, verdict, routed_to, scorer, status, updated_at`
- **`Mascarade_Eval_Items`** : `run_item, run_id, domain, item_idx,
  question, reference, base_answer, base_score, base_scorer,
  base_judge_raw, lora_answer, lora_score, lora_scorer, lora_judge_raw,
  delta, updated_at, review_status, reviewer, reviewed_at, review_note`
- **`Bench_31_domains`** : `model, domain, ppl, stderr_ppl, status,
  samples, date, source, task_score, task_metric, judge_score,
  judge_rationale, judge_independence, host, runtime_s, tokens_per_s,
  run_id, validator_score, validator_image_digest, review_status,
  reviewer, reviewed_at, review_note`

Les anciennes tables `Bench_Results` et `Eval_Items` disparaissent du
schéma.

## Impact code (ripple)

- **`mascarade_eval/grist/llm_schema.py`** — `LLM_DOCS["bench"]` passe
  de `{Bench_Results, Eval_Items}` aux 4 tables ci-dessus.
- **`mascarade_eval/grist/grist_migrate.py`** — `MIGRATION_MAP` : chaque
  entrée a `tgt_doc="bench"` et `tgt_table` = nom de la table source
  (copie même-nom). 4 entrées, `rename` vide.
- **`mascarade_eval/grist/pipeline_sync.py`** — `sync_pipeline` dérive
  le drapeau `evaluated` depuis `Bench_Results`. Le repointer : un
  domaine est `evaluated` s'il apparaît dans `Mascarade_Eval` **ou**
  `Bench_31_domains` (les deux tables ont une colonne `domain`).
- **`mascarade_eval/grist/__init__.py`** — la constante
  `EVAL_TABLE = "Eval_Items"` n'est plus utilisée nulle part ; la
  supprimer.
- Tests : `test_grist_llm_schema.py`, `test_grist_migrate_engine.py`,
  `test_grist_pipeline_sync.py` mis à jour pour le nouveau schéma.

## Re-provisioning

Le doc `bench` a déjà été provisionné avec les 2 tables erronées
(`Bench_Results`, `Eval_Items`), vides. Elles seront supprimées (via
l'API Grist) puis le doc re-provisionné avec les 4 bonnes tables.

## Migration

Après le redesign : re-provisionner le doc `bench`, lancer
`migrate_grist_docs.py --dry-run` (attendu : `dropped_columns` vide pour
les 4 tables), puis le run réel (attendu : `verified: True`, 856 lignes
copiées au total — 400 + 9 + 323 + 124).

## Critères de succès

- `LLM_DOCS["bench"]` déclare les 4 tables avec leurs colonnes réelles.
- La migration copie les 856 lignes sans perte de colonne
  (`dropped_columns` vide, `verified: True`).
- `pipeline_sync` calcule `evaluated` correctement depuis les deux
  tables de bench.
- Suite de tests `mascarade-eval` verte.

## Hors périmètre

- Les tables `Bench_public`, `Bench_niches_ppl`, `Bench_gateway`,
  `Bench_lift_v1`, `Bench_lift_v2` de `mascarade-data` (non migrées —
  hors du périmètre bench mascarade/iact).
- Les docs `domain`, `training`, `workflow` (déjà provisionnés ;
  alimentés par le pipeline, pas par migration).
