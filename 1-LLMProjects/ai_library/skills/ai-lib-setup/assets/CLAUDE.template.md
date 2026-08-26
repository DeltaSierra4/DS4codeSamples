# {{LIBRARY_NAME}}

A document library for an Agentic RAG system. PDFs and text files — mostly blog posts and
announcements, some papers — read once, recorded as attributed claims, and read back by
skills that list, query and compare them.

## Read these first

| File | What it gives you |
|---|---|
| `AGENTS.md` | how to retrieve from and write to this library — the operating contract |
| `SCHEMA.md` | the page contract — frontmatter keys, allowed values, required sections, provenance markers |
| `_config/taxonomy.md` | which topics exist and what belongs in each |
| `index.md` | every document in the library, grouped by topic |

`AGENTS.md`, `SCHEMA.md` and `_config/taxonomy.md` are the authority. This file is a
pointer plus the current state summary below; it deliberately does not restate their rules,
because a summary that drifts from the contract is worse than no summary.

## The one rule worth stating twice

**Every claim carries a marker.** `[p. N]` means this document says it on that page.
`[link: url, accessed date]` means a page it linked to says it, and may only appear in
`## From Linked Pages`. `[inference: ...]` means you concluded it. An unmarked claim is
indistinguishable from a traceable one, and the whole library is worthless the moment one
exists.

## Library settings

- **Owner:** {{OWNER}}
- **Created:** {{CREATED}}
- **Topics:** 5 top-level, 14 leaves — see `_config/taxonomy.md`
- **Link following:** depth 1, authorized by link plan, audited by `/ai-lib-lint`

## Skills

| Command | Use it to |
|---|---|
| `/ai-lib-setup` | scaffold a library (already run for this one) |
| `/ai-lib-ingest` | add a PDF or text file, following its links one hop |
| `/ai-lib-refresh` | re-check stored sources, find newer versions, mark dead links |
| `/ai-lib-list` | build a browsable HTML catalog of the whole library |
| `/ai-lib-query` | ask the library a question and get an attributed answer |
| `/ai-lib-compare` | put two or more documents side by side, benchmarks joined |
| `/ai-lib-lint` | health-check the library and regenerate `index.md` |

Run `/ai-lib-lint` after every handful of ingests, and before relying on any answer.

## Library Brief

<!-- library-brief-start -->
_No Library Brief yet. Run `/ai-lib-lint` after your first ingest to populate this section._
<!-- library-brief-end -->

## Standing caveat

This library records what a collection of documents says. A document being here implies
nothing about whether it is correct — a first-party announcement is a marketing artifact
as well as a technical one, a preprint has not been reviewed, and a blog post may have been
edited since it was captured. Every answer built from this library names the kind of source
it rests on, and flags an answer resting on a single document, on sources that are all
first-party, or on a page whose publication date has gone stale.
