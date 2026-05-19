# Runbook — per-domain pages in ailiance-llm-domain

`scripts/build_domain_pages.py` best-effort creates one Grist page per
domain. Any domain it reports under "pages to create by hand" needs the
manual steps below — Grist's API cannot always create pages.

## Per domain (manual fallback)

In the Grist UI, open the `ailiance-llm-domain` document, then for each
domain listed by the script:

1. Add a new page named `Domain: <domain>` (e.g. `Domain: kicad`).
2. On that page, add a table widget for `Sourcing`.
3. Add a second table widget for `Dataset_Items`.
4. On each widget, add a filter: column `domain` equals `<domain>`.
5. Save.

## Checking orphans

If the script prints `orphan domains in data, not in DOMAINS`, a domain
appears in `Dataset_Items` that is not in the `DOMAINS` constant
(`mascarade_eval/__init__.py`). Decide per case: either add the domain
to `DOMAINS` (if legitimate) or correct the offending rows.
