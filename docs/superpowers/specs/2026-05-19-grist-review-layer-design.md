# Grist Human-Review Layer — Design

**Date:** 2026-05-19
**Status:** Approved (brainstorming)
**Scope:** Human verification UX inside `grist.saillant.cc` for the
ailiance / mascarade-eval datasets and benchmarks.

## Context

The Grist dataset-management project (see
`2026-05-19-grist-dataset-management-design.md`) makes Grist the
canonical source of truth: mining ingests insert-only, training and HF
publication consume a deterministic export.

This spec covers the **human-review layer** on top of that data: the
views, forms and validation workflow that let a human verify and
validate/reject rows *before* they are exported. It is a sibling
sub-project — it depends on the schema produced by the pipeline but
delivers the review UX, not the ingest/export plumbing.

### Live Grist state (inspected 2026-05-19)

Doc `ailiance-llm-workflow` (`eGbbrpzN3TeLq3sUd2YFA2`):

| Table | Rows | Role |
|---|---|---|
| `Heldout_Items` | 400 | eval items (prompt + reference) |
| `Datasets` | 29 | HF dataset catalog |
| `Models` | 23 | model registry |
| `TrainingRuns` | 150 | training run log |
| `Adapters` | 31 | LoRA adapter catalog |
| `Benchmarks` | 17 | aggregated benchmark results |

Doc `mascarade-data` (`dhyrySCayizD1PNqCNhCPN`):

| Table | Rows | Role |
|---|---|---|
| `Bench_31_domains` | 124 | iact-bench results (judge + validator) |
| `Mascarade_Eval_Items` | 162 | per-item eval (base vs LoRA) |
| `Mascarade_Eval` | 5 | eval run summary |
| `Bench_public` | 12 | public scoreboard |
| `Bench_niches_ppl` | 8 | perplexity per niche |
| `Bench_gateway` | 11 | gateway routing latency |
| `Bench_lift_v1` / `Bench_lift_v2` | 30 / 18 | LoRA lift before/after |

Doc `f4l-workflow` — Factory 4 Life client/deliverable workflow,
**out of scope**. Each doc carries an empty default `Table1` (A,B,C) —
to be deleted.

## Table classification

**Validation targets** — receive the review columns and a review
surface: `Heldout_Items`, `Datasets`, `Mascarade_Eval_Items`,
`Bench_31_domains`, and the future `Mascarade_Training`.

**Reference / monitoring** — read-only, conditional formatting only:
`Models`, `Adapters`, `TrainingRuns`, `Benchmarks`, `Bench_public`,
`Bench_niches_ppl`, `Bench_gateway`, `Bench_lift_v1`, `Bench_lift_v2`.

## Architecture

The review layer has three pieces, built **hybrid**: a custom widget
for high-volume item review, native Grist views for the benchmarks,
and a schema migration shared by both.

```
   Grist API (schema)            Grist UI (config)
        |                              |
   review columns           pages / views / forms /
   on 5 tables              conditional formatting
        |                              |
        +-------------+----------------+
                      |
        +-------------+----------------+
        |                              |
  Review Console widget          Native review views
  (Heldout_Items,                (Bench_31_domains,
   Mascarade_Training,            Datasets,
   Mascarade_Eval_Items)          read-only scoreboards)
        |                              |
        +-------------+----------------+
                      |
              review_status column
                      |
              export.py snapshot gate
              (only `validated` ships to HF)
```

### 1. Schema — review columns

Four columns added to each validation-target table by an idempotent
script using the Grist API (`POST /docs/{id}/tables/{t}/columns`):

| Column | Grist type | Notes |
|---|---|---|
| `review_status` | Choice | `pending` / `validated` / `rejected` / `needs_fix`; default `pending` |
| `reviewer` | Choice | who decided; seeded with the operator handle |
| `reviewed_at` | DateTime | set automatically when status leaves `pending` |
| `review_note` | Text | rationale; expected for `rejected` / `needs_fix` |

Conditional formatting on `review_status`: grey = pending,
green = validated, red = rejected, amber = needs_fix.

The script is idempotent: a column already present is skipped, never
recreated. It targets both Grist documents.

### 2. Review Console widget (dataset items)

A small static HTML/JS app (vanilla JS + `grist-plugin-api.js`),
**table-agnostic** via Grist column-mapping. The user maps, per page,
which columns feed the "primary" and "secondary" content panels; the
widget always writes the four review columns.

UX:

- One card at a time: primary text (e.g. `prompt`) and secondary text
  (e.g. `reference`) shown in full, plus a few context fields
  (`domain`, `source`).
- Buttons **✓ Validate / ✗ Reject / → Skip**; keyboard shortcuts
  `V` / `R` / arrow.
- A `review_note` text field; progress counter (`137 / 400`).
- On a decision: write `review_status`, `reviewer`, `reviewed_at`,
  `review_note`; advance to the next `pending` row.

Hosting: a static file on electron-server behind the existing
cloudflared tunnel (e.g. `grist-widgets.saillant.cc/review-console`),
registered in Grist as a "Custom URL" widget with full document
access.

The same widget serves `Heldout_Items`, the future
`Mascarade_Training`, and `Mascarade_Eval_Items`.

### 3. Native bench views + form

- **Views**: Grist pages for `Bench_31_domains` with views filtered by
  domain/model, conditional formatting on `judge_score`,
  `validator_score`, `ppl` (green/amber/red thresholds), and a summary
  table. `Datasets` (29 rows of catalog metadata) gets a native
  conditional-formatted grid review view. Read-only scoreboards
  (`Bench_public`, `Bench_niches_ppl`, `Bench_gateway`,
  `Bench_lift_*`) get conditional-formatted grid pages.

`Mascarade_Eval_Items` is per-item review like `Heldout_Items`, so it
is served by the Review Console widget (section 2), not a native view.
- **Form**: a published Grist Form (shareable URL) to manually enter a
  benchmark result into `Bench_31_domains`, exposing the
  human-relevant subset (`model`, `domain`, `ppl`, `task_score`,
  `judge_score`, `source`, `notes`). Automated runs keep inserting via
  the API.

### 4. Review → export gate

The whole point of human verification: `export.py` (Task 5 of the
Phase 1 plan) **filters on `review_status`**. Only `validated` rows
enter the deterministic snapshot exported to HuggingFace;
`rejected` and `needs_fix` are excluded. A `--include-pending` flag
allows early snapshots before review is complete.

This **amends the Phase 1 spec**: the planned boolean `exclure` column
is replaced by `review_status`. Affected:

- `mascarade_eval/grist/__init__.py` (Task 1, already shipped) — the
  `exclure` entry in `TRAINING_COLUMNS` becomes the four review
  columns.
- Tasks 4 (ingest) and 5 (export) — not yet implemented — consume
  `review_status` instead of `exclure`.

## Components & repository layout

In repo `ailiance-bench`:

- `mascarade_eval/grist/schema.py` — idempotent review-column
  migration, with unit tests against a fake transport.
- `widgets/review-console/` — the static widget (`index.html`, JS),
  no build step.
- `docs/superpowers/specs/.../grist-views-recipe.md` — step-by-step
  Grist UI recipe for pages, views, forms and conditional formatting
  (Grist pages/views are not cleanly API-creatable, so this is a
  documented manual procedure).

## Delivery — three lots

- **Lot A** — schema migration + conditional formatting + native bench
  views. Delivers value on day one: native review is usable
  immediately.
- **Lot B** — Review Console widget + hosting + Grist page wiring.
- **Lot C** — bench Form + export gating (`export.py` reads
  `review_status`).

## Testing

- `schema.py` — unit tests with an injected fake transport: idempotency
  (existing column skipped), correct column types, both documents
  targeted.
- Review Console widget — manual smoke test against a Grist scratch
  page: card navigation, write-back of the four columns, keyboard
  shortcuts, progress counter.
- Export gate — unit test that `export.py` excludes non-`validated`
  rows and that `--include-pending` re-includes `pending`.

## Risks

1. **Custom widgets** — self-hosted Grist must allow "Custom URL"
   widgets and the user must grant the widget full document access.
   Mitigation: verify Grist config before Lot B; the widget degrades
   to read-only if access is not granted.
2. **Views not scriptable** — Grist pages/views/forms cannot be
   created reliably via the REST API. Mitigation: ship a documented UI
   recipe rather than a script; only the schema is automated.
3. **Spec amendment** — replacing `exclure` with `review_status`
   touches already-shipped Task 1 constants. Mitigation: amend before
   Tasks 4/5 are implemented (only Task 1 is done).

## Out of scope

- The ingest/export pipeline itself (covered by the Phase 1 spec).
- The `f4l-workflow` document.
- The iact-bench audit document (Phase 3 of the parent project).
- Multi-tenant review or per-row access control.
