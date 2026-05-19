# Review Console widget — hosting, wiring, smoke test

The widget at `widgets/review-console/index.html` is a static file. It
must be served over HTTPS and registered in Grist as a Custom URL
widget.

## 1. Hosting

The widget is served by a dedicated `review-widget` nginx container in
`/home/electron/saillant-sites/` on electron-server, exposed through
traefik on the existing `admin.ailiance.fr` hostname under `/review`
(a `Host && PathPrefix` router — no new cloudflared hostname needed).

Compose service (`saillant-sites/docker-compose.yml`):

```yaml
  review-widget:
    image: nginx:alpine
    container_name: review-widget
    restart: unless-stopped
    networks: [traefik]
    labels:
      - traefik.enable=true
      - traefik.docker.network=traefik
      - traefik.http.routers.review-admin.rule=Host(`admin.ailiance.fr`) && PathPrefix(`/review`)
      - traefik.http.routers.review-admin.entrypoints=websecure
      - traefik.http.routers.review-admin.tls.certresolver=letsencrypt
      - traefik.http.routers.review-admin.service=review-widget
      - traefik.http.services.review-widget.loadbalancer.server.port=80
    volumes:
      - ./train-static:/usr/share/nginx/html:ro
```

The widget file lives at `saillant-sites/train-static/review/index.html`.
Redeploy after editing the widget (nginx serves the mount live, no
restart):

```bash
scp widgets/review-console/index.html \
    electron-server:/home/electron/saillant-sites/train-static/review/index.html
```

Live URL (verified `HTTP 200`): `https://admin.ailiance.fr/review/`

## 2. Add a review page in Grist

In doc *ailiance-llm-workflow*:

1. **Add Page** → `Heldout review`.
2. Add a **Custom** widget. Select **Custom URL** and paste
   `https://admin.ailiance.fr/review/`.
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
