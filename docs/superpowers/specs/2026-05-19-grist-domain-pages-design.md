# Pages Grist par domaine — doc `ailiance-llm-domain`

**Date :** 2026-05-19
**Statut :** design validé, prêt pour planification d'implémentation

## Problème

Le doc `ailiance-llm-domain` a deux tables (`Sourcing`, `Dataset_Items`)
couvrant tous les domaines hardware. Pour la revue, on veut **une page
Grist par domaine** : une vue filtrée de `Sourcing` + `Dataset_Items`
sur ce domaine. Créer ~10 pages à la main est répétitif et sujet à
oubli ; il faut un script qui automatise ce qui peut l'être et un
runbook pour le reste.

## Réalité de l'API Grist

Grist crée ses pages et widgets surtout dans l'UI. Son endpoint
`/apply` (user-actions : `CreateViewSection`, `AddView`…) peut créer
pages et sections, mais l'interface est fragile et dépend de la version
de Grist. Le script aura donc un **cœur solide et testable** (la
réconciliation de la liste des domaines) et une **partie best-effort**
(la création de page), le runbook couvrant ce que l'API ne réussit pas.

## Architecture

### Module `mascarade_eval/grist/domain_pages.py`

- `reconcile_domains(dataset_items_rows, known_domains) -> dict` —
  **pur, le cœur du sous-projet**. Compare les domaines distincts vus
  dans les lignes `Dataset_Items` au tuple `DOMAINS` du package
  (`mascarade_eval.DOMAINS`). Renvoie
  `{"expected": [...], "present": [...], "orphans": [...],
  "missing": [...]}` :
  - `expected` — les domaines de la constante (triés).
  - `present` — domaines de la constante qui ont des lignes.
  - `orphans` — domaines vus dans les données mais absents de la
    constante (à signaler comme données orphelines).
  - `missing` — domaines de la constante sans aucune ligne.
- `page_plan(domain) -> dict` — **pur**. Décrit la page voulue pour un
  domaine : `{"page_name", "widgets", "filter"}` où `widgets` liste les
  tables `Sourcing` et `Dataset_Items` et `filter` est `domain=<domain>`.
- `create_domain_page(client, domain, transport=...) -> dict` —
  **best-effort**. Tente de créer la page via l'API user-actions de
  Grist ; renvoie `{"domain", "status"}` où `status` ∈
  `{"created", "api_unsupported"}`. Le transport HTTP est injectable
  pour les tests.

### Script `scripts/build_domain_pages.py`

1. Résout le doc `domain` (`GRIST_DOC_LLM_DOMAIN` via `load_doc_id`).
2. Lit `Dataset_Items`, appelle `reconcile_domains` avec
   `mascarade_eval.DOMAINS` ; **affiche les `orphans` en alerte** sur
   stderr.
3. Pour chaque domaine `expected`, appelle `create_domain_page`.
4. Imprime un rapport : pages `created` vs `api_unsupported` (à créer à
   la main via le runbook).

### Runbook `mascarade-eval/docs/grist-domain-pages-runbook.md`

Procédure pas-à-pas dans l'UI Grist, pour les pages que l'API n'a pas
pu créer : créer la page nommée d'après le domaine, y ajouter deux
widgets (`Sourcing`, `Dataset_Items`), poser sur chacun le filtre
`domain = <domaine>`.

## Critères de succès

- `reconcile_domains` rapporte exactement les orphelins et les domaines
  manquants face à la constante `DOMAINS`.
- Le script signale tout domaine orphelin et imprime un rapport clair
  pages-créées / pages-à-faire-main.
- Le runbook permet de finir à la main toute page que l'API n'a pas
  créée.
- Les fonctions pures sont testées directement ; `create_domain_page`
  est testé avec un transport injecté (aucun accès réseau en test).

## Hors périmètre

- La table `Sourcing` elle-même (remplie ailleurs).
- Toute mise en forme conditionnelle ou couleur des vues.
- Les autres docs (`training`, `bench`, `workflow`).
