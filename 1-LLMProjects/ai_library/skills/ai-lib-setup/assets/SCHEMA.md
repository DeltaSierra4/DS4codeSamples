# ai-lib — Page Contract (SCHEMA)

The contract every page in this library obeys. `/ai-lib-setup` copies this file into the
library root as `SCHEMA.md`; that runtime copy is the only one downstream skills read.
Skills cite section numbers (`§ 3.1`, `§ 7`) verbatim, so **copy this file byte-for-byte —
never summarize, re-flow, re-number, or paraphrase it.**

This library is the retrieval layer for an Agentic RAG system over a personal collection
of PDFs and text files: AI and LLM material, data science, math, science, technology,
cybersecurity, and whatever else was worth keeping. Every rule below exists to make one
of three things possible: a subagent answering a question about **one leaf topic** without
reading any other topic's pages; a reader tracing **any claim back to a page number**; and
a script producing a comparison **without an LLM re-reading prose**.

Most of what lands here will be a blog post saved as a PDF, not a peer-reviewed paper.
The contract is built for that: authorship and venue are optional, `publication_type` and
`authority` are not, and staleness is treated as a first-class problem because a model
announcement from eighteen months ago is not merely old, it is misleading.

---

## § 1 — Architecture

Five directories at the library root, five roles:

| Path | Holds | Written by | Read by |
|---|---|---|---|
| `topics/` | the taxonomy tree — the knowledge | `/ai-lib-ingest`, `/ai-lib-refresh`, `/ai-lib-lint` | everything |
| `raw/` | immutable originals, mirrored by topic path | `/ai-lib-ingest`, `/ai-lib-refresh` | `/ai-lib-ingest`, `/ai-lib-refresh` |
| `synthesis/` | saved answers, reading lists, briefs | `/ai-lib-query`, `/ai-lib-compare` | humans |
| `output/` | generated HTML, reports, and the scripts' intermediate json | every skill | humans, and the scripts |
| `_config/` | library-level settings and the taxonomy | `/ai-lib-setup` | every skill |

Three files at the library root:

- `SCHEMA.md` — this contract. Copied in at setup; **never edited in place**.
- `index.md` — the catalog of every document, grouped by topic (§ 9). Regenerated, holds no knowledge of its own.
- `log.md` — append-only chronological record (§ 10).

**The leaf topic folder is the unit of parallelism.** Everything a subagent needs to
become the master of one topic is inside that leaf folder and nowhere else. Never store a
document's substance outside its own leaf, and never make one leaf's page depend on
another leaf's page.

```
<library-root>/
├── SCHEMA.md
├── index.md
├── log.md
├── _config/
│   ├── library-config.md
│   └── taxonomy.md
├── topics/
│   └── <topic-path>/
│       ├── topic.md
│       ├── documents/
│       │   └── <doc-slug>.md
│       └── captures/
│           └── <doc-slug>__<link-slug>.md
├── raw/
│   └── <topic-path>/
├── synthesis/
└── output/
```

### § 1.1 — The taxonomy, and the leaf rule

Five top-level topics. Two of them carry subtopics, because their literatures are
genuinely distinct; three do not.

```
topics/
├── ai/                        model-agnostic AI: architectures, training, alignment,
│                              RL, interpretability, evaluation, agents, theory
├── llm/                       model-specific material, one leaf per model family
│   ├── claude/
│   ├── gpt/
│   ├── gemini/
│   ├── grok/
│   ├── qwen/
│   ├── kimi/
│   └── other-models/          every other named model, open or closed
├── data-science/              statistics, ML engineering, data pipelines, analysis,
│                              visualization, experiment design, MLOps
├── math-sci-tech-cyber/
│   ├── math/
│   ├── science/
│   ├── technology/
│   └── cybersecurity/
└── misc/                      real-life material that is none of the above
```

**The leaf rule: documents live only in a leaf.** A topic that has subtopics is a
**branch** and holds `topic.md` and nothing else — no `documents/`, no `captures/`. A
topic with no subtopics is a **leaf** and holds `topic.md`, `documents/` and `captures/`.
A node is either a branch or a leaf, never both.

That makes exactly **fourteen leaves**: `ai`, the seven under `llm/`, `data-science`, the
four under `math-sci-tech-cyber/`, and `misc`. Fourteen is also the maximum useful fan-out
width, which is not a coincidence — the tree was shaped to be the parallelism plan.

`_config/taxonomy.md` is the authority on which paths exist. A document filed at a path
the taxonomy does not define is a lint error, not a new topic. **Adding a topic is a
deliberate edit to `taxonomy.md`, never a side effect of an ingest.**

### § 1.2 — `ai/` versus `llm/`

The single most common placement mistake, so it gets its own rule.

- **`llm/<model>/`** is for material *about a specific model or model family*: an
  announcement, a model card, a capability write-up, a prompting guide for that model, a
  third-party evaluation of it, a post-mortem of its behaviour.
- **`ai/`** is for material about *techniques, theory, or practice that is not tied to
  one model*: RLHF in general, transformer theory, a new optimizer, interpretability
  method, agent architecture, evaluation methodology.

The test is what the document would still be about if you deleted the model name. "How
Claude's constitutional training works" is `llm/claude/`. "Constitutional AI as a method"
is `ai/`. A document about a technique that happens to use one model as its example is
`ai/` — the technique is the subject.

Where a document genuinely straddles both, **file it where its primary contribution
lands and cross-reference the other** in `related:` and in `## Connections`. Do not
duplicate the page. A duplicated document drifts apart on the next refresh and then reads
as a contradiction.

### § 1.3 — Slugs

`<topic-path>` segments and `<doc-slug>` are kebab-case: lowercase, spaces to hyphens,
ampersands to `and`, every other non-alphanumeric character dropped, collapsed hyphens,
no leading or trailing hyphen. `Constitutional AI: Harmlessness from AI Feedback` →
`constitutional-ai-harmlessness-from-ai-feedback`.

Cap a `<doc-slug>` at roughly 60 characters — truncate at a word boundary rather than
mid-word. The full title lives in `title`; the slug only has to be unique within its leaf.

A slug is **durable identity**. Once a document page exists at a path, that path does not
change because a title was reworded — record the new wording in `title` and add the old
one to `aka`. Renaming a page breaks every cross-reference, every saved synthesis, and
every `doc_id` cited in an answer.

---

## § 2 — Document page frontmatter (`topics/<path>/documents/<slug>.md`)

The machine-readable core. `/ai-lib-list`, `/ai-lib-compare` and `/ai-lib-query` read
these keys when building catalogs and matrices, so a value here is a **contract**, not a
note.

```yaml
---
title: Constitutional AI — Harmlessness from AI Feedback
doc_id: "ai__constitutional-ai-harmlessness-from-ai-feedback"
aka: ["CAI paper"]
topic: ai
publication_type: paper
authority: preprint
publisher: Anthropic
authors: [Bai Y., Kadavath S., Kundu S.]
published: 2022-12-15
year: 2022
venue: arXiv
doi: "10.48550/arXiv.2212.08073"
arxiv_id: "2212.08073"
url: "https://arxiv.org/abs/2212.08073"
version: v1
pages: 34
models: [claude-v1]
tags: [rlhf, alignment, harmlessness, ai-feedback]

contribution_type: [method, empirical-study]
maturity: foundational
reproducibility: neither
supersedes: []
superseded_by: []

claim_count: 6
located_claim_count: 6
benchmark_count: 2
has_limitations: true

links_authorized: 11
links_followed: 3
links_declined: 8

builds_on: ["ai__training-a-helpful-and-harmless-assistant-with-rlhf"]
related: ["llm/claude"]

source_file: constitutional-ai.pdf
source_type: pdf
retrieved: 2026-08-26
created: 2026-08-26
last_updated: 2026-08-26
updated_by: ai-lib-ingest
extraction_confidence: high
status: active
---
```

### § 2.1 — Required keys

Present on every document page, always: `title`, `doc_id`, `topic`, `publication_type`,
`authority`, `source_file`, `source_type`, `retrieved`, `created`, `last_updated`,
`updated_by`, `extraction_confidence`, `status`.

These must **exist** and may be empty lists: `aka`, `authors`, `tags`, `models`,
`builds_on`, `related`, `supersedes`, `superseded_by`.

These must exist as integers, `0` being meaningful: `claim_count`,
`located_claim_count`, `benchmark_count`, `links_authorized`, `links_followed`,
`links_declined`.

Everything else is optional and genuinely so. A blog post has no `doi`, no `venue` and
often no named author; omit those keys rather than writing `unknown`. **Absent means "this
document does not have this property."** There is no `TBD` sentinel in this contract —
unlike a plan's premium, a missing DOI is not a knowledge gap, it is a fact about the
document. Where a *knowledge* gap needs recording, it goes in `## Open Questions` with a
`[verify: ...]` marker (§ 7.1).

### § 2.2 — Controlled vocabularies

| Key | Allowed values |
|---|---|
| `topic` | any leaf path in `_config/taxonomy.md` — and only a leaf, never a branch |
| `publication_type` | `blog-post` · `announcement` · `model-card` · `documentation` · `paper` · `preprint` · `report` · `whitepaper` · `tutorial` · `benchmark` · `standard` · `thesis` · `book-chapter` · `transcript` · `newsletter` · `other` |
| `authority` | `first-party` · `peer-reviewed` · `preprint` · `institutional` · `secondary` · `community` |
| `source_type` | `pdf` · `txt` |
| `contribution_type` | `method` · `architecture` · `empirical-study` · `benchmark` · `survey` · `position` · `tooling` · `dataset` · `incident-report` · `explainer` · `announcement` |
| `maturity` | `foundational` · `established` · `emerging` · `speculative` · `superseded` |
| `reproducibility` | `code-released` · `data-released` · `both` · `neither` · `n/a` |
| `extraction_confidence` | `high` · `medium` · `low` |
| `updated_by` | `ai-lib-setup` · `ai-lib-ingest` · `ai-lib-refresh` · `ai-lib-list` · `ai-lib-query` · `ai-lib-compare` · `ai-lib-lint` · `practitioner` |
| `status` | `active` · `superseded` · `draft` |

**`authority` is about who is speaking, not about quality.** An Anthropic post about
Claude is `first-party` — maximally authoritative about what Anthropic built, and not at
all disinterested about how good it is. A third-party benchmark of Claude is `secondary` —
less authoritative on intent, more useful on performance. `institutional` covers a
standards body, a government report, a university lab page. `community` covers a forum
post, a personal blog, a conference talk write-up. This field is what lets `/ai-lib-query`
say *"three sources agree, but all three are the vendor."*

**`extraction_confidence` is about the extraction, not the document.**

- `high` — the text extracted cleanly, you read the whole document, and every claim you recorded carries a page locator.
- `medium` — the document is long and you read it selectively, or the extraction lost some structure (tables, figures, multi-column layout), or some claims are `[unlocated]`.
- `low` — the extraction was partial or garbled, the PDF is a scan, or you worked mostly from a linked page rather than the document itself.

`doc_id` is `<topic-path-with-slashes-as-hyphens>__<doc-slug>` with a **double**
underscore: `llm/claude` + `claude-4-5-system-card` → `llm-claude__claude-4-5-system-card`.
It is globally unique across the library and is the join key used by every skill and every
synthesis page. Always quote it.

### § 2.3 — Types and units

- Dates are `YYYY-MM-DD`. Where a document states only a month or a year, use the first day: `2022-12-01`, `2022-01-01`, and say so in `## Additional capture` under `### Data notes`.
- `year` is a bare four-digit integer, and must agree with `published` where both exist.
- Counts are bare integers. `0` is a real value and means zero, not unknown.
- Booleans are `true` / `false`, never `yes` / `Yes` / `"true"`.
- Lists are inline flow style: `tags: [rlhf, alignment]`, empty as `[]`. Quote any item containing `:`, `#`, `,` or a URL.
- `pages` is the PDF's page count, used to sanity-check locators. A `[p. 40]` on a 12-page document is a lint error.

### § 2.4 — The counts are not decorative

`claim_count`, `located_claim_count` and `benchmark_count` must equal what is actually in
`## Key Claims` and `## Evidence`. The linter checks all three, because they are how
`/ai-lib-query` decides which pages are worth opening, and a page claiming six claims and
holding two is a page that wastes a subagent's context every time it is retrieved.

`located_claim_count` less than `claim_count` means some claims are `[unlocated]`. That is
permitted and it is honest — but the gap is visible, and `extraction_confidence` may not
be `high` when it is non-zero.

Likewise `links_authorized`, `links_followed` and `links_declined`: `followed + declined`
must equal `authorized`, because the link plan (§ 6) enumerated exactly that many and
every one of them was either taken or deliberately passed over. A discrepancy means a link
was neither followed nor consciously declined, which is the state this contract exists to
make impossible.

---

## § 3 — Document page sections

Exactly these ten `##` headings, in this order, **all present on every document page**,
matched case-insensitively and exactly. Do not invent, rename, merge, reorder, or omit
one.

```
## Snapshot
## Problem & Context
## Method
## Key Claims
## Evidence
## Limitations
## Connections
## Open Questions
## From Linked Pages
## Additional capture
```

The title line is `# <title>`, followed by a blank line and one italic provenance line:
`_<publication_type> · <publisher or authors> · <published> · <authority>_`.

An empty section holds the placeholder `_None recorded._` on its own line. It is never
omitted, and content **replaces** the placeholder rather than being written beneath it.

### § 3.1 — What each section holds

**`## Snapshot`** — three to five bullets, and the first one states **why this document
matters**, not what it is. "The first published method for training a harmless assistant
without human harmfulness labels" beats "A paper about Constitutional AI." Retrieval
quality depends on this section more than any other; it is what a subagent quotes when the
question is broad, and often the only part that gets read.

**`## Problem & Context`** — what problem the document addresses, in its own framing, and
what it positions itself against. Two to four sentences. This is where a reader learns
whether the document is even relevant, so resist summarizing the abstract — say what gap
it claims to fill.

**`## Method`** — how the thing works, in enough detail that a reader could describe it
to someone else without reopening the PDF. For an announcement, this is what was actually
shipped. For a tutorial, the procedure. Diagrams cannot be stored, so describe what the
diagram shows.

**`## Key Claims`** — **the most important section in this contract.** A numbered list,
one claim per line, each carrying a locator and a type:

```
1. Self-supervised critique-and-revision removes the need for human harmfulness labels. [p. 2] [type: methodological]
2. RLAIF matches RLHF on helpfulness while scoring better on harmlessness. [p. 15, Fig 7] [type: empirical]
3. Chain-of-thought reasoning improves the harmlessness of the critique step. [p. 9] [type: empirical]
```

Rules, all load-bearing:

- **Numbered continuously, `1.` to `n.`** Do not write every line as `1.` and rely on markdown auto-numbering — it renders correctly and parses as *n* claims all numbered 1.
- **Every claim carries a locator** (§ 7.1). A claim with no marker is the one thing this library may not contain.
- **A claim is what the document asserts, not what is true.** Record a claim you believe to be wrong exactly as the document makes it, and put your disagreement in `## Open Questions` as an `[inference: ...]`.
- **One claim per line.** A line carrying two assertions is two claims.
- **`[type: ...]`** is one of `empirical` · `methodological` · `architectural` · `capability` · `limitation` · `normative` · `forecast`. `forecast` matters: a prediction about future capability is not an empirical result, and a RAG answer that conflates the two is actively misleading.

**`## Evidence`** — the numbers, as a table, so a script can join them across documents
without an LLM re-reading prose:

```
| Benchmark / Eval | Metric | Reported | Baseline | Locator |
|---|---|---|---|---|
| MMLU | 5-shot accuracy | 88.7 | 86.4 (prior best) | p. 5, Table 1 |
| HH-RLHF harmlessness | Elo | 153 | 0 (base model) | p. 15, Fig 7 |
```

Use the document's own benchmark and metric names verbatim — normalizing "MMLU" to
"Massive Multitask Language Understanding" breaks the join. Where the document reports no
numbers, the section holds `_None recorded._` and `benchmark_count` is `0`. **Never
compute a number the document did not report**, and never carry a baseline across from
another document; a baseline belongs to the run that produced it.

**`## Limitations`** — what the document says it cannot do, plus what it conspicuously
does not address. Mark the difference: the first is `[p. N]`, the second is
`[inference: not addressed]`. For a first-party announcement this section is usually the
thinnest part of the source and the most valuable part of the page.

**`## Connections`** — how this document relates to others **in this library**, by
`doc_id`, with the relationship named: builds on, contradicts, supersedes, replicates,
applies, critiques. Do not invent a connection to a document the library does not hold —
`## Open Questions` is where "someone should read X next to this" belongs.

**`## Open Questions`** — what a reader should still wonder, what you could not resolve,
and every `[verify: ...]` this page carries. This is the section `/ai-lib-refresh` works
from and the one that keeps a thin page honest.

**`## From Linked Pages`** — **the quarantine, and its boundary is absolute.** Material
harvested from depth-1 links, and nothing else. One `###` subheading per link, the URL in
the heading, every bullet carrying a `[link: ...]` marker:

```
### https://arxiv.org/abs/2204.05862 — Training a Helpful and Harmless Assistant
- Defines the HH-RLHF dataset this document's evaluation reuses. [link: https://arxiv.org/abs/2204.05862, accessed 2026-08-26]
```

**Nothing from a linked page may appear anywhere above this section**, and nothing this
document itself says may appear inside it. That separation is the whole reason the
depth-1 crawl is safe to run at all: it guarantees a reader — human or subagent — can
always tell what the document said from what something it linked to said. See § 6.

**`## Additional capture`** — the last section of every page and the only place free-form
`###` headings are allowed. Use it for anything real the nine fixed sections cannot hold:
`### Data notes`, `### Notable quotes`, `### Figures described`, `### Terminology`,
`### Reading notes`, `### Related work as listed by the document`. Tools stop reading the
contract here. It is not an overflow bin for content that belongs in a fixed section
above, and it is not where linked-page material goes — that is `## From Linked Pages`,
and only there.

---

## § 4 — Topic pages (`topics/<path>/topic.md`)

Every topic gets one, branch or leaf.

```yaml
---
title: Claude
topic: llm/claude
category: topic
node_type: leaf
parent: llm
document_count: 12
expected_share: 0.35
created: 2026-08-26
last_updated: 2026-08-26
updated_by: ai-lib-ingest
status: active
---
```

`node_type` is `branch` or `leaf` and must agree with the taxonomy. `expected_share` is
the parent top-level topic's expected proportion from `_config/library-config.md`,
carried here for convenience; it is a **weight, never a quota**. `document_count` must
equal the `.md` file count in `documents/`, and is `0` on a branch.

Sections, in order, all present:

```
## Snapshot
## What Belongs Here
## Key Documents
## Themes
## Gaps
## Additional capture
```

**`## What Belongs Here`** is the placement rule in the topic's own words, and it is what
a subagent reads to decide whether a borderline document is theirs. For `llm/claude` that
is something like *"material about Claude specifically — announcements, model cards,
capability write-ups, prompting guidance, third-party evaluations. A technique that merely
uses Claude as its example belongs in `ai/`."*

**`## Key Documents`** is a table, one row per document in this leaf, and it is a **mirror,
not a second source of truth** — every value must match that document's frontmatter:

```
| Document | Type | Authority | Published | Claims | Page |
|---|---|---|---|---|---|
| Claude 4.5 System Card | model-card | first-party | 2025-09-29 | 8 | `documents/claude-4-5-system-card.md` |
```

**`## Themes`** — what the documents in this leaf collectively say, as three to six
bullets, each citing at least two `doc_id`s. This is the only place in the library where
cross-document synthesis is stored inside a topic folder, and it is what makes a
per-topic subagent useful rather than merely a file lister. A theme supported by one
document is not a theme; it is that document's claim.

**`## Gaps`** — what this topic is missing, so `/ai-lib-query` can say so honestly rather
than answering thinly. On a branch page, `## Key Documents` and `## Themes` hold
`_None recorded._` and the subtopics are listed under `## What Belongs Here`.

---

## § 5 — Capture pages (`topics/<path>/captures/<doc-slug>__<link-slug>.md`)

One per depth-1 link **followed**. A receipt, not a summary: it records what was taken and
where it went, so a later reader can retrace any linked claim to its origin.

```yaml
---
title: Training a Helpful and Harmless Assistant with RLHF
category: capture
topic: ai
parent_doc: "ai__constitutional-ai-harmlessness-from-ai-feedback"
source_url: "https://arxiv.org/abs/2204.05862"
url_domain: arxiv.org
link_class: paper
depth: 1
accessed: 2026-08-26
fetch_status: ok
authority: preprint
created: 2026-08-26
last_updated: 2026-08-26
updated_by: ai-lib-ingest
status: active
---
```

`depth` is **always `1`**. There is no other legal value in this contract (§ 6).
`parent_doc` is the `doc_id` of the document whose link plan authorized this fetch.
`link_class` is one of `paper` · `preprint` · `code` · `documentation` · `blog-post` ·
`dataset` · `benchmark` · `announcement` · `video` · `other`. `fetch_status` is one of
`ok` · `partial` · `paywalled` · `not-found` · `blocked` · `js-required` — a capture is
written for a *failed* fetch too, because "we tried and it 404s" is information that stops
the next run trying again.

Exactly three sections:

```
## Metadata
## What was taken
## Not taken
```

**`## Metadata`** — bullets: URL · Domain · Class · Accessed · Fetch status · Authority ·
Title as given · What this page is, in one sentence.

**`## What was taken`** — one line per item harvested, each naming the destination section
on the parent document page:

```
- HH-RLHF dataset definition → `## From Linked Pages` (parent: ai__constitutional-ai-...)
- Preference-model pretraining detail → `## From Linked Pages`
```

The destination is **always** `## From Linked Pages`. If you find yourself writing any
other destination, the quarantine has been breached (§ 3.1, § 6.3).

**`## Not taken`** — every link found *on that page*, listed and **not fetched**, plus
anything on the page you judged irrelevant. This section is the audit trail for the depth
limit: it is the proof that second-depth links were seen and declined rather than never
noticed.

Capture pages are **append-only**. Re-following the same URL appends to
`## What was taken`; it never rewrites `## Metadata`.

### § 5.1 — Synthesis pages (`synthesis/<slug>.md`)

Saved analysis — an answer or a comparison a human will come back to. Written by
`/ai-lib-query` and `/ai-lib-compare`, read by humans, and **never** read as a source of
claims by anything. A synthesis page is a snapshot of a conclusion, so it goes stale by
design and that is not a defect.

```yaml
---
title: Does constitutional training reduce refusals?
category: synthesis
doc_ids: ["ai__constitutional-ai-harmlessness-from-ai-feedback", "llm-claude__claude-4-5-system-card"]
topics: [ai, llm/claude]
question: Does constitutional training reduce over-refusal, and do any of my sources disagree?
created: 2026-08-26
last_updated: 2026-08-26
updated_by: ai-lib-query
status: active
---
```

`doc_ids` cites every document the conclusion rests on, by `doc_id` and never by title —
that is what makes a saved conclusion re-checkable a year later, when two of the documents
have been renamed. `topics` records which leaves were searched, which is how a reader knows
what was **not** looked at.

Sections are free-form: this is the one page type with no fixed section grammar, because an
answer and a rate-change brief are not the same shape. Three contents are required
regardless:

1. **The question, verbatim.** A conclusion recorded without the question it answered is
   uninterpretable six months later, which is exactly when someone reads it.
2. **Every claim still carrying its marker** (§ 7.1), in the same four forms. A synthesis
   page that drops its citations is a synthesis page nobody can check, and it is the most
   likely place for that to happen because the prose reads well without them.
3. **The standing caveat** (§ 12), and what kind of evidence the conclusion rested on — how
   many documents, what authorities, how old.

**Nothing generated ever lands inside a topic folder.** Topic folders hold attributed claims
about documents only.

---

## § 6 — The depth-1 link rule

The library follows links out of a document exactly one hop. This section is the whole
specification, and it is written as a contract rather than a suggestion because the
failure it prevents — an unbounded crawl silently filling the library with material
nobody chose — is not recoverable by editing a page afterwards.

### § 6.1 — Authorization: the link plan

`extract-pdf.py` reads a source document and emits an **authorized link plan** to
`output/_linkplan-<doc-slug>.json`. Every URL in that plan is stamped `depth: 1`.

**The plan is the complete and only set of URLs that may be fetched for that document.**
Not "a starting point", not "a suggestion". A URL that is not in the plan is not
authorized, however relevant it looks and whoever suggests it.

Where the agent finds a URL the extractor missed — a hyperlink whose anchor text hid the
target, which a text-layer extractor cannot see — the correct move is to **add it to the
plan file and record that you did**, not to fetch it unrecorded. The plan is the audit
surface; an unrecorded fetch defeats it.

### § 6.2 — The hop limit, and why it is auditable rather than enforced

A script cannot do the fetching, so a script cannot physically stop a second hop. The
limit is therefore made **auditable**:

1. Every capture page carries `depth: 1` and a `parent_doc`.
2. `/ai-lib-lint` checks every capture's `source_url` against the parent document's link plan. **A capture whose URL is in no plan is an error** — `CAP-UNAUTHORIZED` — and it is the signature of a second-hop fetch.
3. Every link found *on* a fetched page goes in that capture's `## Not taken` section, unfetched. A page whose `## Not taken` is empty when the fetched page plainly had links is a page whose author did not look, and the linter says so.

So: **never fetch a URL you found on a page you fetched.** Record it under `## Not taken`
and stop. If it looks important enough to read, it is important enough to be its own
ingest — save it as a PDF, run `/ai-lib-ingest` on it, and it gets a full page with its
own link plan. That is the sanctioned route from depth 2 to depth 1, and it keeps the
human in the loop where the design wants them.

### § 6.3 — What comes back, and where it goes

Everything harvested from a depth-1 link goes in the parent document's
`## From Linked Pages` section and its own capture page. **Nowhere else, ever.**

Concretely forbidden:

- A linked page's number in `## Evidence`. That table is the document's own reported results.
- A linked page's assertion in `## Key Claims`. Those are the document's claims.
- A linked page's method detail in `## Method`, however much better it explains the method.
- A `[p. N]` locator on anything from a linked page. Page locators mean *this document's* pages.

The last one is the specific error to watch for: a linked arXiv paper has page numbers
too, and writing `[p. 4]` for a claim that came from it makes a linked claim
indistinguishable from the document's own. Linked material takes `[link: <url>, accessed
<date>]` and only that.

### § 6.4 — What not to follow

The extractor filters these out of the plan, and where one slips through, decline it:

- `mailto:`, `javascript:`, `tel:`, bare fragments (`#section`)
- image, video, font and archive files by extension
- a URL on the same page as the document's own canonical `url` (self-links)
- login, signup, cart, unsubscribe, share-intent and tracking URLs
- social media profile and post URLs, unless the post *is* the substantive content
- anything already captured for this document — dedupe by normalized URL

And a judgement call the extractor cannot make: **decline a link whose page you can see is
a navigation index rather than content.** A "Publications" listing page yields nothing but
more links, and following it burns a hop for no substance.

### § 6.5 — Politeness and honesty

Fetch at a human pace. A paywall, a login wall or a robots-disallowed page is a
`fetch_status` other than `ok` and a capture that records the refusal — never a reason to
find another route to the content. A blocked page is a fact about the page, and the
correct response is to write it down.

---

## § 7 — Provenance

### § 7.1 — The four markers, and the rule that governs them

**Every claim in this library carries exactly one marker naming where it came from. A
claim with no marker is the one thing this library may not contain.** The entire value of
a RAG library over documents is that an answer can be traced; an untraceable claim is
worse than an absent one, because it looks identical to a traceable one.

| Marker | Means | Example |
|---|---|---|
| `[p. N]`, `[Table 2]`, `[Fig 4]`, `[p. 8, Table 1]`, or a section of the source such as `[§ 3.2]` | **this document** says it, there | `[p. 15, Fig 7]` |
| `[unlocated]` | this document says it; the page could not be pinned | `[unlocated]` |
| `[link: <url>, accessed <date>]` | a **depth-1 linked page** says it | `[link: https://arxiv.org/abs/2204.05862, accessed 2026-08-26]` |
| `[inference: <what you concluded and from what>]` | **you** concluded it; the document does not say it | `[inference: the method implies a compute cost the paper never states]` |

Plus one that is not a source marker but a flag:

- `[verify: <what a human should resolve>]` — a known weakness. `/ai-lib-lint` reports these; nothing auto-clears them.

**`[inference: ...]` states the derivation, not merely that one occurred.** "This probably
scales" is not an inference marker; "[inference: the linear attention cost implies this
scales to 100k context, which the paper does not test]" is.

**A `[link: ...]` marker may only appear inside `## From Linked Pages`.** A `[p. N]`
marker may only appear outside it. The linter enforces both, and together they are what
make the quarantine real rather than aspirational.

### § 7.2 — Cross-references are `doc_id`s and paths, never wikilinks

Reference another library page by its `doc_id` in backticks, or by its library-relative
path where the path is what matters:
`` `llm-claude__claude-4-5-system-card` ``, `` `topics/ai/documents/constitutional-ai.md` ``.

**Do not use `[[wikilink]]` syntax.** Document titles collide constantly — every model
family has a "system card" and an "announcement" — and `[[System Card]]` cannot resolve.
The `doc_id` is the identity.

Write every cross-reference as an inline reference in the body, not only in `related:` or
`builds_on:`. Orphan detection scans bodies, so a reference living solely in frontmatter
is never link-checked, and a reference nothing checks is a reference that rots.

### § 7.3 — Quoting

A verbatim quotation is a blockquote with a locator, and it is capped at roughly 50 words:

```
> Constitutional AI trains a harmless assistant through self-improvement, without any
> human labels identifying harmful outputs. [p. 1]
```

This library is a set of notes about documents, not a copy of them. `raw/` holds the
original; extended quotation here adds nothing a reader could not get by opening it, and
it turns the library into a redistribution of other people's work.

---

## § 8 — Updates, supersession, and staleness

### § 8.1 — Never delete

No skill deletes a document page. A document that is withdrawn, retracted or replaced
gets `status: superseded`, a `superseded_by` entry naming its replacement, and a line in
`## Additional capture` explaining what happened. What the field believed in 2023 is
useful precisely because it is no longer what the field believes.

A new version of the same document — arXiv v2, a revised blog post, an updated model card
— is handled by **`version` and a note, not a new page**, when the substance is
continuous. Update `version`, update the changed claims, log every change (§ 10). Create
a *new* page only when the document is genuinely a different work: a new model's system
card, a follow-up paper, a substantially rewritten post with a new URL.

That is the opposite of a per-year rule, and the reason is domain-specific: a v2 of a
preprint is the same work corrected, whereas next year's model is a different subject.

### § 8.2 — Resolution policy when sources disagree

When a new source contradicts what a page already says:

1. **Higher `authority` wins for facts about intent and implementation** — a first-party model card beats a third-party blog on what the model was trained to do.
2. **Lower `authority` can win for facts about performance** — an independent evaluation beats a vendor's own benchmark on how the model actually behaves. Where a first-party and a secondary source disagree on a *number*, keep both and name both; that disagreement is itself the finding.
3. **At equal authority, the newer `published` date wins**, except that a document about an earlier version never overwrites one about a later version.
4. **Where neither dominates, keep both**, side by side, under `## Additional capture` as `### Unresolved`, and log it.

Every in-place overwrite is logged with the old value, the new value, both sources, and
the rule that decided it (§ 10). Nobody approved that edit before it landed, so the log is
the only place it can be caught.

**Elaboration is not conflict.** A source adding detail to a page that had none is a
refinement — write it. Two documents reporting different numbers on the same benchmark
are usually *not* in conflict either: different runs, different prompts, different dates.
Record both with their locators before deciding anything is contradictory.

### § 8.3 — Staleness is a first-class property here

Most of this library is blog posts and announcements about a field that moves monthly. A
`llm/gpt` announcement from two years ago is not merely old — read as current, it is
wrong.

`/ai-lib-lint` reports a document as stale on `published`, not on `last_updated`, using
the per-topic thresholds in `_config/library-config.md`. The defaults are deliberately
uneven, because the literatures age at different rates:

| Topic | Default stale-after |
|---|---|
| `llm/*` | 270 days |
| `ai` | 540 days |
| `data-science` | 1095 days |
| `math-sci-tech-cyber/cybersecurity` | 365 days |
| `math-sci-tech-cyber/*` (other) | 1825 days |
| `misc` | 1825 days |

A stale page is **not** a defect and is never auto-superseded. It is a prompt to check
whether something replaced it, and a signal `/ai-lib-query` must surface when it answers
from that page.

### § 8.4 — Contradiction markers

`/ai-lib-ingest` and `/ai-lib-refresh` resolve what they can and log it. What they cannot
settle, `/ai-lib-lint` marks on the page itself, immediately below the newer claim:

```
**CONTRADICTION:** claim 3 states 88.7 on MMLU [p. 5, Table 1] vs. 85.2 reported for the same model and benchmark in `llm-gpt__gpt-5-evaluation-report` [p. 3] — different evaluation harnesses, unresolved. [2026-08-26 via ai-lib-lint]
```

The marker names both values, both locators and both sources. It never picks a winner, and
it never edits either claim.

---

## § 9 — `index.md`

The catalog. It holds no knowledge of its own and is fully rebuildable from `topics/` at
any time, so a stale index is a normal condition rather than an error.

```markdown
# Index

_Generated 2026-08-26 · 14 leaf topics · 87 documents · 41 captures_

## ai — `topics/ai/`

_23 documents (26% of library; expected ~35%)_

| Document | Type | Authority | Published | Claims | Bench | Page |
|---|---|---|---|---|---|---|
| Constitutional AI | paper | preprint | 2022-12-15 | 6 | 2 | `documents/constitutional-ai.md` |
```

One `##` section per **leaf** topic, in taxonomy order — not alphabetical, because the
taxonomy order is meaningful and a reader scanning for `llm/claude` expects it next to
`llm/gpt`. Branch topics get a `##` heading and their share line, then their leaves as
`###`. Superseded documents go in a separate `### Superseded` subsection under their leaf,
never mixed into the main table.

The share line compares actual against expected (§ 8.3's sibling setting) so drift is
visible. **Drift is information, not an error** — if 60% of the library is `llm/` because
that is what you read this quarter, the expected share was a guess and the library is
right.

---

## § 10 — `log.md`

Append-only. Never edit an existing entry. Every entry opens with the date, then the skill
name in the second position, then a one-line detail:

```markdown
## [2026-08-26] ai-lib-ingest | Constitutional AI -> topics/ai — 1 document, 3 of 11 links followed, 6 claims (6 located), 2 benchmarks
### Values updated in place
- `topics/ai/documents/constitutional-ai.md` · claim 2 · "matches RLHF" [p. 15] -> "matches RLHF on helpfulness, exceeds on harmlessness" [p. 15, Fig 7] — same source, finer locator
### Links declined
- 8 of 11 authorized links not followed: 5 navigation indexes, 2 self-links, 1 paywalled
```

The skill vocabulary is the same as `updated_by` (§ 2.2). Optional `###` subsections,
omitted when empty: `### Values updated in place`, `### Not adopted`, `### Unresolved`,
`### Links declined`, `### Held`, `### Superseded`.

---

## § 11 — Writing standards

1. **Significance first.** Every `## Snapshot` opens with why the document matters, not what it is.
2. **One claim per line, one assertion per sentence.**
3. **Locators over adjectives.** "Substantially better" is unusable; "88.7 vs 86.4 on MMLU [p. 5, Table 1]" is.
4. **Tables where the content is tabular.** Benchmark results always are.
5. **The document's own words for names.** Benchmark names, metric names, method names, model names — verbatim, because every join in this library is a string match.
6. **Distinguish claim from truth from inference**, always, with the markers in § 7.1. This is the discipline the whole library rests on.
7. **Literal Unicode, never HTML entities**, in `.md` files. Write `—` and `·`, not `&mdash;` and `&middot;`.
8. **Write for a subagent that will read this page and nothing else.** It cannot see the other topics. A page that only makes sense next to its neighbours is a page that fails at retrieval time.

---

## § 12 — What this library is not

It is a structured record of what a collection of documents says. It is not a substitute
for reading them, not a citation manager, and not an authority in its own right.

Every claim here is attributed to a document, and a document being in the library implies
nothing about whether it is correct. A first-party announcement is a marketing artifact as
well as a technical one; a preprint has not been reviewed; a blog post may have been
quietly edited since it was captured. The markers in § 7.1 exist so that a reader can
always tell what kind of thing they are relying on.

Deliverables built from this library — `/ai-lib-query` answers, `/ai-lib-compare`
matrices, `/ai-lib-list` catalogs — carry that caveat visibly, and no skill removes it.
Where an answer rests on a single document, or on sources that are all first-party, or on
a page marked stale, the deliverable says so.
