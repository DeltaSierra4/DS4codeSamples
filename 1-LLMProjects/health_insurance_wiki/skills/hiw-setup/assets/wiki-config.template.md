# Wiki configuration

Wiki-level settings, written once by `/hiw-setup` and read by every other skill. Flat
`key: value` lines only — no nesting, no YAML front matter, no lists beyond the inline
`[a, b]` form. Every consumer parses this file line by line with no third-party library,
so a nested structure here silently reads as nothing.

Edit by hand freely. No skill rewrites a value you have set; `/hiw-setup` re-run only adds
keys that are entirely absent.

```
wiki_name: {{WIKI_NAME}}
wiki_root: {{WIKI_ROOT}}
plan_year: {{PLAN_YEAR}}
currency: {{CURRENCY}}
geography: {{GEOGRAPHY}}
markets: {{MARKETS}}
created: {{CREATED}}
created_by: hiw-setup
schema_version: 1
```

## What each key controls

| Key | Read by | Effect |
|---|---|---|
| `wiki_name` | `/hiw-list-plan`, `/hiw-compare` | title on every generated HTML deliverable |
| `wiki_root` | all | recorded for provenance only; the skills locate the wiki by finding `SCHEMA.md`, not by trusting this value |
| `plan_year` | `/hiw-ingest`, `/hiw-refresh`, `/hiw-lint` | the default year a source is assumed to describe when it does not say, and the year `/hiw-lint` treats as current. A source that states its own year always wins over this default |
| `currency` | `/hiw-ingest`, `/hiw-compare` | every money field in the wiki is in this currency. A source quoting another currency is converted at ingest with the rate recorded as an `[assumption: ...]`, or the field is `TBD` — never mixed. See `SCHEMA.md` § 6.3 |
| `geography` | `/hiw-query` | the default service area when the user does not state one; also what `/hiw-lint` checks `states:` against for plausibility |
| `markets` | `/hiw-query`, `/hiw-list-plan` | which of the `market` values in `SCHEMA.md` § 2.2 this wiki intends to track. A plan outside this list is still stored and still compared — the list narrows defaults, it never filters knowledge |
| `schema_version` | `/hiw-lint` | the revision of `SCHEMA.md` this wiki was scaffolded against. A mismatch is reported, never auto-migrated |

## Optional keys

Absent by default. Add a line to change the behaviour.

| Key | Default | Effect |
|---|---|---|
| `stale_days` | `120` | how long a plan page may go without an update before `/hiw-lint` reports it stale. Health plans re-rate annually, so the default is deliberately long — a 30-day threshold would flag the entire wiki every quarter and train you to ignore the report |
| `lint_keep` | `5` | how many dated lint reports to retain in `output/` |
| `cost_model_pcp_visits` | `2` | primary-care visits assumed in the `/hiw-compare` low-utilization scenario |
| `cost_model_specialist_visits` | `4` | specialist visits assumed in the moderate scenario |
| `cost_model_rx_months` | `12` | months of tier-1 generic assumed in the low and moderate scenarios |

The three `cost_model_*` keys are the only place the comparison scenarios can be tuned.
They exist because a scenario is an assumption, and an assumption a reader cannot see or
change is indistinguishable from a fabricated number. `/hiw-compare` prints all three on
every deliverable it produces, whether or not you have overridden them.
