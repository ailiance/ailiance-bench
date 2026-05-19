# Grist native review views — operator recipe

Manual Grist UI steps for the parts of the human-review layer that are
not API-scriptable. Run the schema migration first
(`python -m mascarade_eval.grist.cli schema`) so the review columns
exist.

## 1. review_status choice colors

For each table carrying `review_status` (`Heldout_Items`, `Datasets`
in doc *ailiance-llm-workflow*; `Mascarade_Eval_Items`,
`Bench_31_domains` in doc *mascarade-data*, plus `Mascarade_Training`):

1. Open the table, click the `review_status` column header → **Column
   options**.
2. Under **CHOICES**, confirm the four values are present: `pending`,
   `validated`, `rejected`, `needs_fix`.
3. Set the chip color of each: pending = grey `#E8E8E8`,
   validated = green `#C6E5B3`, rejected = red `#F2B5B5`,
   needs_fix = amber `#F5D9A6`.

## 2. Bench_31_domains review page (doc mascarade-data)

1. **Add Page** → name it `Bench review`.
2. Add a **Table** widget bound to `Bench_31_domains`.
3. Add a filter on `review_status` and a second on `domain`; save the
   view so the filters persist.
4. Conditional formatting (column header → **Column options** →
   **Add conditional style**):
   - `judge_score`: red when `$judge_score < 50`, amber when
     `$judge_score < 70`, green otherwise.
   - `validator_score`: red when `$validator_score < 50`, green when
     `$validator_score >= 70`.
   - `ppl`: red when `$ppl > 20`, amber when `$ppl > 10`.
5. Add a **Card List** widget on the same page bound to
   `Bench_31_domains`, linked to the table widget, showing `model`,
   `domain`, `judge_score`, `judge_rationale`, `validator_score`,
   `review_status`, `reviewer`, `review_note` — this is the per-row
   review surface.

## 3. Datasets review view (doc ailiance-llm-workflow)

1. **Add Page** → `Datasets review`.
2. Add a **Table** widget bound to `Datasets`, filtered on
   `review_status`.
3. Show `domain`, `name`, `n_rows`, `license`, `hf_dataset_id`,
   `review_status`, `reviewer`, `review_note`.

## 4. Read-only scoreboards

For `Bench_public`, `Bench_niches_ppl`, `Bench_gateway`,
`Bench_lift_v1`, `Bench_lift_v2`: add one page `Scoreboards` with a
Table widget per table. Apply conditional formatting on the score
columns (green high / red low) as in section 2. No review columns —
these tables are reference only.

## 5. Bench entry form (doc mascarade-data)

1. **Add Page** → `Bench entry`.
2. Add a **Form** widget bound to `Bench_31_domains`.
3. Keep only these fields on the form: `model`, `domain`, `ppl`,
   `task_score`, `task_metric`, `judge_score`, `source`, `date`.
   Remove pipeline-only fields (`validator_image_digest`, `run_id`,
   `host`, `runtime_s`, `tokens_per_s`, …).
4. Click **Publish** and copy the share URL — this is the manual
   bench-result entry form. Automated runs keep writing via the API.

## 6. Clean-up

Delete the empty default `Table1` (columns A/B/C) in each of the three
documents.
