---
name: ai-lib-refresh
description: >-
  Re-check what the ai-lib library already holds: find newer versions of stored documents, go
  after claims still marked unlocated, re-fetch dead depth-1 links, and triage what has gone
  stale in a field that moves monthly. Reports what changed and what a stored answer would now
  say differently. Use when the user says "is this still current", "check for newer versions",
  "what's gone stale", "fix the unlocated claims", "re-check the links", or runs
  /ai-lib-refresh.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion WebFetch mcp__claude-in-chrome__navigate mcp__claude-in-chrome__get_page_text
metadata:
  argument-hint: "(no arguments for the whole library; or a topic path to refresh one leaf)"
---

# /ai-lib-refresh — Re-check, Locate, Triage

Three jobs that share a mechanism, in descending order of how often they matter:

**Staleness.** Most of this library is blog posts and announcements about a field that moves
monthly. An `llm/*` document from eighteen months ago is not merely old — read as current, it
is wrong. This skill is how a library stops quietly rotting.

**Locators.** Every `[unlocated]` claim is a claim nobody can check. The source is sitting in
`raw/`, so the page number is recoverable — it just takes reopening the file. This is the
highest-value repair in the whole family, and no other skill does it.

**Dead links.** A depth-1 capture recorded a URL and a date. The URL may 404 now, or the page
may have been edited since. Either is a fact worth recording.

It is `/ai-lib-ingest` pointed at what the library already knows, and it inherits the same
doctrine: **it resolves and logs; it does not defer.** What it cannot settle, it marks.

Ladders, applied inline in every command block:

```bash
L="skills/ai-lib-lint";   [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
I="skills/ai-lib-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-ingest"
```

---

## STOP conditions — check these first

1. **Nothing to refresh → say so and stop.** No documents, or no document carrying a
   `source_file`, a `url` or an `[unlocated]` claim. *"Nothing here can be re-checked: no
   document records a source I can go back to."* A library whose pages have no recorded origin
   cannot be refreshed, only re-ingested — and saying that plainly is more useful than
   refreshing nothing.

2. **Never invent a locator.** This skill exists to *find* page numbers by reopening the file
   in `raw/`. Where the file is gone, or the claim genuinely is not in it, the claim stays
   `[unlocated]` and that is recorded as "re-checked, still unlocated" so nobody re-checks it
   next month for nothing. **A fabricated `[p. 7]` is worse than `[unlocated]`, because it
   looks traceable.** (Step 4)

3. **A stale document is not a wrong document.** Staleness is never grounds for
   `status: superseded`, for editing a claim, or for deleting anything. It is grounds for
   looking for a successor and for saying so in the report. (Step 5)

4. **A dead link is a finding, not a licence.** A 404 does not permit inferring what the page
   used to say, and it does not permit finding a different page and treating it as the same
   source. Set `fetch_status`, note the date, report it. (Step 6)

5. **Never fetch a URL that is not in a link plan.** Re-fetching an existing capture's URL is
   authorized — it is already in the plan. **A URL you find on that page today is still a
   second hop** and still goes in `## Not taken`. The refresh does not widen the crawl.
   (Step 6)

6. **A newer version is an in-place update; a different work is a new page.** `SCHEMA.md`
   § 8.1. An arXiv v2 or an edited post updates `version` and the changed claims on the
   existing page. A follow-up paper, a next model's card, a substantially rewritten post at a
   new URL is a new page and a `supersedes` link. Getting this backwards either destroys the
   record or duplicates it. (Step 5)

7. **Never overwrite without logging.** Old value, new value, both sources, the deciding rule.
   This is the skill most likely to overwrite a claim someone already read and cited; the log
   is the only place they can catch it. (Step 7)

---

## RULES — read before acting

- **Diff before you write, and for the whole page at once.** You cannot decide what to
  overwrite until you know what the page says, and you cannot decide that one claim at a time
  while a PDF scrolls past.
- **Resolution policy, unchanged** (`SCHEMA.md` § 8.2): higher `authority` wins on intent and
  implementation; an independent source can win on performance; at equal authority the newer
  `published` date wins, except that a document about an earlier version never overwrites one
  about a later version; where neither dominates, keep both under `### Unresolved` and log it.
- **Elaboration is not conflict.** A source that now states something the page had as
  `[unlocated]`, or adds a limitation, is a refinement — write it, and it is the best thing
  that happens in this skill.
- **The document's own names, verbatim**, still. A benchmark renamed during a refresh is a
  join broken during a refresh.
- **Ask through AskUserQuestion when you have it, in plain text when you do not.**
- **Do not restate the contract; apply it.**

---

## Procedure

### Step 1 — Build the work plan

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
```

From `output/_library-data.json`, build four lists. They are the whole run:

1. **Unlocated claims** — every document where `located_claim_count < claim_count`, and every
   `CONF-HIGH-UNLOCATED` finding. Cross-reference `raw/` to see which of them still have their
   source file. **This is the list that makes the run worth doing**, because a locator found
   here is a claim that becomes citable forever.
2. **Stale documents** — every `AGE-STALE`, grouped by leaf. For `llm/*` at 270 days this is
   often most of the leaf; that is the point of the shorter threshold, not a fault.
3. **Re-fetchable captures** — every capture with a `source_url`, with its `accessed` date and
   `fetch_status`. Note any already marked other than `ok`.
4. **Documents with a checkable upstream** — every document carrying a `url`, `arxiv_id` or
   `doi`. Those are the ones where a newer version can actually be looked for.

**Say what you found, in one short paragraph, before fetching or reading anything.** *"87
documents. 14 claims across 6 documents are unlocated and all 6 still have their PDF. 31
documents are past their staleness threshold, 24 of them in `llm/`. 41 captures, 3 already
marked not-found. 52 documents have a checkable URL."* That paragraph is what lets someone
redirect the run before it spends real work.

### Step 2 — Decide the scope

If the argument named a topic path, limit to that leaf. Otherwise run **one AskUserQuestion
call** — header `"Refresh"`, question `"<N> unlocated claims, <M> stale documents, <K>
re-fetchable links. What should I go after?"`, options (exactly these four):
`["Locators first — find the page numbers (recommended)", "Staleness — look for newer versions of the oldest", "Links — re-check every stored URL", "Everything, in that order"]`.
(multiSelect: false) The free-text field takes a topic path where the user wants one leaf; do
not add an option that says so.

**Locators first is the recommended default because it is the only irreversible win here.** A
page number found today stays found; a staleness check has to be repeated next quarter
regardless.

**Below three items in every list, ask nothing and do all of it.** A question whose every
answer is "do the work" is a question not worth asking.

### Step 3 — Skip. (Reserved; the numbering matches the family's other skills.)

### Step 4 — Find the locators

For each document with unlocated claims and a surviving source file:

```bash
I="skills/ai-lib-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-ingest"
python3 "$I/scripts/extract-pdf.py" "raw/<leaf>/<file>" \
  --doc-slug "<doc-slug>" --out-text "output/_relocate-<doc-slug>.txt"
```

Exit 2 means read it natively with the Read tool. Same rule as ingest: **do not approximate.**

Then, for each `[unlocated]` claim:

1. **Search the extracted text for the claim's distinctive phrasing.** The claim was written
   from the document, so its wording is usually close to the document's.
2. **Where you find it, replace `[unlocated]` with the real locator** — `[p. N]`, and add a
   table or figure reference where the claim rests on one.
3. **Where you cannot find it, leave `[unlocated]` and record the attempt** under
   `## Additional capture` as `### Refresh notes`: *"claim 4 re-checked against
   constitutional-ai.pdf on 2026-08-26, phrasing not located in the text."* That line is what
   stops the next run repeating the same failed search.
4. **Where the claim is not in the document at all**, that is a much more serious finding than
   a missing page number: the claim was mis-attributed. Do not delete it — mark it
   `[verify: not located in the source on re-check; may be mis-attributed]` and name it
   prominently in the report.

Update `located_claim_count`, and re-evaluate `extraction_confidence`: a page whose every
claim is now located, from an official source, is `high`. **This is the one field a refresh
should routinely improve, and leaving it stale understates the library.**

### Step 5 — Triage staleness and look for successors

For each stale document with a checkable upstream, in age order:

1. **Fetch its `url`** (or the arXiv abstract page for its `arxiv_id`) with WebFetch. Switch to
   the Chrome tools if a page shell comes back. Where neither works, record the document as
   un-rechecked this run — **an un-rechecked document is a gap in the report, not a licence to
   leave the stored page looking freshly verified.**

2. **Five outcomes, each with one correct handling:**

   | Outcome | What to do |
   |---|---|
   | **Unchanged** | nothing. **Do not touch `last_updated`** — a refreshed timestamp on an unchanged page is a lie about when the content was verified. Record it as re-checked in the log only |
   | **A newer version of the same work** — arXiv v2, an edited post at the same URL | update `version`, update the claims that changed, log each. Same page (§ 8.1) |
   | **A successor work** — a follow-up paper, the next model's card | do **not** edit this page. Report it as a candidate for `/ai-lib-ingest`, with its URL. When ingested, link `supersedes` / `superseded_by` |
   | **Withdrawn or retracted** | `status: superseded`, a `superseded_by` if there is one, and a line in `## Additional capture` saying what happened. Never delete |
   | **404 or moved** | the upstream is gone. Note it under `### Refresh notes` with the date and the response. Change no claim — **the page is still a valid record of what the document said** |

3. **A stale document with no newer version is a normal and useful outcome.** Record
   "re-checked <date>, no successor found" so the next run knows. Foundational work stays
   foundational; a two-year-old transformer paper is not stale in the way a two-year-old model
   announcement is, which is why the thresholds differ by topic.

### Step 6 — Re-check the links

For each capture with a `source_url`, oldest `accessed` first:

1. **Re-fetch the URL.** It is already in the parent's link plan, so this is authorized.

2. **Update `fetch_status` and `accessed`.** A page that was `ok` and now 404s becomes
   `not-found`, and that is recorded rather than hidden.

3. **Where the page changed materially**, update the `## From Linked Pages` items it supports
   on the parent document, keeping the `[link: ...]` marker and **bumping its access date**.
   An undated or wrongly-dated web claim cannot be re-verified.

4. **Where the page is gone**, leave the material in place with its original access date and
   add a line to the capture's `## Metadata`: *"re-checked <date>, 404."* The claim was true of
   a page that existed; that remains a fact.

5. **Every link you see on the re-fetched page goes in `## Not taken`, unfetched.** The refresh
   does not widen the crawl. A URL that was a second hop last month is a second hop today.

### Step 7 — Write and log

Same mechanics as `/ai-lib-ingest` Step 7. Update `last_updated` and set
`updated_by: ai-lib-refresh` **only on pages that actually changed**.

Then re-lint and regenerate the index, because the tree moved:

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
python3 "$L/scripts/index-library.py" --data output/_library-data.json --library .
```

Append one entry to `log.md`, omitting any subsection with no entries:

```markdown
## [2026-08-26] ai-lib-refresh | all topics — 9 locators found, 3 still unlocated, 2 versions updated, 4 successors found, 3 dead links, 31 stale re-checked

### Locators found
- `topics/ai/documents/constitutional-ai.md` · claim 4 · [unlocated] -> [p. 22] — located in constitutional-ai.pdf

### Still unlocated after re-check
- `topics/ai/documents/constitutional-ai.md` · claim 6 — re-checked 2026-08-26, phrasing not found in the source

### Values updated in place
- `topics/llm/claude/documents/claude-4-5-system-card.md` · claim 2 · "30% fewer refusals" [p. 4] -> "34% fewer refusals" [p. 4] — v2 of the card, same URL

### Successors found (not ingested)
- `topics/llm/gpt/documents/gpt-5-eval.md` — a v2 exists at <url>; candidate for /ai-lib-ingest

### Dead links
- `topics/ai/captures/constitutional-ai__example-org-method.md` — 404 on 2026-08-26, fetch_status not-found

### Unresolved
- `topics/ai/documents/x.md` · claim 3 — vendor and independent source disagree, both retained
```

### Step 8 — Report

Lead with what changed, because that is what someone ran this for.

1. **Locators found**, by document and claim. The quiet win, and the durable one.
2. **Still unlocated after an honest attempt**, and where you looked — this is what stops the
   next run repeating it. Flag separately and prominently **any claim that could not be found
   in its source at all**, because that is a possible mis-attribution rather than a missing
   page number.
3. **What changed in a document**, as old value → new value with both locators and the
   deciding rule. Every in-place overwrite, explicitly: nobody approved these before they
   landed.
4. **Successors found but not ingested**, with URLs — a ready-made worklist for
   `/ai-lib-ingest`.
5. **Staleness after the run**, by leaf: how many re-checked, how many have a successor, how
   many are foundational and fine. **Say plainly which stale documents are fine** — a
   two-year-old method paper is not the same problem as a two-year-old model announcement, and
   a report that treats them alike trains the user to ignore it.
6. **Dead links**, and what now has no live origin.
7. **Confidence changes**, both directions.
8. **What a stored answer would now say differently.** One or two sentences. *"Three saved
   answers in `synthesis/` cite claim 2 of the Claude 4.5 card, which now reads 34% rather
   than 30% — worth re-reading if you acted on any of them."* Nothing else in the report says
   this, and it is the reason the refresh was worth running.

Close with the standing caveat, once.

---

## Fan-out

**Two leaves or fewer: no fan-out** — the same threshold as every other skill in this family.
Above that, **one subagent per leaf** for the *reading*, never for the write:

> You are the master of `topics/<leaf>/`. Read `SCHEMA.md`, then every document page in your
> leaf. Here is the freshly extracted text for the source files in this leaf: `<paths>`.
> **Read nothing outside your leaf. Write nothing.**
>
> For each document with `[unlocated]` claims, search the extracted text and return JSON:
>
> ```json
> {"topic":"<leaf>","documents":[{
>   "doc_id":"<verbatim>",
>   "located":[{"claim_n":4,"was":"[unlocated]","now":"[p. 22]","source_phrase":"<the exact sentence from the document that carries this claim>"}],
>   "still_unlocated":[{"claim_n":6,"searched_for":"<the phrasing you looked for>"}],
>   "not_in_source":[{"claim_n":9,"why":"<no sentence in the document supports this claim>"}],
>   "suspect":[{"claim_n":2,"why":"<why the stored claim looks like a mis-read of the source>"}]
> }]}
> ```
>
> Rules: **quote the source phrase for every locator you found** — the parent decides whether
> to write it and needs to see what it is deciding from; never invent a page number; a claim
> you cannot find goes in `still_unlocated`, and one that appears to be absent from the
> document entirely goes in `not_in_source`, which is a much more serious finding; `doc_id`
> and claim numbers verbatim.

`not_in_source` is why this fan-out is worth running: a claim nobody can find in its own
source is the most serious defect this library can develop, and only a careful re-read
surfaces it.

**Collect every result before writing anything.** The parent does all the writing, all the
conflict resolution, all the confidence re-evaluation and all the logging — one change list,
one log entry, auditable. **Fan out to read; funnel to write.**

---

## Files in this skill

No scripts of its own. It borrows three:

| Script | From | Used for |
|---|---|---|
| `lint-library.py` | `skills/ai-lib-lint/scripts/` | Step 1's work plan, and the re-lint in Step 7 |
| `index-library.py` | `skills/ai-lib-lint/scripts/` | Step 7, after the tree moved |
| `extract-pdf.py` | `skills/ai-lib-ingest/scripts/` | Step 4, re-reading a source to find a page number |

Run all three by path; never inline or rewrite one.

---

## Anti-patterns

- Do not invent a locator. This skill exists to find them by reopening the file; a fabricated `[p. 7]` is worse than `[unlocated]` because it looks traceable.
- Do not leave a failed search unrecorded. "Re-checked <date>, not located" is what stops the next run repeating it.
- Do not treat a claim that is absent from its own source as a missing page number. That is a possible mis-attribution and it goes at the top of the report.
- Do not set a stale document to `superseded`. Staleness is grounds for looking for a successor, nothing else.
- Do not edit a page because a successor exists. Report the successor for `/ai-lib-ingest`; a successor is a new page and a `supersedes` link.
- Do not create a new page for an arXiv v2 or an edited post at the same URL. That is the same work corrected: update `version` in place.
- Do not touch `last_updated` on a page that did not change. A refreshed timestamp on unchanged content is a lie about when it was verified.
- Do not infer what a 404'd page used to say, and do not find a different page and treat it as the same source. A different document is a new source with its own authority, date and receipt.
- Do not delete a capture whose URL is dead. The claim was true of a page that existed; that remains a fact.
- Do not fetch a URL you find on a re-fetched page. The refresh does not widen the crawl — a second hop last month is a second hop today.
- Do not forget to bump the access date on a `[link: ...]` claim you updated. An undated or wrongly-dated web claim cannot be re-verified.
- Do not rename a benchmark during a refresh. A renamed benchmark is a broken join.
- Do not overwrite a claim without logging old, new, both sources and the deciding rule. This is the skill most likely to overwrite something someone already cited.
- Do not leave `extraction_confidence` stale on a page you improved. It is the one field a refresh should routinely raise.
- Do not report every stale document as a problem. A two-year-old method paper is not a two-year-old model announcement, and treating them alike trains the user to ignore the report.
- Do not report a document as verified when you could not fetch its upstream. An un-rechecked document is a gap in the report.
- Do not fan out to write. One change list, one log entry, auditable.
- Do not accept a subagent's locator without its quoted source phrase. The parent decides, and it needs to see what it is deciding from.
- Do not begin writing before every subagent has returned.
- Do not approximate a PDF you could not extract. Read it natively.
- Do not bury the locators found. They are the durable win, and the only irreversible one in this skill.
- Do not omit the sentence about what a stored answer would now say differently. Nothing else in the report says it, and it is why the refresh was worth running.
