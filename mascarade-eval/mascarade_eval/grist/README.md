# mascarade_eval.grist — Grist-backed dataset management

Grist is the canonical source of truth for the mascarade training corpus.
Mining ingests in insert-only mode (edits made in Grist are never
overwritten); training and HF publication consume a deterministic export.

## One-time setup

1. Create an empty Grist doc "Mascarade Training" at grist.saillant.cc.
2. Add `GRIST_DOC_TRAINING=<doc-id>` to `~/.config/electron-rare/grist.env`
   (the file already holds `GRIST_API_KEY`).

## Commands

Run with `uv run python -m mascarade_eval.grist.cli <subcommand>`.

- `migrate --domain kicad` — backfill a domain's HF training data into
  Grist (insert-only). Run once per domain to seed the doc.
- `ingest --domain kicad --jsonl mine.jsonl` — insert-only ingest of a
  new mining/curation file. Existing rows are never touched.
- `export --domain kicad` — write a hashed `.jsonl` snapshot to
  `exports/` and log a row in the `Exports` table.
- `publish --snapshot exports/kicad.<ts>.jsonl --hf-dataset
  Ailiance-fr/mascarade-kicad-dataset --filename kicad_chat.jsonl` —
  upload a snapshot to its HF dataset repo.

Add `--dry-run` to `ingest`, `export`, or `migrate` to preview without
writing to Grist or disk.

## Human review

Edit rows directly in the Grist UI. Each row carries a `review_status`
(`pending` / `validated` / `rejected` / `needs_fix`); `export` ships only
`validated` rows. Pass `--include-pending` to `export` to also include
rows still awaiting review. See `docs/grist-native-views-recipe.md` and
`docs/grist-widget-setup.md` for the review surfaces.
