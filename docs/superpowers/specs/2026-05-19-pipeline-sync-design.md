# Synchro `Pipeline_Status` du doc `ailiance-llm-workflow`

**Date :** 2026-05-19
**Statut :** design validé, prêt pour planification d'implémentation

## Problème

Le doc `ailiance-llm-workflow` a une table `Pipeline_Status` (1 ligne
par domaine : `sourced`, `trained`, `evaluated`, `served`) censée être
la tour de contrôle du pipeline. Grist ne fait pas de référence croisée
entre documents : `Pipeline_Status` ne peut donc pas se calculer toute
seule depuis les docs `domain`, `training`, `bench`. Il faut un script
de synchro — le seul pont entre les 4 documents.

## Objectif

Un script qui lit l'état des docs `domain`/`training`/`bench` plus la
gateway, calcule le statut de chaque domaine, et **upsert** les lignes
de `Pipeline_Status` dans le doc `workflow`.

## Architecture

### Module `mascarade_eval/grist/pipeline_sync.py`

- `collect_domains(domain_rows, training_rows, bench_rows) -> set[str]`
  — l'univers des domaines = union des valeurs de la colonne `domain`
  vues dans les lignes des 3 docs.
- `domain_status(domain, sourced, trained, evaluated, served) -> dict`
  — **pur** : `sourced`/`trained`/`evaluated`/`served` sont des
  booléens (le domaine appartient-il à l'ensemble) ; renvoie une ligne
  `Pipeline_Status` complète : `domain`, les 4 drapeaux, `updated_at`
  (timestamp ISO UTC), `notes` (vide).
- `fetch_served_aliases(gateway_url, transport=...) -> set[str]` — GET
  `<gateway_url>/v1/models`, renvoie l'ensemble des IDs de modèles.
  Transport injectable pour les tests.
- `sync_pipeline(domain_client, training_client, bench_client,
  workflow_client, served, dry_run=False) -> dict` — orchestre : lit
  `Dataset_Items` / `Training_Runs` / `Bench_Results`, calcule par
  domaine, upsert dans `workflow`/`Pipeline_Status` (clé `domain`).
  Renvoie un rapport `{domain: status_row}`. `dry_run` calcule sans
  écrire.

### Dérivation des drapeaux

Par présence de lignes dans les 3 docs, plus la gateway pour `served` :

| Drapeau | Vrai si… |
|---------|----------|
| `sourced` | le domaine apparaît dans `domain`/`Dataset_Items` |
| `trained` | le domaine apparaît dans `training`/`Training_Runs` |
| `evaluated` | le domaine apparaît dans `bench`/`Bench_Results` |
| `served` | l'alias `ailiance-<domain>` ∈ `/v1/models` de la gateway |

L'alias du LoRA d'un domaine suit le motif **`ailiance-<domain>`**
(schéma d'alias mascarade de la gateway). `served` est donc vrai si
`f"ailiance-{domain}"` figure dans l'ensemble retourné par
`fetch_served_aliases`.

### Déclenchement

À la demande, par deux entrées appelant le même `sync_pipeline` :
- `scripts/sync_pipeline_status.py` — script autonome.
- une sous-commande `sync` dans le CLI grist existant
  (`python -m mascarade_eval.grist.cli sync`).

La logique vit dans le module ; les deux entrées sont des coquilles
fines. L'URL de la gateway et les 4 doc IDs viennent de l'env /
`grist.env` ; un cron pourra appeler le script plus tard sans le
modifier.

## Critères de succès

- Après un run, `Pipeline_Status` a une ligne par domaine connu, avec
  les 4 drapeaux reflétant l'état réel des 3 docs + la gateway.
- Re-lancer le script met les lignes à jour sans en dupliquer (upsert
  sur `domain`).
- `--dry-run` n'écrit rien.
- Fonctions pures testées directement ; gateway et clients Grist
  injectables pour les tests (aucun accès réseau en test).

## Hors périmètre

- Les colonnes `Audit_Log` du doc `workflow` (autre alimentation).
- Tout cron/automatisation (le script reste lançable à la main).
- La création des docs (sous-projet 1) et la migration (sous-projet 2).
