---
name: ai-lib-setup
description: >-
  Scaffold an ai-lib document library — the knowledge base the other six ai-lib skills read
  and write. Creates the five directories, the fourteen-leaf topic tree, the page contract
  copied byte-for-byte, the taxonomy, the operating rules and the config. Does NOT ingest
  anything or create a document page; a tree of empty topics is the correct end state. Use
  when the user says "set up my document library", "scaffold the AI library", "start a PDF
  knowledge base", or runs /ai-lib-setup.
allowed-tools: Read Write Edit Bash Glob Grep AskUserQuestion mcp__scheduled-tasks__create_scheduled_task
metadata:
  argument-hint: "(optional: a path for the library root; otherwise interactive)"
---

# /ai-lib-setup — Scaffold the Document Library

Creates the five directories, the sixteen-node topic tree and the six root files every
other `ai-lib-*` skill depends on. Nothing else. The library it produces is deliberately
empty of documents: a scaffold with fourteen empty leaves is a library nobody has ingested
into yet, which is a normal state and the correct end state of this skill.

Self-contained skill. Its five assets live in `assets/` beside this file, resolved with
the two-rung ladder every command block below applies inline:

```bash
S="skills/ai-lib-setup"; [ -d "$S/assets" ] || S="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-setup"
```

If neither rung resolves, report the missing asset and stop. Do not reconstruct a template
from memory — see STOP condition 2.

---

## STOP conditions — check these first

Short list, at the top, because on a long file the rules that matter get read last.

1. **A library already here → verify and fill gaps; never re-scaffold.** If the target
   path already holds `SCHEMA.md`, `_config/taxonomy.md` or a non-empty `topics/`, this is
   a re-run. Ask the Step 1 re-run question, then add only what is missing. **Never
   overwrite any of the six root files that already exist** — `SCHEMA.md`, `AGENTS.md`,
   `CLAUDE.md`, `index.md`, `log.md`, `_config/library-config.md` — nor
   `_config/taxonomy.md`, nor any existing `topic.md`. `CLAUDE.md` and `taxonomy.md` matter
   most and are the easiest to forget: `/ai-lib-lint` keeps the live Library Brief between
   the `<!-- library-brief-start -->` markers, and the taxonomy is the one file a user
   deliberately edits. (Step 1, Step 5)

2. **Copy the assets; never retype them.** `SCHEMA.md` is cited by section number
   (`§ 6.3`, `§ 7.1`) by every other skill in this family, and `taxonomy.md` carries a
   fenced ```` ```taxonomy ```` block that `lint-library.py` parses with an exact format. A
   re-flowed, summarized or paraphrased copy still looks correct and silently breaks both.
   Use `cp`. If a file cannot be found, say so and seed nothing — a thin hand-written
   substitute under the canonical name is worse than an absent one, because every later
   agent will read it, believe it is the contract, and never learn the real one. (Step 4)

3. **Never create a document page or a capture.** Not an example, not a placeholder.
   `/ai-lib-ingest` owns `documents/` and `captures/`, and an invented document page is
   indistinguishable from a real one three weeks later — and it will be cited in an answer.
   (Step 3)

4. **Never edit the taxonomy during setup.** Copy it as shipped. If the user wants a
   different tree, scaffold the shipped one, say plainly that the taxonomy is a file they
   own and can edit, and point at `_config/taxonomy.md` and the "Adding, renaming and
   moving" section inside it. A tree invented at setup time has no `## What Belongs Here`
   written for it. (Step 4)

5. **Never delete anything.** This skill only creates. If something is in the way, report
   it and stop.

---

## RULES — read before acting

This is a **rigid, prescribed procedure**, not a set of suggestions. Follow the steps in
order and execute each AskUserQuestion **exactly as written** — same questions, same
options.

- **Do not invent, add, reword, merge, or reorder questions or options.** Only the
  questions spelled out below may be asked. If a step lists no question, you ask none.
- **Every AskUserQuestion has at most 4 options.** The UI auto-appends a free-text path;
  never add your own "type it" / "other" / "chat about this" option. For a free-text answer
  such as a path or a name, the listed options are genuine fallbacks, never a restatement
  of "type it".
- **Ask through AskUserQuestion when you have it, in plain text when you do not, and never
  by taking a default silently.** Where a scheduled run invoked you with no user present,
  write the documented defaults and name every default you took in the closing report.
- **Non-destructive and mergeable.** Every write is create-if-absent. A second run over a
  live library must be safe, and must report what it found rather than what it wished it
  had found.
- **Report the ground state before writing.** Say what you found at the target path in
  plain text, so the user can correct your reading of it early rather than at the end.
- **`AGENTS.md`, `SCHEMA.md` and `taxonomy.md` are the authority; this skill is their
  courier.** Do not restate their rules in `CLAUDE.md`, in a topic page, or in the closing
  report. A second copy drifts out of agreement with the first, and then two files disagree
  about the contract.

---

## Procedure

### Step 1 — Locate the root and read the ground state

1. **Take the path from the argument if there is one.** Otherwise use the current working
   directory — the directory the user is working in, not the directory the skill files live
   in.

2. **Look, before asking anything.** Cheap checks, no file parsed:

   ```bash
   ls -d SCHEMA.md AGENTS.md CLAUDE.md index.md log.md _config topics raw synthesis output 2>/dev/null
   ls topics 2>/dev/null | head -20
   ```

3. **Report what you found, in plain text**, in one short paragraph. Name the path you are
   about to write into, absolutely, so a wrong guess is caught now.

4. **If `SCHEMA.md` exists or `topics/` holds anything**, this is a re-run. Run **one
   AskUserQuestion call** — header `"Re-run"`, question `"A library already exists at this
   path. What do you want to do?"`, options (exactly these two):
   `["Verify only — report what's present, create nothing", "Fill in anything missing, leave everything that exists untouched"]`.
   (multiSelect: false) On "Verify only", print the inventory and stop; skip every remaining
   step.

5. **If the path does not exist**, say so and create it. Creating a directory the user
   named is not a decision worth a question.

### Step 2 — The two settings

Run **one AskUserQuestion call** carrying both questions. One call, not two turns.

- Question 1 — header `"Library name"`, question `"What should this library be called? (type it in the field)"`, options (exactly these two): `["AI Library", "Use the folder name"]`. (multiSelect: false)
- Question 2 — header `"Owner"`, question `"Whose library is this? Recorded for attribution only. (type it in the field)"`, options (exactly these two): `["Leave it unattributed", "Use my system username"]`. (multiSelect: false)

That is the whole configuration conversation. **Everything else — the fourteen leaves, the
expected topic shares, the staleness thresholds, the link caps — ships with sensible
defaults in `library-config.template.md` and `taxonomy.md`, both of which are files the
user edits later.** Asking about them now would be asking someone to tune a library they
have not used yet.

**Defaults when a question is unanswered or the run is unattended:** library name = folder
name; owner = the empty string. Name every default you took in Step 7.

### Step 3 — Create the directories and the topic tree

```bash
mkdir -p topics raw synthesis output _config
```

Five directories, and the design decisions behind them are already resolved:

| Path | Holds | Written by |
|---|---|---|
| `topics/` | the taxonomy tree — the knowledge | `/ai-lib-ingest`, `/ai-lib-refresh`, `/ai-lib-lint` |
| `raw/` | immutable originals, mirrored by topic path | `/ai-lib-ingest`, `/ai-lib-refresh` |
| `synthesis/` | saved answers, reading lists, briefs | `/ai-lib-query`, `/ai-lib-compare` |
| `output/` | generated HTML, reports, link plans, intermediate json | every skill |
| `_config/` | the taxonomy and the settings | this skill |

Then the topic tree. **Create every node the taxonomy defines**, branches and leaves both:

```bash
S="skills/ai-lib-setup"; [ -d "$S/assets" ] || S="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-setup"
I="skills/ai-lib-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-ingest"
for p in $(grep -E '^[a-z][a-z0-9/-]* *\| *(leaf|branch) *\|' _config/taxonomy.md | cut -d'|' -f1 | tr -d ' '); do
  python3 "$I/scripts/new-page.py" topic --library . --topic "$p"
done
```

`new-page.py topic` reads `_config/taxonomy.md` itself, so it knows whether each node is a
branch or a leaf, gives it the right sections, and writes a readable display name — `AI`
rather than `Ai`, `GPT` rather than `Gpt`. **A leaf also gets `documents/` and `captures/`
the first time `/ai-lib-ingest` writes into it**; do not pre-create them, because an empty
`documents/` and a leaf nobody has ingested into are the same fact and one of them is
easier to read.

**`topics/` gets sixteen `topic.md` files and no document pages.** That is the end state.

**Then fill each `## What Belongs Here` from the taxonomy.** `new-page.py` cannot do this —
it parses the taxonomy's machine block, not its prose — and skipping it is not cosmetic.
`## What Belongs Here` is **what a subagent reads to decide whether a borderline document is
theirs**, and a leaf whose boundary was never stated is a leaf whose subagent cannot do its
job. `_config/taxonomy.md` already has the prose for all sixteen nodes under "What belongs
where"; for each topic page, replace the `_None recorded._` placeholder in
`## What Belongs Here` with that topic's paragraph, condensed to two or three sentences,
**including the boundary test where the taxonomy gives one** — the `ai` versus `llm/<model>`
rule for those two, and the `data-science` versus `ai` rule for that one.

For `llm/other-models`, carry across the sentence that it is a real topic rather than a
dumping ground. For `misc`, carry across that it should stay small. Those two are the leaves
most likely to accumulate mis-filed material, and the boundary is the only defence.

A `/ai-lib-lint` run after this step should report **zero** `TOP-NO-BOUNDARY` findings. If it
reports fourteen, this step was skipped.

### Step 4 — Copy the contract, the taxonomy and the operating rules

```bash
S="skills/ai-lib-setup"; [ -d "$S/assets" ] || S="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-setup"
[ -f SCHEMA.md ]                 || cp "$S/assets/SCHEMA.md" SCHEMA.md
[ -f AGENTS.md ]                 || cp "$S/assets/AGENTS.template.md" AGENTS.md
[ -f _config/taxonomy.md ]       || cp "$S/assets/taxonomy.md" _config/taxonomy.md
```

Three literal copies. **Copy them; do not read them and retype them.** Then verify all
three landed and are the size you expect:

```bash
wc -l SCHEMA.md AGENTS.md _config/taxonomy.md
grep -c '|' _config/taxonomy.md
grep -E '^[a-z][a-z0-9/-]* *\| *(leaf|branch) *\|' _config/taxonomy.md | wc -l
```

The last number must be **16** — one per node. The match is on the line shape rather than
on the fenced block, so it keeps working if the fence marker ever changes. If it is not 16,
the taxonomy did not survive the copy
and every placement check downstream is broken — stop and say so rather than proceeding
with a truncated tree.

### Step 5 — Write the config, the pointer file, the index and the log

**`_config/library-config.md`** — from `assets/library-config.template.md`, substituting
`{{LIBRARY_NAME}}`, `{{LIBRARY_ROOT}}` (absolute), `{{OWNER}}` and `{{CREATED}}`. Keep the
prose: it documents every share weight, staleness threshold and link cap, and a config
nobody understands is a config nobody tunes.

**`CLAUDE.md`** — **only if absent.** From `assets/CLAUDE.template.md`, substituting
`{{LIBRARY_NAME}}`, `{{OWNER}}` and `{{CREATED}}`. If it already exists, edit **only** the
`## Library settings` bullets in place and leave everything else — in particular everything
between `<!-- library-brief-start -->` and `<!-- library-brief-end -->`, which belongs to
`/ai-lib-lint` and holds the only live summary of what the library currently contains.

**`index.md`** — a stub, because `index-library.py` regenerates it wholesale and anything
written here is thrown away on the first lint:

```markdown
# Index

_No documents yet. Run `/ai-lib-ingest` with a PDF, then `/ai-lib-lint` to build this
catalog._
```

**`log.md`** — the append-only timeline, seeded with this run. Every other skill appends one
entry per run under the subsection vocabulary in `SCHEMA.md` § 10, so this is the one shared
timeline across the family and the header belongs in it from the start:

```markdown
# Log

## [YYYY-MM-DD] ai-lib-setup | library scaffolded — 5 top-level topics, 14 leaves
```

### Step 6 — Verify, and say so out loud even when it is clean

```bash
for f in SCHEMA.md AGENTS.md CLAUDE.md index.md log.md _config/library-config.md \
         _config/taxonomy.md; do
  [ -f "$f" ] && echo "ok   $f" || echo "MISS $f"
done
for d in topics raw synthesis output _config; do
  [ -d "$d" ] && echo "ok   $d/" || echo "MISS $d/"
done
N=$(find topics -name topic.md | wc -l);      echo "topic.md files: $N (expect 16)"
T=$(grep -E '^[a-z][a-z0-9/-]* *\| *(leaf|branch) *\|' _config/taxonomy.md | wc -l); echo "taxonomy nodes: $T (expect 16)"
D=$(find topics -path '*/documents/*.md' | wc -l); echo "document pages: $D (expect 0)"
```

Then run the linter once, because it is the only thing that can tell you the scaffold is
actually consistent with its own contract:

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
```

A fresh scaffold should report **zero errors** and **zero `TOP-NO-BOUNDARY`** — the latter
only if Step 3's boundary-filling was done, which is exactly why it is checked here. Expect
`TOP-EMPTY-LEAF` at info severity on all fourteen leaves: that is correct for a library
nobody has ingested into, and Step 7 explains it rather than hiding it.

Print the result. "Twelve file checks, sixteen topic pages, sixteen taxonomy nodes, zero
documents, zero lint errors" is a useful thing to have said out loud before handing the
library over.

### Step 7 — Report and hand off

Five short parts, in this order:

1. **What was created** — the tree at one level of depth, and the absolute path of the root.
2. **The settings you recorded**, and **every default you took**, named individually.
3. **The taxonomy, briefly** — five top-level topics, fourteen leaves, and the one
   distinction worth stating out loud because it is the most common placement mistake:
   `llm/<model>` is material *about a model*; `ai` is material about *techniques not tied
   to one model*. The test is what the document would still be about with every model name
   deleted.
4. **What the linter said**, including that the fourteen empty-leaf notices are expected
   and that `TOP-NO-BOUNDARY` should be zero.
5. **What to do next**, concretely: `/ai-lib-ingest` with a PDF path. Say that the first
   ingest into a leaf creates its `documents/` folder, and that `/ai-lib-lint` builds
   `index.md` once something is in there.

Then offer the cadence, but only if a person is there and the harness can schedule. Run
**one AskUserQuestion call** — header `"Freshness"`, question `"Most of this library will
be blog posts about a field that moves monthly, so staleness matters. Want a scheduled
check that re-runs /ai-lib-lint and reports what has gone stale?"`, options (exactly these
three): `["Monthly (recommended)", "Quarterly", "No, not now"]`. (multiSelect: false)
Where the harness has no scheduling capability, say so in one clause and skip the question —
offering a cadence you cannot create is worse than not offering one.

Close with the standing caveat, once: this library records what documents say; a document
being in it implies nothing about whether it is correct.

---

## Files in this skill

| File | What it is |
|---|---|
| `assets/SCHEMA.md` | the page contract. Copied to the library root byte-for-byte; cited by section number by every other skill |
| `assets/taxonomy.md` | the topic tree and the placement rules. Copied to `_config/taxonomy.md`; its fenced ```` ```taxonomy ```` block is parsed by `lint-library.py` and `new-page.py` |
| `assets/AGENTS.template.md` | the workspace operating rules. Copied to `AGENTS.md`; agent-agnostic by design |
| `assets/CLAUDE.template.md` | the pointer + state summary. Substituted, then written to `CLAUDE.md` |
| `assets/library-config.template.md` | shares, staleness thresholds, link caps. Substituted, then written to `_config/library-config.md` |

Copied, never loaded into context and retyped. This skill also calls `new-page.py` from
`skills/ai-lib-ingest/scripts/` to scaffold the topic pages, and `lint-library.py` from
`skills/ai-lib-lint/scripts/` for the Step 6 check.

---

## Anti-patterns

- Do not create a document page or a capture. Sixteen topic pages and zero documents is the correct end state.
- Do not create an example document "so the user can see the shape". Three weeks later nobody can tell it from a real one, and `/ai-lib-query` will cite it in an answer.
- Do not read `SCHEMA.md` and retype it. Its section numbers are cited verbatim elsewhere; a re-flowed copy breaks every citation while looking correct.
- Do not reformat, re-indent or "tidy" the ```` ```taxonomy ```` block. `lint-library.py` parses `path | node_type | expected_share` exactly; a tidied table is an unparseable one and every placement check silently stops working.
- Do not edit the taxonomy to suit what the user says they read. Scaffold the shipped tree and point them at the file. A tree invented here has no `## What Belongs Here` written for it, and a leaf whose boundary was never stated is a leaf whose subagent cannot do its job.
- Do not substitute a short hand-written guide when a template cannot be found. A thin file under the canonical name is worse than an absent one.
- Do not overwrite an existing `SCHEMA.md`, `AGENTS.md`, `CLAUDE.md`, `taxonomy.md`, `index.md`, `log.md`, `library-config.md` or `topic.md`. A re-run fills gaps; it does not reset.
- Do not overwrite `CLAUDE.md` on a re-run. `/ai-lib-lint` keeps the live Library Brief in it, and resetting it to the template discards the only current summary of what the library holds.
- Do not restate the contract's rules in `CLAUDE.md`, in a topic page, or in the closing report. A second copy drifts, and then two files disagree.
- Do not pre-create `documents/` or `captures/` inside a leaf. An empty `documents/` and a leaf nobody has ingested into are the same fact, and the absence reads more clearly.
- Do not write a real `index.md` here. `index-library.py` regenerates it wholesale, so anything written now is thrown away — and a hand-written index that survives is worse, because it holds facts no page holds.
- Do not ask about shares, staleness thresholds or link caps. They ship with defaults in files the user edits later; asking now is asking someone to tune a library they have not used.
- Do not ask two separate questions across two turns for the two settings. One call.
- Do not skip the Step 6 taxonomy node count. A truncated `cp` leaves a tree that looks fine and breaks every placement check downstream — that is the one failure here that is subtly wrong rather than obviously broken.
- Do not present the empty-leaf lint notices as problems. Fourteen empty leaves is what a fresh scaffold looks like.
- Do not skip filling `## What Belongs Here`. It is what a subagent reads to decide whether a borderline document is theirs, and fourteen `TOP-NO-BOUNDARY` findings is the signature of having skipped it.
- Do not narrate each `mkdir` and each topic page. Report the tree once, at the end.
- Do not offer the scheduled freshness check on an unattended run, or where the harness cannot schedule.
