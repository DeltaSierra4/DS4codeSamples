# Library configuration

Library-level settings, written once by `/ai-lib-setup` and read by every other skill.
Flat `key: value` lines only — no nesting, no YAML front matter, no lists beyond the
inline `[a, b]` form. Every consumer parses this file line by line with no third-party
library, so a nested structure here silently reads as nothing.

Edit by hand freely. No skill rewrites a value you have set; a `/ai-lib-setup` re-run only
adds keys that are entirely absent.

```
library_name: {{LIBRARY_NAME}}
library_root: {{LIBRARY_ROOT}}
owner: {{OWNER}}
created: {{CREATED}}
created_by: ai-lib-setup
schema_version: 1
```

## Expected topic shares

Reporting weights, not quotas. `/ai-lib-lint` compares actual document counts against
these and reports the drift; nothing refuses an ingest because a topic is over its share.
They are a guess about what you will read, and where reality disagrees, reality is right —
the useful signal is a topic sitting near zero, which usually means you have been filing
its material somewhere else.

```
share_ai: 0.35
share_llm: 0.35
share_data_science: 0.15
share_math_sci_tech_cyber: 0.10
share_misc: 0.05
drift_report_threshold: 0.15
```

`drift_report_threshold` is the absolute difference at which drift gets mentioned in the
lint report. At `0.15`, a topic expected at 35% is reported once it falls below 20% or
rises above 50%.

## Staleness thresholds, in days

Set per topic because these literatures age at very different rates. Staleness is measured
from a document's `published` date, not from when you filed it — a two-year-old post
ingested yesterday is two years old.

```
stale_days_llm: 270
stale_days_ai: 540
stale_days_data_science: 1095
stale_days_cybersecurity: 365
stale_days_math_sci_tech: 1825
stale_days_misc: 1825
```

A stale page is a prompt to check whether something replaced it, never a defect and never
grounds for auto-superseding. Its one hard consequence is that `/ai-lib-query` must say so
when it answers from a stale page.

## Link following

The depth limit is **not** configurable. `depth: 1` is a contract term (`SCHEMA.md` § 6),
enforced by audit rather than by a flag, and a setting that could raise it would be a
setting that eventually gets raised.

```
max_links_per_document: 25
link_fetch_delay_seconds: 2
follow_domains_denied: [twitter.com, x.com, facebook.com, instagram.com, linkedin.com, reddit.com]
follow_domains_preferred: [arxiv.org, github.com, openreview.net, aclanthology.org, nature.com, acm.org, ieee.org]
```

| Key | Effect |
|---|---|
| `max_links_per_document` | cap on the authorized link plan. A 60-reference paper yields a plan of 25, prioritized by `follow_domains_preferred` then document order. The rest are recorded as declined-by-cap, so the cap is visible rather than silent |
| `link_fetch_delay_seconds` | pause between fetches. Fetch at a human pace |
| `follow_domains_denied` | never enters a link plan. Social domains are excluded because a link to a post is almost never the substance, and the pages are usually JS-only anyway |
| `follow_domains_preferred` | ranked first when the cap bites — not fetched preferentially in any other sense |

## Optional keys

Absent by default. Add a line to change the behaviour.

| Key | Default | Effect |
|---|---|---|
| `lint_keep` | `5` | how many dated lint reports to retain in `output/`. Advisory: nothing prunes them, since no skill in this family deletes anything |
| `min_claims_for_high_confidence` | `3` | below this many located claims, `/ai-lib-lint` questions an `extraction_confidence: high` |
| `max_doc_slug_length` | `60` | where `new-page.py` truncates a derived slug, at a word boundary |
| `query_fanout_threshold` | `2` | leaf topics in scope above which `/ai-lib-query` fans out rather than reading inline |
| `theme_min_documents` | `2` | `doc_id`s a `## Themes` bullet must cite. A theme supported by one document is that document's claim |
