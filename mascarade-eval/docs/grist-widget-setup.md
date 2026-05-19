# Review Console widget — hosting, wiring, smoke test

The widget at `widgets/review-console/index.html` is a static file. It
must be served over HTTPS and registered in Grist as a Custom URL
widget.

## 1. Host the static file

Serve the file behind the existing electron-server cloudflared tunnel.

```bash
# from the repo, on the dev machine
scp widgets/review-console/index.html \
    electron-server:/srv/grist-widgets/review-console/index.html
```

On electron-server, expose `/srv/grist-widgets/` via the existing
static file server / Caddy / nginx and add a cloudflared route so the
file is reachable at:

```
https://grist-widgets.saillant.cc/review-console/index.html
```

Verify: `curl -sI https://grist-widgets.saillant.cc/review-console/index.html`
should return `HTTP/2 200`.

> Hosting touches shared infra (cloudflared, electron-server) — confirm
> with the operator before applying the route.

## 2. Add a review page in Grist

In doc *ailiance-llm-workflow*:

1. **Add Page** → `Heldout review`.
2. Add a **Custom** widget. Select **Custom URL** and paste
   `https://grist-widgets.saillant.cc/review-console/index.html`.
3. Bind the widget to the `Heldout_Items` table.
4. When prompted, grant the widget **Full document access** (it must
   write the review columns).
5. Open the widget's **Column mapping**:
   - `primary` → `prompt`
   - `secondary` → `reference`
   - `context` → `domain`, `source`

Repeat for the future `Mascarade_Training` table (map `primary` →
`user_msg`, `secondary` → `assistant_msg`) and for
`Mascarade_Eval_Items` in doc *mascarade-data* (map `primary` →
`question`, `secondary` → `reference`).

## 3. Smoke-test checklist

On the `Heldout review` page:

- [ ] The progress line shows `revus 0 / 400 — en attente 400`.
- [ ] The first pending item's prompt and reference render in full.
- [ ] Pressing `V` writes `review_status = validated`, `reviewer`,
      `reviewed_at` (ISO-8601) and advances to the next item; the
      progress counter increments.
- [ ] Pressing `R` and `F` write `rejected` / `needs_fix`.
- [ ] A value typed in the note field lands in `review_note` and the
      field clears after the decision.
- [ ] `S` / `→` skips without writing.
- [ ] After every pending row is decided, the widget shows
      "Tous les items en attente sont revus ✓".
- [ ] Re-running `python -m mascarade_eval.grist.cli export --domain
      <d>` ships only the rows marked `validated`.
