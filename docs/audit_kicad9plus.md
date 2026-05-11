# Audit légal — `electron-rare/kicad9plus-sch-corpus`

**Date**: 2026-05-11
**Auditeur**: revue de conformité interne (electron-rare)
**Statut**: NON-COMPLIANT (déprécié, splitté en deux datasets)

## TL;DR

Le dataset `electron-rare/kicad9plus-sch-corpus` (307 samples, première version 2026-05-11) a été uploadé sous **CC-BY-SA-4.0** alors qu'il agrège des sources sous **GPL-3.0 (169)**, **CERN-OHL-S-2.0 (36)** et **EUPL-1.2 (4)**. Ce mélange viole la directionnalité copyleft.

> **Conclusion**: 209 / 307 samples (68%) sont incompatibles avec l'umbrella CC-BY-SA-4.0. Le dataset a été déprécié sur place, et splitté en deux datasets compliants :
>
> - `electron-rare/kicad9plus-permissive` — 98 samples — CC-BY-SA-4.0
> - `electron-rare/kicad9plus-copyleft` — 209 samples — GPL-3.0-or-later

## Contexte

Le pipeline `scripts/kicad9plus_pipeline.sh` filtre les fichiers `.kicad_sch` GitHub par SPDX whitelist (Apache-2.0, MIT, CC0-1.0, CERN-OHL-P-2.0, GPL-3.0, CERN-OHL-S-2.0, EUPL-1.2). À l'upload v1, l'umbrella CC-BY-SA-4.0 a été appliqué uniformément, sans tri par compatibilité copyleft.

## Distribution réelle des licences (input)

| License           | Count | %     | Catégorie           |
|-------------------|------:|------:|---------------------|
| GPL-3.0           |   169 | 55.0% | copyleft strong     |
| Apache-2.0        |    74 | 24.1% | permissive          |
| CERN-OHL-S-2.0    |    36 | 11.7% | copyleft strong (HW)|
| MIT               |    20 |  6.5% | permissive          |
| EUPL-1.2          |     4 |  1.3% | copyleft (EU)       |
| CC0-1.0           |     3 |  1.0% | public domain       |
| CERN-OHL-P-2.0    |     1 |  0.3% | permissive (HW)     |
| **Total**         | **307** | **100%** | |

## Problème 1 — directionnalité CC-BY-SA-4.0 ↔ GPLv3

CC-BY-SA-4.0 est explicitement **one-way compatible vers GPLv3**, jamais l'inverse :

> "CC BY-SA 4.0 [...] adaptations of CC BY-SA 4.0 material may be released under GPLv3 [but] CC-licensed material cannot incorporate GPL-licensed material"
> — [Creative Commons announcement, 2015](https://creativecommons.org/2015/10/08/cc-by-sa-4-0-now-one-way-compatible-with-gplv3/)

Reformuler 169 samples GPL-3.0 sous une umbrella CC-BY-SA-4.0 viole §5b de la GPL-3.0 (obligation que les copies modifiées restent sous GPL-3.0+) ainsi que la déclaration d'unidirectionnalité de la CC.

## Problème 2 — CERN-OHL-S-2.0

CERN-OHL-S-2.0 est une licence **strongly reciprocal** pour matériel hardware (la "S" = Strongly reciprocal). §4.2 impose que toute Modified Source soit redistribuée sous CERN-OHL-S-2.0, et §7 ne reconnaît la compatibilité qu'avec un sous-ensemble strict (essentiellement GPL-3.0+ via la clause d'interopérabilité GPL). CC-BY-SA-4.0 n'est **pas** dans ce sous-ensemble.

## Problème 3 — EUPL-1.2

EUPL-1.2 §5 ("Copyleft clause") impose la même licence ou une "Compatible Licence" listée à l'Appendix. CC-BY-SA-4.0 n'y figure pas (les CC ne sont jamais listées comme Compatible Licences EUPL). GPL-3.0+ y figure, donc l'EUPL-1.2 reste compatible avec une umbrella GPL-3.0-or-later.

## Problème 4 — `ia_act_status: compliant`

Le champ metadata indiquait `ia_act_status: compliant` sur les 307 samples. Cette affirmation est **prématurée** : la conformité au Template AI Office (juillet 2025) demande une analyse explicite par catégorie de source, l'application correcte des licences et la prise en compte des reservations of rights TDM. Le statut a été abaissé à `requires_review` sur les deux datasets splittés.

## Action — Option C (split par compatibilité)

Trois options ont été envisagées :

- **A** : tout reformuler en GPL-3.0-or-later. Dégrade 98 samples permissifs sans nécessité.
- **B** : retirer 209 samples copyleft. Perte de 68% du corpus.
- **C** : ✅ **split en deux datasets séparés** (chacun homogène en compatibilité), preserve attribution per-sample.

## Mise en œuvre

### 1. Split du JSONL

```python
permissive_licenses = {'Apache-2.0', 'MIT', 'CC0-1.0', 'CERN-OHL-P-2.0', 'BSD-3-Clause', 'BSD-2-Clause', 'ISC'}
copyleft_licenses   = {'GPL-3.0', 'GPL-3.0-only', 'GPL-3.0-or-later', 'CERN-OHL-S-2.0', 'EUPL-1.2', 'AGPL-3.0'}
# + ia_act_status: 'compliant' -> 'requires_review' partout
```

Voir `scripts/kicad9plus_split_compliance.py` (committé avec ce rapport).

### 2. Création des deux nouveaux repos HF

- https://huggingface.co/datasets/electron-rare/kicad9plus-permissive (98 samples, CC-BY-SA-4.0)
- https://huggingface.co/datasets/electron-rare/kicad9plus-copyleft (209 samples, GPL-3.0-or-later)

Chacun avec : `dataset.jsonl`, `LICENSE_INVENTORY.md` séparé, `README.md` aligné Template AI Office (juillet 2025) couvrant General information / Data sources / Data processing / Data characteristics / Licenses applied / Copyright considerations.

### 3. Dépréciation de l'ancien repo

Le repo `electron-rare/kicad9plus-sch-corpus` est conservé pour archivage / reproductibilité, avec un bandeau DEPRECATED en tête de README pointant vers les deux datasets splittés et vers ce rapport.

## Compatibilité du subset copyleft (GPL-3.0-or-later)

- **GPL-3.0 → GPL-3.0+** : trivialement compatible.
- **CERN-OHL-S-2.0 → GPL-3.0+** : compatible via §7 CERN-OHL-S (clause d'interopérabilité GPL).
- **EUPL-1.2 → GPL-3.0+** : compatible via §5 + Appendix EUPL (GPL-3.0 listé comme Compatible Licence).

L'umbrella GPL-3.0-or-later est donc le plus petit dénominateur commun valide.

## Compatibilité du subset permissive (CC-BY-SA-4.0)

- **Apache-2.0 → CC-BY-SA-4.0** : compatible (Apache permet la redistribution sous CC-BY-SA, mais le patent grant Apache §3 ne se transmet pas automatiquement par CC-BY-SA — noté dans le README).
- **MIT → CC-BY-SA-4.0** : compatible (MIT n'a aucune clause copyleft).
- **CC0-1.0 → CC-BY-SA-4.0** : compatible (CC0 = public domain, peut être réutilisé sous n'importe quelle licence).
- **CERN-OHL-P-2.0 → CC-BY-SA-4.0** : compatible (CERN-OHL-P = Permissive, équivalent BSD/MIT pour HW).

Per-sample attribution préservée dans `metadata.license_spdx` et `metadata.source_url` ; `LICENSE_INVENTORY.md` séparé liste chaque sample.

## Alignement EU AI Act — Template AI Office (juillet 2025)

Les deux nouveaux READMEs couvrent explicitement les sections demandées :

1. **General information** (nom, modalité, langues, intended use)
2. **Data sources** : publicly available datasets / web scraping / licensed data — explicitement séparés
3. **Data processing** : méthode de collecte, filtrage, dédup, validation
4. **Data characteristics** : taille, mix de licences input, mix de versions KiCad
5. **Licenses applied** : licence du dataset agrégé + préservation per-sample
6. **Copyright considerations** : opt-out (c.saillant@gmail.com), respect de robots.txt / noai / TDMRep

## Suivi

- [x] Audit légal documenté (ce fichier)
- [x] Split JSONL : 98 perm + 209 copy = 307 ✓
- [x] LICENSE_INVENTORY séparé par subset
- [x] READMEs Template AI Office
- [x] Repos HF créés et uploadés
- [x] Ancien repo déprécié
- [x] `ia_act_status` corrigé à `requires_review`
- [ ] Re-runs des évaluations downstream avec le subset approprié selon licence cible
- [ ] Vérification annuelle des reservations of rights TDM sur les repos sources

## Références

- [Creative Commons one-way compatibility note (2015)](https://creativecommons.org/2015/10/08/cc-by-sa-4-0-now-one-way-compatible-with-gplv3/)
- [GPL-3.0 §5 (Conveying Modified Source Versions)](https://www.gnu.org/licenses/gpl-3.0.html#section5)
- [CERN-OHL-S-2.0 §7 (License Compatibility)](https://ohwr.org/cern_ohl_s_v2.txt)
- [EUPL-1.2 §5 + Appendix (Compatibility clause)](https://eupl.eu/1.2/en/)
- [EU AI Act — Template AI Office, juillet 2025](https://digital-strategy.ec.europa.eu/en/library/template-public-summary-content-used-training-general-purpose-ai-models)
- [DSM Directive (EU 2019/790) Article 4(3) — TDM opt-out](https://eur-lex.europa.eu/eli/dir/2019/790/oj)
