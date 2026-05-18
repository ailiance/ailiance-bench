# Held-out sources — upstream mining contract

**Task 1 research spike** — 2026-05-18. This document is the contract that
`mine_upstream.py` (sous-projet A, composant 1) implements. It pins down,
per domain, a concrete source of fresh `(prompt, reference)` pairs that the
10 mascarade LoRA have never seen in training.

## TL;DR

- The plan's premise — "inspect a `_provenance` field on each dataset row" —
  **does not hold**. The `Ailiance-fr/mascarade-<domain>-dataset` rows have
  **no `_provenance` field**. There is only an optional `metadata` key, and
  it is an *attribution-recovery audit flag*, not a build-provenance record.
- Real per-domain provenance lives in the **dataset README cards** (the
  EU AI Act "Data sources" section) and in
  `docs/audit_mascarade_se_attribution.md`.
- Only **4 of 10 domains** (`kicad`, `emc`, `power`, `dsp`) have any
  Stack Exchange content at all, and only ~5 % of those datasets is SE.
  For those 4, a temporal cut is **trivially clean**: the newest SE post
  in training is from **early 2012** (see table below), so anything posted
  after 2012 is unseen by ~14 years.
- The other **6 domains** (`spice`, `stm32`, `embedded`, `platformio`,
  `freecad`, `iot`) are **not derived from Stack Exchange** and have **no
  timestamped upstream** — a temporal cut is impossible. Each gets an
  alternative fresh source or an explicitly flagged hand-curate fallback.

## What was inspected

10 datasets `Ailiance-fr/mascarade-<domain>-dataset`, file `<domain>_chat.jsonl`,
downloaded via `huggingface_hub` and inspected row by row.

### Row schema (verified, not the schema the plan assumed)

Three shapes are in use across the family — all ShareGPT/chat style:

| Domain(s)                                  | Top-level keys           | Turn format                          |
|--------------------------------------------|--------------------------|---------------------------------------|
| kicad, emc, dsp, power                     | `conversations`, `metadata` | `{from: system/human/gpt, value}`  |
| spice, stm32, embedded, iot                | `conversations`          | `{from: system/human/gpt, value}`  |
| platformio, freecad                        | `messages`               | `{role: system/user/assistant, content}` |

There is **no `_provenance` key anywhere**. `mine_upstream.py` and the
leakage-check must handle both `conversations` and `messages` shapes.

### The `metadata` key (where present)

Present on 100 % of rows for `kicad`, `emc`, `dsp`, `power`; **absent** on
all other 6 domains. It is *not* build provenance — it is the output of the
SE attribution audit (`docs/audit_mascarade_se_attribution.md`, 2026-05-11):

- `attribution_recovery = matched_on_se` — confirmed SE Electronics post.
  Carries a `stack_exchange_attribution` sub-object with `url`, `post_id`,
  `author_user_id`, **`creation_date_unix`**, `license`, `match_confidence`.
- `attribution_recovery = not_found_on_se` — SE-styled but no API match;
  "Likely synthetic/curated".
- `attribution_recovery = low_confidence_match` — weak candidate, URL only.
- `{}` (empty) — synthetic / unique to the dataset.

`creation_date_unix` on `matched_on_se` rows is the **only timestamp** in
the entire corpus, and it exists for only 4 domains.

## Temporal cutoff — the 4 Stack Exchange domains

Newest SE-matched post per domain (computed over all `matched_on_se` rows):

| Domain | SE-matched rows | Oldest SE post | **Newest SE post** | Max `post_id` |
|--------|----------------:|----------------|--------------------|--------------:|
| kicad  | 146 | 2009-11-01 | **2012-04-09** (epoch 1333959234) | 29530 |
| emc    | 136 | 2009-11-04 | **2012-02-18** (epoch 1329557886) | 26798 |
| power  | 159 | 2009-11-01 | **2012-01-16** (epoch 1326697418) | 25135 |
| dsp    | 169 | 2009-11-17 | **2012-04-25** (epoch 1335366633) | 30686 |

Interpretation: the SE slice of training was harvested from an old SE dump
(latest post April 2012). **Any SE post created after 2012 is unseen by
construction.** To be conservative against re-posts / edits / citations and
to leave a wide margin, `mine_upstream.py` uses a cutoff of
**`fromdate = 1735689600` (2025-01-01 00:00 UTC)** — 13 years past the
training frontier. That is the safe `fromdate` for all 4 SE domains.

The leakage guard (composant 2) is still mandatory: a 2025 post can quote or
duplicate a pre-2012 question. Temporal cut reduces risk; it does not remove it.

## Stack Exchange API — verified access method

Live-tested 2026-05-18 against `api.stackexchange.com/2.3` (anonymous, no
key — quota ~300/day; with a key, 10 000/day). Findings:

- **Endpoint**: `GET /2.3/questions?site=<site>&tagged=<tag>&fromdate=<epoch>`
  `&sort=creation&order=desc&pagesize=100&filter=withbody`.
- **Filter**: use the built-in **`withbody`** filter. It returns, per item:
  `title`, `body` (HTML), `creation_date`, `link`, `question_id`,
  `accepted_answer_id`, `answer_count`, `score`, `tags`, `owner`,
  `content_license`. *Note*: `withbody` gives `body` as **HTML**, not
  `body_markdown`. A custom filter including `question.body_markdown` was
  attempted but the generated filter id contains characters that broke the
  request even url-encoded — so `mine_upstream.py` should take `body` (HTML)
  and strip tags itself, or just use `title` as the prompt (recommended:
  `title` is a clean, self-contained question).
- **Reference answer**: a second call
  `GET /2.3/questions/{id}/answers?site=<site>&filter=withbody&sort=votes`
  `&order=desc` returns answers with `body` (HTML), `score`, `is_accepted`.
  Pick the accepted answer, else the highest-scored. Verified: returns
  `answer_id`, `score`, `is_accepted`, `body`.
- **Pagination**: response carries `has_more` and `quota_remaining`; the SE
  `backoff` field must be honored (the existing `lib_compliance.compliant_get`
  in `scripts/scraping_compliant/` already does this — reuse it).
- **Compliance**: reuse `scripts/scraping_compliant/lib_compliance.py`
  (`Ailiance-Compliance-Crawler/1.0` UA, robots/TDMRep preflight, audit
  JSONL). SE content is CC-BY-SA-4.0 — keep `link` + `owner` for attribution.

### Field mapping → `{prompt, reference}`

```
prompt    = question "title"            (clean, single-sentence question)
            (optionally append stripped body for context)
reference = accepted answer body (HTML→text), else top-voted answer body
metadata  = {source: "stackexchange", site, question_id, link,
             creation_date, answer_id, answer_score, is_accepted,
             content_license, owner}
```

Items with `answer_count == 0` are dropped (no reference available).

## Per-domain held-out source plan

Yield target per domain: **≥25 clean items** after the leakage guard.
"Recent question count" below is `filter=total`, `fromdate=2025-01-01`,
measured live 2026-05-18.

### kicad — Stack Exchange (temporal cut) ✅

- **Source**: `electronics.stackexchange.com` via API.
- **Site / tag**: `site=electronics`, `tagged=kicad`.
- **Cutoff**: `fromdate=1735689600` (2025-01-01). Training frontier 2012-04.
- **Recent yield**: 49 questions since 2025-01-01. With `answer_count>0`
  filtering, expect ~30–40 usable → meets ≥25. If short, widen with
  tags `pcb-design`, `eda` or drop `fromdate` to 2023-01-01 (still post-2012).
- **Mapping**: standard SE mapping above.

### emc — Stack Exchange (temporal cut) ✅

- **Source**: `electronics.stackexchange.com` via API.
- **Site / tag**: `site=electronics`, `tagged=emc`.
- **Cutoff**: `fromdate=1735689600`. Training frontier 2012-02.
- **Recent yield**: 81 questions since 2025-01-01 → comfortably ≥25.
- **Mapping**: standard SE mapping.

### power — Stack Exchange (temporal cut) ✅

- **Source**: `electronics.stackexchange.com` via API.
- **Site / tag**: `site=electronics`, `tagged=power-supply` (the `power`
  domain in training mapped to electronics power-electronics Q&A).
- **Cutoff**: `fromdate=1735689600`. Training frontier 2012-01.
- **Recent yield**: 471 questions since 2025-01-01 → highest-yield domain.
  Optionally also `tagged=dc-dc-converter`, `power-electronics`, `battery`.
- **Mapping**: standard SE mapping.

### dsp — Stack Exchange (temporal cut) ✅ — note site choice

- **Source**: Stack Exchange via API.
- **Site / tag**: training rows were attributed against `site=electronics`
  (the audit only searched the Electronics site). For held-out mining,
  **`site=dsp` (dsp.stackexchange.com)** is the right topical site and is a
  *different* SE site from the one the training audit searched — so it is
  doubly unseen. Use `site=dsp`, `tagged=fft` ∪ `filters` ∪ `audio`.
- **Cutoff**: `fromdate=1735689600`. Training frontier 2012-04 (electronics).
- **Recent yield**: dsp.SE since 2025-01-01: `fft` 68, `filters` 68,
  `audio` 25 → union easily ≥25 after dedup.
- **Mapping**: standard SE mapping, `site=dsp`.

### spice — alternative source (Masala-CHAI), NO temporal cut ⚠️

- **Training provenance** (README): derived from the **Masala-CHAI** dataset
  (`github.com/jitendra-bhandari/Masala-CHAI`, arXiv:2411.14299, CC-BY-4.0),
  itself textbook-derived + light LLM augmentation. **No Stack Exchange,
  no timestamps.** A temporal cut is impossible.
- **Held-out plan**: do NOT reuse Masala-CHAI (it IS the training source).
  Two options for `mine_upstream.py`:
  1. **Preferred** — mine `electronics.stackexchange.com` `tagged=spice`
     ∪ `ltspice` ∪ `ngspice`, `fromdate=2025-01-01`. This is a *different
     upstream* than the training source, so it is unseen by construction
     (not by date). Real SPICE-netlist questions exist there.
  2. **Fallback** — hand-curate ≥25 netlist tasks (write a netlist for X;
     debug this convergence error), flagged `source: "hand-curated"`.
- **Recommendation**: option 1, with option 2 to top up if SE yield < 25.
- **Status**: needs a yield probe in implementation (spice/ltspice tag
  counts not measured in this spike).

### stm32 — alternative source, NO temporal cut ⚠️

- **Training provenance** (README): **100 % LLM-generated** in the
  electron-rare pipeline. No external dataset, no scraping, no timestamps.
- **Held-out plan**: mine `electronics.stackexchange.com` `tagged=stm32`
  (227 questions since 2025-01-01 — ample), `fromdate=2025-01-01`. SE is a
  *different upstream* than the synthetic training data → unseen by source,
  not by date. Optionally also the `stm32` tag on Arduino.SE.
- **Mapping**: standard SE mapping, `site=electronics`.
- **Status**: usable; yield (227) verified.

### embedded — alternative source, NO temporal cut ⚠️

- **Training provenance** (README family pattern): LLM-generated /
  pipeline-internal. No timestamped upstream.
- **Held-out plan**: mine `electronics.stackexchange.com`,
  `tagged=microcontroller` (277 since 2025-01-01) ∪ `embedded` (57) ∪
  `firmware` (8), `fromdate=2025-01-01`. Union ≥25 easily.
- **Mapping**: standard SE mapping, `site=electronics`.
- **Status**: usable; yield verified.

### platformio — alternative source, NO temporal cut ⚠️

- **Training provenance** (README): built from pre-curated HF datasets —
  `gavmac00/arduino-docs` (Apache-2.0), `gouthamsk/esp_idf_code` (MIT),
  `bshada/arduino.stackexchange.com` (CC-BY-SA-4.0),
  `bshada/electronics.stackexchange.com` (CC-BY-SA-4.0). The two `bshada/*`
  sources **are** SE dumps — so naive SE mining risks overlap. The
  `bshada/*` dumps have a frozen snapshot date (unknown here; HF card of
  those repos must be checked at implementation time).
- **Held-out plan**: mine `electronics.stackexchange.com` `tagged=esp32`
  (204 since 2025-01-01), `fromdate=2025-01-01`. Recent posts are very
  likely past the `bshada/*` snapshot, but **the leakage guard is load-
  bearing here** — it must run against the training JSONL, not against the
  `bshada` dumps. The `arduino`-SE `platformio` tag is too thin (4 posts).
- **Mapping**: standard SE mapping, `site=electronics`.
- **Status**: usable with caution; confirm `bshada/*` snapshot date when
  implementing, and lean on the leakage guard.

### freecad — alternative source, NO temporal cut ⚠️

- **Training provenance** (README): built from `redcathode/thingiverse-openscad`
  (CC-BY-SA-3.0) and `ThomasTheMaker/OpenSCAD` HF datasets. **No Stack
  Exchange, no timestamps.** Temporal cut impossible.
- **Held-out plan**: there is no FreeCAD-specific SE site. Candidate
  sources, in preference order:
  1. The **KiCad/FreeCAD-adjacent doc route is not applicable** (no Q&A
     corpus). Try `blender.stackexchange.com` / general — too off-domain.
  2. The **FreeCAD forum** (`forum.freecad.org`) has Python-scripting Q&A
     but no clean API and uncertain TOS — not recommended.
  3. **Fallback — hand-curate** ≥25 parametric-CAD tasks (write a FreeCAD
     Python script for an enclosure with X; an OpenSCAD module for Y),
     flagged `source: "hand-curated"`. The functional scorer can still run
     (does the script execute / produce valid geometry).
- **Recommendation**: **hand-curate, explicitly flagged**. freecad is the
  one domain with no clean fresh upstream. Its verdict will be marked
  *low-confidence* per the spec's "held-out insuffisant" rule unless ≥25
  curated items are authored.
- **Status**: ⚠️ no clean upstream — hand-curate fallback required.

### iot — alternative source, NO temporal cut ⚠️

- **Training provenance** (README): ~33 % from `acon96/Home-Assistant-Requests`
  (MIT), ~67 % LLM-generated (ESP32/BLE/MQTT/LoRaWAN). No timestamps.
- **Held-out plan**: mine `electronics.stackexchange.com` `tagged=esp32`
  (204) ∪ `iot` (15) ∪ `wifi`/`bluetooth-low-energy`, `fromdate=2025-01-01`.
  Note `esp32` overlaps the platformio domain's source — dedup across the
  two held-out sets, and the per-domain leakage guard handles training
  overlap. The `acon96/Home-Assistant-Requests` slice is not SE-derived,
  so SE mining cannot re-leak that part.
- **Mapping**: standard SE mapping, `site=electronics`.
- **Status**: usable; `esp32`/`iot` yields verified.

## Summary table

| Domain | Method | Site / source | Tag(s) | Cutoff | Recent yield (2025+) | Confidence |
|--------|--------|---------------|--------|--------|----------------------|-----------|
| kicad      | SE temporal cut | electronics.SE | `kicad` | 2025-01-01 | 49 | high |
| emc        | SE temporal cut | electronics.SE | `emc` | 2025-01-01 | 81 | high |
| power      | SE temporal cut | electronics.SE | `power-supply` | 2025-01-01 | 471 | high |
| dsp        | SE diff-site + cut | dsp.SE | `fft`,`filters`,`audio` | 2025-01-01 | 161 (union) | high |
| spice      | SE diff-source | electronics.SE | `spice`,`ltspice`,`ngspice` | 2025-01-01 | not probed | medium |
| stm32      | SE diff-source | electronics.SE | `stm32` | 2025-01-01 | 227 | medium |
| embedded   | SE diff-source | electronics.SE | `microcontroller`,`embedded`,`firmware` | 2025-01-01 | 342 (union) | medium |
| platformio | SE diff-source | electronics.SE | `esp32` | 2025-01-01 | 204 | medium (leakage-sensitive) |
| freecad    | hand-curate | n/a — no clean upstream | n/a | n/a | 0 — author ≥25 | **low — flagged** |
| iot        | SE diff-source | electronics.SE | `esp32`,`iot` | 2025-01-01 | 219 (union) | medium |

"Confidence" reflects how strongly the held-out is guaranteed unseen:
**high** = both a different/older timestamp *and* upstream; **medium** =
unseen by upstream-source argument, leakage guard does the rest; **low** =
no clean upstream, hand-curated and explicitly flagged per spec §"garde".

## Open items for `mine_upstream.py` implementation

1. Get an SE API key (`~/.cache/stackexchange/api_key` per the existing
   `scrape_se_attribution.py`) — anonymous quota (~300/day) is too small for
   a 10-domain run with answer fetches.
2. Reuse `scripts/scraping_compliant/lib_compliance.py` for UA / preflight /
   backoff / audit trail.
3. Probe `spice`/`ltspice`/`ngspice` tag yields on electronics.SE before
   the run; if union < 25, trigger the hand-curate top-up.
4. Check the HF snapshot date of `bshada/electronics.stackexchange.com` and
   `bshada/arduino.stackexchange.com` to quantify the platformio overlap
   window.
5. Author the ≥25 hand-curated `freecad` items (and any `spice` top-up),
   each flagged `source: "hand-curated"` so the verdict aggregator can mark
   the domain *low-confidence*.
6. The leakage guard (composant 2) is mandatory for **all** domains, not
   just the 4 SE-temporal ones — for the 6 alternative-source domains it is
   the *primary* (not secondary) integrity mechanism.
