# Scraping Compliance — EU AI Act + DSM Directive

**Owner**: Ailiance-fr / Electron Rare
**Contact**: c.saillant@gmail.com
**Last updated**: 2026-05-11
**Scope**: every dataset under `electron-rare/mascarade-*` and `Ailiance-fr/mascarade-*`, plus the KiCad 9+ corpus and any future scrape that feeds an Ailiance training pipeline.

This document explains what we collect, why we are legally allowed to collect it, and how the pipeline enforces machine-readable opt-out signals at fetch time.

---

## 1. Legal basis

| Source | Article / Section | What it says | What we do |
|---|---|---|---|
| **DSM Directive 2019/790** | Art. 4(3) | Right-holders may reserve TDM rights via "machine-readable means" (robots.txt, TDMRep, HTML meta). | We probe robots.txt and TDMRep before every HTTP GET. |
| **EU AI Act (Regulation 2024/1689)** | Art. 53(1)(c) | GPAI providers must adopt a policy to comply with EU copyright law, including Art. 4(3) DSM. | This very document is that policy, persisted in-repo. |
| **GPAI Code of Practice (July 2025)** | Chapter 2.1 (Copyright) | Signatories commit to respect TDM reservations expressed by robots.txt, TDMRep, and equivalents. | We follow the Code, with an auditable JSONL trail. |
| **RFC TDM-AI (2024, IETF I-D)** | TDM-Reservation HTTP header / `/.well-known/tdmrep.json` | Defines the machine-readable opt-out format. | Both the header and well-known are checked. |

References:
- <https://eur-lex.europa.eu/eli/dir/2019/790/oj> (DSM)
- <https://eur-lex.europa.eu/eli/reg/2024/1689/oj> (AI Act)
- <https://digital-strategy.ec.europa.eu/en/policies/ai-code-practice> (Code of Practice)
- <https://www.w3.org/community/tdmrep/> (TDMRep spec)

---

## 2. Our policy in 8 points

1. **Identifiable, contactable User-Agent.** Every HTTP request carries
   `Ailiance-Compliance-Crawler/1.0 (+https://huggingface.co/Ailiance-fr; contact: c.saillant@gmail.com; EU AI Act compliance audit)`.
   We never spoof a browser.

2. **robots.txt is checked before every GET.** `lib_compliance.check_robots_txt(url)` parses the host's `robots.txt` and only returns `allowed=True` if both our explicit UA and `*` are permitted.

3. **TDMRep signals are honored.** `lib_compliance.check_tdmrep(url)` queries `/.well-known/tdmrep.json` and the `TDM-Reservation` HTTP header. A `tdm-reservation: 1` value blocks the fetch.

4. **HTML `noai` / `noimageai` meta tags are honored.** `lib_compliance.check_noai_meta(html)` blocks downstream extraction when a page carries `<meta name="robots" content="noai">` or equivalents.

5. **Rate-limit headers are honored.** `lib_compliance.compliant_get` reads `Retry-After` on HTTP 429 and sleeps before retrying. Stack Exchange's `backoff` JSON field is also honored.

6. **Per-sample provenance is persisted.** Every retained sample carries a `compliance` block with: source URL, license SPDX at fetch time, git commit SHA when relevant, fetch timestamp (UTC ISO 8601), User-Agent string, robots.txt verdict, and TDMRep status.

7. **JSONL audit trail.** Every preflight check appends one line to
   `~/eu-kiki-data/scraping_logs/<timestamp>.jsonl`. The trail is the proof
   we ran the checks; it is preserved with the corpus.

8. **Idempotent local cache.** We never re-fetch a file whose `.meta.json`
   already records a successful fetch. This minimizes bandwidth load on the
   sources we depend on.

---

## 3. Allowed sources and rejection rules

| Source | Access method | License gate | Notes |
|---|---|---|---|
| **GitHub repositories** | `git clone` + GitHub REST API (`gh api`). | SPDX must match: MIT, Apache-2.0, BSD-2/3, MPL-2.0, CC0-1.0, Unlicense, CC-BY-4.0, CC-BY-SA-4.0, CERN-OHL-*, GPL-2.0/3.0, LGPL-2.1/3.0. | `UNKNOWN`, `null`, or proprietary licenses are skipped at clone time. |
| **`raw.githubusercontent.com`** | HTTPS GET with our UA. | Same SPDX gate via parent repo. | robots.txt currently allows; if a host adopts TDMRep, we will honor it. |
| **Stack Exchange (Electronics)** | Official API `api.stackexchange.com/2.3` with our `key`. | Content is CC-BY-SA-4.0 by SE Terms of Service. | We respect `backoff` and quota; never scrape HTML pages. |
| **Hugging Face datasets** | `huggingface_hub.snapshot_download` (authenticated). | Each upstream dataset must declare a permissive or share-alike license (Apache-2.0, MIT, CC-BY, CC-BY-SA, CC0). | We never republish without preserving the original license tag. |
| **Local (`grosmac.local`)** | rsync over SSH. | Owner-controlled; flagged `internal-use-only`. | Excluded from any public dataset by default. |

Sources NOT used:
- No anonymous web scraping of editorial websites, blogs, forums, or social media.
- No headless-browser bypass of paywalls or anti-bot mitigations.
- No downloading of content marked `noai` / `noimageai` / `noml` even if technically reachable.

---

## 4. Pipeline modules

All compliance-critical code lives under `scripts/scraping_compliant/`.

| File | Role |
|---|---|
| [`lib_compliance.py`](../scripts/scraping_compliant/lib_compliance.py) | `check_robots_txt`, `check_noai_meta`, `check_tdmrep`, `compliant_get`, `log_compliance_check`, `preflight`. |
| [`scrape_kicad9plus.py`](../scripts/scraping_compliant/scrape_kicad9plus.py) | KiCad 9+ corpus orchestrator. Defaults to `--dry-run`. `--enrich-meta` backfills compliance blocks into existing `.meta.json`. `--execute` delegates to `kicad9plus_phase2_download.sh` after preflight passes. |
| [`scrape_se_attribution.py`](../scripts/scraping_compliant/scrape_se_attribution.py) | Stack Exchange attribution orchestrator. Wraps `~/scripts/se_attribution/audit_remaining.py`, re-stamps the UA, and logs every API call. |

### Sample `compliance` block (sidecar `.meta.json`)

```json
{
  "source_url": "https://github.com/KiCad/kicad-source-mirror/blob/<sha>/demos/foo.kicad_sch",
  "license_spdx": "GPL-3.0",
  "commit_sha": "<sha>",
  "downloaded_at": "2026-05-11T20:30:00Z",
  "compliance": {
    "robots_txt": {"allowed": true, "reason": "robots.txt allow ..."},
    "tdmrep": {"status": "no_tdmrep", "policy": null},
    "noai_meta_html": false,
    "user_agent_used": "Ailiance-Compliance-Crawler/1.0 (+https://huggingface.co/Ailiance-fr; contact: c.saillant@gmail.com; EU AI Act compliance audit)",
    "fetched_at": "2026-05-11T20:30:00Z",
    "license_spdx_at_fetch": "GPL-3.0",
    "audit_basis": [
      "DSM Directive 2019/790 Art. 4(3)",
      "EU AI Act Art. 53(1)(c)",
      "GPAI Code of Practice (2025) Ch. 2.1"
    ]
  }
}
```

---

## 5. Audit trail

Every preflight produces one JSONL line in
`~/eu-kiki-data/scraping_logs/<timestamp>.jsonl`:

```json
{
  "ts": "2026-05-11T20:30:00Z",
  "url": "https://raw.githubusercontent.com/.../foo.kicad_sch",
  "allowed": true,
  "robots_txt": {"allowed": true, "reason": "..."},
  "tdmrep": {"status": "no_tdmrep", "policy": null},
  "user_agent": "Ailiance-Compliance-Crawler/1.0 ..."
}
```

These logs are not pushed to GitHub (they may contain ephemeral URLs); they are retained locally as the audit basis for any future regulatory inquiry.

---

## 6. Handling opt-out signals after collection

If, after a sample is in our corpus, the upstream host adopts an opt-out
(robots disallow / TDMRep reservation / license change to proprietary),
we apply the following protocol:

1. The sample is **flagged** (`compliance.opt_out_observed_at`).
2. The sample is **removed** from the next dataset revision pushed to the
   Hugging Face Hub.
3. The audit trail records the removal so re-introduction is impossible.

This honors the DSM Directive's continuing-effect principle for TDM
reservations.

---

## 7. How to run the compliance pipeline

```bash
# 1. Smoke test the library
python3 ~/scripts/scraping_compliant/lib_compliance.py

# 2. Backfill compliance blocks into existing KiCad 9+ sidecars
python3 ~/scripts/scraping_compliant/scrape_kicad9plus.py \
    --enrich-meta ~/ailiance-data/kicad9plus-corpus/sources

# 3. Preflight-only check for the Stack Exchange API
python3 ~/scripts/scraping_compliant/scrape_se_attribution.py --check-only

# 4. Audit a dataset with logged SE API calls
python3 ~/scripts/scraping_compliant/scrape_se_attribution.py \
    --dataset emc \
    --api-key "$(cat ~/.cache/stackexchange/api_key)"
```

---

## 8. Change log

- **2026-05-11** — Initial version. Pipeline split out of ad-hoc shell
  scripts; documented under `docs/scraping_compliance.md`.
