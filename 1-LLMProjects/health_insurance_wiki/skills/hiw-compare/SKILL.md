---
name: hiw-compare
description: >-
  Build a side-by-side comparison of two or more health insurance plans from the
  health-insurance-wiki, with deterministic annual-cost modelling across three
  utilization scenarios. Takes plans the user names, or helps them choose — running
  /hiw-list-plan when they need to see the options and /hiw-query when they want a
  recommendation first. Fans out one subagent per carrier represented for the coverage
  detail, then emits a self-contained HTML matrix. Use when the user says "compare these
  plans", "which is better", "side by side", "difference between X and Y", or runs
  /hiw-compare.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion
metadata:
  argument-hint: "(two or more plan names or plan_ids, comma-separated; omit for interactive selection)"
---

# /hiw-compare — Two or More Plans, Side by Side

Produces `output/comparison-<date>.html`: every comparable field as a row, every plan
as a column, and three annual-cost scenarios computed in Python.

The arithmetic is delegated on purpose. An LLM asked to add a premium, a deductible and
four specialist copays will usually get it right and will occasionally not, and there is
no way to tell which run you got. Money arithmetic belongs in code you can read once and
trust thereafter. `build-comparison.py` is that code; the cost model is forty lines and
the SKILL does not duplicate it.

Ladders, applied inline in every command block:

```bash
L="skills/hiw-lint";    [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
K="skills/hiw-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/hiw-compare"
```

---

## STOP conditions — check these first

1. **Fewer than two plans in the wiki → say so and stop.** *"There is only one plan
   stored, so there is nothing to compare it against. Run `/hiw-ingest` for another
   carrier."*

2. **Fewer than two plans resolved → do not build.** The script exits 1 and prints
   every id it could not match. Report the misses by name, offer the selection flow in
   Step 2, and try again. Never build a one-column comparison, and never substitute a
   plan the user did not name. (Step 3)

3. **A `TBD` is never a zero, and a scenario missing an input is never estimated.** The
   script enforces this: a scenario needing a `TBD` field reports as not computable
   with the missing inputs named. Do not work around it by supplying a plausible value
   on the command line, and do not describe an uncomputed scenario as an approximation
   in your summary. (Step 4)

4. **Never rank across plans on a field only some of them record.** The script computes
   every ranking over the plans that actually have the value and displays the count.
   Repeat that count in your summary: "cheapest of the 3 plans that record a
   deductible, out of 5" — never "cheapest". (Step 5)

5. **This is not advice.** The caveat is on the HTML page and belongs in the chat
   summary too, because the chat is where the impression forms. No step removes it.

6. **Three questions maximum:** at most two in the selection flow (Step 2) and the save
   offer (Step 6). Ask no others. Where the argument named the plans, Step 2 asks nothing
   and the budget is one.

---

## RULES — read before acting

- **Never compare across plan years without saying so.** A 2026 plan against a 2025
  plan is a rate-change analysis, not a plan comparison, and it is genuinely useful —
  but only if it is labelled. The script flags a superseded plan in the selection; carry
  that flag into your summary.
- **The frontmatter is the machine truth.** Where a subagent's narrative disagrees with
  a number, the number wins and the disagreement is a finding about that page.
- **Fan out by carrier, never by plan.** Two plans from one carrier is one subagent.
- **Collect every subagent result before writing your summary.**
- **Say which scenario governs, and why.** Three scenarios with no guidance is a table;
  three scenarios with "if you expect a heavy year, the bad-year column is the only
  honest basis and it reverses the ranking" is an answer.
- **Do not restate the cost model.** It is documented in
  `scripts/build-comparison.py`'s module docstring and printed on every page it
  generates. A second description here would drift out of agreement with the code.
- **Ask through AskUserQuestion when you have it, in plain text when you do not.**

---

## Procedure

### Step 1 — Walk the wiki

```bash
L="skills/hiw-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$L/scripts/lint-wiki.py" --wiki . --out output/_wiki-data.json
```

Note the plan count and the `error`-severity finding count. If any of the plans that
end up selected carry an error-level finding, the generated page says so and so should
you — a comparison built on a page with an impossible OOP max is a comparison of a
mis-read.

### Step 2 — Establish which plans, in three escalating moves

**If the argument named plans, use them.** Skip to Step 3. A user who typed two plan
names does not want a menu.

Otherwise run **one AskUserQuestion call** — header `"Selection"`, question `"Which
plans do you want to compare? Name them in the field, or pick a route."`, options
(exactly these three):
`["Show me everything first — build the catalog", "I don't know yet — ask me what I need and recommend", "Compare the cheapest plan from each carrier"]`.
(multiSelect: false)

The three routes, and each is a real handoff rather than a hint:

1. **"Show me everything first"** — run `/hiw-list-plan` to build
   `output/plan-catalog.html` and open it. Then build a **short chooser list** in chat
   from `output/_wiki-data.json` — plan title, carrier, tier, network, premium, one line
   each — so the user can name plans without leaving the conversation. That is a chooser,
   not the catalog: `/hiw-list-plan`'s rule against pasting the catalog into chat is
   about not substituting a wall of text for the file, and a dozen one-line entries is
   the opposite of that. Then run **one AskUserQuestion call** — header `"Plans"`,
   question `"Which of these? Name two or more in the field."`, options (exactly these
   three): `["The cheapest and the most expensive", "One from each carrier", "All plans in one tier (say which)"]`.
   (multiSelect: false) That is the second and last question.

2. **"I don't know yet"** — hand off to `/hiw-query`. Run its needs assessment, take
   its shortlist, and come back here with those `plan_id`s. Do not run a needs
   assessment inline; `/hiw-query` owns that conversation and duplicating it here means
   two versions of it drifting apart.

3. **"Compare the cheapest from each carrier"** — resolve it yourself from
   `output/_wiki-data.json`: the lowest `premium_monthly_individual` per company among
   active plans. **Plans whose premium is `TBD` are not candidates for "cheapest"** —
   an unknown is not a low number. Where a carrier's every plan has a `TBD` premium,
   name that carrier as unrepresented rather than picking one arbitrarily.

**Where the user is still undecided after all three**, do not loop. Pick a defensible
default — the cheapest and the most expensive active plan in the wiki, plus the
median-premium plan — build it, and say exactly that: *"You were undecided, so I
compared the cheapest, the median and the most expensive active plan. Name any two
plans and I'll rebuild it."* A built comparison someone can react to beats a fourth
question.

### Step 3 — Resolve the ids

```bash
K="skills/hiw-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/hiw-compare"
python3 "$K/scripts/build-comparison.py" --data output/_wiki-data.json --list
```

The matcher accepts a full `plan_id`, a bare plan slug, or a case-insensitive title, and
it tries them in that order — exact id first, always. Two carriers each having a "Gold
80 PPO" is the normal case, not an edge case, so a title that matches more than one
plan is reported as ambiguous and skipped rather than guessed at.

**Report every miss and every ambiguity by name before building.** A comparison quietly
built from three of the four plans the user named is the worst failure available here,
because the missing plan was probably the one they cared about.

### Step 4 — Build

**4a — Fan out for the coverage detail first, if it is worth it.** Skip this entirely
for a two-plan comparison; the matrix plus the pages' own fit notes carry it. The order
matters: the notes file has to exist before the build reads it, and a build run before
the fan-out silently loses every subagent's prose.

For **three or more plans spanning more than one carrier**, fan out **one subagent per
carrier represented in the selection** — not one per plan. Brief:

> You are the master of `companies/<slug>/`. Read `SCHEMA.md` first, then read only
> these plan pages in your own folder: `<paths>`. **Read nothing outside your company
> folder. Write nothing.**
>
> For each, return JSON:
>
> ```json
> {"plans": [{
>   "plan_id": "<verbatim>",
>   "one_liner": "<under 100 chars: why pick this over its siblings, not what it is>",
>   "suits": "<who, anchored to a number on the page>",
>   "look_elsewhere": "<who should not, anchored to a number on the page>",
>   "notable_limits": "<visit caps, prior-authorization rules, waiting periods, exclusions that would change a decision — from '## Exclusions & Limits'>",
>   "exclusions": "<what this plan does not cover at all>"
> }]}
> ```
>
> Rules: every claim traces to a sentence or a number on the page; **never state a cost
> figure** — the parent has the frontmatter and will contradict you visibly; a page whose
> `## Fit Notes` is `_TBD._` gets empty `suits` and `look_elsewhere`; never mention
> another carrier; `plan_id` verbatim, it is the join key.

Collect every return, then write `output/_compare-notes.json` as
`{"plans": [ ... ]}`. Drop any `plan_id` not present in `output/_wiki-data.json` — it
was reconstructed rather than copied. Drop any note whose cost figure contradicts the
frontmatter, and report the page.

**4b — Build.** `--plans` is required; the script exits 1 without it. Pass the ids you
resolved in Step 3, comma-separated, in the order you want the columns.

```bash
K="skills/hiw-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/hiw-compare"
python3 "$K/scripts/build-comparison.py" \
  --data output/_wiki-data.json \
  --plans "<id1>,<id2>,<id3>" \
  --notes output/_compare-notes.json \
  --out "output/comparison-$(date +%F).html" \
  --json output/_comparison.json
```

`--notes` is optional; without it the page falls back to each plan's own `## Fit Notes`
and `## Snapshot`, which is usually adequate. `--json` writes the computed payload —
every scenario total, every ranking, every missing input — so Step 5 reads numbers
rather than re-deriving them from the HTML.

Read the stderr receipt: plan count, how many scenarios came back uncomputable, and the
error and warning counts on the pages compared. Those three numbers are the honest
headline of the run.

**Why the fan-out is worth it here at all:** `## Exclusions & Limits` is the section
most often skipped during ingest and most often decisive during a comparison, and it is
prose that no frontmatter key can hold. The matrix compares what is comparable; the
subagents surface what is not.

### Step 5 — Read the result and say what it means

The page is built and `output/_comparison.json` holds every number on it. Read that
file, not the HTML. Now do the part the script cannot: interpret it.

1. **Name the governing scenario.** All three are on the page. Which one matters
   depends on expected utilization, and if the user has not said, ask nothing — present
   the fork instead: *"On a healthy year the Bronze plan is $3,600 cheaper. On a bad
   year it is $1,000 cheaper. On a moderate year it is $2,300 more expensive. The
   decision turns on whether you expect to meet the deductible."*

2. **Name the crossover.** The most useful sentence a comparison produces is where the
   ranking flips. Two plans whose ranking reverses between the healthy-year and
   bad-year columns is the whole story of that comparison, and it is invisible in a
   table someone skims.

3. **Report every uncomputable scenario and why.** "The moderate-year figure for Silver
   70 PPO could not be computed because its imaging copay is not recorded" — the field
   name, the plan, the consequence. That sentence is what turns a gap into a task.

4. **Repeat the comparability counts.** Never "cheapest deductible" where only three of
   five plans record one. Say "the lowest deductible among the three plans that record
   one."

5. **Surface the non-cost differences that decide real choices**, from the fan-out or
   the pages: referral requirements, out-of-network coverage, formulary tier placement,
   visit caps, prior authorization. A $40/month premium difference is routinely
   outweighed by a brand-name drug sitting on tier 4 rather than tier 2.

6. **Flag any superseded or off-year plan in the selection**, and say what the
   comparison then is: a rate-change analysis, not a plan choice.

7. **Flag the error-level findings** on the pages compared, and point at `/hiw-lint`.
   Do not fix them here.

8. **The caveat**, once, in the chat as well as on the page.

### Step 6 — Open it, save it, log it

```bash
OUT="$(cd output && pwd)/comparison-$(date +%F).html"
[ -f "$OUT" ] && echo "$OUT" || echo "MISSING: $OUT"
```

Resolve to absolute, verify, then open — `open` on macOS, `start ""` on Windows,
`xdg-open ... >/dev/null 2>&1 &` on Linux — and print the path alongside. **In Cowork,
always also present the file**; the OS opener cannot reach the user's desktop from a
sandboxed session.

Then run **one AskUserQuestion call**, but only if this comparison took real work
(three or more plans, or a fan-out) — header `"Save"`, question `"Save this comparison
to the wiki so you can re-open the reasoning later?"`, options (exactly these two):
`["Save it as a synthesis page", "The HTML file is enough"]`. (multiSelect: false)

On save, write `synthesis/comparison-<YYYY-MM-DD>-<slug>.md` with frontmatter
`title`, `category: synthesis`, `plan_ids: [...]`, `governing_scenario`, `created`,
`last_updated`, `updated_by: hiw-compare`, `status: active`, and a body carrying the
scenario table, the crossover, the unknowns and the caveat. **Nothing generated ever
lands inside a company folder.**

Append to `log.md`:

```markdown
## [YYYY-MM-DD] hiw-compare | <N> plans across <M> carriers — <K> scenario(s) uncomputable, governing scenario <name>
```

---

## Files in this skill

| File | What it does |
|---|---|
| `scripts/build-comparison.py` | resolves plan ids, computes the three annual-cost scenarios, ranks over the plans that record each field, and emits one self-contained HTML matrix. Stdlib only. `--list` prints every plan_id |
| `scripts/comparison-template.html` | the HTML/CSS/JS shell. Filters for "only rows where the plans differ" and "hide rows nobody recorded" |

Plus `lint-wiki.py` from `skills/hiw-lint/scripts/`. Executed, never loaded into
context. Run by path; never inline, retype or rewrite one — the shipped file is the
single source of truth for what the cost model does, and an edited copy silently
changes every number on the page.

---

## Anti-patterns

- Do not build a one-column comparison. Two plans is the minimum, and the script exiting 1 is correct behaviour.
- Do not omit `--plans`. The script exits 1 without it, and Step 3's `--list` resolves ids without passing them anywhere.
- Do not run the build before the fan-out. The notes file has to exist before the build reads it, and a build run first silently loses every subagent's prose.
- Do not scrape the scenario totals out of the HTML island. Pass `--json` and read the file. Two readers of one number means the second one drifting.
- Do not substitute a plan the user did not name because one of theirs did not resolve. Report the miss and ask.
- Do not build from three of the four plans the user named without saying so. The missing one was probably the one they cared about.
- Do not add up a scenario yourself. Run the script. An LLM doing money arithmetic is right most of the time, which is exactly the problem.
- Do not supply a plausible value on the command line to make an uncomputable scenario compute.
- Do not describe an uncomputable scenario as an approximation. Name the missing field and the plan.
- Do not say "cheapest" where only some plans record the field. Say "cheapest of the three that record it".
- Do not treat a `TBD` premium as a candidate for "cheapest from each carrier". An unknown is not a low number.
- Do not compare a 2026 plan against a 2025 plan without labelling it a rate-change analysis.
- Do not present the three scenarios and stop. The crossover — where the ranking flips — is the whole story, and it is invisible to someone skimming a table.
- Do not lead with premium alone. Premium plus out-of-pocket maximum is the number that decides how much a bad year can cost, and it is the least quoted figure in the industry.
- Do not omit the non-cost differences. A $40/month premium gap is routinely outweighed by a drug sitting on tier 4 rather than tier 2.
- Do not fan out by plan page. One subagent per carrier represented, and none at all for a two-plan comparison — the same threshold as every other skill in this family.
- Do not let a subagent read another carrier's folder, state a cost figure, or write anything.
- Do not begin the summary before every subagent has returned.
- Do not accept a `plan_id` that is not in the linter's json. It was reconstructed, and it silently drops that plan's narrative.
- Do not restate the cost model in this file. It lives in the script's docstring and prints on every page; a second copy drifts.
- Do not run a needs assessment inline. `/hiw-query` owns that conversation; two versions of it drift apart.
- Do not loop on an undecided user. Build a defensible default, say exactly what you chose, and invite a correction.
- Do not fix a lint finding here. Surface it and point at `/hiw-lint`.
- Do not assume a relative path opens. Resolve to absolute, verify, open, print.
- Do not paste the whole matrix into chat. Link the file, then say the governing scenario, the crossover, and what could not be computed.
- Do not write a synthesis page into a company folder. Company folders hold sourced facts only.
- Do not drop the caveat from the chat summary because it is already on the page. The chat is where the impression forms.
