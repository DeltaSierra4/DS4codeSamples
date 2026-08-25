---
name: hiw-list-plan
description: >-
  Build a browsable HTML catalog of every health insurance plan in the wiki, grouped by
  carrier, with filter, sort and search. Fans out one subagent per company folder — each
  becomes the master of its own carrier and returns the narrative its plan pages support
  — then joins that prose to the deterministic frontmatter numbers on plan_id. Use when
  the user says "what plans do we have", "list the plans", "show me everything by
  company", "build the plan catalog", or runs /hiw-list-plan.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion
metadata:
  argument-hint: "(no arguments — reads the whole wiki; optionally a carrier slug to limit it)"
---

# /hiw-list-plan — Every Plan, Grouped by Carrier

Produces `output/plan-catalog.html`: one self-contained page, no server, no CDN, that
answers "what do we have" and "which is cheapest" without anyone re-reading a plan
page.

The architecture is the point:

- **The numbers are deterministic.** `lint-wiki.py` walks the tree and
  `build-catalog.py` renders what it found. No language model retypes a premium.
- **The narrative is delegated.** One subagent per company folder writes the prose the
  frontmatter cannot hold — why a plan exists, who it suits, what its exclusions
  actually mean.
- **The two are joined on `plan_id`**, and where they disagree, the number wins and the
  note is shown beside it rather than replacing it.

Self-contained apart from the linter, which lives with `/hiw-lint` because it is the
family's single walker. Both ladders, applied inline in every command block below:

```bash
L="skills/hiw-lint";      [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
C="skills/hiw-list-plan"; [ -d "$C/scripts" ] || C="$CLAUDE_PLUGIN_ROOT/skills/hiw-list-plan"
```

---

## STOP conditions — check these first

1. **No `companies/` → say so and stop, without ceremony.** *"This wiki has no
   carriers yet, so there is nothing to catalog. Run `/hiw-ingest` with a plan document
   or a carrier URL."* An empty wiki is not an error. Do not build an empty HTML file
   to prove the pipeline works.

2. **Collect every subagent result before building anything.** A partial fan-out
   produces a catalog missing a carrier's narrative — and worse, a catalog that looks
   complete. (Step 3)

3. **Subagents read; they never write.** No subagent in this skill edits a plan page,
   touches `index.md`, appends to `log.md`, or runs a script. They return structured
   text to the parent, and the parent writes. (Step 3)

4. **Never let a note contradict a number.** A subagent that reports a premium
   different from the frontmatter has misread its own page. Keep the frontmatter value,
   drop the claim, and name the discrepancy in the report — it is a real finding about
   that page. (Step 5)

5. **Never fabricate a narrative for a page that has none.** A plan whose
   `## Fit Notes` is still `_TBD._` gets no "suits" line. The catalog renders that
   honestly, and a manufactured recommendation is worse than a blank field.

---

## RULES — read before acting

- **The company folder is the unit of parallelism.** Everything a subagent needs to
  become the master of one carrier is inside `companies/<slug>/` and nowhere else. That
  is why the layout is what it is: a per-carrier subagent has a naturally bounded
  context and cannot contaminate one carrier's facts with another's.
- **Fan out by company, never by file, and never "N agents, split the work".**
- **The linter is the source of truth for what exists.** The fan-out is for narrative
  and situational awareness; if a subagent's plan list disagrees with the linter's, the
  linter is right and the disagreement is a finding.
- **Do not restate the contract; apply it.** `SCHEMA.md` § 3.1 defines what
  `## Snapshot` and `## Fit Notes` hold, and the subagent brief below cites it rather
  than copying it.
- **Ask at most one question, and only when there is something to decide.** If the
  wiki has one carrier, do not ask which carriers to include.

---

## Procedure

### Step 1 — Walk the wiki

```bash
L="skills/hiw-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$L/scripts/lint-wiki.py" --wiki . --out output/_wiki-data.json
```

The receipt on stderr tells you the carrier count, the plan count and the finding
counts. Read `output/_wiki-data.json` for `companies[]`, `plans[]` and `counts` — that
is your inventory, and it is the only inventory. Do not glob `companies/` yourself.

If the linter reports `error`-severity findings, note the count. You will surface it in
the catalog and in the report; you will not fix it here — that is `/hiw-lint`'s job.

### Step 2 — Decide the scope, if there is anything to decide

If the argument named a carrier, use it. If the wiki holds **five or more** carriers,
run **one AskUserQuestion call** — header `"Scope"`, question `"<N> carriers in the
wiki. Catalog all of them, or narrow it?"`, options (exactly these three):
`["All carriers", "All carriers, active plans only", "Include superseded plans too — I want the rate history"]`. The free-text field takes a
carrier list where the user wants to narrow it; do not add an option that says so.
(multiSelect: false)

Below five carriers, ask nothing and catalog everything.

Superseded plans are **excluded by default**. Pass `--include-superseded` only if the
user asked for rate history — a catalog that lists plans nobody can buy, mixed in with
plans they can, is how someone shops for a plan that no longer exists.

### Step 3 — Fan out, one subagent per carrier

**Threshold.** Two carriers or fewer: read the plan pages inline and write the notes
yourself. More than two: fan out, **one subagent per company folder** —
`companies/blue-shield-ca/`, `companies/kaiser-permanente/`,
`companies/aetna-ca/`, and so on. One agent per carrier, however many plans that
carrier has. Never one agent per plan page, and never a fixed number of agents dividing
the list.

**The brief.** Send each subagent this, substituting the carrier:

> You are the master of one health insurance carrier: `companies/<slug>/`. Read
> `companies/<slug>/company.md` and every file in `companies/<slug>/plans/`. Read
> `SCHEMA.md` at the wiki root first so you know what each section is for — § 3.1 in
> particular. **Read nothing outside your own company folder.** Do not write, edit or
> create any file.
>
> Return exactly this JSON and nothing else:
>
> ```json
> {
>   "company": "<slug>",
>   "positioning": "<one or two sentences: what distinguishes this carrier's line-up as a whole — network model, price position, who it is built for. Grounded in a specific number or a specific network name from the pages you read.>",
>   "networks": "<the network names and what each one costs you in access, in one sentence>",
>   "watch_outs": "<the one thing a shopper would most regret not knowing about this carrier. Empty string if the pages do not support one.>",
>   "plans": [
>     {
>       "plan_id": "<verbatim from the page frontmatter>",
>       "one_liner": "<under 100 characters. Why someone would pick THIS plan over its siblings — never what it is. 'Lowest deductible in the individual PPO line, at the second-highest premium' beats 'A Gold-tier PPO'.>",
>       "suits": "<who this plan suits, anchored to a specific number on its page>",
>       "look_elsewhere": "<who should not buy it, anchored to a specific number on its page>",
>       "notable_limits": "<visit caps, prior-authorization requirements, waiting periods, exclusions that would change a decision. This comes from '## Exclusions & Limits', which is the section most often skipped during ingest and most often decisive.>",
>       "unstated": ["<frontmatter fields reading TBD that a shopper would care about>"]
>     }
>   ]
> }
> ```
>
> Hard rules:
>
> - **Every claim traces to a number or a sentence on the page you read.** If you
>   cannot point at it, leave the field an empty string. An empty field renders
>   honestly; an invented one does not.
> - **Never state a cost figure that is not on the page.** The catalog gets its numbers
>   from the frontmatter directly and will contradict you visibly if you guess.
> - **A page whose `## Fit Notes` is `_TBD._` gets empty `suits` and
>   `look_elsewhere`.** Do not write the fit notes the page is missing — say nothing,
>   and the report will name the gap.
> - **Never compare to another carrier.** You cannot see their pages, and a
>   cross-carrier claim you cannot check is exactly the contamination the folder
>   boundary exists to prevent.
> - **`plan_id` verbatim.** It is the join key. A retyped or reconstructed id silently
>   drops your entire narrative for that plan.

**The barrier.** Collect every subagent result before merging any of them. Do not begin
Step 4 until every fan-out task has returned. A partial merge produces a catalog where
one carrier is mysteriously terse, which reads as a thin carrier rather than as a
failed subagent.

**A subagent that returns nothing usable** is reported as such and its carrier is
catalogued from numbers alone. Say so in the report. The catalog is complete without
the narrative — just drier — which is why this fan-out is not load-bearing.

### Step 4 — Merge the notes

Write `output/_catalog-notes.json`:

```json
{
  "companies": [ { "company": "...", "positioning": "...", "networks": "...", "watch_outs": "..." } ],
  "plans":     [ { "plan_id": "...", "one_liner": "...", "suits": "...", "look_elsewhere": "...", "notable_limits": "..." } ]
}
```

`build-catalog.py` reads exactly those keys and ignores anything else, so the subagents'
`unstated` lists do not go in the file. **They go in the Step 7 report instead** — a
carrier subagent naming the fields a shopper would care about and its pages do not record
is the most actionable thing the fan-out produces, and dropping it on the floor because
the HTML has no column for it would waste the one pass that collected it.

Two checks before you write it, both cheap and both catching a real failure mode:

1. **Every `plan_id` in the notes exists in `output/_wiki-data.json`.** One that does
   not was reconstructed rather than copied; drop it and name it in the report.
2. **No note states a cost figure that contradicts that plan's frontmatter.** Drop the
   claim, keep the number, and report the discrepancy — it means the subagent misread
   its own page, which is worth knowing about that page.

### Step 5 — Build

```bash
C="skills/hiw-list-plan"; [ -d "$C/scripts" ] || C="$CLAUDE_PLUGIN_ROOT/skills/hiw-list-plan"
python3 "$C/scripts/build-catalog.py" \
  --data output/_wiki-data.json \
  --notes output/_catalog-notes.json \
  --out output/plan-catalog.html
```

The notes file is optional. Without it the catalog builds from numbers alone and says
so; the script prints a note rather than failing.

What the generated page does, so you can describe it accurately rather than guess:
one section per carrier (or one flat table on request), sortable on every column,
filterable by carrier, tier, network and market, full-text search, a per-plan detail
drawer with every frontmatter field grouped, and a toggle to hide plans with unknown
core costs. `/` focuses the search box.

**The three states are visually distinct and never collapsed:** a real `0` renders as
`$0`, a `TBD` renders as a TBD badge, an absent key renders as an em dash. In every
ascending sort, unknowns go **last** — a "cheapest first" list that floats an unknown
premium to the top is worse than no sort at all.

### Step 6 — Open it, and prove that you did

```bash
OUT="$(cd output && pwd)/plan-catalog.html"
[ -f "$OUT" ] && echo "$OUT" || echo "MISSING: $OUT"
```

Resolve to an absolute path, verify it exists, then open it and print the path
alongside. A silent no-open is the exact bug to avoid.

```bash
case "$(uname -s 2>/dev/null)" in
  Darwin) open "$OUT" ;;
  Linux)  xdg-open "$OUT" >/dev/null 2>&1 & ;;
  *)      start "" "$OUT" ;;
esac
```

**In Cowork, always also present the file.** The OS opener cannot reach the user's
desktop from a sandboxed session, so that is the reliable path there.

### Step 7 — Log and report

Append one line to `log.md`:

```markdown
## [YYYY-MM-DD] hiw-list-plan | catalog rebuilt — <N> carriers, <M> plans, <K> with an unknown core cost
```

Then report, briefly:

1. **The path to the catalog**, and that it is a snapshot — regenerate after each
   ingest.
2. **The headline shape**: carriers, plans, and the cheapest and most expensive
   premiums with the plans that carry them. Numbers, from the data, not impressions.
3. **What is unknown**: plans with a `TBD` core cost, named, plus the `unstated` lists
   the carrier subagents returned — the fields a shopper would care about and the pages
   do not record. This is the most actionable thing in the report and it is what
   `/hiw-refresh` works from. The HTML has no column for it, which is exactly why it has
   to be said here rather than left in the fan-out returns.
4. **What is thin**: carriers whose subagent found no fit notes to work from, and pages
   that are still empty scaffolds.
5. **What is broken**: the `error`-severity finding count, and a pointer to `/hiw-lint`.
   Do not fix any of it here.
6. **Next steps**: `/hiw-compare` for a side-by-side of specific plans, `/hiw-query`
   for a recommendation from a needs assessment.

Close with the standing caveat, once. It is already on the HTML page; say it in chat
too, because the chat is where the user forms their impression.

---

## Files in this skill

| File | What it does |
|---|---|
| `scripts/build-catalog.py` | joins the linter's json to the notes json on `plan_id` and emits one self-contained HTML file. Stdlib only |
| `scripts/catalog-template.html` | the HTML/CSS/JS shell. Two `{{...}}` placeholders, `{{TITLE}}` and `{{CATALOG_DATA}}`; the data island is substituted last so page content carrying a literal `{{TITLE}}` cannot be substituted into |

Plus `lint-wiki.py`, which lives in `skills/hiw-lint/scripts/` because it is the
family's single walker. Run all of them by path; never inline or rewrite one.

---

## Anti-patterns

- Do not glob `companies/` to build your inventory. The linter's json is the inventory, and two inventories eventually disagree.
- Do not fan out by plan page. One subagent per company folder, however many plans it holds.
- Do not fan out below the threshold. Two carriers read inline is faster than two subagents.
- Do not begin the merge before every subagent has returned. A partial merge produces a catalog where one carrier is mysteriously terse, and that reads as a thin carrier rather than a failed subagent.
- Do not let a subagent read another carrier's folder. The folder boundary is what makes the fan-out safe; a cross-carrier claim nobody can check is exactly what it exists to prevent.
- Do not let a subagent write anything. Fan out to read, funnel to write.
- Do not accept a note whose cost figure contradicts the frontmatter. Keep the number, drop the claim, report the page.
- Do not accept a `plan_id` that is not in the linter's json. It was reconstructed, not copied, and it silently drops that plan's whole narrative.
- Do not write fit notes for a page that has none. An empty field renders honestly; a manufactured recommendation does not.
- Do not include superseded plans by default. Mixed into a live catalog, they are how someone shops for a plan that no longer exists.
- Do not render a `TBD` as `0`, as blank, or as "n/a". Three states, three renderings, all the way to the DOM.
- Do not sort unknowns to the top of an ascending list. A "cheapest first" list led by an unknown premium is worse than no sort.
- Do not fix a lint finding here. Surface the count and point at `/hiw-lint`.
- Do not build an empty catalog to demonstrate that the pipeline works. Say the wiki is empty and point at `/hiw-ingest`.
- Do not assume a relative path opens. Resolve to absolute, verify, open, print the path.
- Do not describe the catalog's features from memory. They are listed in Step 5.
- Do not paste the catalog's contents into chat as the deliverable. Link the file, then say the three things a person actually wants: the shape, what is unknown, and what to do next. (A short chooser list of a dozen plan names, when the user is about to pick two to compare, is not this — that is `/hiw-compare` Step 2's job and it is fine.)
- Do not drop the subagents' `unstated` lists. They do not belong in the notes file, and they are the most actionable thing the fan-out produces — they go in the report.
