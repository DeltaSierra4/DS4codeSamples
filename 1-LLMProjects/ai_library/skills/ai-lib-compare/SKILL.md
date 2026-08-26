---
name: ai-lib-compare
description: >-
  Put two or more documents from the ai-lib library side by side, with their benchmark tables
  joined deterministically on the exact (benchmark, metric) pair and every disagreement
  flagged with both numbers and both locators. Lays out claims by type with provenance markers
  intact, and says plainly when every source is first-party or every source is stale. Use when
  the user says "compare these", "how do these differ", "do these agree", "which of these
  says what about X", or runs /ai-lib-compare.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion
metadata:
  argument-hint: "(two or more doc_ids or titles, comma-separated; omit for interactive selection)"
---

# /ai-lib-compare — Documents Side by Side, Benchmarks Joined

Produces `output/compare-<date>.html`: a benchmark join, a metadata matrix, and every claim
laid out by type with its marker intact.

**The benchmark join is the point, and it is deterministic.** Documents are joined on the
exact normalized (benchmark, metric) pair from their `## Evidence` tables. Where two documents
report the same benchmark and metric with different numbers, that is flagged as a
disagreement — both numbers, both locators, both authorities. Two sources reporting different
MMLU scores for the same model is exactly the finding a library like this exists to surface,
and it is a string join plus a numeric compare, so it belongs in code that can be read once
and trusted thereafter rather than in a prompt.

**A disagreement is not an error.** Different harnesses, prompts, dates and checkpoints all
produce different numbers legitimately. The page names the difference and shows the evidence;
it never picks a winner, because which number applies to a given case is not something the
library can know.

Ladders, applied inline in every command block:

```bash
L="skills/ai-lib-lint";    [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
K="skills/ai-lib-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-compare"
```

---

## STOP conditions — check these first

1. **Fewer than two documents in the library → say so and stop.** *"There is only one
   document stored, so there is nothing to compare it against. Run `/ai-lib-ingest` for
   another."*

2. **Fewer than two documents resolved → do not build.** The script exits 1 and prints every
   id it could not match. Report the misses by name, offer the selection flow, and try again.
   **Never substitute a document the user did not name**, and never build a one-column
   comparison. (Step 3)

3. **Never adjudicate a disagreement.** Name it, show both numbers with both locators and
   both authorities, and say what would settle it. Choosing a winner means asserting a fact
   neither document supports. (Step 5)

4. **The join is exact, and that is deliberate.** "MMLU" and "Massive Multitask Language
   Understanding" do not join; nor do a 5-shot and a 0-shot result recorded under different
   metric names. Do not work around it by editing a page's benchmark name to force a match —
   fuzzy matching would report agreement where none exists, and editing a name to make a table
   look tidier corrupts the source of truth. (Step 4)

5. **Never compare a claim across documents by paraphrase.** Each claim keeps its own wording
   and its own marker. Two claims that look like the same claim, phrased differently, are two
   claims — and whether they agree is a judgement for the summary, not a merge in the table.
   (Step 5)

6. **Three questions maximum:** at most two in the selection flow and the save offer. Where
   the argument named the documents, the budget is one.

---

## RULES — read before acting

- **Say what kind of comparison this is.** Two first-party announcements from rival labs is a
  marketing comparison. A vendor claim against an independent evaluation is an audit. Two
  papers on the same method is a replication check. The shape of the answer follows.
- **Authority asymmetry is the finding, often.** Where every document is `first-party`, the
  comparison cannot settle anything about quality and must say so. Where one is independent,
  its disagreement with the others is the most informative row on the page.
- **Age asymmetry too.** Comparing a 2026 model card against a 2024 one is a
  year-over-year comparison, not a like-for-like one. Say which it is.
- **The frontmatter and the evidence tables are the machine truth.** Where a subagent's
  narrative disagrees with a number, the number wins and the disagreement is a finding about
  that page.
- **Fan out by leaf, never by document.** Two documents from one leaf is one subagent — and
  for a two-document comparison, no subagent at all.
- **Do not restate the cost of the join.** It is documented in `build-compare.py`'s module
  docstring and printed on every page it generates. A second description here would drift.
- **Ask through AskUserQuestion when you have it, in plain text when you do not.**

---

## Procedure

### Step 1 — Walk the library

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
```

Note the document count and the `error`-severity finding count. If any selected document
carries an unmarked claim or an unauthorized capture, the generated page says so and so should
you — a comparison resting on an untraceable claim is a comparison of something nobody can
check.

### Step 2 — Establish which documents, in three escalating moves

**If the argument named documents, use them.** Skip to Step 3. A user who typed two titles
does not want a menu.

Otherwise run **one AskUserQuestion call** — header `"Selection"`, question `"Which documents
do you want to compare? Name them in the field, or pick a route."`, options (exactly these
four):
`["Show me what's there first — build the catalog", "Everything in one topic — say which", "The documents that report the same benchmark", "I have a question — ask me and recommend"]`.
(multiSelect: false)

The four routes, each a real handoff rather than a hint:

1. **"Show me what's there"** — run `/ai-lib-list`, open it, then build a **short chooser
   list** in chat from `output/_library-data.json`: title, topic, type, authority, date, one
   line each. That is a chooser, not the catalog. Then run **one AskUserQuestion call** —
   header `"Documents"`, question `"Which of these? Name two or more in the field."`, options
   (exactly these three):
   `["The two most recent in one topic", "One first-party and one independent on the same subject", "Everything in one topic"]`.
   (multiSelect: false) That is the second and last selection question.

2. **"Everything in one topic"** — resolve it yourself from the inventory: every active
   document in that leaf. Where the leaf holds more than six, take the six most recent and say
   which you dropped and why — a matrix twelve columns wide is a matrix nobody reads.

3. **"The documents that report the same benchmark"** — resolve it from the inventory's
   `evidence` arrays: group documents by normalized (benchmark, metric) and pick the group
   with the most members. **This is the highest-value default**, because a shared benchmark is
   where a disagreement can actually be detected. Say which benchmark you chose and how many
   documents report it.

4. **"I have a question"** — hand off to `/ai-lib-query`. It searches, returns the documents
   that bear on the question, and you come back here with those `doc_id`s. Do not run a
   library-wide search inline; `/ai-lib-query` owns that and duplicating it means two versions
   drifting apart.

**Where the user is still undecided**, do not loop. Pick a defensible default — the largest
shared-benchmark group, or failing that the two most recent documents in the largest leaf —
build it, and say exactly what you chose: *"You were undecided, so I compared the three
documents that report HH-RLHF harmlessness. Name any two and I'll rebuild it."* A built
comparison someone can react to beats a fourth question.

### Step 3 — Resolve the ids

```bash
K="skills/ai-lib-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-compare"
python3 "$K/scripts/build-compare.py" --data output/_library-data.json --list
```

The matcher accepts a full `doc_id`, a bare document slug, or a case-insensitive title, in
that order — exact id first, always. **Titles collide constantly here**: every model family
has a "system card" and an "announcement", so a title matching more than one document is
reported as ambiguous and skipped rather than guessed at.

**Report every miss and every ambiguity by name before building.** A comparison quietly built
from three of the four documents the user named is the worst failure available, because the
missing one was probably the point.

### Step 4 — Fan out for the reading, then build

**4a — Fan out, if it is worth it.** Skip entirely for a two-document comparison: the matrix
plus the pages' own claims carry it. For **three or more documents spanning more than one
leaf**, fan out **one subagent per leaf represented** — not one per document:

> You are the master of `topics/<leaf>/`. Read `SCHEMA.md` first, then read only these
> document pages in your own leaf: `<paths>`. **Read nothing outside your leaf. Write
> nothing.**
>
> For each, return JSON:
>
> ```json
> {"documents": [{
>   "doc_id": "<verbatim>",
>   "position": "<one or two sentences: what this document's overall stance is on the subject these documents share>",
>   "distinctive": "<what this document says that the others in this comparison do not — the reason it is in the comparison at all>",
>   "caveat": "<what to distrust: first-party optimism, an old benchmark, a claim with no locator, a missing limitations section>",
>   "method_note": "<how this document measured what it measured, if it says — the thing that explains a benchmark disagreement>"
> }]}
> ```
>
> Rules: every claim traces to a sentence on the page; **never state a number** — the parent
> has the evidence tables and will contradict you visibly; a page whose `## Limitations` is a
> placeholder gets that said in `caveat`; never mention a document outside your leaf;
> `doc_id` verbatim.

**`method_note` is the field that earns the fan-out.** A benchmark disagreement is usually
explained by a harness or prompt difference stated in prose that no frontmatter key holds, and
it is the difference between "these disagree" and "these disagree because one used a different
prompt format".

**4b — Build.** `--docs` is required; the script exits 1 without it.

```bash
K="skills/ai-lib-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-compare"
python3 "$K/scripts/build-compare.py" \
  --data output/_library-data.json \
  --docs "<id1>,<id2>,<id3>" \
  --out "output/compare-$(date +%F).html" \
  --json output/_compare.json
```

`--json` writes the computed payload — every join row, every disagreement with its spread,
every claim split from its marker — so Step 5 reads numbers rather than re-deriving them from
the HTML. Read the stderr receipt: documents, benchmark rows, how many are shared, and the
disagreement count.

### Step 5 — Read the result and say what it means

The page is built and `output/_compare.json` holds every number on it. **Read that file, not
the HTML.** Now do the part the script cannot: interpret it.

1. **Name the kind of comparison.** Marketing comparison, audit, replication check,
   year-over-year. One clause, and it frames everything after it.

2. **Lead with the disagreements.** For each: the benchmark, both numbers, both locators, both
   authorities, and the spread. Then — from the subagents' `method_note` or the pages
   themselves — **what would explain it**. A 15-point Elo gap between a vendor's own number
   and an independent re-run is the most informative thing on the page, and the explanation is
   usually in one sentence of someone's methods section.

3. **Say what is not comparable, and why.** The join reports how many rows appear in more than
   one document. Where most rows are single-document, say so plainly: *"only one of the three
   benchmarks is reported by more than one document, so this is mostly three separate
   pictures rather than a comparison."*

4. **Report the authority profile.** Every document `first-party` means the comparison cannot
   settle anything about quality — say it. One independent source among vendor material means
   its numbers carry different weight — say that too.

5. **Report the age profile**, and flag any document past its topic's staleness threshold.

6. **Where the claims agree and disagree in substance**, not just in numbers. Two documents
   claiming the same capability with different framings, or one document's `## Limitations`
   contradicting another's `## Key Claims`. Cite both, with markers.

7. **Flag untraceable material.** Any unmarked claim on any compared page, and any capture
   outside its link plan. A comparison resting on those is a comparison of something nobody
   can check.

8. **The caveat**, once, in the chat as well as on the page.

### Step 6 — Open it, save it, log it

```bash
OUT="$(cd output && pwd)/compare-$(date +%F).html"
[ -f "$OUT" ] && echo "$OUT" || echo "MISSING: $OUT"
case "$(uname -s 2>/dev/null)" in
  Darwin) open "$OUT" ;;
  Linux)  xdg-open "$OUT" >/dev/null 2>&1 & ;;
  *)      start "" "$OUT" ;;
esac
```

Resolve to absolute, verify, open, print the path. **In Cowork, always also present the
file.**

Then, only where this took real work — three or more documents, or a fan-out — run **one
AskUserQuestion call** — header `"Save"`, question `"Save this comparison so you can re-open
the reasoning later?"`, options (exactly these two):
`["Save it as a synthesis page", "The HTML file is enough"]`. (multiSelect: false)

On save, write `synthesis/compare-<YYYY-MM-DD>-<slug>.md` per `SCHEMA.md` § 5.1, with
frontmatter `title`, `category: synthesis`, `doc_ids: [...]`, `topics: [...]`,
`question` (what the comparison was for), `created`, `last_updated`,
`updated_by: ai-lib-compare`, `status: active`. Body: **what you were comparing and why**,
the disagreements with both locators, the authority and age profile, what is not comparable,
and the caveat. **Nothing generated ever lands inside a topic folder.**

Append to `log.md`:

```markdown
## [2026-08-26] ai-lib-compare | 3 documents across 2 leaves — 3 benchmark rows, 1 shared, 1 disagreement (HH-RLHF harmlessness, spread 15.0)
```

---

## Files in this skill

| File | What it does |
|---|---|
| `scripts/build-compare.py` | resolves doc ids, joins evidence tables on the exact (benchmark, metric) pair, detects disagreements with their spread, splits every claim from its marker, and emits one self-contained HTML matrix. `--list` prints every doc_id; `--json` emits the computed payload. Stdlib only |
| `scripts/compare-template.html` | the HTML/CSS/JS shell. Highlights a disagreeing row rather than marking a winner in it |

Plus `lint-library.py` from `skills/ai-lib-lint/scripts/`. Executed, never loaded into
context. Run by path; never inline, retype or rewrite one — the shipped file is the single
source of truth for what the join does, and an edited copy silently changes every number on
the page.

---

## Anti-patterns

- Do not build a one-column comparison. Two documents is the minimum, and the script exiting 1 is correct behaviour.
- Do not substitute a document the user did not name because one of theirs did not resolve.
- Do not build from three of the four documents named without saying so. The missing one was probably the point.
- Do not omit `--docs`. The script exits 1 without it, and `--list` resolves ids without passing them anywhere.
- Do not run the build before the fan-out. The notes have to exist before the build reads them.
- Do not scrape the join out of the HTML. Pass `--json` and read the file.
- Do not adjudicate a disagreement. Name it, show both locators, say what would settle it.
- Do not edit a page's benchmark name to force a join. That corrupts the source of truth to make a table look tidier, and the exactness of the join is what makes it trustworthy.
- Do not merge two similarly-worded claims into one row. They are two claims with two markers, and whether they agree is a judgement for the summary.
- Do not report a shared-benchmark count of one as a comparison. Say most rows are single-document and that this is three separate pictures.
- Do not omit the authority profile. All-first-party means the comparison cannot settle anything about quality.
- Do not compare a 2026 document against a 2024 one without labelling it year-over-year.
- Do not bury the disagreements. They are the reason the page exists, and the explanation for one is usually a single sentence in someone's methods section.
- Do not omit the `method_note` from the fan-out. It is the field that turns "these disagree" into "these disagree because".
- Do not let a subagent state a number, read another leaf, or write anything.
- Do not accept a `doc_id` that is not in the linter's json.
- Do not fan out for a two-document comparison, or by document rather than by leaf.
- Do not ignore an unmarked claim on a compared page. A comparison resting on one is a comparison of something nobody can check.
- Do not run a library-wide search inline. `/ai-lib-query` owns that conversation.
- Do not loop on an undecided user. Build a defensible default and say what you chose.
- Do not assume a relative path opens. Resolve to absolute, verify, open, print.
- Do not paste the whole matrix into chat. Link the file, then say the kind of comparison, the disagreements, and what is not comparable.
- Do not write a synthesis page into a topic folder.
- Do not drop the caveat from the chat because it is on the page.
