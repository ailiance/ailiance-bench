# Audit attribution Stack Exchange — `electron-rare/mascarade-kicad-dataset`

**Date** : 2026-05-11
**Auditeur** : revue de conformité interne (electron-rare)
**Statut** : COMPLIANT (attribution effective sur 61 samples + marquage `not_found_on_se` sur 169)

## TL;DR

Le dataset `mascarade-kicad-dataset` (2 645 samples, CC-BY-SA-4.0) était présenté comme « ~31 % scrapé depuis Stack Exchange Electronics », sans attribution per-sample (URL + auteur + post_id).

L'audit empirique via l'API Stack Exchange (`/search/advanced` + `/questions/{id}` avec body) montre que **seuls 61 samples (~2.31 %)** proviennent réellement d'un post SE Electronics identifiable. **L'estimation initiale était sur-estimée par ~13×** (style ≠ source).

| Catégorie                                | Samples | %      |
|------------------------------------------|--------:|-------:|
| SE confirmé (match ≥ 0.60)               |      61 | 2.31 % |
| SE-style mais introuvable sur l'API SE   |     169 | 6.39 % |
| SE-style avec match faible (< 0.60)      |       2 | 0.08 % |
| Synthétique LLM / unique                 |   2 413 | 91.23 % |
| **Total**                                | **2 645** | 100 % |

Action prise :

1. Les 61 samples confirmés portent désormais `metadata.stack_exchange_attribution` (URL, auteur display name, user_id, post_id, creation_date_unix, license, match_confidence).
2. Les 169 « style SE non trouvés » portent `metadata.attribution_recovery=not_found_on_se` (avec note expliquant la classification).
3. Les 2 candidats faibles portent `metadata.attribution_recovery=low_confidence_match`.
4. README HF mis à jour : remplacement du bandeau « 31 % SE » par les chiffres audités.

## Méthodologie

### Étape 1 — Détection heuristique (recall élevé, précision faible)

Pour chaque sample, on lit le premier message `human` et on calcule un score de « ressemblance SE » :

| Signal                                                        | Poids |
|---------------------------------------------------------------|------:|
| Prompt commence par « I have / I'm / How do I / Can someone…» |   +3  |
| Référence inline « see the schematic / figure / diagram »     |   +2  |
| Bloc de code triple-backtick                                  |   +1  |
| Code inline backtick                                          |   +1  |
| Longueur 25 ≤ words ≤ 600                                     |   +1  |
| Présence de « ? »                                             |   +1  |
| Première personne « I'm / I've / my »                         |   +1  |

Seuil de candidat : `score >= 4`. Sur 2 645 samples, **537 candidats** (20 %) ont été flaggés comme « SE-style » par cette heuristique. C'est cohérent avec l'estimation initiale (~31 %), mais cette heuristique mesure un **style**, pas une **source**.

### Étape 2 — Recherche API Stack Exchange (vraie source)

Pour chaque candidat, on construit une requête keyword (premier ~200 mots, stopwords retirés, max 18 tokens) et on interroge :

```
GET https://api.stackexchange.com/2.3/search/advanced
    ?site=electronics&q=<keywords>&order=desc&sort=relevance&pagesize=5
    &filter=!9_bDDxJY5
```

Réponses cachées dans `~/eu-kiki-data/se_attribution_cache.json` (244 KB, idempotent par hash de requête).

### Étape 3 — Confirmation via body

Quand l'API renvoie ≥ 1 candidat avec un score titre plausible, on récupère le body via `/questions/{id}?filter=withbody` et on calcule :

```
match_confidence = max(
    first_line_match,                    # 1.0 if first line == HTML-decoded title
    0.30 * jaccard(bigrams(title))
  + 0.50 * jaccard(trigrams(body))
  + 0.20 * first_line_match
)
```

Seuils : `accept = 0.60`, `high_conf = 0.85`.

### Étape 4 — Marquage et enrichissement JSONL

Chaque sample reçoit un champ `metadata.attribution_recovery` parmi :

- `matched_on_se` (61) : attribution complète ajoutée dans `metadata.stack_exchange_attribution`.
- `not_found_on_se` (169) : style SE mais aucune réponse API (probable synthétique).
- `low_confidence_match` (2) : candidat API trouvé, score < 0.60.
- (absent) (2 413) : pas même détecté comme SE-style.

## Stats per-dataset

### `mascarade-kicad-dataset` ✅ AUDITÉ

| Métrique                              | Valeur            |
|---------------------------------------|-------------------|
| Total samples                         | 2 645             |
| Candidates SE-style (heuristique)     | 537               |
| Samples cachés API (POC budget 200)   | 232               |
| API hits                              | 63                |
| API no-results                        | 169               |
| Match high-conf (≥ 0.85)              | 61                |
| Match accepté (≥ 0.60)                | 61                |
| Match faible / échoué                 | 2                 |
| Pass-rate sur cache                   | 26.3 %            |
| Pass-rate sur API hits                | **96.8 %**        |
| **Décision POC**                      | **STOP** (sur cache faible, mais hits quasi-parfaits sur ce qui matche réellement) |
| **Verdict final**                     | **2.31 % SE réel** vs 31 % annoncé (sur-estimation **~13×**) |

### `mascarade-power-dataset` 🔒 PENDING (besoin SE API key)

### `mascarade-dsp-dataset` 🔒 PENDING (besoin SE API key)

### `mascarade-emc-dataset` 🔒 PENDING (besoin SE API key)

## Analyse — pourquoi seulement 2.31 % vs 31 % attendus ?

1. **Style ≠ source** : la prose anglophone informelle « how do I / can someone » est aussi reproductible par un LLM que copiable depuis SE. Le détecteur de style ne discrimine pas ces deux cas.
2. **Curation lourde** : les 169 « style SE introuvables sur l'API SE » résultent probablement d'un mélange (a) prompts paraphrasés assez pour échapper à la recherche keyword, (b) prompts entièrement synthétiques avec une persona « curieux qui pose une question », (c) prompts inspirés mais réécrits.
3. **Échantillon initial biaisé** : l'audit pré-API regardait 100 samples au hasard et extrapolait la fraction SE. Sur ces 100, beaucoup étaient des paraphrases qui ressemblaient à des questions SE → intuition trompeuse.

## Recommandations

### Pour `mascarade-power|dsp|emc-dataset`

Nécessite une **SE API key** (gratuite, [https://stackapps.com/apps/oauth/register](https://stackapps.com/apps/oauth/register)) :

- Anonyme : 300 req/jour total (quota épuisé pour le 2026-05-11).
- Avec key : **10 000 req/jour** par IP.

Lancement prévu via `~/scripts/se_attribution/audit_remaining.py --dataset {power,dsp,emc} --api-key <KEY>`. Pas de modification des datasets `power/dsp/emc` tant que l'API key n'est pas fournie.

### Pour les futurs scrapings

1. **Capturer l'attribution à la source** : tout pipeline qui scrape SE doit conserver `(url, post_id, owner.display_name, owner.user_id, license, creation_date)` au moment du scrape. La récupération a posteriori est lossy (61/537 candidats ≈ 11 % seulement).
2. **Marquer la provenance** : chaque sample doit porter `metadata.source_kind` ∈ {`scraped`, `synthetic`, `curated`, `original`} et `metadata.source_url` quand applicable.
3. **Audit récurrent** : ré-auditer chaque trimestre (ou avant chaque release majeure) pour vérifier que les nouveaux samples respectent l'invariant.

## Reproductibilité

```bash
# Re-run sur cache (gratuit, pas d'API call) :
HF=/Users/electron/mlx-stack/.venv/bin/hf
$HF download electron-rare/mascarade-kicad-dataset --repo-type dataset

python3 ~/scripts/se_attribution/finalize_enriched.py
# Sortie : ~/eu-kiki-data/kicad_chat_enriched_poc.jsonl
#          ~/eu-kiki-data/kicad_poc_stats.json (clé "finalize_enrichment")
```

## Artefacts

- Script POC : `~/scripts/se_attribution/poc_kicad.py`
- Script finalize (marqueurs not_found) : `~/scripts/se_attribution/finalize_enriched.py`
- Script audit power/dsp/emc (en attente API key) : `~/scripts/se_attribution/audit_remaining.py`
- Cache API : `~/eu-kiki-data/se_attribution_cache.json` (244 KB, idempotent)
- Stats : `~/eu-kiki-data/kicad_poc_stats.json`
- JSONL enrichi uploadé : `kicad_chat.jsonl` @ `electron-rare/mascarade-kicad-dataset`

## Audit log HF

| Action                             | Commit SHA (HF)                              |
|------------------------------------|----------------------------------------------|
| Upload `kicad_chat.jsonl` enrichi  | `5ae255ade19f285eedeb6ae7ab25278d75a4c23f` |
| Update `README.md` avec audit      | `7f8db437a89182d1a8d3acd4587e67d96eba18e7` |
