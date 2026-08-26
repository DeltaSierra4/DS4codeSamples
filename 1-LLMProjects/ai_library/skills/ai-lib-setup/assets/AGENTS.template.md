# ai-lib — Operating Rules

The workspace contract for any agent session working in this library. Seeded by
`/ai-lib-setup` and never overwritten. It is deliberately agent-agnostic: no host-specific
tool names, no assumption that skills are invoked as slash commands, and no hard-coded
topic list — everything specific to this library is read at runtime from
`_config/taxonomy.md`, `_config/library-config.md` and `index.md`.

---

## 1. What this library is

A structured record of what a collection of PDFs and text files says, built to be read by
agents. It exists so that questions like *"what have I got on prompt injection, and do any
of these sources disagree?"* can be answered from stored, attributed claims rather than by
re-reading a folder of PDFs each time.

Most of it is blog posts and announcements, not papers. Plan for that: authorship is often
absent, recency matters more than it would in an academic corpus, and a first-party post
is simultaneously the best source on what was built and the worst source on how good it is.

Three invariants hold everywhere:

1. **The leaf topic folder is the unit of everything.** Ingest writes into one leaf. A
   subagent is assigned one leaf. A cross-topic query reads several leaves and writes into
   none of them. If you find a document's substance outside its own leaf, that is a defect.
2. **Every claim carries a marker.** `[p. N]` for the document, `[link: url, accessed date]`
   for a depth-1 linked page, `[inference: ...]` for your own conclusion, `[unlocated]`
   where the document says it but the page could not be pinned. An unmarked claim is the
   one thing this library may not contain — it is indistinguishable from a traceable one
   and destroys the only property that makes the library worth having.
3. **`doc_id` is the join key.** `<topic-path-hyphenated>__<doc-slug>`, double underscore.
   Answers, synthesis pages and comparison matrices cite documents by `doc_id`, never by
   title — titles collide constantly, and every model family has a "system card".

| To learn | Read | Written by |
|---|---|---|
| The page contract — frontmatter, sections, markers | `SCHEMA.md` | `/ai-lib-setup` (copied; never edit in place) |
| Which topics exist, and what belongs in each | `_config/taxonomy.md` | `/ai-lib-setup`, then deliberate human edits |
| What documents exist, and where | `index.md` | regenerated wholesale by `index-library.py`; never hand-edited |
| What has happened to this library | `log.md` | every skill, append-only |
| Shares, staleness thresholds, link caps | `_config/library-config.md` | `/ai-lib-setup` |

## 2. Folder map

| Path | Holds | Writes here | Exists once |
|---|---|---|---|
| `topics/<path>/topic.md` | topic overview, themes, document roster | `/ai-lib-ingest`, `/ai-lib-refresh`, `/ai-lib-lint` | `/ai-lib-setup` |
| `topics/<leaf>/documents/*.md` | one page per document — the knowledge | `/ai-lib-ingest`, `/ai-lib-refresh`, `/ai-lib-lint` | first ingest into that leaf |
| `topics/<leaf>/captures/*.md` | one receipt per depth-1 link followed | `/ai-lib-ingest`, `/ai-lib-refresh` | as above |
| `raw/<path>/` | immutable originals | `/ai-lib-ingest`, `/ai-lib-refresh` | as above |
| `synthesis/` | saved answers, reading lists, briefs | `/ai-lib-query`, `/ai-lib-compare` | `/ai-lib-setup` |
| `output/` | generated HTML, reports, link plans, intermediate json | every skill | `/ai-lib-setup` |
| `_config/` | taxonomy and settings | `/ai-lib-setup` | `/ai-lib-setup` |

### 2.1 Establish what exists before you rely on it

Five checks, each cheap, none requiring a file to be parsed:

- `SCHEMA.md` at the library root — the contract is available.
- `_config/taxonomy.md` — the topic tree is available. Without it you cannot place a document.
- `topics/` holding leaf folders with non-empty `documents/` — something has been ingested.
- `index.md` exists — a catalog is available. It may be stale; the tree is the truth.
- `_config/library-config.md` — the library was set up rather than assembled by hand.

When one is missing: say what you looked for, name the skill that owns it, offer the
degraded path **and label it as degraded**, do not block, and do not create the missing
thing yourself. An empty `topics/` is not an error — it is a library nobody has ingested
into yet, and the correct response is to say so and point at `/ai-lib-ingest`.

**Skills here are standalone.** Any of them can be the first thing that ever runs. They
recommend an order; none require one, and none block.

## 3. How to retrieve

The retrieval ladder. Stop at the layer that answers the question; each rung down costs
substantially more context than the one above it.

- **Layer 0** — `index.md`. Every document, its topic, type, authority, publication date, claim and benchmark counts. Most "what have I got on X" questions end here.
- **Layer 1** — `topics/<path>/topic.md`. What the leaf covers, its themes, its gaps, its document roster. The cheapest way to learn what a topic collectively says.
- **Layer 2** — document page frontmatter only (first ~45 lines). Type, authority, dates, counts, the graph edges. This is the layer `/ai-lib-compare` builds its matrices from.
- **Layer 3** — `## Snapshot` and `## Key Claims` on the relevant document pages. Attributed claims with locators. **This is the layer most questions are actually answered from.**
- **Layer 4** — full document page bodies: method, evidence, limitations, and `## From Linked Pages`.
- **Layer 5** — `topics/<leaf>/captures/*.md`, then `raw/`. Only when a claim is disputed or needs retracing to its origin.

**Fan out by leaf topic, never by file.** When a task spans **more than two leaf topics**,
assign one subagent per leaf — one agent per leaf, however many documents it holds. Never
one agent per document, and never a fixed number of agents dividing the list. Each returns
a structured result for its own leaf and reads no other leaf's pages. This is why the
layout is what it is: a per-leaf subagent has a naturally bounded context and cannot
contaminate one topic's material with another's.

**Two leaf topics or fewer, read inline.** Two subagents to read two folders costs more
than it saves. The threshold is deliberately the same number in every skill, so nobody has
to remember which one it was.

**Collect every subagent result before analyzing any of them.** Partial fan-out results
produce answers that silently omit a topic.

## 4. How to write

The page contract is `SCHEMA.md` at the library root. Read it before writing a page. It is
a copy — the master ships with `/ai-lib-setup` — so if it looks wrong, report the
divergence rather than editing this copy.

Standing rules, which the contract expands:

- **Every claim carries a marker** (`SCHEMA.md` § 7.1). No exceptions, in any section.
- **A claim is what the document asserts, not what is true.** Record a claim you think is wrong exactly as made, and put the disagreement in `## Open Questions` as an `[inference: ...]`.
- **Depth-1 linked material lives only in `## From Linked Pages`** and its capture page. Never in `## Key Claims`, never in `## Evidence`, never carrying a `[p. N]` locator. See `SCHEMA.md` § 6.3.
- **Never fetch a URL you found on a page you fetched.** Record it under the capture's `## Not taken` and stop. The route from depth 2 to depth 1 is to save that page and ingest it deliberately.
- **Never compute a number the document did not report**, and never carry a baseline across from another document.
- **The document's own names, verbatim** — benchmarks, metrics, methods, models. Every join in this library is a string match.
- **Cross-references are `doc_id`s or library-relative paths in backticks, never `[[wikilinks]]`.** Write them inline in the body, not only in frontmatter — orphan detection scans bodies.
- **Never delete a page.** A withdrawn or replaced document gets `status: superseded` and a `superseded_by`. A revised version of the same work updates `version` in place; a genuinely different work is a new page (`SCHEMA.md` § 8.1).
- **Ingest resolves, lint flags.** `/ai-lib-ingest` and `/ai-lib-refresh` apply the resolution policy (`SCHEMA.md` § 8.2) and log what they decided. `/ai-lib-lint` marks what could not be decided and never picks a winner.
- **`index.md` is regenerated, never edited.** It is derived from `topics/`, rebuilt by `index-library.py` on every lint run. Do not hand-edit it and do not patch it incrementally — a stale index is a normal condition; an index carrying a fact no page carries is the one state that makes regeneration destructive.
- **Literal Unicode in markdown**, never HTML entities.
- **Append to `log.md` on every operation.** One entry per run, `## [YYYY-MM-DD] <skill> | <detail>`. Subsection vocabulary is `SCHEMA.md` § 10.

### 4.1 Where output goes

Generated artifacts go to `output/`. Saved analysis — something a human will come back to —
goes to `synthesis/` as a markdown page with frontmatter. Nothing generated ever lands
inside a topic folder; topic folders hold attributed claims about documents and nothing
else.

## 5. The skills

| Skill | Produces |
|---|---|
| `/ai-lib-setup` | the library scaffold, `SCHEMA.md`, `_config/taxonomy.md`, `_config/library-config.md`, this file |
| `/ai-lib-ingest` | document pages, capture pages, `raw/` originals, authorized link plans |
| `/ai-lib-refresh` | re-checked sources, newer versions found, dead links marked, staleness triaged |
| `/ai-lib-list` | `output/library.html` — every document, browsable by topic |
| `/ai-lib-query` | an attributed answer over the library, and optionally a saved synthesis page |
| `/ai-lib-compare` | `output/compare-*.html` — documents side by side, benchmarks joined |
| `/ai-lib-lint` | a health report, a regenerated `index.md`, contradiction markers |

Set up once, ingest repeatedly, lint after every handful of ingests, and query or compare
whenever.

## 6. Guardrails

- **Never write a claim the document does not make.** Not from the abstract's implication, not from what a similar document said, not from what you know about the subject. `[inference: ...]` exists for your own reasoning and makes it visible as yours.
- **Never let a linked page's claim read as the document's.** That is the specific failure the quarantine section exists to prevent, and the specific reason a `[p. N]` on linked material is an error rather than a style nit.
- **Never present this library as authority.** A document being here implies nothing about whether it is correct. Every deliverable says what kind of source it rests on, and flags an answer resting on one document, or on sources that are all first-party, or on a page marked stale.
- **Never exceed one hop.** Auditable, not enforced (`SCHEMA.md` § 6.2) — which means the discipline is yours.
- **Read before you write.** A document page that already exists is updated under the resolution policy, not overwritten.
- **Ask when ambiguous** — one consolidated question naming the candidates, not a sequence of narrowing ones.

## 7. Quick reference

| Question | Where |
|---|---|
| What have I got on X? | `index.md`, then the leaf's `topic.md` |
| Which topics exist, and what goes in each? | `_config/taxonomy.md` |
| Is this `ai` or `llm/<model>`? | `SCHEMA.md` § 1.2 — delete the model name and see what is left |
| What does this frontmatter key mean? | `SCHEMA.md` § 2 |
| Which sections does a document page need? | `SCHEMA.md` § 3 |
| Which marker do I use? | `SCHEMA.md` § 7.1 |
| Can I follow this link? | `SCHEMA.md` § 6 — only if it is in the document's authorized link plan |
| Where did this claim come from? | its marker, then `topics/<leaf>/captures/`, then `raw/` |
| What changed, and when? | `log.md` |
| What is broken? | run `/ai-lib-lint` |
| How current is this? | the document's `published` date against `stale_days_*` in `_config/library-config.md` |
