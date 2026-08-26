---
name: ai-lib-lint
description: >-
  Health-check the ai-lib document library and regenerate index.md. Audits every claim for a
  provenance marker and every depth-1 capture against its authorized link plan, auto-repairs
  only counts and formats, marks contradictions for a human rather than resolving them, fans
  out one subagent per leaf topic for the prose defects no regex can see, and writes a dated
  report. Runs interactively or unattended on a schedule. Use when asked to check, lint,
  audit or clean up the library, when index.md looks stale, or before relying on an answer.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion mcp__scheduled-tasks__create_scheduled_task mcp__scheduled-tasks__list_scheduled_tasks
metadata:
  argument-hint: "(no arguments for an interactive run; pass --scheduled for an unattended one)"
---

# /ai-lib-lint — Audit the Library, Repair the Mechanical, Flag the Rest

The library's maintenance pass, and the only thing that regenerates `index.md`.

**The division of labour with `/ai-lib-ingest` is deliberate, and it is the opposite of what
you might assume.** `/ai-lib-ingest` is the autonomous writer: where a source settles a
question it settles it and logs the decision. **`/ai-lib-lint` never resolves a conflict.**
It marks what it cannot decide and leaves it for a person. An ingest that deferred every
conflict would fill the library with unresolved pairs; a linter that resolved them would
overwrite attributed claims with no source of its own to justify it.

**Two audits are the reason this skill exists**, and neither can be done by reading:

1. **Every claim carries a provenance marker.** `CLM-UNMARKED` is the highest-severity
   finding in the family. A prompt can ask for markers; only a checker can prove they are
   there.
2. **No capture escaped its link plan.** A script cannot do the fetching, so it cannot
   physically stop a second hop — but it can prove, after the fact, that every URL fetched
   was authorized by a plan generated from a source document. `CAP-UNAUTHORIZED` is the
   signature of a second-hop fetch, and this skill is where the one-hop limit stops being a
   promise and becomes a fact.

Self-contained. Three scripts in `scripts/`, resolved with the two-rung ladder that every
command block below applies inline:

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
```

If neither rung resolves, report the missing script and stop. Do not reconstruct one.

---

## The tiering principle — read this before anything else

**Auto-apply the unambiguous; raise only the genuinely undecidable; stop asking about the
merely informational.**

| Tier | Findings | What happens | Asked about? |
|---|---|---|---|
| **1. Auto-repair** | counts realigned to what the sections actually hold (`claim_count`, `located_claim_count`, `benchmark_count`, `document_count`), identifiers realigned to the tree (`doc_id`, `topic`, `node_type`, `depth`), quoting and boolean form, absent required keys the linter could derive, an absent fixed section on an otherwise-clean page | applied in **both** modes, counted in the log | **No** — a count corrected against the section it summarizes is not a decision |
| **2. Human resolves** | contradictions, both structured and prose-detected | a `**CONTRADICTION:**` marker inserted next to the claim, logged, and left | Surfaced, but there is **no fix to approve** — do not put these on the Step 7 menu |
| **3. Approval required** | placement corrections (a document on a branch, or at an undefined path), and orphaned `builds_on` references | proposed; applied only on explicit approval. Unattended: queued, unapplied | **Yes — this is what Step 7 asks about** |
| **4. Informational** | **`CLM-UNMARKED`**, `LNK-OUTSIDE-QUARANTINE`, `LNK-PAGE-LOCATOR`, `CAP-UNAUTHORIZED`, `CLM-PAGE-RANGE`, `EVI-NO-LOCATOR`, `SEC-INVENTED`, staleness, stubs, thin themes, share drift | counted in the log, listed per-item in the report | **No** — demoted off the menu entirely |

**Do not ask permission for a tier-1 repair.** A `claim_count` corrected from 9 to 4 against
a section holding 4 claims is not a decision; putting it on the menu trains the user to
approve without reading, which is how a real decision slips through.

**Tier 4 is not "ignorable" — it is where the most important findings live**, and the reason
is precisely that they matter. `CLM-UNMARKED` cannot be autofixed because the only correct
fix is to reopen the source and find the page; **a marker invented to satisfy a linter is
worse than the unmarked claim it replaced.** `CAP-UNAUTHORIZED` cannot be autofixed because
deleting the capture would erase the evidence of a fetch that should not have happened.
`LNK-OUTSIDE-QUARANTINE` cannot be autofixed because moving a sentence between sections is a
judgement about what that sentence means. These are the four findings to lead the report
with, not the four to bury.

---

## Three modes, distinguished by whether a person is there

- **Interactive, structured** — a person invoked it in a harness with `AskUserQuestion`. Ask
  the Step 7 tier-3 question through the UI.
- **Interactive, plain** — a person invoked it in a harness with **no** `AskUserQuestion`.
  Put the tier-3 menu in plain text, numbered, one per line, and end the turn. Do **not**
  silently fall through to unattended behaviour.
- **Unattended** — a schedule, a hook or a cron invoked it with nobody there. Ask nothing,
  apply tier 1 only, queue tier 3 in the report, write both artifacts, exit 0.

**Distinguish the last two by whether a person is there, not by which tools you have.**

Mode detection is Step 0. **Do not use a TTY test.** Stdin is not a terminal in essentially
any agent runtime, so `test -t 0` classifies a live user as unattended and the tier-3 gate
then silently never fires — a failure that looks like a clean run. Decide from the
invocation instead:

| Signal | Mode |
|---|---|
| `--scheduled` passed, or a scheduled task / hook / cron is the invoker | **Unattended** |
| A person asked for this in conversation, and `AskUserQuestion` is available | **Interactive, structured** |
| A person asked for this in conversation, and it is not | **Interactive, plain** |

When the invocation is genuinely ambiguous, **assume a person is there.** Asking a question
nobody answers costs one wasted turn; skipping the gate silently applies nothing and reports
that everything is fine.

---

## STOP conditions — check these first

1. **No library → HALT and create nothing.** No `SCHEMA.md` and no `topics/` means the
   linter exits 1 with the message to run `/ai-lib-setup`. Relay it. Do not scaffold.

2. **Never invent a provenance marker.** Not to clear a `CLM-UNMARKED`, not to make a page
   look complete, not because the claim is obviously from page 3. The only correct fix is to
   reopen the source in `raw/` and find the page — which is `/ai-lib-refresh`'s job or a
   human's, not this skill's. A fabricated locator is worse than an unmarked claim because it
   *looks* traceable. (Step 6)

3. **Never delete or move a capture, however unauthorized.** `CAP-UNAUTHORIZED` means a
   fetch happened that should not have; erasing the evidence is the opposite of the right
   response. Report it, name the URL, and let a human decide whether the content stays.

4. **Never resolve a contradiction.** Not with a majority of sources, not because one value
   looks more plausible, not in either mode. Insert the marker naming both values and both
   locators, log it, move on. The report is where you may observe; the page is where you only
   mark.

5. **The prose scan never feeds the patcher.** Two detection layers, one write contract: the
   regex layer (`lint-library.py`) may feed `patch-library.py`; the subagent layer (Step 5)
   may only produce markers, log lines and report entries. This is the cleanest safety
   boundary in the family — do not route around it.

6. **Run the shipped scripts by path; never inline, retype or rewrite one.** The shipped file
   is the single source of truth for what gets detected, and an edited copy changes the result
   while still appearing to work.

7. **Never delete a page and never rename one.** A superseded document gets
   `status: superseded`.

8. **Two questions maximum, both interactive-only:** the Step 7 tier-3 menu and the Step 9
   schedule offer.

---

## Procedure

### Step 0 — Mode

Detect the mode and say which one you are in, in one clause. A user who expected to be asked
something and was not deserves to know why.

### Step 1 — Detect

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
mkdir -p output
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
```

Exit 1 means there is no library; relay the message and stop. Otherwise the stderr receipt
gives you the shape of the run — and read it carefully, because two of its numbers are the
ones that matter: **claims unmarked** and **captures unauthorized**. **Findings never affect
the exit code**; a library with 400 violations still exits 0, because the JSON is the report.

Read `output/_library-data.json`. `counts.by_rule` is your table of contents.

**Note whether link plans exist at all.** `CAP-NO-PLANS` at warn means `output/` holds no
`_linkplan-*.json`, so the depth-1 audit could not run for anything. That is not a clean bill
of health — it is a missing audit, and the report must say so rather than reporting zero
unauthorized captures as if it had checked.

### Step 2 — Repair the mechanical

Dry run first, always, so the plan is available to the report before anything moves:

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/patch-library.py" --data output/_library-data.json --dry-run \
  --out output/_patch-plan.json
```

Read it, then apply — in **both** modes, because everything in it is tier 1:

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/patch-library.py" --data output/_library-data.json \
  --out output/_patch.json
```

**The patcher's own output is the tier-1/tier-3 split.** Its `applied` array is tier 1; its
`skipped` array — each entry carrying a `reason` — needs a human. And read
`never_autofixed`: that map is the patcher telling you which findings it deliberately
declined and why, and those are the ones the report leads with.

**Then re-run the linter**, because the patcher moved things and everything downstream reads
the JSON:

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
```

Chained detection is expected here, not a symptom: correcting a `claim_count` can surface a
`CONF-HIGH-UNLOCATED` that the wrong count was masking. Say so if the finding count rises.

### Step 3 — Read every page (fan out above the threshold)

You need the substance of the pages in context for Step 5, but reading dozens inline is
slow. The library is a set of leaf topics, so the natural unit of parallelism is a **leaf**,
not a file.

1. **Two leaf topics with documents or fewer:** read the pages inline with Read.
2. **More than two:** fan out, **one subagent per leaf topic that holds documents** —
   `topics/ai/`, `topics/llm/claude/`, `topics/math-sci-tech-cyber/cybersecurity/`, and so
   on. One agent per leaf, however many documents it holds. Never one agent per document,
   and never a fixed number of agents dividing the list. The threshold is the same number in
   every skill in this family, so nobody has to remember which one it was.

Each subagent returns, for every document page in its leaf:

- `doc_id` and title, verbatim;
- **every claim, with its marker and type, verbatim** — not paraphrased;
- every `## Evidence` row, with its locator;
- every `[inference:]` and `[verify:]` tag, verbatim;
- whether a `**CONTRADICTION:**` marker is already present;
- **anything in `## From Linked Pages` that reads like the document's own claim**, and
  anything anywhere else that reads like it came from a linked page;
- anything under `## Additional capture` that belongs in a fixed section.

**Step 5 needs those claims and this is the only pass that collects them.** Enumerate them;
do not summarize.

**Collect all subagent results before any analysis** — do not begin Step 5 until every task
has returned.

**The fan-out is for speed and awareness only.** The linter already read every file from
disk in Step 1 and is the source of truth for what exists. That is what makes a lost
subagent degrade the run to slower rather than to wrong, and why there is no retry doctrine:
note the leaf that failed, and say its prose went unscanned.

### Step 4 — Skip. (Reserved; the numbering matches the family's other skills.)

### Step 5 — The prose scan

The linter is deterministic and checks the *presence and shape* of markers. It cannot check
whether a marker is **telling the truth**. Five things to look for, and only these five:

1. **A claim whose locator is implausible.** A `[p. 3]` on a claim about a conclusion, on a
   30-page paper. The linter catches a page beyond `pages`; it cannot catch a page that
   exists but is wrong.
2. **A `[link: ...]` claim wearing this document's voice.** Sitting correctly inside
   `## From Linked Pages`, but phrased as though the document asserted it. The quarantine is
   structural; the phrasing is not, and a subagent quoting it later will drop the marker.
3. **A claim in the document's voice that plainly came from elsewhere.** The inverse, and
   harder: a `## Method` paragraph in far more detail than an eight-page blog post could
   contain, with a `[p. 4]` on it. That is linked material that has been laundered.
4. **Two documents contradicting each other** on the same subject — the same benchmark with
   different numbers and no note, or one document's `## Limitations` flatly denied by
   another's `## Key Claims`. `build-compare.py` catches the benchmark case
   deterministically; prose contradictions need reading.
5. **An `[inference: ...]` doing the work of a claim.** An inference that carries the page's
   argument is a conclusion presented as a finding, and it should be in
   `## Open Questions`.

**This step detects and never resolves, and it never feeds the patcher.** Findings go to
exactly three places: a marker on the page (Step 6), a `log.md` entry, and the report.

**When in doubt, do not flag.** A false positive costs the user's attention, and attention
spent on a non-finding is attention not spent on a real one. Two documents reporting
different numbers from different harnesses are not contradicting each other. A first-party
post being optimistic is not a defect.

### Step 6 — Insert the markers

Strictly additive. Insert marker lines; change nothing else.

```markdown
**CONTRADICTION:** claim 2 reports 153 Elo on HH-RLHF harmlessness [p. 15, Fig 7] vs. 138 for the same benchmark in `llm-gpt__gpt-5-evaluation-report` [p. 4, Table 2] — different harnesses, unresolved. [2026-08-26 via ai-lib-lint]
```

Four rules:

1. **Put the marker inside the section that holds the claim** — never above the first
   heading, and never below `## Additional capture` where consumers stop reading.
2. **Leave both claims exactly as they are.** Do not edit either, and do not add a
   recommendation about which is right.
3. **Do not double-mark.** Search for an existing marker naming the same two values first.
   Re-running this skill must be idempotent.
4. **Update `last_updated` and set `updated_by: ai-lib-lint`** on a page you marked.

**Do not add a marker to fix an unmarked claim.** That is inventing provenance, and it is
forbidden by STOP condition 2. An unmarked claim goes in the report, named, with its page and
line.

### Step 7 — The one question

Regenerate the index first, because it needs no approval and its input is now current:

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/index-library.py" --data output/_library-data.json --library .
```

`index.md` is a **derived catalog**. It holds no knowledge of its own, so it is rewritten on
every run, in both modes, no approval. **Never record anything in it that is not on a page** —
the moment it holds a fact of its own, regenerating it destroys that fact and this step stops
being safe to run unattended.

Then, **interactive modes only**, run **one AskUserQuestion call** — header `"Fix these"`,
`multiSelect: true`, question `"Repaired {n} count and format issues automatically, and
marked {n} contradictions on their pages. {n} items need your call:"`, options:

- `"Move {n} document(s) filed on a branch topic into a leaf — I'll show you which"`
- `"Move {n} document(s) filed at an undefined taxonomy path"`
- `"Clear {n} orphaned builds_on reference(s) that point at no document"`
- `"None of these — leave them all in the report"`

Include only the option lines with a non-zero count. **If tier 3 is empty, skip the question
entirely** and say so — do not ask a question with nothing to decide. **Do not ask a
follow-up**: anything not authorized in that single answer stays in the report for next time.

**`CLM-UNMARKED`, `CAP-UNAUTHORIZED`, `LNK-OUTSIDE-QUARANTINE` and `LNK-PAGE-LOCATOR` are
never on this menu.** Each needs a source reopened or a sentence judged, and offering to
"fix" one would mean inventing a marker, deleting evidence, or guessing at what a sentence
means.

On approval, apply exactly what was approved — a placement move is: move the file, move its
captures, move its `raw/` original, update `doc_id` and `topic`, fix any `builds_on` that
referenced the old id, and log both paths. Then re-run the linter and `index-library.py`, so
the index is not built from a pre-approval snapshot.

### Step 8 — Write the report, and the log

**`output/lint-<YYYY-MM-DD>.md`** — eight numbered sections, fixed order, each omitted only
if genuinely empty. **The first three are the point of the file:**

1. **Untraceable claims** — every `CLM-UNMARKED`, with page, line and the claim text. This
   is the list that matters most and it goes first.
2. **Quarantine breaches** — `LNK-OUTSIDE-QUARANTINE`, `LNK-PAGE-LOCATOR`,
   `EVI-LINKED-NUMBER`, `CLM-LINKED-CLAIM`. Linked material reading as the document's own.
3. **Depth-1 audit** — every `CAP-UNAUTHORIZED` with its URL and parent, plus the count of
   captures that could not be audited at all because no plan exists.
4. **Summary counts** — topics, documents, claims, located claims, captures, findings by
   severity.
5. **Contradictions** — `### Structured` and `### In prose`, both values and both locators
   each.
6. **Locator problems** — `CLM-PAGE-RANGE`, `EVI-NO-LOCATOR`, `CONF-HIGH-UNLOCATED`.
7. **Staleness and coverage** — stale documents by leaf, stubs, empty leaves, thin themes,
   share drift.
8. **Applied / Awaiting decision / Skipped** — every tier-1 repair with old and new value;
   tier 3 with what approving would do; every patcher refusal with its reason.

A re-run on the same date overwrites that date's file — the date, not the run, is the unit.
**Nothing prunes them:** where `output/lint-*.md` exceeds `lint_keep`, say so and let the
user delete. STOP condition 7 forbids this skill from deleting anything.

**Append one entry to `log.md`:**

```markdown
## [2026-08-26] ai-lib-lint | 14 leaves, 87 documents — 6 auto-repaired, 2 contradictions marked, 3 unmarked claims, 1 unauthorized capture, 11 stale
```

Two logs, and do not merge them. `log.md` is the durable audit trail shared with every
skill; `output/lint-<date>.md` is the verbose drill-down. **The log is the skim; the report is
the drill-down.**

**Refresh the Library Brief in `CLAUDE.md`**, between the `<!-- library-brief-start -->` and
`<!-- library-brief-end -->` markers: document count by leaf, claim and located-claim totals,
share drift, and the one or two things most worth fixing. Replace what is between the
markers; touch nothing outside them.

### Step 9 — Report, and offer the cadence

In chat, five things and no more:

1. **The shape** — leaves with documents, document count, claim count, and whether
   `index.md` changed.
2. **Can an answer be trusted right now?** One sentence, and it is the sentence people
   actually opened the report for: *"Nothing blocking — 87 documents, every claim marked, all
   41 captures authorized, 11 stale in `llm/`."* Or: *"Three claims carry no marker and one
   capture is outside its link plan; treat any answer touching those four pages as
   unverified."*
3. **What needs a person**, as specific items with page paths and line numbers. Lead with
   untraceable claims and quarantine breaches.
4. **What was repaired**, as a count by rule. Not a list; the report has the list.
5. **Staleness**, by leaf, with a pointer to `/ai-lib-refresh`.

**Say when there is nothing to say.** "Ten rule families, nothing to flag, index regenerated"
is a useful thing to have said out loud. A manufactured finding is worse than an honest short
report.

Then, **interactive modes only**, check for an existing schedule first
(`mcp__scheduled-tasks__list_scheduled_tasks`) and skip if one exists. Where the harness
cannot schedule, say so in one clause and skip. Otherwise run **one AskUserQuestion call** —
header `"Auto-check"`, question `"This runs well on a cadence — an unattended run repairs
counts, marks contradictions, regenerates the index and writes the report, and leaves
anything ambiguous for you. Schedule it?"`, options (exactly these three):
`["Monthly (recommended)", "Weekly", "No, not now"]`. (multiSelect: false)

---

## Files in this skill

| File | What it does |
|---|---|
| `scripts/lint-library.py` | the only detector, and the family's only tree walker. Read-only. Emits the inventory **and** the findings as one json — the write contract every other script consumes. Parses `## Evidence` rows so `build-compare.py` can join them |
| `scripts/patch-library.py` | the only writer of page fixes. Consumes `autofix: true` findings, re-detects nothing, and declines by design anything needing a source reopened or a sentence judged |
| `scripts/index-library.py` | regenerates `index.md` from the json, in taxonomy order. Never walks the tree |

Executed, never loaded into context. They are deliberately decoupled: **the linter is the
only detector and never writes; nothing else re-detects.** The JSON is the single write
contract between them, and prose-detected findings are never routed into it.

---

## Anti-patterns

- Do not invent a provenance marker to clear a `CLM-UNMARKED`. A fabricated locator is worse than an unmarked claim, because it looks traceable.
- Do not delete or move an unauthorized capture. It is evidence of a fetch that should not have happened; erasing it is the opposite of the right response.
- Do not move a sentence between sections to fix a quarantine breach. Which sentence belongs where is a judgement about what it means, and the patcher declines it for that reason.
- Do not resolve a contradiction. Mark it, naming both values and both locators, and move on.
- Do not put `CLM-UNMARKED`, `CAP-UNAUTHORIZED`, `LNK-OUTSIDE-QUARANTINE` or `LNK-PAGE-LOCATOR` on the approval menu. Each would mean inventing a marker, deleting evidence, or guessing.
- Do not bury the untraceable-claim list. It goes first in the report, because it is the finding that invalidates answers.
- Do not report zero unauthorized captures when no link plans exist. That is a missing audit, not a clean one, and `CAP-NO-PLANS` says so.
- Do not ask permission for a tier-1 repair. A count corrected against the section it summarizes is not a decision, and asking trains the user to approve without reading.
- Do not ask a question with nothing to decide. Skip it and say you skipped it.
- Do not ask a follow-up after the tier-3 question. One question; the rest waits.
- Do not detect the mode with `test -t 0`. Stdin is not a terminal in an agent runtime, so it classifies a live user as unattended and the gate silently never fires.
- Do not fall through to unattended behaviour because the harness has no question tool. Ask in plain text and end the turn.
- Do not skip the second linter run after patching. A corrected count is what lets a masked confidence problem become visible.
- Do not treat a rising finding count after a patch as a failure. It is the second pass reaching what the first could not.
- Do not route a prose-detected finding into the patcher's input. Two detection layers, one write contract.
- Do not inline, retype or regenerate any of the three scripts. An edited copy changes what gets detected while still appearing to work.
- Do not walk `topics/` yourself. The linter walks; everything else reads its json. Two walkers eventually disagree.
- Do not hand-edit `index.md`, and do not record anything in it that is not on a page.
- Do not begin the prose scan before every fan-out subagent has returned.
- Do not fan out by document page, or below the threshold of two leaves.
- Do not flag two documents reporting different numbers from different harnesses as a contradiction. Different runs produce different numbers legitimately.
- Do not flag a first-party post for being optimistic. That is what `authority: first-party` records.
- Do not put a marker above the first heading or below `## Additional capture`.
- Do not double-mark. Re-running must be idempotent.
- Do not delete an old lint report. Say the count exceeds `lint_keep` and let the user decide.
- Do not manufacture a finding to make the report look substantial.
- Do not omit the one-sentence verdict on whether an answer can be trusted right now. It is what people opened the report for.
