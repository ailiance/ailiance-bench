# Audit attribution Stack Exchange — famille `mascarade-*-dataset`

**Date** : 2026-05-11
**Auditeur** : revue de conformité interne (electron-rare)
**Statut** : COMPLIANT (4 datasets audités : `kicad`, `power`, `dsp`, `emc`)

## TL;DR

Les 4 datasets `electron-rare/mascarade-{kicad,power,dsp,emc}-dataset` (CC-BY-SA-4.0) étaient présentés comme « ~30 % scrapés depuis Stack Exchange Electronics », sans attribution per-sample (URL + auteur + post_id).

L'audit empirique via l'API Stack Exchange (`/search/advanced` + `/questions/{id}` avec body) confirme la même tendance sur les 4 datasets : **l'estimation initiale était sur-estimée par ~5,5–7×** (style ≠ source). Au total, **610 samples (~4.7 % du corpus mascarade-{kicad,power,dsp,emc} agrégé)** proviennent réellement de Stack Exchange Electronics et portent désormais une attribution complète.

### Synthèse — 4 datasets

| Dataset                | Samples | SE-detected (heuristique) | SE confirmés (≥0.60) | %    | Not-found-on-API | Low-conf | Synthetic | Over-count |
|------------------------|--------:|--------------------------:|---------------------:|-----:|-----------------:|---------:|----------:|-----------:|
| `mascarade-kicad`      |   2 645 |                       537 |                  146 | 5.52 |              386 |        5 |     2 108 |     ~5.6×  |
| `mascarade-power`      |   3 267 |                       585 |                  159 | 4.87 |              424 |        2 |     2 682 |     ~6.4×  |
| `mascarade-dsp`        |   3 160 |                       707 |                  169 | 5.35 |              535 |        3 |     2 453 |     ~5.7×  |
| `mascarade-emc`        |   3 360 |                       620 |                  136 | 4.05 |              482 |        2 |     2 740 |     ~7.6×  |
| **Total**              |**12 432**|                **2 449**|              **610**| **4.91** |        **1 827**|   **12** | **9 983** |  **~6.3×** |

> NB : pour `mascarade-kicad`, le compteur est passé de 61 (POC du 2026-05-11 matin, budget anonyme 232/537 cachés) à 146 après l'audit complet (456 nouveaux appels API avec key, couverture 537/537 candidats).

Action prise par dataset :

1. Les samples confirmés portent `metadata.stack_exchange_attribution` (URL, auteur `display_name`, `user_id`, `post_id`, `creation_date_unix`, `license`, `match_confidence`).
2. Les « style SE non trouvés sur l'API » portent `metadata.attribution_recovery=not_found_on_se` (avec note expliquant la classification).
3. Les candidats faibles portent `metadata.attribution_recovery=low_confidence_match` (URL candidate uniquement).
4. README HF mis à jour (sur les 4 datasets electron-rare + 4 mirrors Ailiance-fr) : remplacement du bandeau « ~30 % SE » par les chiffres audités.
5. LoRA héritant du warning : `Ailiance-fr/apertus-emc-dsp-power-lora` et `apertus-emc-dsp-power-curriculum-lora` mis à jour avec les vrais chiffres training-data.

## Méthodologie (commune aux 4 datasets)

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

Seuil de candidat : `score >= 4`. Mesure un **style**, pas une **source**.

### Étape 2 — Recherche API Stack Exchange (vraie source)

Pour chaque candidat, on construit une requête keyword (premier ~200 mots, stopwords retirés, max 18 tokens) et on interroge :

```
GET https://api.stackexchange.com/2.3/search/advanced
    ?site=electronics&q=<keywords>&order=desc&sort=relevance&pagesize=5
    &filter=!9_bDDxJY5&key=<SE_API_KEY>
```

Réponses cachées en JSON idempotent par hash de requête. Une clé API gratuite (registration `https://stackapps.com/apps/oauth/register`) lève la limite anonyme 300 req/jour à 10 000 req/jour par IP.

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

Seuils : `accept = 0.60`, `high_conf = 0.85`. **Pass-rate sur API hits = 96–99 %** (le scoring discrimine très bien le bruit). La perte de signal est presque exclusivement liée à l'étape 1 → étape 2 (samples qui ressemblent à SE mais qui ont été paraphrasés assez pour échapper à la recherche keyword).

### Étape 4 — Marquage et enrichissement JSONL

Chaque sample reçoit un champ `metadata.attribution_recovery` parmi :

- `matched_on_se` (610 total) : attribution complète ajoutée dans `metadata.stack_exchange_attribution`.
- `not_found_on_se` (1 827 total) : style SE mais aucune réponse API (probable synthétique / paraphrase lourde).
- `low_confidence_match` (12 total) : candidat API trouvé, score < 0.60.
- (absent) (9 983 total) : pas même détecté comme SE-style (synthétique LLM ou unique).

## Stats détaillées par dataset

### `mascarade-kicad-dataset` ✅ AUDITED

| Métrique                              | Valeur            |
|---------------------------------------|-------------------|
| Total samples                         | 2 645             |
| Candidates SE-style (heuristique)     | 537               |
| API calls totaux (POC + complement)   | 232 + 456 = 688   |
| Match high-conf (≥ 0.85)              | 146               |
| Match accepté (≥ 0.60)                | 146               |
| Not-found-on-SE                       | 386               |
| Low-conf                              | 5                 |
| Synthetic / unique                    | 2 108             |
| Pass-rate sur API hits                | **96.8 %**        |
| **Verdict final**                     | **5.52 % SE réel** vs 30 % annoncé (sur-estimation **~5.6×**) |

### `mascarade-power-dataset` ✅ AUDITED

| Métrique                              | Valeur            |
|---------------------------------------|-------------------|
| Total samples                         | 3 267             |
| Candidates SE-style (heuristique)     | 585               |
| API calls (avec key)                  | 746               |
| Match high-conf (≥ 0.85)              | 159               |
| Not-found-on-SE                       | 424               |
| Low-conf                              | 2                 |
| Synthetic / unique                    | 2 682             |
| **Verdict final**                     | **4.87 % SE réel** vs 30 % annoncé (sur-estimation **~6.2×**) |

### `mascarade-dsp-dataset` ✅ AUDITED

| Métrique                              | Valeur            |
|---------------------------------------|-------------------|
| Total samples                         | 3 160             |
| Candidates SE-style (heuristique)     | 707               |
| API calls (avec key)                  | 879               |
| Match high-conf (≥ 0.85)              | 169               |
| Not-found-on-SE                       | 535               |
| Low-conf                              | 3                 |
| Synthetic / unique                    | 2 453             |
| **Verdict final**                     | **5.35 % SE réel** vs 30 % annoncé (sur-estimation **~5.6×**) |

### `mascarade-emc-dataset` ✅ AUDITED

| Métrique                              | Valeur            |
|---------------------------------------|-------------------|
| Total samples                         | 3 360             |
| Candidates SE-style (heuristique)     | 620               |
| API calls (avec key)                  | 758               |
| Match high-conf (≥ 0.85)              | 136               |
| Not-found-on-SE                       | 482               |
| Low-conf                              | 2                 |
| Synthetic / unique                    | 2 740             |
| **Verdict final**                     | **4.05 % SE réel** vs 30 % annoncé (sur-estimation **~7.4×**) |

## Analyse — pourquoi seulement ~5 % vs ~30 % attendus ?

**Constat reproduit sur 4 datasets indépendants** : la fraction réelle scrapée depuis SE est de **4.05 %–5.52 %**, alors que l'estimation initiale était de ~30 %. La sur-estimation est cohérente (~5.6×–7.6×) à travers les 4 domaines, ce qui confirme un biais méthodologique commun et non un artefact spécifique à un dataset.

1. **Style ≠ source** : la prose anglophone informelle « how do I / can someone » est aussi reproductible par un LLM que copiable depuis SE. Le détecteur de style ne discrimine pas ces deux cas.
2. **Curation lourde** : les 1 827 samples « style SE introuvables sur l'API SE » résultent probablement d'un mélange (a) prompts paraphrasés assez pour échapper à la recherche keyword, (b) prompts entièrement synthétiques avec une persona « curieux qui pose une question », (c) prompts inspirés mais réécrits.
3. **Échantillon initial biaisé** : l'audit pré-API regardait ~100 samples au hasard et extrapolait la fraction SE. Sur ces 100, beaucoup étaient des paraphrases qui ressemblaient à des questions SE → intuition trompeuse.
4. **Fiabilité API-search** : le pass-rate sur API hits est de 96–99 % — quand l'API renvoie un candidat, le scoring confirme presque toujours la correspondance. Les faux-positifs SE sont donc *quasi nuls*, ce qui valide a posteriori le `match_confidence >= 0.60` comme seuil sûr.

## Méthodologie validée

L'audit est **reproductible et idempotent** :

- Cache JSON par hash de requête (`~/eu-kiki-data/{ds}_attribution_cache.json` pour `power|dsp|emc`, `~/eu-kiki-data/se_attribution_cache.json` pour `kicad`).
- Coût : ~3 200 appels API total pour les 4 datasets (largement sous le quota 10 000/jour avec key).
- Temps : ~25 min pour ré-auditer les 4 datasets from-scratch.

## Recommandations

### Pour les futurs scrapings

1. **Capturer l'attribution à la source** : tout pipeline qui scrape SE doit conserver `(url, post_id, owner.display_name, owner.user_id, license, creation_date)` au moment du scrape. La récupération a posteriori est lossy (~25 % des candidats heuristiques sont confirmés ; ~75 % échappent au keyword search par paraphrase).
2. **Marquer la provenance** : chaque sample doit porter `metadata.source_kind` ∈ {`scraped`, `synthetic`, `curated`, `original`} et `metadata.source_url` quand applicable.
3. **Audit récurrent** : ré-auditer chaque trimestre (ou avant chaque release majeure) pour vérifier que les nouveaux samples respectent l'invariant.

### Pour les autres datasets de la famille mascarade

Les datasets `mascarade-{stm32,spice,iot,embedded}` ont des profils différents (plus de contenu généré, moins de prose SE-style). Un audit similaire serait utile pour confirmation, mais la priorité conformité est traitée avec les 4 datasets ci-dessus (ceux qui portaient explicitement le bandeau « ~30 % SE »).

## Artefacts

- Script POC kicad : `~/scripts/se_attribution/poc_kicad.py`
- Script audit `power|dsp|emc|kicad` : `~/scripts/se_attribution/audit_remaining.py`
- Script finalize (marqueurs not_found, post-POC) : `~/scripts/se_attribution/finalize_enriched.py`
- Script rendering READMEs : `~/scripts/se_attribution/render_dataset_readmes.py`
- Script update LoRA disclosure : `~/scripts/se_attribution/update_lora_disclosure.py`
- Script upload HF : `~/scripts/se_attribution/upload_to_hf.sh`
- Caches API : `~/eu-kiki-data/{power,dsp,emc}_attribution_cache.json` (~ 650–700 KB chacun) ; `~/eu-kiki-data/se_attribution_cache.json` (kicad, ~ 580 KB).
- Stats : `~/eu-kiki-data/{power,dsp,emc,kicad}_audit_stats.json`
- JSONL enrichis : `~/eu-kiki-data/{power,dsp,emc,kicad}_chat_enriched.jsonl`

## Reproductibilité

```bash
# Pre-requis : clé API SE (gratuite, https://stackapps.com/apps/oauth/register)
mkdir -p ~/.cache/stackexchange && echo "<KEY>" > ~/.cache/stackexchange/api_key

# Audit complet, 4 datasets, ~25 min :
KEY=$(cat ~/.cache/stackexchange/api_key)
for ds in power dsp emc kicad; do
  /Users/electron/mlx-stack/.venv/bin/python ~/scripts/se_attribution/audit_remaining.py --dataset $ds --api-key "$KEY"
done

# Re-render des 8 READMEs (electron-rare + Ailiance-fr) :
/Users/electron/mlx-stack/.venv/bin/python ~/scripts/se_attribution/render_dataset_readmes.py

# Upload (JSONL + README) sur les 2 mirrors :
for ds in power dsp emc kicad; do
  bash ~/scripts/se_attribution/upload_to_hf.sh $ds
done

# Update LoRA cards qui héritent :
/Users/electron/mlx-stack/.venv/bin/python ~/scripts/se_attribution/update_lora_disclosure.py
# upload manuel des 2 README.md ensuite
```

## Audit log HF (2026-05-11)

| Action                                                  | Org / Repo                                                   |
|---------------------------------------------------------|--------------------------------------------------------------|
| Upload `power_chat.jsonl` + README                      | `electron-rare/mascarade-power-dataset`, `Ailiance-fr/...`   |
| Upload `dsp_chat.jsonl` + README                        | `electron-rare/mascarade-dsp-dataset`, `Ailiance-fr/...`     |
| Upload `emc_chat.jsonl` + README                        | `electron-rare/mascarade-emc-dataset`, `Ailiance-fr/...`     |
| Upload `kicad_chat.jsonl` + README (audit complet)      | `electron-rare/mascarade-kicad-dataset`, `Ailiance-fr/...`   |
| Update README `apertus-emc-dsp-power-lora`              | `Ailiance-fr/apertus-emc-dsp-power-lora`                     |
| Update README `apertus-emc-dsp-power-curriculum-lora`   | `Ailiance-fr/apertus-emc-dsp-power-curriculum-lora`          |
