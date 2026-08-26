---
name: ai-lib-ingest
description: >-
  Read a PDF or text file into the ai-lib document library as a structured page of
  attributed claims, then follow the links it contains exactly one hop and fold what they
  say into a quarantined section. Places the document in one of fourteen leaf topics,
  records every claim with a page locator, writes a capture receipt per link followed, and
  mirrors the original into raw/. Use when the user says "ingest this PDF", "add this paper",
  "read this blog post into the library", "file this", or runs /ai-lib-ingest.
allowed-tools: Read Write Edit Bash Glob Grep AskUserQuestion WebFetch Task mcp__claude-in-chrome__navigate mcp__claude-in-chrome__get_page_text
metadata:
  argument-hint: "<path to a .pdf or .txt file; or a folder to ingest one at a time>"
---

# /ai-lib-ingest — A Document into Attributed Claims

The engine of this library. Everything else reads what this skill writes.

One run handles one document. A folder of twenty PDFs is twenty runs — the document page is
the unit of everything here, and a run that writes several cannot report cleanly on any of
them.

Two jobs, and the second is the one that needs discipline:

**Read the document** and record what it claims, with a page locator on every claim.
**Follow its links one hop** and record what they say, quarantined so it can never be
mistaken for what the document said.

Self-contained skill. Its two scripts are resolved with the two-rung ladder, applied
inline in every command block below:

```bash
I="skills/ai-lib-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-ingest"
```

---

## STOP conditions — check these first

Short list, at the top, because this is a long file and the rules that matter get read
last. Each ends the run or bounds it, and each is expanded below.

1. **No library → HALT and create nothing.** If there is no `SCHEMA.md` and no
   `_config/taxonomy.md` at the target root, say: *"There is no library here, so there is
   no taxonomy to file this against. Run `/ai-lib-setup` first — it creates the contract,
   the topic tree and the directories this skill fills."* Do not create `topics/`, do not
   invent a taxonomy, and do not derive a topic from the document. (Step 1)

2. **Every claim carries a marker, without exception.** `[p. N]` when the document says it
   on that page; `[unlocated]` when it says it and you could not pin the page;
   `[link: <url>, accessed <date>]` when a depth-1 linked page says it;
   `[inference: ...]` when you concluded it. **A claim with no marker is the one thing this
   library may not contain** — it is indistinguishable from a traceable one, and the whole
   value of the library is that an answer can be traced. If you find yourself writing a
   sentence you cannot attribute, that is the signal to find the page or drop the sentence.
   (Step 5)

3. **Never fetch a URL that is not in the authorized link plan.** `extract-pdf.py` emits
   the plan; it is the complete and only set of URLs authorized for this document, each
   stamped `depth: 1`. **Never fetch a URL you found on a page you fetched** — record it in
   that capture's `## Not taken` and stop. `/ai-lib-lint` audits every capture against the
   plans and a capture outside them is an error. (Step 4, Step 6)

4. **Linked-page material lives only in `## From Linked Pages`.** Never in `## Key Claims`,
   never in `## Evidence`, never in `## Method`, and never carrying a `[p. N]` locator —
   a linked paper has page numbers too, and a `[p. 4]` on borrowed material makes it
   indistinguishable from the document's own. (Step 6)

5. **A PDF that cannot be extracted is read natively, never approximated.**
   `extract-pdf.py` exits 2 rather than return partial text. Read it with the Read tool. A
   plausible mis-read of a benchmark table is worse than no read, because either way the
   number lands in the library and gets cited. (Step 3)

6. **One leaf, from the taxonomy, never invented.** `_config/taxonomy.md` is the authority.
   `new-page.py` refuses an undefined path and refuses a branch. Where a document fits
   nothing well, file it in the closest leaf, say so plainly in the report, and raise the
   taxonomy question separately. (Step 2)

7. **Never delete, never rename.** A superseded document gets `status: superseded` and a
   `superseded_by`. A revised version of the same work updates `version` in place. (Step 7)

---

## RULES — read before acting

This is a **rigid, prescribed procedure**, not a set of suggestions.

- **This skill is the library's autonomous writer.** Where a source settles a question it
  settles it and logs the decision; it does not defer to a human and does not leave two
  values hoping `/ai-lib-lint` will sort them out. The division of labour is deliberate and
  it is the opposite of what you might assume: **ingest resolves and logs; lint flags and
  never picks a winner.**
- **A claim is what the document asserts, not what is true.** Record a claim you believe is
  wrong exactly as the document makes it, and put your disagreement in `## Open Questions`
  as an `[inference: ...]`. This is a record of what was said.
- **Locate everything you can.** `[unlocated]` is permitted and honest, but it costs the
  page its `extraction_confidence: high` and it is what `/ai-lib-refresh` comes back for.
  Finding the page number is the single highest-value minute in this whole procedure.
- **The document's own names, verbatim** — benchmarks, metrics, methods, models. Every join
  in this library is a string match, and normalizing "MMLU" to its expanded name breaks the
  comparison silently.
- **Ask through AskUserQuestion when you have it, in plain text when you do not, and never
  by taking a default.** Every question here is blocking.
- **Do not restate the contract; apply it.** `SCHEMA.md` at the library root defines the
  frontmatter keys (§ 2), the ten sections (§ 3), the depth-1 rule (§ 6) and the markers
  (§ 7.1). Read it before writing your first page of the run. This file cites its sections
  and deliberately does not copy them.
- **Capture everything of substance.** Where a fact will not fit one of the nine fixed
  sections, it goes under `## Additional capture` with a `###` heading of your choosing and
  a marker. Never drop detail to fit a section — the point of this library is that it is
  the thing you did not have to re-read the PDF for.

---

## Procedure

### Step 1 — Readiness gate, cheap-first

This skill runs many times, so the common case must cost a directory check, not a parse.

1. **`SCHEMA.md` and `_config/taxonomy.md` both present → go to Step 2.**
2. **`taxonomy.md` present, `SCHEMA.md` absent →** proceed, and note in the report that the
   contract file is missing and `/ai-lib-setup` should be re-run. A missing contract is a
   degraded run, not a blocked one.
3. **`taxonomy.md` absent → HALT** with the STOP-1 message. Without it there is no way to
   tell a real topic from an invented one.

Read `_config/library-config.md` if it exists, for `max_links_per_document` and
`link_fetch_delay_seconds`. Absent is fine; note that you are using the defaults (25 links,
2 seconds).

### Step 2 — Identify the document and choose its leaf

1. **Take the path from the argument.** If a folder was named, list the `.pdf` and `.txt`
   files in it and run **one AskUserQuestion call** — header `"Which file"`, question
   `"<N> file(s) here. One document per run — which first?"`, options: up to 4 filenames.
   (multiSelect: false) Then handle that one and offer the rest at the end.

2. **Read enough to place it.** Title, publisher, date, and what it is *about*. Do not read
   the whole thing yet.

3. **Choose the leaf**, and apply the one test that matters (`SCHEMA.md` § 1.2):

   > **Delete every model name from this document. Is it still about something?**
   > Yes → `ai` (or `data-science`, or one of the four under `math-sci-tech-cyber`).
   > No → `llm/<that model>`.

   "How Claude's constitutional training works" is `llm/claude`. "Constitutional AI as a
   method" is `ai`. A technique that merely uses one model as its example is `ai` — the
   technique is the subject.

4. **State the leaf and the reason, in one line, before writing anything.** A wrong
   placement caught here costs a sentence; caught later it costs a `doc_id` and every
   reference to it.

5. **Where two leaves are genuinely arguable**, run **one AskUserQuestion call** — header
   `"Topic"`, question `"This sits between two leaves. Where should it live?"`, options: the
   two candidate paths plus `"File it in the closer one and cross-reference the other"`.
   (multiSelect: false) Do not ask when the answer is clear; most documents have one obvious
   home.

6. **Check for a near-duplicate** before creating anything:
   ```bash
   ls topics/<leaf>/documents/ 2>/dev/null
   grep -rl "<distinctive title fragment>" topics/*/documents/ 2>/dev/null
   ```
   Two pages for one document is the worst outcome this skill can produce: they drift apart
   on the next refresh and then read as a contradiction. If one exists, this is an update
   under `SCHEMA.md` § 8.1, not a new page.

### Step 3 — Extract the text and the link plan

```bash
I="skills/ai-lib-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-ingest"
mkdir -p "raw/<leaf>" output
cp "<source path>" "raw/<leaf>/"
python3 "$I/scripts/extract-pdf.py" "raw/<leaf>/<file>" \
  --doc-slug "<doc-slug>" \
  --out-text "output/_extract-<doc-slug>.txt" \
  --out-plan "output/_linkplan-<doc-slug>.json"
```

**Pass `--doc-slug` matching the slug the page will use.** The linter matches a capture to
its plan by that slug; a plan named after the PDF filename still works, but naming it after
the document makes the audit trail obvious rather than merely functional.

**Exit 2 is a normal outcome, not a failure.** It means `pdftotext` is unavailable, failed,
or the PDF is a scan. Read the file with the **Read** tool — it reads PDFs natively, page by
page — and then **build the link plan by hand**: create the same json shape with every URL
you can see, each stamped `depth: 1`, and record in the report that you built it manually.
Do not skip the plan; without it every capture is unauditable.

**Read the whole document.** Skimming is how a limitation section gets missed, and
`## Limitations` is the most valuable part of a first-party announcement.

**Note what the extractor could not see.** The plan reports
`annotation_only_authorized` — URLs recovered from PDF hyperlink annotations that never
appear in the visible text. It also warns that annotations inside compressed object streams
are invisible to it. Where you read natively and find a hyperlink the plan does not list,
**add it to the plan file and say you added it**. Never fetch an unrecorded URL: the plan is
the audit surface, and an unrecorded fetch defeats it.

Copy the original into `raw/<leaf>/`, never move it. The user's file stays where they put
it.

### Step 4 — Decide which links to follow

Read `output/_linkplan-<doc-slug>.json`. Every entry is authorized at depth 1; **authorized
is not the same as worth following.** Judge each:

| Follow it when | Decline it when |
|---|---|
| it is the paper or post this document builds on | it is a navigation or listing page — a "Publications" index yields only more links |
| it is the code or dataset the document released | its content is plainly restated in the document already |
| it is a benchmark or leaderboard the document cites for a number | it is a bare homepage with no specific content |
| it is a definition or method the document assumes you know | it is behind a paywall or login you cannot pass |
| it materially changes what the document means | it is one of dozens of routine references and you have already followed the substantive ones |

**Follow few, and follow well.** Three well-chosen links beat fifteen skimmed ones: the
budget is your context, and every capture you write is a page someone may later read.
`max_links_per_document` caps the plan at 25; following all 25 is almost never right.

Run **one AskUserQuestion call** where the plan holds more than 8 authorized links —
header `"Links"`, question `"<N> links authorized at depth 1. How far should I go?"`,
options (exactly these four):
`["Follow the substantive ones — papers, code, datasets (recommended)", "Follow only what the document builds on", "Follow all of them", "Skip links entirely — just read the document"]`.
(multiSelect: false) At 8 or fewer, decide yourself and say what you decided.

### Step 5 — Read the document and build the claim list

**Nothing is written yet.** This step is where the page's quality is determined.

1. **Fill the frontmatter from `SCHEMA.md` § 2**, field by field. `publication_type` and
   `authority` are the two that carry the most downstream weight:
   - `authority` is **who is speaking**, not how good it is. An Anthropic post about Claude
     is `first-party` — maximally authoritative on what was built, not at all disinterested
     about how good it is. A third-party evaluation is `secondary`. This field is what lets
     `/ai-lib-query` say *"three sources agree, but all three are the vendor."*
   - Omit an optional key the document does not have. **There is no `TBD` in this contract**
     — a blog post genuinely has no DOI, and that is a fact about the document rather than a
     gap in your knowledge. Knowledge gaps go in `## Open Questions` as `[verify: ...]`.

2. **Build `## Key Claims`.** Aim for three to eight; a document making twenty distinct
   claims usually means the list is recording sentences rather than claims.
   - Numbered continuously, `1.` to `n.`
   - **Every claim carries a locator.** Go find the page. `[unlocated]` is a last resort.
   - One assertion per line.
   - `[type: ...]` on each — and be careful with `forecast`: a prediction about future
     capability is not an empirical result, and conflating the two is how a RAG answer
     becomes actively misleading.

3. **Build `## Evidence`** as a table, using the document's benchmark and metric names
   **verbatim**. Every row needs a locator. **Never compute a number the document did not
   report**, and never carry a baseline across from another document — a baseline belongs to
   the run that produced it.

4. **Write `## Limitations` honestly**, and mark the difference between what the document
   admits (`[p. N]`) and what it simply never addresses
   (`[inference: not addressed]`).

5. **Sanity-check the locators**: a `[p. 40]` on a 12-page document is an error, and the
   linter will catch it. Set `pages` from the extractor's count so it can.

### Step 6 — Follow the links, one hop, and quarantine what comes back

For each link you decided to follow, in order, pausing `link_fetch_delay_seconds` between:

1. **Fetch it with WebFetch.** If what comes back is a page shell, a spinner, an "enable
   JavaScript" notice, or navigation with no content, switch to the Chrome tools
   (`navigate`, then `get_page_text`). Do not retry and do not work from the fragment. Where
   neither is available, write the capture with `fetch_status: js-required` and take nothing
   from it — a capture recording the failure is information; a capture guessing at the
   content is not.

2. **Take only what changes what the document means.** A capture is not a summary of the
   linked page. Two or three lines is a good capture.

3. **Write the capture page:**
   ```bash
   I="skills/ai-lib-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-ingest"
   python3 "$I/scripts/new-page.py" capture --library . --topic "<leaf>" \
     --parent-doc "<doc_id>" --title "<the linked page's title>" \
     --set source_url="<url>" --set link_class=preprint --set authority=preprint \
     --set fetch_status=ok
   ```
   Then fill its three sections. **`## Not taken` is not optional**: list every link you saw
   *on that page*, unfetched. That list is the audit trail proving second-depth links were
   seen and declined rather than never noticed, and an empty one on a page that plainly had
   links is a page nobody looked at.

4. **Fold the content into `## From Linked Pages` on the document page**, one `###`
   subheading per link with the URL in the heading, every bullet carrying
   `[link: <url>, accessed <date>]`.

**The four things that are forbidden here, restated because this is where they happen:**

- A linked page's number in `## Evidence`.
- A linked page's assertion in `## Key Claims`.
- A linked page's method detail in `## Method`, however much better it explains the method.
- A `[p. N]` on anything from a linked page.

**And the one that matters most: never fetch a URL you found on a page you fetched.** It
goes in `## Not taken` and stops there. If it looks important enough to read, it is
important enough to be its own ingest — save it as a PDF and run this skill on it. That is
the sanctioned route from depth 2 to depth 1, and it keeps you in the loop where the design
wants you.

Update the three counts: `links_authorized` from the plan, `links_followed`,
`links_declined`. They must sum, because the plan enumerated exactly that many and each was
either taken or deliberately passed over.

### Step 7 — Write

Now it is mechanical.

**7a — The document page.** For a new document:

```bash
I="skills/ai-lib-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-ingest"
python3 "$I/scripts/new-page.py" document --library . --topic "<leaf>" \
  --title "<Full Title>" \
  --set publication_type=blog-post --set authority=first-party \
  --set publisher=Anthropic --set published=2026-03-14 --set pages=8 \
  --set 'tags=[alignment, training]' --set 'models=[claude-4-5]' \
  --set url="<canonical url>" \
  --source-file "<file>" --source-type pdf --links-authorized 11
```

The script guarantees the shape: every required key present, the ten sections in contract
order, `doc_id` agreeing with the path, the taxonomy path validated, and the counts
initialized to `0`. Pass every value you actually have via `--set`; then write the section
bodies with Edit and correct the counts.

For an **existing** page the script exits 3 and prints the path. That refusal is correct —
and `--force` exists but **do not use it**. It is there for a human repairing a corrupted
page, not for this skill; every legitimate update goes through Edit under the resolution
policy (`SCHEMA.md` § 8.2).

- **A section holding `_None recorded._` is a placeholder — replace it**, do not write beneath it.
- **New substance appends**; a superseded value is edited in place and appears in the log.
- Update `last_updated`, set `updated_by: ai-lib-ingest`.
- **A revised version of the same work** — arXiv v2, an edited post — updates `version` and
  the changed claims **in place**. A genuinely different work is a new page. That is the
  opposite of a per-year rule, and the reason is domain-specific: a v2 is the same work
  corrected, whereas next year's model is a different subject.

**7b — The topic page.** Add a row to `## Key Documents`, bump `document_count`, and — if
this document supports a theme with at least one other document in the leaf — add or extend
a `## Themes` bullet citing both `doc_id`s. **A theme supported by one document is that
document's claim, not a theme**, and the linter enforces the minimum.

### Step 8 — Lint, index, log

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
```

**Read the findings for the page you just wrote, and fix what is yours to fix** — a
mis-stated count, a missing `[type:]`, a locator out of range. Then re-run the linter.

**Do not hand-patch `index.md`.** `index-library.py` rebuilds it wholesale; a second writer
of one file means the two eventually disagree about what the library contains. The index is
now stale, and **a stale index is a normal condition rather than an error** — say so in the
report and point at `/ai-lib-lint`.

Append one entry to `log.md`, omitting any subsection with no entries:

```markdown
## [YYYY-MM-DD] ai-lib-ingest | <Title> -> topics/<leaf> — 6 claims (6 located), 2 benchmarks, 3 of 11 links followed
### Links declined
- 8 of 11 authorized: 5 navigation indexes, 2 already restated in the document, 1 paywalled
### Held
- 1 figure described in prose because the diagram cannot be stored
```

### Step 9 — Report

1. **Where it went, and why that leaf.** One line.
2. **The claim list, with its locators** — this is the substance of the run and the part
   worth reading. Name any `[unlocated]` claim and why the page could not be pinned.
3. **What the links added.** Which you followed, what each contributed, and **which you
   declined and why**. A run that followed nothing is a fine outcome if the links were all
   navigation pages; a run that followed everything usually means nobody chose.
4. **What you saw on those pages and did not fetch** — the second-depth links, counted. This
   is the sentence that proves the hop limit held.
5. **Every `[inference: ...]` and `[verify: ...]`** you wrote, and why.
6. **What the document did not cover** — saying so is what stops someone reading a thin page
   as a complete one.
7. **What the linter said** about this page after your fixes.
8. **Next steps:** `/ai-lib-lint` to rebuild `index.md`; `/ai-lib-ingest` for the next
   file; `/ai-lib-list` once several leaves have material.

Close with the standing caveat, once.

---

## Fan-out

**This skill does not fan out for the write, and that is deliberate.** One run, one
document, one page. Subagents are how `/ai-lib-list`, `/ai-lib-query`, `/ai-lib-compare` and
`/ai-lib-lint` read many leaves at once; ingest is the writer, and a writer split across
subagents produces a claim list nobody can audit. **Fan out to read; funnel to write.**

**One exception, and it is a read.** A document over roughly 40 pages — a long survey, a
thesis, a book chapter — may be parsed by one subagent per major section, each returning:

```json
{"section": "<the document's own section heading>",
 "pages": "<page range read>",
 "claims": [{"text": "<one assertion>", "locator": "[p. N]", "type": "<claim type>"}],
 "evidence": [{"benchmark": "...", "metric": "...", "reported": "...", "baseline": "...", "locator": "[p. N, Table X]"}],
 "limitations": ["<what this section admits, with its locator>"],
 "quotes": [{"text": "<under 50 words, verbatim>", "locator": "[p. N]"}],
 "urls_seen": ["<any URL visible in this section>"]}
```

**Every claim comes back with its locator or it does not come back.** A subagent returning
an unlocated claim has not done the job, because the parent cannot find the page on its
behalf. `urls_seen` feeds back into the link plan, recorded as added.

Collect every result before writing anything, and let the parent do all the writing, all
the conflict resolution and all the logging — one page, one claim list, auditable.

---

## Files in this skill

| File | What it does |
|---|---|
| `scripts/extract-pdf.py` | text out of a PDF (via `pdftotext -layout`) or a txt, **plus the authorized depth-1 link plan** — the artifact the whole hop limit is audited against. Recovers hyperlink-annotation targets the visible text does not show. Exit 2 means "read it natively instead" |
| `scripts/new-page.py` | emits a schema-conformant document, topic or capture skeleton. Refuses an undefined topic, refuses a branch, refuses to overwrite (exit 3) |

Executed, never loaded into context. Run them by path; never inline, retype or rewrite one.
The shipped file is the single source of truth for what gets extracted and what gets
authorized, and an edited copy silently changes the result. If a script is missing, say so
and stop — do not reconstruct it.

This skill also calls `lint-library.py` from `skills/ai-lib-lint/scripts/`.

---

## Anti-patterns

- Do not write a claim without a marker. It is indistinguishable from a traceable one, and it destroys the only property that makes this library worth having.
- Do not write `[p. N]` on anything that came from a linked page. A linked paper has page numbers too, and this is the specific error that makes borrowed material read as the document's own.
- Do not put a linked page's number in `## Evidence`, its assertion in `## Key Claims`, or its method detail in `## Method`. `## From Linked Pages` is the only destination.
- Do not fetch a URL you found on a page you fetched. Record it in `## Not taken` and stop. If it matters, save it and ingest it — that is the route from depth 2 to depth 1.
- Do not fetch a URL that is not in the authorized link plan. If you found one the extractor missed, add it to the plan and say you added it.
- Do not leave `## Not taken` empty on a page that plainly had links. That list is the proof the hop limit held.
- Do not follow all 25 authorized links because they are authorized. Authorized is not worth following; three well-chosen beat fifteen skimmed.
- Do not follow a navigation or listing page. It yields only more links and burns a hop for no substance.
- Do not record a claim as the document's when it is your conclusion. `[inference: ...]` exists, and it states the derivation, not merely that one occurred.
- Do not record what you think is true. Record what the document says, and put the disagreement in `## Open Questions`.
- Do not settle for `[unlocated]` without looking. Finding the page number is the highest-value minute in this procedure.
- Do not compute a number the document did not report, and do not carry a baseline across from another document.
- Do not normalize a benchmark or metric name. Every join in this library is a string match; "MMLU" expanded is a row that no longer joins.
- Do not type a `forecast` claim as `empirical`. A prediction about future capability is not a result, and conflating them makes an answer actively misleading.
- Do not file a document at a path the taxonomy does not define, or on a branch topic. `new-page.py` refuses both, and the refusal is correct.
- Do not file model-agnostic work in `llm/<model>`, or model-specific work in `ai`. Delete every model name and see what is left.
- Do not create a second page for a document the library already has. Two pages for one document drift apart and then read as a contradiction.
- Do not use `new-page.py --force`. It is for a human repairing a corrupted page, not for this skill.
- Do not write beneath a `_None recorded._` placeholder. Replace it.
- Do not create a new page for a revised version of the same work. Update `version` and the changed claims in place; only a genuinely different work is a new page.
- Do not approximate a PDF you could not extract. Read it natively. A plausible mis-read of a benchmark table gets cited exactly like a correct one.
- Do not work from a WebFetch result that came back as a page shell. Switch to the Chrome tools, or record `fetch_status: js-required` and take nothing.
- Do not write a capture that summarizes a linked page. Take only what changes what the document means; two or three lines is a good capture.
- Do not hand-patch `index.md`. `index-library.py` rebuilds it wholesale.
- Do not write a `## Themes` bullet supported by one document. That is that document's claim.
- Do not ingest two documents in one run. The claim list and the log entry both stop being auditable.
- Do not fan out to write. One page, one claim list, auditable.
- Do not accept a subagent claim with no locator. The parent cannot find the page on its behalf.
- Do not skip the report's second-depth count. It is the sentence that proves the hop limit held, and nothing else in the run says it.
