# Surface de revue Grist sous `admin.ailiance.fr`

**Date :** 2026-05-19
**Statut :** design validé, prêt pour planification d'implémentation

## Problème

La revue humaine des datasets (`review_status` : `pending` / `validated`
/ `rejected` / `needs_fix`) se fait aujourd'hui uniquement dans l'UI brute
de Grist (`grist.saillant.cc`). Il manque une **surface dédiée**,
intégrée à l'admin ailiance, où réviser les vues, saisir des données via
formulaire, et enchaîner les items au clavier via la console de revue.

## Objectif

Surfacer trois outils de revue sous `admin.ailiance.fr` : les **vues de
revue** Grist natives, les **formulaires** de saisie Grist, et le
**widget custom Review Console** (`widgets/review-console/index.html`,
déjà écrit). Approche retenue : widget custom hébergé + intégration dans
le cockpit-admin existant.

## Contexte d'infrastructure (reconnaissance 2026-05-19)

- `admin.ailiance.fr` **existe déjà** : routeur Traefik + Keycloak SSO
  (realm `electron_rare`) + tunnel cloudflared, servant l'app
  `cockpit-admin`.
- `cockpit-admin` = SPA **React 19 + TanStack Router/Query + Vite**,
  repo `/Users/electron/ailiance-demo` (monorepo pnpm), déployée en
  nginx SPA. Pages existantes : Training, Datasets, Workers.
- Grist sait publier pages et formulaires en URL partageable,
  embarquable en `<iframe>`.
- Le widget `review-console/index.html` existe dans `ailiance-bench`
  (`mascarade-eval/widgets/review-console/`) ; les recettes
  `grist-native-views-recipe.md` et `grist-widget-setup.md` documentent
  la config Grist.

## Architecture — trois couches

Un widget Grist custom est une page HTML hébergée en HTTPS hors de
Grist, que Grist charge en iframe et alimente via `grist-plugin-api.js`.
D'où trois couches distinctes.

### Couche 1 — Hébergement du widget (intégré à la couche 3)

Le widget `mascarade-eval/widgets/review-console/` est embarqué comme
**asset statique de `cockpit-admin`**, servi par le même nginx à
`admin.ailiance.fr/review-console/`. Pas d'hôte séparé, pas de
modification du tunnel cloudflared, pas de sous-domaine tiers : la copie
du widget est une étape du sous-projet `ailiance-demo` (couche 3). Le
domaine reste cohérent avec la marque ailiance et hérite du SSO
Keycloak du parent.

### Couche 2 — Configuration du doc Grist (runbook, pas de code)

Dans le doc Grist mascarade, créer trois pages nommées :
- **Vues de revue** : tables Bench / Datasets / Heldout, filtres +
  formatage conditionnel sur `review_status`.
- **Formulaire** Grist de saisie manuelle.
- **Page widget** : widget custom pointé sur l'URL de la couche 1.

Réalisé dans l'UI Grist par l'opérateur. Livrable de cette couche : un
runbook pas-à-pas dérivé des deux recettes existantes.

### Couche 3 — Route dans `cockpit-admin` (code)

Nouvelle route « Revue datasets » dans la SPA React/TanStack de
`ailiance-demo/cockpit-admin`. Elle embarque le doc Grist en `<iframe>`
(ou des cartes liant chaque page Grist). Keycloak protège déjà le
parent ; Grist conserve sa propre session dans l'iframe.

**Dépendance** : le câblage de la couche 3 exige l'**URL de partage du
doc Grist**, publiée depuis l'UI (couche 2). Tant qu'elle n'existe pas,
la route est scaffoldée avec l'URL en constante de configuration, à
renseigner ensuite.

## Découpage en sous-projets

1. **`ailiance-demo` (couches 1 + 3)** — repo `ailiance-demo`. Embarque
   le widget review-console comme asset statique servi à
   `/review-console/`, ET ajoute la route « Revue datasets » dans
   `cockpit-admin` (composant iframe + entrée de navigation).
   Scaffoldable avant la couche 2 grâce à la constante de config pour
   l'URL Grist.
2. **Runbook Grist (couche 2)** — documentation seule, dérivée des
   recettes existantes ; exécutée dans l'UI Grist par l'opérateur.

Ordre conseillé : sous-projet 1 (widget + route, avec URL Grist en
placeholder de config), puis sous-projet 2 (runbook + l'opérateur publie
les pages Grist), puis renseigner l'URL réelle dans la constante de
config.

## Critères de succès

- Le widget Review Console répond en HTTPS à une URL stable et se
  charge dans un iframe Grist sans erreur CORS.
- Depuis `admin.ailiance.fr`, une route « Revue datasets » donne accès
  aux trois surfaces (vues, formulaire, console).
- L'accès reste protégé par le SSO Keycloak existant ; aucune nouvelle
  exposition non authentifiée n'est introduite.
- Aucun secret ni credential n'est committé (le widget n'utilise que
  l'API publique Grist côté navigateur).

## Hors périmètre

- Modification du schéma Grist ou du code `mascarade_eval.grist`
  (livré et mergé séparément).
- Authentification de Grist lui-même (conserve sa session propre).
- Refonte de `cockpit-admin` au-delà de l'ajout de la route.
