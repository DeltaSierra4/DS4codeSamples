---
name: hiw-setup
description: >-
  Scaffold a health-insurance-wiki — the knowledge base the other six hiw skills read
  and write. Creates the five directories, copies in the page contract byte-for-byte,
  seeds the operating rules, the pointer file and the wiki config, and writes an empty
  index and log.
  Does NOT ingest anything, create a company folder, or invent a plan; an empty
  companies/ is the correct end state. Use when the user says "set up a health
  insurance wiki", "start a plan comparison knowledge base", "scaffold the insurance
  wiki", or runs /hiw-setup.
allowed-tools: Read Write Edit Bash Glob Grep AskUserQuestion mcp__scheduled-tasks__create_scheduled_task
metadata:
  argument-hint: "(optional: a path for the wiki root; otherwise interactive)"
---

# /hiw-setup — Scaffold the Health-Insurance Wiki

Creates the five directories and the six root files that every other `hiw-*` skill
depends on — `SCHEMA.md`, `AGENTS.md`, `CLAUDE.md`, `index.md`, `log.md` and
`_config/wiki-config.md`. Nothing else. The wiki it produces is deliberately empty: a scaffold with
no plans is a wiki nobody has ingested into yet, which is a normal state and the
correct end state of this skill.

Self-contained skill. Its three templates and the page contract live in
`assets/` beside this file, resolved with the two-rung ladder every command block
below applies inline:

```bash
S="skills/hiw-setup"; [ -d "$S/assets" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-setup"
```

If neither rung resolves, report the missing asset and stop. Do not reconstruct a
template from memory — see STOP condition 2.

---

## STOP conditions — check these first

Short list, at the top, because on a long file the rules that matter get read last.

1. **A wiki already here → verify and fill gaps; never re-scaffold.** If the target
   path already holds `SCHEMA.md` or a non-empty `companies/`, this is a re-run. Ask
   the Step 1 re-run question, then add only what is missing. **Never overwrite any of
   the six root files that already exist** — `SCHEMA.md`, `AGENTS.md`, `CLAUDE.md`,
   `index.md`, `log.md`, `_config/wiki-config.md`. `CLAUDE.md` matters most here and is
   the easiest to forget: `/hiw-lint` writes the live Wiki Brief into it between the
   `<!-- wiki-brief-start -->` markers, so re-writing it from the template silently
   discards the only current summary of what the wiki holds and replaces it with
   `_No Wiki Brief yet._` (Step 1, Step 5)

2. **Copy the assets; never retype them.** `SCHEMA.md` is cited by section number
   (`§ 2.4`, `§ 7.2`) by every other skill in this family. A re-flowed, summarized or
   paraphrased copy still looks correct and silently breaks every one of those
   citations. Use `cp`. If the file cannot be found, say so and seed nothing — a thin
   hand-written substitute under the canonical name is worse than an absent file,
   because every later agent will read it, believe it is the contract, and never
   learn the real one. (Step 4)

3. **Never create a company folder, a plan page, or a source record.** Not even an
   example, not even a placeholder. `/hiw-ingest` owns `companies/`, and an invented
   plan page is indistinguishable from a real one three weeks later. (Step 3)

4. **Never invent a plan year, a currency or a geography.** These settings drive
   every downstream comparison. Ask, take the answer, and where the user does not
   know, write the documented default and say which default you wrote. (Step 2)

5. **Never delete anything.** This skill only creates. If something is in the way,
   report it and stop.

---

## RULES — read before acting

This is a **rigid, prescribed procedure**, not a set of suggestions. Follow the steps
in order and execute each AskUserQuestion **exactly as written** — same questions,
same options.

- **Do not invent, add, reword, merge, or reorder questions or options.** Only the
  questions spelled out below may be asked. If a step lists no question, you ask none.
- **Every AskUserQuestion has at most 4 options.** The UI auto-appends a free-text
  path; never add your own "type it" / "other" / "chat about this" option. For a
  free-text answer such as a path or a carrier list, the two listed options are
  genuine fallbacks, never a restatement of "type it".
- **Ask through AskUserQuestion when you have it, in plain text when you do not, and
  never by taking a default silently.** Where the harness has no question tool, ask
  in plain text with numbered options and end the turn. Where a scheduled run invoked
  you with no user present, write the documented defaults and name every default you
  took in the closing report.
- **Non-destructive and mergeable.** Every write is create-if-absent. A second run
  over a live wiki must be safe, and must report what it found rather than what it
  wished it had found.
- **Report the ground state before writing.** Say what you found at the target path
  in plain text, so the user can correct your reading of it early rather than at the
  end.
- **`AGENTS.md` and `SCHEMA.md` are the authority; this skill is their courier.** Do
  not restate their rules in `CLAUDE.md`, in the closing report, or anywhere else. A
  second copy drifts out of agreement with the first, and then two files disagree
  about the contract.

---

## Procedure

### Step 1 — Locate the root and read the ground state

1. **Take the path from the argument if there is one.** Otherwise use the current
   working directory — the directory the user is working in, not the directory the
   skill files live in.

2. **Look, before asking anything.** Four cheap checks, no file parsed:

   ```bash
   ls -d SCHEMA.md AGENTS.md index.md log.md _config companies raw synthesis output 2>/dev/null
   ```

3. **Report what you found, in plain text**, in one short paragraph. Name the path
   you are about to write into, absolutely, so a wrong guess is caught now.

4. **If `SCHEMA.md` exists or `companies/` is non-empty**, this is a re-run. Run
   **one AskUserQuestion call** — header `"Re-run"`, question `"A wiki already exists
   at this path. What do you want to do?"`, options (exactly these two):
   `["Verify only — report what's present, create nothing", "Fill in anything missing, leave everything that exists untouched"]`.
   (multiSelect: false) On "Verify only", print the inventory and stop; skip every
   remaining step.

5. **If the path does not exist**, say so and create it. Creating a directory the
   user named is not a decision worth a question.

### Step 2 — The five settings

Two calls, five questions: four in the first, one in the second. Not five sequential
turns — this is a setup wizard, and five turns to name a currency is how a setup wizard
becomes something people avoid running.

**Call 1 — four questions, one call:**

- Question 1 — header `"Wiki name"`, question `"What should this wiki be called? (type it in the field)"`, options (exactly these two): `["Health Insurance Wiki", "Use the folder name"]`. (multiSelect: false)
- Question 2 — header `"Plan year"`, question `"Which plan year will you mostly be comparing?"`, options (exactly these three): `["2026", "2027", "Not sure yet — I'll set it later"]`. (multiSelect: false)
- Question 3 — header `"Currency"`, question `"Which currency are the premiums in? Every money field in the wiki will be in this one currency."`, options (exactly these three): `["USD", "GBP", "EUR"]`. (multiSelect: false)
- Question 4 — header `"Markets"`, question `"Which markets will you track? This narrows defaults; it never filters what the wiki can store."`, `multiSelect: true`, options (exactly these four): `["Individual / family (ACA marketplace)", "Employer group (small or large)", "Medicare (Advantage, Supplement, Part D)", "Dental and vision"]`.

**Call 2 — one question**, on its own because its answer depends on nothing above and
its default is genuinely fine:

- header `"Geography"`, question `"Which geography? Used as the default service area when a query does not state one. (type it in the field)"`, options (exactly these two): `["United States — nationwide", "Not sure yet"]`. (multiSelect: false)

**Defaults when a question is unanswered or the run is unattended:** wiki name =
folder name; `plan_year` = the current calendar year; `currency` = `USD`; `markets` =
`[individual]`; `geography` = the empty string. Name every default you took in
Step 7.

### Step 3 — Create the directories

```bash
mkdir -p companies raw synthesis output _config
```

Exactly five, and the design decisions behind them are already resolved:

| Path | Holds | Written by |
|---|---|---|
| `companies/` | one folder per carrier — the knowledge | `/hiw-ingest`, `/hiw-refresh`, `/hiw-lint` |
| `raw/` | immutable originals, mirrored by company | `/hiw-ingest`, `/hiw-refresh` |
| `synthesis/` | saved comparisons, recommendations, briefs | `/hiw-query`, `/hiw-compare` |
| `output/` | generated HTML and reports | `/hiw-list-plan`, `/hiw-compare`, `/hiw-lint` |
| `_config/` | wiki-level settings | this skill |

**`companies/` stays empty.** Do not create a company folder, and do not create a
`.gitkeep` inside one. `/hiw-ingest` special-cases "no folder for this carrier yet" as
a real and meaningful signal — it is how the skill knows to write a company page. A
pre-created empty folder makes that signal indistinguishable from an ingest that
half-failed.

**Do not create `raw/assets/`, `companies/_template/`, or an `examples/` directory.**
Nothing reads them and every later agent has to work out whether they matter.

### Step 4 — Copy the page contract and the operating rules

```bash
S="skills/hiw-setup"; [ -d "$S/assets" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-setup"
[ -f SCHEMA.md ] || cp "$S/assets/SCHEMA.md" SCHEMA.md
[ -f AGENTS.md ] || cp "$S/assets/AGENTS.template.md" AGENTS.md
```

Both are literal copies. **Copy them; do not read them and retype them.**
`SCHEMA.md`'s section numbers are cited verbatim by the other six skills, and
`AGENTS.md` is written to be agent-agnostic on purpose — it names no host, assumes no
slash commands, and reads everything wiki-specific at runtime.

Verify both landed and are the size you expect. If either `cp` failed, stop and say
which one; do not proceed with a partial contract in place.

### Step 5 — Write the config, the pointer file, the index and the log

**`_config/wiki-config.md`** — from `assets/wiki-config.template.md`, substituting
`{{WIKI_NAME}}`, `{{WIKI_ROOT}}` (absolute), `{{PLAN_YEAR}}`, `{{CURRENCY}}`,
`{{GEOGRAPHY}}`, `{{MARKETS}}` (inline flow list of the `market` values from
`SCHEMA.md` § 2.2 that the Step 2 answer maps onto) and `{{CREATED}}`. Keep the
prose; it documents every optional key and a config nobody understands is a config
nobody tunes.

**`CLAUDE.md`** — **only if absent.** From `assets/CLAUDE.template.md`, substituting
`{{WIKI_NAME}}`, `{{WIKI_PURPOSE}}` (one sentence, from what the user said they are
comparing), `{{PLAN_YEAR}}`, `{{CURRENCY}}`, `{{GEOGRAPHY}}`, `{{MARKETS}}`. This file is
a pointer plus a state summary; it deliberately does not restate the contract.

If it already exists and the Step 2 settings changed, edit **only** the
`## Wiki settings` bullets in place. Leave everything else, and in particular everything
between `<!-- wiki-brief-start -->` and `<!-- wiki-brief-end -->` — that region belongs to
`/hiw-lint` and holds the only live summary of what the wiki currently contains.

**`index.md`** — a stub, because `/hiw-lint` regenerates it wholesale and anything
written here is thrown away on the first lint:

```markdown
# Index

_No plans yet. Run `/hiw-ingest` with a plan document or a carrier URL, then
`/hiw-lint` to build this catalog._
```

**`log.md`** — the append-only timeline, seeded with this run. Every other skill appends
one entry per run, under the subsection vocabulary in `SCHEMA.md` § 9, so this is the one
shared timeline across the family and the header belongs in it from the start:

```markdown
# Log

## [YYYY-MM-DD] hiw-setup | wiki scaffolded — plan year <Y>, currency <C>, markets <M>
```

### Step 6 — Verify, and say so out loud even when it is clean

Twelve checks — six files, five directories, and one that the contract copy is the real
one rather than a truncated `cp`:

```bash
for f in SCHEMA.md AGENTS.md CLAUDE.md index.md log.md _config/wiki-config.md; do
  [ -f "$f" ] && echo "ok   $f" || echo "MISS $f"
done
for d in companies raw synthesis output _config; do
  [ -d "$d" ] && echo "ok   $d/" || echo "MISS $d/"
done
N=$(grep -c "hiw-" SCHEMA.md); [ "$N" -ge 15 ] \
  && echo "ok   SCHEMA.md references the skills ($N mentions)" \
  || echo "MISS SCHEMA.md looks truncated — only $N skill reference(s)"
[ -z "$(ls -A companies 2>/dev/null)" ] && echo "ok   companies/ empty, as intended"
```

Print the result. "Twelve checks, nothing missing, `companies/` empty as intended" is a
useful thing to have said out loud before handing the wiki over.

### Step 7 — Report and hand off

Four short parts, in this order:

1. **What was created** — the tree, and the absolute path of the root.
2. **The settings you recorded**, and **every default you took because a question went
   unanswered**, named individually. A silently-defaulted currency surfaces three
   weeks later as a comparison in the wrong money.
3. **What to do next**, concretely: `/hiw-ingest` with a file path or a carrier URL.
   Say that the first ingest creates the first company folder.
4. **The standing caveat**, once: this wiki records what published sources say; it is
   not advice, not a quote, and not an eligibility determination.

Then offer the cadence, but only if a person is there. Run **one AskUserQuestion
call** — header `"Freshness"`, question `"Plan rates change annually and mid-year
corrections happen. Want a scheduled check that re-runs /hiw-lint and reports what
has gone stale?"`, options (exactly these three):
`["Monthly (recommended)", "Quarterly", "No, not now"]`. (multiSelect: false) On a
choice other than "No", create the scheduled task with a prompt that runs `/hiw-lint`
and reports only if it finds something. Skip this question entirely on an unattended
run.

---

## Files in this skill

| File | What it is |
|---|---|
| `assets/SCHEMA.md` | the page contract. Copied to the wiki root byte-for-byte; cited by section number by every other skill |
| `assets/AGENTS.template.md` | the workspace operating rules. Copied to `AGENTS.md`; agent-agnostic by design |
| `assets/CLAUDE.template.md` | the pointer + state summary. Substituted, then written to `CLAUDE.md` |
| `assets/wiki-config.template.md` | the settings file. Substituted, then written to `_config/wiki-config.md` |

Copied, never loaded into context and retyped. Read one only to confirm a placeholder
name.

---

## Anti-patterns

- Do not create a company folder, a plan page, or a source record. An empty `companies/` is the correct end state of this skill.
- Do not create an example or template plan page "so the user can see the shape". Three weeks later nobody can tell it from a real one, and `/hiw-compare` will rank it.
- Do not read `SCHEMA.md` and retype it. Its section numbers are cited verbatim elsewhere; a re-flowed copy breaks every citation while looking correct.
- Do not substitute a short hand-written folder guide when a template cannot be found. A thin file under the canonical name is worse than an absent one.
- Do not overwrite an existing `SCHEMA.md`, `AGENTS.md`, `index.md`, `log.md` or `_config/wiki-config.md`. A re-run fills gaps; it does not reset.
- Do not restate the contract's rules in `CLAUDE.md` or in the closing report. A second copy drifts, and then two files disagree about the contract.
- Do not invent a plan year, a currency, a geography or a market list. Ask; and where you default, name the default.
- Do not write a real `index.md` here. `/hiw-lint` regenerates it wholesale, so anything written now is thrown away on the first lint — and a hand-written index that survives is worse, because it holds facts no page holds.
- Do not ask five separate questions across five turns for the five settings. Two calls.
- Do not turn Step 1's path resolution into a question. The argument or the working directory answers it; ask only if both are genuinely unusable.
- Do not overwrite `CLAUDE.md` on a re-run. `/hiw-lint` keeps the live Wiki Brief in it, and resetting it to the template discards the only current summary of what the wiki holds.
- Do not offer the scheduled freshness check when the harness has no scheduling capability. Offering a cadence you cannot create is worse than not offering one.
- Do not create `raw/assets/`, `companies/_template/`, or `examples/`. Nothing reads them.
- Do not run `git init`, install a plugin, wire a hook, or add an MCP server. This skill scaffolds a knowledge base and nothing else.
- Do not skip Step 6 because Step 5 appeared to work. `cp` failing silently and leaving no `SCHEMA.md` is the one failure that makes every later skill subtly wrong rather than obviously broken.
- Do not narrate each `mkdir`. Report the tree once, at the end.
- Do not offer the scheduled freshness check on an unattended run — there is nobody to answer, and a defaulted "yes" creates a task the user never asked for.
