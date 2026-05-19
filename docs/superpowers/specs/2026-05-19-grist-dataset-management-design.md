# Grist comme source de vérité pour les datasets ailiance / mascarade

**Date :** 2026-05-19
**Statut :** design validé et implémenté. Le workflow de revue humaine a
depuis évolué — voir `2026-05-19-grist-review-layer-design.md`. Le flag
booléen `exclure` décrit plus bas a été remplacé par un champ
`review_status` (`pending` / `validated` / `rejected` / `needs_fix`) ;
l'export ne livre que les lignes `validated`.

## Problème

Les datasets de fine-tuning ailiance/mascarade sont dispersés : fichiers
`.jsonl` locaux produits par le mining, datasets HuggingFace `Ailiance-fr/`,
et un export Grist partiel. Il n'existe aucune surface de vérification et de
modification humaine des données, et aucune traçabilité reliant une version
de dataset au LoRA qu'elle a entraîné.

L'intégration Grist actuelle (`scripts/export_grist.py`) pousse `.jsonl →
Grist` en *upsert* : Grist est un miroir aval. Toute édition faite dans Grist
serait écrasée au prochain export.

## Objectif

Faire de **Grist la source de vérité canonique** des datasets. Le mining
alimente Grist, la revue humaine se fait dans Grist, et l'entraînement comme
la publication HuggingFace consomment un export généré depuis Grist.

## Décisions de cadrage

- **Rôle de Grist** : source de vérité canonique (pas miroir, pas
  lecture seule).
- **Périmètre** : training mascarade, eval/heldout, datasets HF publiés
  (= cible de publication du training, pas une famille distincte),
  iact-bench.
- **Revue humaine** : édition libre des champs + booléen `exclure`. Pas
  d'état de validation formel ; tout item non exclu est exporté.
- **Export & versioning** : snapshot `.jsonl` horodaté + hashé à la
  demande, journalisé dans une table `Exports`.
- **Organisation Grist** : approche B — un document Grist par famille
  (isolation).

## Changement d'architecture central

Le flux doit être **inversé** par rapport à l'existant : l'ingestion
n'écrit dans Grist qu'en **insertion seule** (jamais d'écrasement → les
corrections humaines survivent), et l'**export Grist → `.jsonl`** devient
la direction canonique.

```
mining/curation ──ingest (INSERT-only)──▶  Doc Grist (source de vérité)
                                              │
                                  revue humaine : édition libre + flag exclure
                                              │
                         export (filtre exclure=false) ──▶ snapshot .jsonl horodaté+hashé
                                              │                       │
                                    ligne dans Exports (du doc)  publish ──▶ HF dataset
                                                                        │
                                                          training consomme le snapshot figé
```

## Organisation Grist (approche B)

Trois documents Grist. La famille « datasets HF publiés » n'est pas un
document : les dépôts HF `mascarade-*-dataset` *sont* le corpus de
training, donc une cible de publication du document Training.

| Document Grist | Famille | Tables | État |
|----------------|---------|--------|------|
| **Doc Heldout** = `eGbbrpzN3TeLq3sUd2YFA2` | eval / heldout | `Datasets`, `Heldout_Items` (+ `exclure`, `notes`), `Exports` (nouveau) | étend l'existant |
| **Doc Training** = à créer | training mascarade → publication HF | `Datasets_Registry`, `Mascarade_Training`, `Exports` | document neuf |
| **Doc Iact-Bench** | bench EU AI Act | schéma d'audit à caler | phase 3 |

### Schéma des tables

**`Mascarade_Training`** — 1 ligne par item d'entraînement, 10 domaines :

| Colonne | Type | Notes |
|---------|------|-------|
| `item_key` | texte | clé — SHA1 du `user_msg` |
| `domain` | texte | kicad, spice, stm32, emc, embedded, platformio, freecad, dsp, iot, power |
| `system` | texte | message système (optionnel) |
| `user_msg` | texte | tour utilisateur / instruction |
| `assistant_msg` | texte | sortie attendue |
| `extra_turns` | texte (JSON) | repli si item multi-turn ; vide sinon |
| `source` | texte | URL / provenance |
| `exclure` | booléen | exclut l'item de l'export |
| `notes` | texte | annotations de revue |

**`Heldout_Items`** — étend la table existante :

| Colonne | Type | Notes |
|---------|------|-------|
| `item_key` | texte | clé — SHA1 du `prompt` (existant) |
| `domain` | texte | existant |
| `prompt` | texte | existant |
| `reference` | texte | existant |
| `source` | texte | existant |
| `exclure` | booléen | **ajouté** |
| `notes` | texte | **ajouté** |

**`Datasets_Registry`** / **`Datasets`** — 1 ligne par dataset :
`name` (clé), `family`, `domain`, `hf_dataset_id`, `license`, `n_items`,
`notes`.

**`Exports`** — journal des snapshots, présent dans chaque document :
`export_id`, `domain`, `created_at`, `n_items`, `content_hash`,
`output_file`, `hf_dataset_id`.

### Format training aplati

Les fichiers HF `<domain>_chat.jsonl` sont au format messages
(ShareGPT / OpenAI). Ils sont aplatis en trois colonnes éditables
`system` / `user_msg` / `assistant_msg`, car Grist édite mal le JSON
imbriqué. Hypothèse : items single-turn Q&A (cas attendu du SFT
mascarade). Si la migration trouve du multi-turn, le tableau `messages`
complet est conservé dans `extra_turns` (JSON) ; l'export reconstruit
depuis `extra_turns` si présent, sinon depuis les trois colonnes.

## Outillage

Modules à responsabilité unique dans `mascarade-eval/scripts/grist/` :

| Fichier | Responsabilité |
|---------|----------------|
| `grist_client.py` | Wrapper API Grist : auth (`~/.config/electron-rare/grist.env`), CRUD records, ciblage doc + table. Reprend le code Grist de `export_grist.py`. |
| `dataset_cli.py` | Point d'entrée `argparse`, 4 sous-commandes. |
| `ingest.py` | mining/curation `.jsonl` → Grist, **insertion seule**. |
| `export.py` | Grist → snapshot `.jsonl` figé + ligne `Exports`. |
| `publish.py` | snapshot → dataset HF. |
| `migrate.py` | backfill unique des données existantes vers Grist. |

La règle « insertion seule » est isolée dans `ingest.py` et ne peut être
contournée par accident.

### Sous-commandes

- **`ingest <doc> <jsonl>`** — calcule `item_key` (SHA1 du
  `user_msg`/`prompt`), lit les clés déjà présentes dans la table,
  insère uniquement le delta. Ne modifie jamais une ligne d'item
  existante. Rapport : `N nouveaux, N déjà présents (ignorés)`. Les
  lignes de registre peuvent être en upsert (métadonnées, pas de donnée
  éditée).
- **`export <doc> <domain|all>`** — lit la table, filtre
  `exclure=false`, **trie par `item_key`** (ordre déterministe), écrit
  `exports/<domain>.<timestamp>.jsonl`, calcule `content_hash` = SHA256
  du fichier canonique, ajoute une ligne `Exports`.
- **`publish <doc> <export_id>`** — reprend le snapshot d'une ligne
  `Exports`, l'upload vers `Ailiance-fr/mascarade-<domain>-dataset`,
  renseigne `hf_dataset_id` dans la ligne `Exports` et le registre.
  Échec HF → `hf_dataset_id` reste vide, rejouable.
- **`migrate <doc>`** — backfill unique : tire les
  `<domain>_chat.jsonl` HF (training) ou les `heldout/*.clean.jsonl`
  locaux (eval) et les ingère en insertion seule.

### Gestion d'erreurs

- `ingest` : ligne JSON malformée → ignorée + loguée, pas d'abandon du
  lot.
- `export` : Grist injoignable → échec net, aucun fichier partiel
  écrit.
- multi-turn détecté à la migration → `messages` complet dans
  `extra_turns`, `user_msg`/`assistant_msg` remplis avec la 1ʳᵉ paire.
- collision `item_key` (2 prompts différents, même SHA1) → warning à
  l'ingestion.

## Migration de l'existant

- **`export_grist.py` actuel** : son code Grist part dans
  `grist_client.py` ; sa direction `.jsonl → Grist` devient `ingest`,
  convertie d'upsert en insertion seule pour les items.
- **« 13 datasets HF »** = 10 `mascarade-*-dataset` + 3 non identifiés.
  La phase 1 identifie les 3 et décide de leur périmètre.
- Volumétrie : Grist encaisse des dizaines de milliers de lignes ; aucun
  problème attendu.

## Phasage

Chaque phase est livrable et validable seule.

- **Phase 1 — Training mascarade.** Créer le document Grist neuf +
  schéma ; `grist_client.py`, `ingest.py`, `export.py`, `publish.py`,
  `migrate.py`. Backfill des 10 `Ailiance-fr/mascarade-<domain>-dataset`.
  Valider round-trip de migration, workflow `exclure`, export + hash,
  journal `Exports`, publish HF.
- **Phase 2 — Heldout / eval.** Étendre le document existant
  `eGbbrpzN...` : colonnes `exclure`/`notes` sur `Heldout_Items`, table
  `Exports`. Adapter `ingest`/`export` au schéma heldout. Migrer
  `heldout/*.clean.jsonl`. Reconvertir l'ancien `export_grist.py` en
  `ingest` insertion seule.
- **Phase 3 — iact-bench.** Document séparé, schéma d'audit à caler,
  `ingest`. Indépendant des phases 1-2.

## Tests

- **Unitaires** : déterminisme `item_key` ; logique insertion seule
  (clés déjà présentes ignorées) ; déterminisme export (même état Grist
  → même `content_hash`) ; round-trip d'aplatissement multi-turn
  (`messages` → colonnes → `messages`).
- **Intégration** : sur une table Grist jetable — `migrate` d'un
  échantillon → `export` → assertion d'égalité sémantique.
- **Test de sûreté (garantie source de vérité)** : (a) `ingest` deux
  fois → le 2ᵉ passage insère 0 ligne ; (b) éditer une ligne dans Grist
  puis ré-`ingest` → l'édition survit.

## Critères de succès

- Le mining alimente Grist sans jamais écraser une édition humaine.
- Un réviseur peut corriger un champ ou cocher `exclure` dans Grist, et
  l'export reflète immédiatement le changement.
- Chaque dataset entraîné est traçable jusqu'à une ligne `Exports`
  (date, hash, nombre d'items, fichier).
- Le round-trip de migration ne perd aucune information sémantique.
