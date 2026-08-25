---
name: hiw-lint
description: >-
  Health-check the health-insurance-wiki and regenerate index.md. Runs the deterministic
  linter over every company folder, auto-repairs only the unambiguous and
  value-preserving, marks contradictions for a human rather than resolving them, fans out
  one subagent per carrier for the prose contradictions no regex can see, and writes a
  dated report. Runs interactively or unattended on a schedule. Use when asked to check,
  lint, audit, verify or clean up the wiki, when index.md looks stale, or before relying
  on a comparison.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion mcp__scheduled-tasks__create_scheduled_task mcp__scheduled-tasks__list_scheduled_tasks
metadata:
  argument-hint: "(no arguments for an interactive run; pass --scheduled for an unattended one)"
---

# /hiw-lint — Scan the Wiki, Repair the Mechanical, Flag the Rest

The wiki's maintenance pass, and the only thing that regenerates `index.md`.

**The division of labour with `/hiw-ingest` is deliberate, and it is the opposite of
what you might assume.** `/hiw-ingest` is the autonomous writer: where a source settles
a question it settles it, overwrites in place, and logs what it decided.
**`/hiw-lint` never resolves a conflict.** It marks what it cannot decide and leaves it
for a person. An ingest that deferred every conflict would fill the wiki with unresolved
pairs; a linter that resolved them would overwrite sourced facts with no source of its
own to justify it.

Self-contained. Three scripts in `scripts/`, resolved with the two-rung ladder that
every command block below applies inline:

```bash
S="skills/hiw-lint"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
```

If neither rung resolves, report the missing script and stop. Do not reconstruct one.

---

## The tiering principle — read this before anything else

**Auto-apply the unambiguous and value-preserving; raise only the genuinely undecidable;
stop asking about the merely informational.**

| Tier | Findings | What happens | Asked about? |
|---|---|---|---|
| **1. Auto-repair** | format normalizations that preserve the value (`1,000` → `1000`, `20%` → `20`, `yes` → `true`), absent required keys the linter could derive, absent list keys, an absent fixed section on an otherwise-clean page, a single-candidate broken cross-reference, a retired `[[wikilink]]` with one resolution, `plan_count` and `plan_id` realigned to the tree | applied in **both** modes, counted in the log | **No** — a comma removed from a number is not a decision |
| **2. Human resolves** | contradictions, both regex-detected and prose-detected | a `**CONTRADICTION:**` marker is inserted next to the claim, logged, and left | Surfaced, but there is **no fix to approve** — do not put these on the Step 6 menu |
| **3. Approval required** | ambiguous cross-references (zero or several candidates), roster values disagreeing with frontmatter, off-year plans still marked `active` | proposed; applied only on explicit approval. Unattended: queued, unapplied | **Yes — this is what Step 6 asks about** |
| **4. Informational** | `TBD` core fields, blocked cost scenarios, stale pages, empty scaffolds, missing source receipts, open `[verify:]` tags, invented section headings, superseded plans with no named successor, impossible number pairs | counted in the log, listed per-item in the report | **No** — demoted off the menu entirely |

**Do not ask permission for a tier-1 repair.** A comma stripped from a number and a
derivable frontmatter key are not decisions; putting them on the menu trains the user to
approve without reading, which is how a real decision slips through.

**Tier 4 is not "ignorable".** It is where every finding lands that has no fix an agent
may legitimately apply — and several of them are the highest-signal things this skill
produces. `TBD-CORE` and `COST-MODEL-BLOCKED` are the working lists for `/hiw-refresh`.
`PROV-NO-SOURCE` means a number on that page cannot be trusted at all. And
`CON-OOP-LT-DEDUCTIBLE` — an out-of-pocket maximum below its own deductible — is the
single most consequential thing this skill finds, and it sits in tier 4 precisely
*because* it matters: fixing it means deciding which of two sourced numbers was mis-read,
and that answer is in the source document, not in the wiki.

---

## Three modes, distinguished by whether a person is there

- **Interactive, structured** — a person invoked it in a harness with
  `AskUserQuestion`. Ask the Step 6 tier-3 question through the UI.
- **Interactive, plain** — a person invoked it in a harness with **no**
  `AskUserQuestion`. Put the tier-3 menu in plain text, numbered, one per line, and end
  the turn. Do **not** silently fall through to unattended behaviour.
- **Unattended** — a schedule, a hook or a cron invoked it with nobody there. Ask
  nothing, apply tier 1 only, queue tier 3 in the report, write both artifacts, exit 0.

**Distinguish the last two by whether a person is there, not by which tools you have.**
No question tool plus a waiting user is *interactive, plain*. No question tool because
nothing invoked you interactively is *unattended*.

Mode detection is Step 0 and must come first. **Do not use a TTY test.** Stdin is not a
terminal in essentially any agent runtime, so `test -t 0` classifies a live user as
unattended and the tier-3 gate then silently never fires. That is the exact failure this
doctrine exists to prevent, and it looks like a clean run.

Decide from the invocation instead:

| Signal | Mode |
|---|---|
| `--scheduled` passed, or a scheduled task / hook / cron is the invoker | **Unattended** |
| A person asked for this in conversation, and `AskUserQuestion` is available | **Interactive, structured** |
| A person asked for this in conversation, and it is not | **Interactive, plain** |

When the invocation is genuinely ambiguous, **assume a person is there.** Asking a
question nobody answers costs one wasted turn; skipping the gate silently applies
nothing and reports that everything is fine.

---

## STOP conditions — check these first

1. **No wiki → HALT and create nothing.** No `SCHEMA.md` and no `companies/` means the
   linter exits 1 with the message to run `/hiw-setup`. Relay it. Do not scaffold.

2. **Never resolve a contradiction.** Not in either mode, not with a majority of
   sources, not because one value looks more plausible. Insert the marker naming both
   values and both sources, log it, move on. The report is where you may observe; the
   page is where you only mark.

3. **Never touch a `TBD`.** `TBD` is a correct value meaning "known unknown"
   (`SCHEMA.md` § 2.4). Replacing it with a plausible number is the exact failure this
   whole wiki exists to prevent, and the patcher is built to refuse it.

4. **The prose scan never feeds the patcher.** Two detection layers, one write contract:
   the regex layer (`lint-wiki.py`) may feed `patch-wiki.py`; the subagent layer
   (Step 4) may only produce markers, log lines and report entries. This is the cleanest
   safety boundary in the family — do not route around it. (Step 4)

5. **Run the shipped scripts by path; never inline, retype or rewrite one.** Do not
   paste a script into a heredoc, do not improve one mid-run, do not author a
   replacement. The shipped file is the single source of truth for what gets detected,
   and an edited copy changes the result while still appearing to work.

6. **Never delete a page and never rename one.** A withdrawn plan gets
   `status: superseded`.

7. **Two questions maximum, both interactive-only:** the Step 6 tier-3 menu and the
   Step 8 schedule offer. Ask no others.

---

## Procedure

### Step 0 — Mode

Detect the mode and say which one you are in, in one clause. A user who expected to be
asked something and was not deserves to know why.

### Step 1 — Detect

```bash
S="skills/hiw-lint"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
mkdir -p output
python3 "$S/scripts/lint-wiki.py" --wiki . --out output/_wiki-data.json
```

Exit 1 means there is no wiki here; relay the script's message and stop. Otherwise the
stderr receipt gives you the shape of the run: carriers, plans, findings by severity,
and how many are autofixable. **Findings never affect the exit code** — a wiki with 400
violations still exits 0, because the JSON is the report and the flow does not branch on
`$?`.

Read `output/_wiki-data.json`. `counts.by_rule` is your table of contents. Each finding
carries a stable `rule` id, a `severity`, an `autofix` flag, the page, and where the
detector could compute the sanctioned fix, a `derived` map.

### Step 2 — Repair the mechanical

Dry run first, always, so the plan is available to the report before anything moves:

```bash
S="skills/hiw-lint"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$S/scripts/patch-wiki.py" --data output/_wiki-data.json --dry-run \
  --out output/_patch-plan.json
```

Read it. Then apply — in **both** modes, because everything in it is tier 1:

```bash
S="skills/hiw-lint"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$S/scripts/patch-wiki.py" --data output/_wiki-data.json \
  --out output/_patch.json
```

**The patcher's own output is the tier-1/tier-3 split.** Its `applied` array is tier 1;
its `skipped` array — each entry carrying a `reason` — is what needs a human. That is
why it runs before anything is proposed.

Two of its refusals are worth understanding rather than working around:

- **A rewrite that would not preserve the value is refused**, even though the linter
  marked it autofixable. The patcher re-checks the bytes on disk, and a disagreement
  with the linter means the page changed since the scan. Refusing is correct.
- **A required key with no derivable value is left absent.** There is no fallback guess.
  The reason names the fields, and they go in the report.

**Then re-run the linter**, because the patcher moved things and everything downstream
reads the JSON:

```bash
S="skills/hiw-lint"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$S/scripts/lint-wiki.py" --wiki . --out output/_wiki-data.json
```

This second pass routinely surfaces findings the first could not reach. A
`deductible_individual: 1,000` parses as nothing until the comma is stripped; once it is
a number, the linter can see that the OOP max below it is impossible. **Chained
detection is expected, not a symptom of a broken first pass** — say so if the finding
count goes up.

### Step 3 — Read every page (fan out above the threshold)

You need the substance of the pages in context to do Step 4, but reading dozens inline
is slow. The wiki is a set of carrier folders, so the natural unit of parallelism is a
**carrier**, not a file.

1. **Two carriers or fewer:** read the pages inline with Read.
2. **More than two carriers:** fan out, **one subagent per company folder** —
   `companies/blue-shield-ca/`, `companies/kaiser-permanente/`,
   `companies/aetna-ca/`, and so on. One agent per carrier, however many plans it holds.

Each subagent returns, for every page in its folder:

- the plan title and `plan_id` verbatim;
- every **numeric or factual claim stated in the page BODY**, with its `[source:]` — a
  premium quoted in `## Cost Structure` prose, a copay in the `## Covered Services`
  table, a network size, a visit cap, a waiting period, a formulary tier, a service-area
  exclusion;
- every `[assumption:]` and `[verify:]` tag, verbatim;
- whether any `**CONTRADICTION:**` marker is already present;
- anything under `## Additional capture` that looks like it belongs in a fixed section.

**Step 4 needs those claims and this is the only pass that collects them.** Enumerate
them; do not summarize.

**Collect all subagent results before any analysis** — do not begin Step 4 until every
fan-out task has returned.

**The fan-out is for speed and awareness only.** The linter already re-read every file
from disk in Step 1 and is the source of truth for what exists. That is what makes a
lost subagent degrade the run to slower rather than to wrong, and it is why there is no
retry doctrine here: note the carrier that failed, and say its prose went unscanned.

### Step 4 — The prose scan

The linter is deterministic and compares only **structured frontmatter values**, so it
misses the common case: a body that contradicts its own frontmatter, or one source's
prose contradicting another's, inside the same page.

Four things to look for, and only these four:

1. **Body against frontmatter.** `## Cost Structure` prose saying "the deductible is
   $1,000" on a page whose frontmatter says `deductible_individual: 750`. This is the
   most common real defect in an ingested wiki and no regex will find it.
2. **Prose against prose.** Two `[source:]`-tagged claims on one page that cannot both
   be true — "$35 primary care copay [source: A]" and "$45 primary care copay
   [source: B]".
3. **A coinsurance that reads inverted.** A Bronze plan whose `## Covered Services`
   table describes the plan paying 40% while `coinsurance_in_network: 40` says the
   member does. One of the two is wrong and the consequence is large.
4. **Content in `## Additional capture` that belongs in a fixed section.** An
   exclusions list filed under `### Notes` is invisible to `/hiw-compare`, which reads
   `## Exclusions & Limits`.

**This step detects and never resolves, and it never feeds the patcher.** Its findings
go to exactly three places: a marker on the page (Step 5), a `log.md` entry, and the
report.

**When in doubt, do not flag.** A false positive here costs the user's attention, and
attention spent on a non-finding is attention not spent on a real one. Two figures for
different plan years are not a contradiction. Two figures for different family sizes are
not a contradiction. `TBD` is not a claim and never conflicts with anything.

### Step 5 — Insert the markers

Strictly additive. Insert marker lines; change nothing else.

```markdown
**CONTRADICTION:** deductible_individual 750 [source: blue-2026-sbc.pdf] vs. body text "$1,000 deductible" [source: blue-2026-brochure.pdf] — unresolved, pending your decision. [2026-08-25 via hiw-lint]
```

Four rules:

1. **Put the marker inside the fixed section that holds the claim** — never above the
   first heading, and never below `## Additional capture`, where consumers stop reading
   the contract. It is a line beside a claim, not a page banner.
2. **Leave both claims exactly as they are.** Do not edit either, and do not add a
   recommendation about which is right. The report is where you may observe; the page is
   where you only mark.
3. **Do not double-mark.** Search for an existing marker naming the same two values
   before inserting. Re-running this skill must be idempotent.
4. **Update `last_updated` and set `updated_by: hiw-lint`** on a page you marked.

### Step 6 — The one question

Regenerate the index first, because it needs no approval and its input is now current:

```bash
S="skills/hiw-lint"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$S/scripts/index-wiki.py" --data output/_wiki-data.json --wiki .
```

`index.md` is a **derived catalog**. It holds no knowledge of its own, so it is
rebuildable from `companies/` at any moment and is rewritten on every run, in both
modes, no approval. **Never record anything in `index.md` that is not on a page** — the
moment it holds a fact of its own, regenerating it destroys that fact and this step
stops being safe to run unattended.

Then, **interactive modes only**, run **one AskUserQuestion call** — header
`"Fix these"`, `multiSelect: true`, question `"Repaired {n} formatting and frontmatter
issues automatically, and marked {n} contradictions on their pages for you. {n} items
need your call:"`, options:

- `"Repoint {n} ambiguous cross-reference(s) — I'll show you the candidates"`
- `"Correct {n} roster row(s) on company pages that disagree with the plan frontmatter"`
- `"Set {n} off-year plan(s) still marked active to superseded"`
- `"None of these — leave them all in the report"`

`multiSelect: true`, so "None of these" means selecting nothing else; treat it as
authoritative if it is chosen alongside another option — an explicit "leave it" beats an
implicit "fix it".

Include only the option lines with a non-zero count. **If tier 3 is empty, skip the
question entirely** and say so in your closing message — do not ask a question with
nothing to decide. **Do not ask a follow-up**: you get one question here, so anything not
authorized in that single answer stays in the report for next time.

An impossible number pair — an OOP max below its deductible — is **never** on this menu.
Fixing it means deciding which of two sourced numbers was mis-read, and the answer is in
the source document, not in the wiki. It goes in the report with the page path and both
values.

On approval, apply exactly what was approved. Then re-run the linter and
`index-wiki.py` once more, so the index is not built from a pre-approval snapshot.

### Step 7 — Write the report, and the log

**`output/lint-<YYYY-MM-DD>.md`** — eight numbered sections, fixed order, each omitted
only if genuinely empty:

1. **Summary counts** — carriers, plans, findings by severity, applied, skipped,
   awaiting decision.
2. **Contradictions** — two subsections, `### Structured` (from the linter) and
   `### In prose` (from Step 4). Both values, both sources, the page, for each.
3. **Unknown costs** — every `TBD-CORE` and `TBD-CORE-ABSENT`, grouped by carrier. **This
   is the working list for `/hiw-refresh` and the most actionable section in the file.**
4. **Provenance gaps** — `PROV-NO-SOURCE` first and prominently: a page with no source
   marker has no number anyone can trust. Then missing receipts and open `[verify:]`
   tags.
5. **Contract drift** — invented headings, sections out of order, source records
   carrying plan keys, stray files inside company folders.
6. **Applied** — every tier-1 repair, with old and new value per field.
7. **Awaiting decision** — tier 3, each with the page, the values, and what approving
   would do.
8. **Skipped** — every patcher refusal with its reason. A refusal is a finding: it means
   either the page changed mid-run or the fix was not derivable.

A re-run on the same date overwrites that date's file rather than adding another — the
date, not the run, is the unit, so a wiki linted daily accumulates one file a day rather
than one a run.

**Nothing prunes them.** `lint_keep` in `_config/wiki-config.md` is advisory: when the
count of `output/lint-*.md` files exceeds it, say so in the closing report and let the
user delete the old ones. STOP 6 forbids this skill from deleting anything, and a
retention policy that quietly removes a report someone was about to read is not a
retention policy worth having.

**Append one entry to `log.md`:**

```markdown
## [YYYY-MM-DD] hiw-lint | <C> carriers, <P> plans — <A> auto-repaired, <M> contradictions marked, <Q> awaiting decision, <T> plans with an unknown core cost
```

Two logs, and do not merge them. `log.md` is the durable audit trail shared with every
skill; `output/lint-<date>.md` is the verbose per-item drill-down. **The log is the skim;
the report is the drill-down.**

**Refresh the Wiki Brief in `CLAUDE.md`**, between the
`<!-- wiki-brief-start -->` and `<!-- wiki-brief-end -->` markers: carrier count, plan
count, premium range, markets covered, and the one or two things most worth fixing.
Replace what is between the markers; touch nothing outside them.

### Step 8 — Report, and offer the cadence

In chat, five things, and no more:

1. **The shape** — carriers, plans, and whether `index.md` changed.
2. **What was repaired**, as a count by rule. Not a list; the report has the list.
3. **What needs a person**, as specific items with page paths. This is the part worth
   reading.
4. **What is unknown** — the `TBD` core count and the carriers it concentrates in, with
   a pointer to `/hiw-refresh`.
5. **Whether a comparison can be trusted right now.** One sentence, and it is the
   sentence people actually want: *"Nothing blocking — 19 plans, all sourced, four with
   an unrecorded copay that `/hiw-compare` will show as unknown."* Or: *"Two plan pages
   have no source marker at all; treat any comparison including them as unverified."*

**Say when there is nothing to say.** "Ten rule families, nothing to flag, index
regenerated" is a useful thing to have said out loud. A manufactured finding is worse
than an honest short report.

Then, **interactive modes only**, check for an existing schedule first
(`mcp__scheduled-tasks__list_scheduled_tasks`) and skip this entirely if one is already
set up. Where the harness has no scheduling capability at all, say so in one clause and
skip the question — offering a cadence you cannot create is worse than not offering one.
Otherwise run **one AskUserQuestion call** — header `"Auto-check"`, question `"This runs well on a cadence —
an unattended run repairs formatting, marks contradictions, regenerates the index and
writes the report, and leaves anything ambiguous for you. Schedule it?"`, options
(exactly these three): `["Monthly (recommended)", "Weekly", "No, not now"]`.
(multiSelect: false)

---

## Files in this skill

| File | What it does |
|---|---|
| `scripts/lint-wiki.py` | the only detector, and the family's only tree walker. Read-only. Emits the inventory **and** the findings as one json — the write contract every other script consumes |
| `scripts/patch-wiki.py` | the only writer of page fixes. Consumes the linter's `autofix: true` findings and re-detects nothing. Re-checks value preservation on disk and refuses when it fails |
| `scripts/index-wiki.py` | regenerates `index.md` from the linter's json. Never walks the tree |

Executed, never loaded into context. Read one only to debug its behaviour. They are
deliberately decoupled: **the linter is the only detector and never writes; nothing else
re-detects.** The JSON is the single write contract between them, and prose-detected
findings are never routed into it.

---

## Anti-patterns

- Do not resolve a contradiction. Not with a majority of sources, not because one value looks more plausible, not in either mode. Mark it and move on.
- Do not replace a `TBD` with a plausible number. It is a correct value meaning "known unknown", and replacing it is the exact failure this wiki exists to prevent.
- Do not route a prose-detected finding into the patcher's input. Two detection layers, one write contract; the regex layer may write, the LLM layer may not.
- Do not ask permission for a tier-1 repair. Stripping a comma from a number is not a decision, and putting it on the menu trains the user to approve without reading.
- Do not put a contradiction on the approval menu. There is no fix to approve.
- Do not put an impossible number pair on the approval menu. Fixing it means deciding which of two sourced numbers was mis-read, and the answer is in the source document, not the wiki.
- Do not ask a question with nothing to decide. Skip it and say you skipped it.
- Do not ask a follow-up after the tier-3 question. One question; the rest waits for next time.
- Do not fall through to unattended behaviour because the harness has no question tool. Ask in plain text and end the turn. A person is either there or not, and that is what distinguishes the modes — not the tooling.
- Do not skip the second linter run after patching. A comma stripped from a number is what lets the impossible OOP max below it become visible. Chained detection is expected.
- Do not treat a rising finding count after a patch as a failure. It is the second pass reaching what the first could not.
- Do not inline, retype, patch or regenerate any of the three scripts. A script pasted into a heredoc or reconstructed from memory changes what gets detected while still appearing to work.
- Do not walk `companies/` yourself. The linter walks; everything else reads its json. Two walkers eventually disagree.
- Do not record anything in `index.md` that is not on a page. The moment it holds a fact of its own, regenerating it destroys that fact and the step stops being safe unattended.
- Do not hand-edit `index.md`. It is rewritten wholesale on every run.
- Do not begin the prose scan before every fan-out subagent has returned. Collect first, then analyze.
- Do not fan out by plan page, or below the threshold. The threshold is the same number in every skill in this family — more than two carriers — so nobody has to remember which one it was.
- Do not flag two figures for different plan years, different family sizes, or a `TBD` against a value. None of those is a contradiction, and a false positive costs attention that a real finding then does not get.
- Do not put a marker above the first heading or below `## Additional capture`. It is a line beside a claim, not a page banner.
- Do not double-mark. Re-running this skill must be idempotent.
- Do not add a recommendation to a page marker about which value is right. Observe in the report; mark on the page.
- Do not edit either claim in a contradiction. Both stay exactly as they are.
- Do not delete or rename a page. A withdrawn plan gets `status: superseded`.
- Do not bury the unknown-cost list. It is the working list for `/hiw-refresh` and the most actionable thing this skill produces.
- Do not bury `PROV-NO-SOURCE`. A page with no source marker has no number anyone can trust.
- Do not merge the log entry and the report. The log is the skim; the report is the drill-down.
- Do not manufacture a finding to make the report look substantial. An honest short report is worth more.
- Do not detect the mode with `test -t 0`. Stdin is not a terminal in an agent runtime, so it classifies a live user as unattended and the approval gate then silently never fires — a failure that looks like a clean run.
- Do not offer a schedule you cannot create, and do not offer one when a schedule already exists.
- Do not delete an old lint report. Say the count is above `lint_keep` and let the user decide.
- Do not omit the one-sentence verdict on whether a comparison can be trusted right now. It is what people actually opened the report for.
