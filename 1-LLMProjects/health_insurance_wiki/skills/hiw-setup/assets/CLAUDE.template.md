# {{WIKI_NAME}}

{{WIKI_PURPOSE}}

A health-insurance knowledge base for an Agentic RAG system. Facts about carriers and their plans
are stored here once, sourced, and read back by skills that list, query, and compare them.

## Read these first

| File | What it gives you |
|---|---|
| `AGENTS.md` | how to retrieve from and write to this wiki — the operating contract |
| `SCHEMA.md` | the page contract — frontmatter keys, allowed values, required sections |
| `index.md` | every plan in the wiki, grouped by company |
| `_config/wiki-config.md` | currency, plan year, geography, defaults |

`AGENTS.md` and `SCHEMA.md` are the authority. This file is a pointer plus the current state
summary below; it deliberately does not restate their rules, because a summary that drifts from the
contract is worse than no summary.

## Wiki settings

- **Plan year:** {{PLAN_YEAR}}
- **Currency:** {{CURRENCY}}
- **Geography:** {{GEOGRAPHY}}
- **Markets tracked:** {{MARKETS}}

## Skills

| Command | Use it to |
|---|---|
| `/hiw-setup` | scaffold a wiki (already run for this one) |
| `/hiw-ingest` | add a carrier's plans from files or a URL |
| `/hiw-refresh` | re-fetch previously ingested sources and diff against stored plans |
| `/hiw-list-plan` | build a browsable HTML catalog of every plan |
| `/hiw-query` | get a recommendation through an interactive needs assessment |
| `/hiw-compare` | build a side-by-side comparison of two or more plans |
| `/hiw-lint` | health-check the wiki and regenerate `index.md` |

Run `/hiw-lint` after every handful of ingests, and before any comparison you intend to act on.

## Wiki Brief

<!-- wiki-brief-start -->
_No Wiki Brief yet. Run `/hiw-lint` after your first ingest to populate this section._
<!-- wiki-brief-end -->

## Standing caveat

This wiki records what published sources say. It is not advice, not a quote, and not an eligibility
determination. Stored premiums are list values for a stated basis and will differ from what a
specific person is offered. Coverage decisions rest on the carrier's official plan documents.
