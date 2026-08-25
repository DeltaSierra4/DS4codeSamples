# health-insurance-wiki — Operating Rules

The workspace contract for any agent session working in this wiki. Seeded by `/hiw-setup` and
never overwritten. It is deliberately agent-agnostic: no host-specific tool names, no assumption
that skills are invoked as slash commands, and no carrier names — everything specific to this wiki
is read at runtime from `_config/wiki-config.md` and `index.md`.

---

## 1. What this wiki is

A structured knowledge base about health insurance plans, built to be read by agents. It exists so
that questions like *"which of these plans is cheapest for someone with a chronic condition"* can
be answered from stored, sourced facts rather than by re-reading a stack of PDFs each time.

Two invariants hold everywhere:

1. **The company folder is the unit of everything.** Ingest writes into one company folder. A
   subagent is assigned one company folder. A comparison reads several company folders and writes
   into none of them. If you find a plan's facts living outside `companies/<its-company>/`, that is
   a defect.
2. **`plan_id` is the join key.** `<company-slug>__<plan-slug>`, double underscore. Deliverables,
   synthesis pages, and comparison matrices all cite plans by `plan_id`, never by marketing name —
   marketing names collide across carriers and change between plan years.

| To learn | Read | Written by |
|---|---|---|
| The page contract — frontmatter, sections, tags | `SCHEMA.md` | `/hiw-setup` (copied; never edit in place) |
| What plans exist, and where | `index.md` | regenerated wholesale by `index-wiki.py`, which `/hiw-lint` owns and `/hiw-refresh` may re-run after moving pages. Never hand-edited, never patched by hand |
| What has happened to this wiki | `log.md` | every skill, append-only |
| Wiki-level settings — currency, plan year, geography | `_config/wiki-config.md` | `/hiw-setup` |

## 2. Folder map

| Path | Holds | Writes here | Exists once |
|---|---|---|---|
| `companies/<slug>/company.md` | carrier overview + plan roster | `/hiw-ingest`, `/hiw-refresh`, `/hiw-lint` | `/hiw-ingest` first runs for that carrier |
| `companies/<slug>/plans/*.md` | one page per plan — the knowledge | `/hiw-ingest`, `/hiw-refresh`, `/hiw-lint` | as above |
| `companies/<slug>/sources/*.md` | one receipt per ingested document or URL | `/hiw-ingest`, `/hiw-refresh` | as above |
| `raw/<slug>/` | immutable originals | `/hiw-ingest`, `/hiw-refresh` | as above |
| `synthesis/` | saved comparisons, recommendations, briefs (`SCHEMA.md` § 5.1) | `/hiw-query`, `/hiw-compare` | `/hiw-setup` |
| `output/` | generated HTML, reports, and the scripts' intermediate json | every skill | `/hiw-setup` |
| `_config/` | wiki settings | `/hiw-setup` | `/hiw-setup` |

### 2.1 Establish what exists before you rely on it

Four checks, each cheap, none requiring a file to be parsed:

- `SCHEMA.md` at the wiki root — the contract is available.
- `companies/` non-empty — something has been ingested.
- `index.md` exists — a catalog is available (it may be stale; the tree is the truth).
- `_config/wiki-config.md` exists — the wiki was set up rather than assembled by hand.

When one is missing: say what you looked for, name the skill that owns it, offer the degraded path
**and label it as degraded**, do not block, and do not create the missing thing yourself. An empty
`companies/` is not an error — it is a wiki nobody has ingested into yet, and the correct response
is to say so and point at `/hiw-ingest`.

## 3. How to retrieve

The retrieval ladder. Stop at the layer that answers the question; each rung down costs
substantially more context than the one above it.

- **Layer 0** — `index.md`. Every plan, its company, tier, network, premium, deductible, OOP max. Most "what plans exist" and "which is cheapest" questions end here.
- **Layer 1** — `companies/<slug>/company.md`. Carrier positioning, networks, service area, plan roster.
- **Layer 2** — `companies/<slug>/plans/<plan>.md` frontmatter only (first ~50 lines). Every comparable number. This is the layer `/hiw-compare` builds its matrices from.
- **Layer 3** — full plan page bodies. Coverage detail, exclusions, fit notes. Needed for any question about *what is covered* rather than *what it costs*.
- **Layer 4** — `companies/<slug>/sources/*.md`, then `raw/`. Only when a number is disputed or a claim needs retracing to its origin.

**Fan out by company, never by file.** When a task spans **more than two carriers**, assign one
subagent per company folder — one agent per carrier, however many plans that carrier has. Never
one agent per plan page, and never a fixed number of agents dividing the list. Each returns a
structured result for its own carrier and reads no other carrier's pages. This is why the folder
layout is what it is: a per-company subagent has a naturally bounded context and cannot
contaminate one carrier's facts with another's.

**Two carriers or fewer, read inline.** Two subagents to read two folders costs more than it
saves. The threshold is deliberately the same number in every skill, so nobody has to remember
which one it was.

**Collect every subagent result before analyzing any of them.** Partial fan-out results produce
comparisons that silently omit a carrier.

## 4. How to write

The page contract is `SCHEMA.md` at the wiki root. Read it before writing a page. It is a copy —
the master lives with the `/hiw-setup` skill — so if it looks wrong, report the divergence rather
than editing this copy.

Standing rules, which the contract expands:

- **`TBD` over a guess.** A cost field the source did not state is `TBD`. Never infer a number from the metal tier, from a sibling plan, or from market norms. See `SCHEMA.md` § 2.4.
- **Percentages are the member's share.** `coinsurance_in_network: 20` means the member pays 20%.
- **Money is a bare number.** No currency symbol, no separators.
- **Every non-obvious claim carries `[source: ...]`.** A URL-sourced claim carries the access date too.
- **Cross-references are wiki-relative paths in backticks, never `[[wikilinks]]`.** Plan names collide across carriers; the path is the identity. See `SCHEMA.md` § 6.2.
- **Never delete a plan page.** A withdrawn or replaced plan gets `status: superseded`. A new plan year is a new page.
- **Ingest resolves, lint flags.** `/hiw-ingest` and `/hiw-refresh` apply the resolution policy (`SCHEMA.md` § 7.2) and log what they decided. `/hiw-lint` marks what could not be decided and never picks a winner.
- **Literal Unicode in markdown**, never HTML entities.
- **Append to `log.md` on every operation.** One entry per run, `## [YYYY-MM-DD] <skill> | <detail>`. Subsection vocabulary is `SCHEMA.md` § 9.
- **`index.md` is regenerated, never edited.** It is a derived catalog holding no knowledge of its own, so it is rebuilt from `companies/` by `index-wiki.py` — on every `/hiw-lint` run, and by `/hiw-refresh` after it has moved pages. Do not hand-edit it and do not patch it incrementally. A stale index is a normal condition; an index carrying a fact no page carries is the one state that makes regeneration destructive.

### 4.1 Where output goes

Generated artifacts go to `output/`. Saved analysis — something a human will come back to — goes to
`synthesis/` as a markdown page with frontmatter. Nothing generated ever lands inside a company
folder; company folders hold sourced facts only.

## 5. The skills

| Skill | Produces |
|---|---|
| `/hiw-setup` | the wiki scaffold, `SCHEMA.md`, `_config/wiki-config.md`, this file |
| `/hiw-ingest` | company folders, plan pages, source records, `raw/` originals |
| `/hiw-refresh` | re-fetched sources, diffed against stored plans, rate-change reports |
| `/hiw-list-plan` | `output/plan-catalog.html` — every plan, grouped by company |
| `/hiw-query` | an interactive needs assessment and a ranked recommendation |
| `/hiw-compare` | `output/comparison-*.html` — a side-by-side matrix with cost modelling |
| `/hiw-lint` | a health report, a regenerated `index.md`, contradiction markers |

Every skill is standalone. Any of them can be the first thing that ever runs here. They
recommend an order; none of them require one, and none of them block — a missing
prerequisite is a degraded run that says what would make the next one better.

The order is a recommendation, not a requirement: set up once, ingest repeatedly, lint after every
handful of ingests, and query or compare whenever.

## 6. Guardrails

- **Never fabricate a plan fact.** Not a premium, not a copay, not a network name. `TBD` is always available and always correct when the source is silent.
- **Never present this wiki as advice.** Every deliverable carries the caveat in `SCHEMA.md` § 11, and no skill removes it. Stored premiums are list values for a stated basis; a real quote depends on age, ZIP, tobacco use, household size, and subsidy eligibility.
- **Never let a comparison outrun its data.** A plan with `TBD` in a field being compared is shown as unknown, never as zero, never as "not applicable", and never quietly dropped from the table.
- **Read before you write.** A plan page that already exists is updated under the resolution policy, not overwritten.
- **Ask when ambiguous** — one consolidated question naming the candidates, not a sequence of narrowing ones.

## 7. Quick reference

| Question | Where |
|---|---|
| What plans do we have? | `index.md` |
| What does this field mean? | `SCHEMA.md` § 2 |
| Which sections does a plan page need? | `SCHEMA.md` § 3 |
| Where did this number come from? | the `[source: ...]` tag, then `companies/<slug>/sources/` |
| What changed, and when? | `log.md` |
| What is broken? | run `/hiw-lint` |
| What currency / plan year is this wiki? | `_config/wiki-config.md` |
