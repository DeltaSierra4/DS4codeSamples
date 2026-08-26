---
name: ai-lib-list
description: >-
  Build a browsable HTML catalog of the whole ai-lib document library, grouped by topic, with
  search across claims, filters by type, authority and staleness, and every provenance marker
  rendered distinctly. Fans out one subagent per leaf topic — each the master of its own topic
  — for the narrative the frontmatter cannot hold, then joins it to the deterministic counts on
  doc_id. Use when the user says "what's in my library", "show me everything", "build the
  catalog", "list what I have by topic", or runs /ai-lib-list.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion
metadata:
  argument-hint: "(no arguments — reads the whole library; optionally a topic path to limit it)"
---

# /ai-lib-list — Every Document, Grouped by Topic

Produces `output/library.html`: one self-contained page, no server, no CDN, that answers
"what have I got" and "where is that thing about X" without opening a single PDF.

The architecture is the point:

- **The counts are deterministic.** `lint-library.py` walks the tree and `build-library.py`
  renders what it found. No language model retypes a claim count or a publication date.
- **The narrative is delegated.** One subagent per leaf topic writes the prose the
  frontmatter cannot hold — what this topic is collectively about, why a document is worth
  reading, what to distrust about it.
- **The two are joined on `doc_id`**, and where they disagree, the data wins and the note is
  shown beside it.
- **Provenance stays visible.** Every claim renders with its marker, and the four kinds
  render differently. A claim with no marker renders as a loud red badge rather than as plain
  text, because that is the one thing the library may not contain.

Both ladders, applied inline in every command block below:

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
C="skills/ai-lib-list"; [ -d "$C/scripts" ] || C="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-list"
```

---

## STOP conditions — check these first

1. **No documents → say so and stop, without ceremony.** *"The library has no documents yet,
   so there is nothing to catalog. Run `/ai-lib-ingest` with a PDF."* An empty library is not
   an error. Do not build an empty HTML file to prove the pipeline works.

2. **Collect every subagent result before building.** A partial fan-out produces a catalog
   missing a topic's narrative — and worse, one that looks complete. (Step 3)

3. **Subagents read; they never write.** No subagent here edits a page, touches `index.md`,
   appends to `log.md`, or runs a script. They return structured text; the parent writes.
   (Step 3)

4. **Never let a note contradict the data.** A subagent reporting a claim count or a date
   different from the frontmatter has misread its own page. Keep the frontmatter value, drop
   the claim, and name the discrepancy in the report — it is a real finding about that page.
   (Step 4)

5. **Never write narrative for a page that has none.** A document whose `## Snapshot` is a
   placeholder gets no `why_read` line. The catalog renders that honestly, and a manufactured
   recommendation is worse than a blank field.

---

## RULES — read before acting

- **The leaf topic folder is the unit of parallelism.** Everything a subagent needs to become
  the master of one topic is inside that leaf and nowhere else. That is why the layout is what
  it is: a per-leaf subagent has a naturally bounded context and cannot contaminate one
  topic's material with another's.
- **Fan out by leaf, never by document, and never "N agents, split the work".**
- **The linter is the source of truth for what exists.** The fan-out is for narrative; if a
  subagent's document list disagrees with the linter's, the linter is right and the
  disagreement is a finding.
- **Do not restate the contract; apply it.** `SCHEMA.md` § 3.1 defines what `## Snapshot` and
  `## Key Claims` hold, and the subagent brief cites it rather than copying it.
- **Ask at most one question, and only where there is something to decide.**

---

## Procedure

### Step 1 — Walk the library

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
```

The stderr receipt gives you the shape: leaves, documents, captures, claims and how many are
located, plus the two counts that matter — **claims unmarked** and **captures
unauthorized**. Read `output/_library-data.json` for `topics[]`, `documents[]`, `shares` and
`counts`. **That is your inventory, and it is the only inventory** — do not glob `topics/`
yourself.

Note the `error`-severity finding count. You will surface it in the catalog and in the report;
you will not fix it here — that is `/ai-lib-lint`'s job.

### Step 2 — Decide the scope, if there is anything to decide

If the argument named a topic path, limit to it and its descendants.

Otherwise: if the library holds documents in **six or more leaves**, run **one
AskUserQuestion call** — header `"Scope"`, question `"<N> leaves hold documents. Catalog all
of them?"`, options (exactly these three):
`["All topics", "All topics, active documents only", "Include superseded documents too — I want the history"]`.
The free-text field takes a topic path where the user wants to narrow it; do not add an option
that says so. (multiSelect: false)

Below six leaves, ask nothing and catalog everything.

Superseded documents are **excluded by default**. Pass `--include-superseded` only if asked —
a catalog mixing withdrawn material into the live list is how someone cites a retracted
document.

### Step 3 — Fan out, one subagent per leaf

**Threshold.** Two leaves with documents or fewer: read the pages inline and write the notes
yourself. More than two: fan out, **one subagent per leaf that holds documents** —
`topics/ai/`, `topics/llm/claude/`, `topics/data-science/`, and so on. One agent per leaf,
however many documents it holds. Never one agent per document, and never a fixed number of
agents dividing the list. Skip empty leaves entirely; there is nothing for an agent to master.

**The brief.** Send each subagent this, substituting the leaf:

> You are the master of one topic in a document library: `topics/<leaf>/`. Read
> `topics/<leaf>/topic.md` and every file in `topics/<leaf>/documents/`. Read `SCHEMA.md` at
> the library root first — § 3.1 on what each section holds, § 2.2 on what `authority` means.
> **Read nothing outside your own leaf folder.** Do not write, edit or create any file.
>
> Return exactly this JSON and nothing else:
>
> ```json
> {
>   "topic": "<leaf path>",
>   "positioning": "<one or two sentences: what this topic collectively covers, as evidenced by what is actually in it. Not what the topic could contain — what it does. Ground it in a specific document or a specific recurring subject.>",
>   "themes": "<what two or more documents here agree on, or contest. Cite the doc_ids. Empty string if fewer than two documents support any theme.>",
>   "gaps": "<what someone reading this topic would expect to find and would not. Empty string if you cannot say.>",
>   "documents": [
>     {
>       "doc_id": "<verbatim from the page frontmatter>",
>       "one_liner": "<under 100 characters. Why this document is worth opening, not what it is. 'The only source here that reports a compute cost' beats 'A paper about training'.>",
>       "why_read": "<one or two sentences: what a reader gets from this that the other documents here do not>",
>       "caveat": "<what to distrust about it — first-party optimism, an old benchmark, a claim with no locator, a limitation section that is missing. Empty string if there is genuinely nothing.>"
>     }
>   ],
>   "defects": ["<any page problem worth a human's attention: a claim with no marker, linked material reading as the document's own, a section that is still a placeholder>"]
> }
> ```
>
> Hard rules:
>
> - **Every claim you make traces to something on the page you read.** If you cannot point at
>   it, leave the field an empty string. An empty field renders honestly; an invented one
>   does not.
> - **Never state a count, a date or a benchmark number.** The catalog gets those from the
>   frontmatter directly and will contradict you visibly if you guess.
> - **A page whose `## Snapshot` is `_None recorded._` gets an empty `one_liner` and an empty
>   `why_read`.** Do not write the snapshot the page is missing — say nothing, and the report
>   will name the gap.
> - **`caveat` is the most valuable field here.** A first-party announcement's caveat is that
>   it is first-party. An old benchmark's caveat is its date. Say it plainly.
> - **Never compare to another topic.** You cannot see the other leaves, and a cross-topic
>   claim nobody can check is exactly the contamination the folder boundary prevents.
> - **`doc_id` verbatim.** It is the join key. A retyped id silently drops that document's
>   whole narrative.

**The barrier.** Collect every result before merging any of them. A partial merge produces a
catalog where one topic is mysteriously terse, which reads as a thin topic rather than as a
failed subagent.

**A subagent that returns nothing usable** is reported and its leaf is catalogued from counts
alone. Say so. The catalog is complete without the narrative — just drier — which is why this
fan-out is not load-bearing.

### Step 4 — Merge the notes

Write `output/_library-notes.json`:

```json
{
  "topics":    [ { "topic": "...", "positioning": "...", "themes": "...", "gaps": "..." } ],
  "documents": [ { "doc_id": "...", "one_liner": "...", "why_read": "...", "caveat": "..." } ]
}
```

Three checks before you write it, each catching a real failure mode:

1. **Every `doc_id` exists in `output/_library-data.json`.** One that does not was
   reconstructed rather than copied; drop it and name it in the report.
2. **No note states a count, a date or a number.** Drop the claim, keep the data, report the
   page — a subagent that invented a figure needs its other returns looked at.
3. **No `positioning` or `themes` mentions another topic.** Drop the cross-reference; the
   subagent read outside its bounds or guessed.

`build-library.py` reads exactly the keys above and ignores anything else, so the subagents'
`defects` arrays do not go in the file. **They go in the Step 7 report instead** — a leaf
master naming the pages with holes is the most actionable thing the fan-out produces, and
dropping it because the HTML has no column for it would waste the one pass that collected it.

### Step 5 — Build

```bash
C="skills/ai-lib-list"; [ -d "$C/scripts" ] || C="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-list"
python3 "$C/scripts/build-library.py" \
  --data output/_library-data.json \
  --notes output/_library-notes.json \
  --out output/library.html
```

The notes file is optional; without it the catalog builds from counts alone and says so.

What the generated page does, so you can describe it accurately rather than guess: one
section per topic in taxonomy order with branches nesting their leaves; per-topic share
against expected; a click-to-expand claim list per document showing **every claim with its
marker**; filters for topic, publication type and authority; a hide-stale toggle; an
only-pages-with-problems toggle; an expand-all-claims toggle; full-text search across titles,
snapshots and **claim text**; and `/` to focus search.

**The four markers render distinctly and are never collapsed** — a page locator, an
`[unlocated]`, a `[link: ...]` and an `[inference: ...]` are four different epistemic states,
and a claim with no marker renders as a red `none` badge.

### Step 6 — Open it, and prove that you did

```bash
OUT="$(cd output && pwd)/library.html"
[ -f "$OUT" ] && echo "$OUT" || echo "MISSING: $OUT"
case "$(uname -s 2>/dev/null)" in
  Darwin) open "$OUT" ;;
  Linux)  xdg-open "$OUT" >/dev/null 2>&1 & ;;
  *)      start "" "$OUT" ;;
esac
```

Resolve to an absolute path, verify it exists, then open it and print the path alongside. A
silent no-open is the exact bug to avoid. **In Cowork, always also present the file** — the OS
opener cannot reach the user's desktop from a sandboxed session.

### Step 7 — Log and report

Append one line to `log.md`:

```markdown
## [2026-08-26] ai-lib-list | catalog rebuilt — 14 leaves, 87 documents, 312 claims (298 located), 41 captures
```

Then report, briefly:

1. **The path to the catalog**, and that it is a snapshot — regenerate after each ingest.
2. **The shape**: leaves with documents, document count, claim count and how many are located,
   and the two or three largest leaves. Numbers, from the data.
3. **What is untraceable**: the unmarked claim count and which pages, plus the leaf masters'
   `defects` lists. This is the most actionable part of the report and the HTML has no column
   for it.
4. **Share drift**, where any topic is more than `drift_report_threshold` off its expected
   share. **Drift is information, not an error** — a topic near zero usually means its material
   is being filed somewhere else, which is worth knowing; a topic well over its share usually
   means the expected share was a guess, and reality is right.
5. **What is thin**: leaves with no documents, pages that are still stubs, topics whose
   subagent found no themes.
6. **What is stale**, by leaf, with a pointer to `/ai-lib-refresh`.
7. **Next steps**: `/ai-lib-query` to ask the library something, `/ai-lib-compare` for two
   documents side by side.

Close with the standing caveat, once. It is already on the page; say it in chat too, because
the chat is where the impression forms.

---

## Files in this skill

| File | What it does |
|---|---|
| `scripts/build-library.py` | joins the linter's json to the notes json on `doc_id` and emits one self-contained HTML file. Splits each claim into prose + marker so the four marker kinds can render distinctly. Stdlib only |
| `scripts/library-template.html` | the HTML/CSS/JS shell. Two `{{...}}` placeholders, `{{TITLE}}` and `{{LIBRARY_DATA}}`; the data island is substituted last so page content carrying a literal `{{TITLE}}` cannot be substituted into |

Plus `lint-library.py` from `skills/ai-lib-lint/scripts/`, because it is the family's single
tree walker. Run all of them by path; never inline or rewrite one.

---

## Anti-patterns

- Do not glob `topics/` to build your inventory. The linter's json is the inventory, and two inventories eventually disagree.
- Do not fan out by document page. One subagent per leaf, however many documents it holds.
- Do not fan out below the threshold, and do not spawn an agent for an empty leaf.
- Do not begin the merge before every subagent has returned. A partial merge makes a failed subagent look like a thin topic.
- Do not let a subagent read another leaf or make a cross-topic claim. The folder boundary is what makes the fan-out safe.
- Do not let a subagent write anything. Fan out to read, funnel to write.
- Do not accept a note that states a count, a date or a benchmark number. Keep the data, drop the claim, report the page.
- Do not accept a `doc_id` that is not in the linter's json. It was reconstructed, and it drops that document's whole narrative.
- Do not write a `one_liner` for a page whose snapshot is a placeholder. An empty field renders honestly.
- Do not drop the subagents' `defects` lists. They do not belong in the notes file, and they are the most actionable thing the fan-out produces.
- Do not include superseded documents by default. Mixed into the live list, they are how someone cites a retracted document.
- Do not collapse the four provenance markers into one rendering. They are four different epistemic states.
- Do not render an unmarked claim as plain text. It gets a red badge, because it is the one thing the library may not contain.
- Do not present share drift as an error. A topic near zero means its material is going elsewhere; a topic over its share means the guess was wrong.
- Do not fix a lint finding here. Surface the count and point at `/ai-lib-lint`.
- Do not build an empty catalog to demonstrate the pipeline. Say the library is empty and point at `/ai-lib-ingest`.
- Do not assume a relative path opens. Resolve to absolute, verify, open, print the path.
- Do not describe the catalog's features from memory. They are listed in Step 5.
- Do not paste the catalog's contents into chat. Link the file, then say the shape, what is untraceable, and what to do next.
