---
name: hiw-refresh
description: >-
  Re-fetch the sources already recorded in the health-insurance-wiki, diff what they say
  now against what is stored, and go after the fields still reading TBD. Reports rate
  changes plan by plan, resolves what the policy settles and logs it, and leaves genuine
  conflicts marked. Use when the user says "are these rates still current", "re-check the
  sources", "what changed since we ingested", "fill in the missing costs", "open
  enrollment is coming", or runs /hiw-refresh.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion WebFetch mcp__claude-in-chrome__navigate mcp__claude-in-chrome__get_page_text
metadata:
  argument-hint: "(no arguments for the whole wiki; or a carrier slug to refresh one)"
---

# /hiw-refresh — Re-fetch, Diff, Fill the Gaps

Two jobs that share a mechanism:

**Currency.** Premiums re-rate annually and mid-year corrections happen. A wiki that
was accurate in March is a wiki nobody should quote from in November without checking.
This skill re-reads the sources it already has receipts for and says what moved.

**Completeness.** Every `TBD` in the wiki is a known unknown that someone deliberately
did not guess at. This skill is how they stop being unknown — it takes the
`TBD-CORE` list `/hiw-lint` produces and goes looking for those specific fields.

It is `/hiw-ingest` pointed at what the wiki already knows, so it inherits the same
doctrine: **it resolves and logs; it does not defer.** Where a re-fetch settles a
question, it settles it and records the decision. What it cannot settle, it marks.

Ladders, applied inline in every command block:

```bash
L="skills/hiw-lint";   [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
I="skills/hiw-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/hiw-ingest"
```

---

## STOP conditions — check these first

1. **No source records → say so and stop.** *"No plan page cites a source I can go back
   to, so there is nothing to re-fetch. `/hiw-ingest` writes those receipts."* A wiki
   whose facts have no recorded origin cannot be refreshed, only re-ingested — and
   saying that plainly is more useful than refreshing nothing.

2. **`TBD` over a guess, still and always.** A field the re-fetched source still does
   not state stays `TBD`. That the field has been unknown for six months does not make a
   market-typical value acceptable. **A `TBD` that survives a refresh is a successful
   outcome of this skill**, and it is recorded as "re-checked, still unstated" so nobody
   re-checks it next week for nothing. (Step 5)

3. **Never overwrite without logging.** Every in-place change records the old value, the
   new value, both sources, and the rule that decided it. This is the skill most likely
   to overwrite a number a person previously read and trusted; the log is the only place
   they can catch it. (Step 6)

4. **A dead source is a finding, not a licence.** A URL that 404s, a document that has
   been withdrawn, a page whose plan is gone — none of that permits inferring the
   current value. Mark the source `status: superseded`, note it on the plan page, report
   it. (Step 3)

5. **Never invent a URL.** If a source record has no `source_url` and no file in `raw/`,
   it cannot be re-fetched. Do not search for a plausible replacement page and treat it
   as the same source — a different document with the same subject is a *new* source
   with its own authority, its own date, and its own receipt. (Step 2)

6. **A new plan year is a new page, never an edit.** This is the skill that will most
   often meet one. `SCHEMA.md` § 7.1: write the new page, set the old one to
   `status: superseded`, name the successor. Editing last year's page in place destroys
   the rate history that is the most useful thing this wiki accumulates. (Step 6)

---

## RULES — read before acting

- **Diff before you write, always, and for the whole plan at once.** You cannot decide
  what to overwrite until you know what the page says, and you cannot decide that one
  field at a time while a rate table scrolls past.
- **Percentages are the member's share.** Re-read which one the source means every
  time. A carrier that redesigns its brochure between plan years routinely flips from
  "you pay 20%" to "we pay 80%", and an inverted coinsurance that arrives via a refresh
  is harder to spot than one that arrived at ingest, because the page already looked
  right.
- **Resolution policy, unchanged** (`SCHEMA.md` § 7.2): higher `authority` wins; at
  equal authority the newer `retrieved` date wins, except that a source for an earlier
  plan year never overwrites a later one; at equal authority and the same date keep the
  existing value, record the new one under `### Unresolved`, and log it.
- **Elaboration is not conflict.** A source that now states a field the page had as
  `TBD` is a refinement — write it, and it is the best thing that happens in this skill.
- **Ask through AskUserQuestion when you have it, in plain text when you do not.**
- **Do not restate the contract; apply it.**

---

## Procedure

### Step 1 — Establish what there is to refresh

```bash
L="skills/hiw-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$L/scripts/lint-wiki.py" --wiki . --out output/_wiki-data.json
```

From `output/_wiki-data.json`, build three lists. They are the whole work plan:

1. **Re-fetchable sources** — every entry in `sources[]` with a `source_url`, or a
   `source_ref` matching a file in `raw/<company>/`. Note each one's `retrieved` date
   and `authority`.
2. **Unknown core costs** — every `TBD-CORE` finding, grouped by carrier and plan. This
   is the list that makes the run worth doing.
3. **Aging pages** — every `AGE-STALE` and `AGE-PLAN-YEAR-PAST` finding. An off-year
   plan still marked `active` is the highest-value item in the whole list, because it
   means a plan year turned over and nobody noticed.

**Say what you found, in one short paragraph, before fetching anything.** "3 carriers,
19 plans, 4 sources with URLs, 11 core cost fields unknown, and 2 plans still marked
active on 2025 rates." That paragraph is what lets someone redirect the run before it
spends real work.

### Step 2 — Decide the scope

If the argument named a carrier, refresh only that carrier. Otherwise run **one
AskUserQuestion call** — header `"Refresh"`, question `"<N> re-fetchable sources, <M>
unknown cost fields, <K> plan(s) on a past plan year. What should I go after?"`, options
(exactly these four):
`["Everything — re-fetch all sources and chase the gaps", "Just the unknown costs — fill in the TBDs", "Just the past-year plans — check whether rates turned over", "Just the sources older than six months"]`.
(multiSelect: false) The free-text field takes a single carrier name where the user wants
to narrow it to one; do not add an option that says so.

**Below three sources and three unknown fields, ask nothing and do all of it.** A
question whose every answer is "do the work" is a question not worth asking.

### Step 3 — Re-fetch

**For a URL source:** WebFetch first. If what comes back is a page shell, a spinner, an
"enable JavaScript" notice, or navigation with no plan data, the page is client-rendered
— switch to the Chrome tools (`navigate`, then `get_page_text`). Do not retry, and do not
work from the fragment. Where neither is available, report the source as un-refetchable
this run and change nothing on its plan pages — an un-refetched source is a gap in the
report, not a licence to leave the stored value looking freshly verified.

Four outcomes, and each has one correct handling:

| Outcome | What to do |
|---|---|
| **Fetched, plan still listed** | proceed to Step 4 |
| **Fetched, plan is gone from the page** | the plan may be withdrawn. Do **not** set `status: superseded` on that basis alone — a redesigned site is not a withdrawn plan. Report it as needing confirmation, and note it on the page under `## Additional capture` as `### Open questions` |
| **404, 403, or a redirect to a landing page** | the source is dead. Set the source record's `status: superseded` with a line naming the date and the response. Change nothing on the plan pages. Report it |
| **Fetched, but behind a quote form with different parameters than last time** | the premium is not comparable. Record the new parameters, and treat the figure as a **new source**, not an update to the old one |

**For a file source in `raw/`:** the file has not changed — that is what `raw/` is for.
Re-reading it is only worth doing when the previous ingest left `TBD`s that the document
may actually answer, which happens more often than it should: a first pass reads the
rate table and misses the pharmacy appendix. Re-extract and re-read the sections the
`TBD`s point at:

```bash
I="skills/hiw-ingest"; [ -d "$I/scripts" ] || I="$CLAUDE_PLUGIN_ROOT/skills/hiw-ingest"
python3 "$I/scripts/extract-source.py" "raw/<company>/<file>" --out "output/_refetch-<slug>.txt"
```

Exit 2 means read it natively. Same rule as ingest: do not approximate.

**Mirror every new fetch into `raw/<company>/` with today's date in the filename** —
`<slug>-2026-08-25.html`. Never overwrite an earlier capture. Two dated captures of one
page are how a rate change becomes provable rather than asserted.

### Step 4 — Diff, per plan, before writing anything

For each plan the re-fetched source covers, compare **every field**, not just the ones
you expected to move. Classify each into exactly one of five buckets:

| Bucket | Meaning | Action |
|---|---|---|
| **Unchanged** | source says what the page says | nothing. Do not touch `last_updated` for an unchanged page — a refreshed timestamp on an unchanged page is a lie about when the fact was verified |
| **Filled** | page had `TBD`, source now states it | write it. This is the best outcome available and it goes at the top of the report |
| **Still unknown** | page had `TBD`, source still silent | leave `TBD`. Record "re-checked <date>, still unstated" under `## Additional capture` as `### Refresh notes`, so nobody re-checks it next week for nothing |
| **Changed** | both state it, and they differ | run the resolution policy. Log old, new, both sources, deciding rule |
| **New plan year** | the source describes a different `plan_year` | **a new page**, not an edit. See Step 6 |

**Two things that look like changes and are not:**

- A **different family size or age band** in a quote form. Not a rate change. Record the
  parameters and move on.
- A **post-subsidy figure** where the page holds an unsubsidized one. Not a rate change.
  `premium_basis` differs, so these are two different facts, and neither overwrites the
  other.

**Verify the direction of every change.** A premium that fell 40% and a deductible that
doubled are both possible and both more often a mis-read — a monthly figure read off an
annual column, or a family rate read into an individual field. Re-read the source before
writing it. Where the source really does say the surprising thing, write it and note why
under `### Refresh notes`. Strangeness in the source is signal.

### Step 5 — Chase the remaining gaps

For the `TBD-CORE` fields no re-fetch answered, one targeted attempt each — and only
where you have somewhere real to go:

1. **The carrier's own site**, if the plan page or the company page records a `website`.
   A carrier's own SBC or plan brochure is `authority: official`.
2. **The government exchange for the plan's state**, for an individual-market plan.
   Also `official`.
3. **Nothing else.** Do not search for a copay on an aggregator and record it as though
   it were the carrier's own figure. If you do use a secondary source, it is
   `authority: secondary`, it gets its own source record, and it drags that plan's
   `confidence` to `medium` at best.

**Where nothing turns it up, stop looking and say so.** A `TBD` that has survived two
honest attempts is more informative than a number from a source nobody would cite —
because a comparison shows the `TBD` as unknown, while it shows the bad number as fact.

### Step 6 — Write

Same mechanics as `/hiw-ingest` Step 7, and the same three rules:

- **Replace a `_TBD._` section stub; do not write beneath it.**
- **New substance appends**, tagged `[<date> via hiw-refresh]`.
- **A superseded value is edited in place**, tagged `[<date> updated via hiw-refresh]`,
  and it appears in the log.

Update `last_updated` and set `updated_by: hiw-refresh` **only on pages that actually
changed**. Append any new `source_ref` to `sources`.

**Re-evaluate `confidence`** on every page you touched. A page that was `low` because
half its cost fields were `TBD` and now has them all from an official SBC is `high`. A
page that gained a value from a broker site is `medium`. This is the one field a refresh
should routinely improve, and leaving it stale understates the wiki.

**A new plan year** (`SCHEMA.md` § 7.1):

1. Decide the new path: `<plan-slug>-<year>.md`, with `plan_year` set accordingly.
2. Write it with `new-page.py plan` (it will refuse if the path already exists, which is
   the check you want), then fill the sections.
3. Set the prior page to `status: superseded` and add a line to its
   `## Additional capture` naming the successor by path.
4. Update the company page's roster and `plan_count`.
5. Log every action.

**Then re-run the linter and regenerate the index**, because the tree moved:

```bash
L="skills/hiw-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$L/scripts/lint-wiki.py" --wiki . --out output/_wiki-data.json
python3 "$L/scripts/index-wiki.py" --data output/_wiki-data.json --wiki .
```

Append one entry to `log.md`. Omit any subsection with no entries:

```markdown
## [YYYY-MM-DD] hiw-refresh | <Carrier or "all"> — <S> sources re-fetched, <F> TBDs filled, <C> values changed, <N> new-year pages, <D> dead sources, <X> unresolved

### Values updated in place
- `companies/<slug>/plans/<plan>.md` · `premium_monthly_individual` · 598.10 [source: blue-2026-sbc.pdf, retrieved 2026-03-02] -> 612.40 [source: https://blueshieldca.com/plans, accessed 2026-08-25] — newer retrieval, equal authority

### TBDs filled
- `companies/<slug>/plans/<plan>.md` · `copay_imaging` · TBD -> 75 [source: blue-2026-sbc.pdf]

### Still unknown after re-check
- `companies/<slug>/plans/<plan>.md` · `rx_tier4_specialty` — re-checked 2026-08-25, source still silent

### Dead sources
- `companies/<slug>/sources/<src>.md` — 404 on 2026-08-25, marked superseded

### Unresolved (equal authority, same date)
- `companies/<slug>/plans/<plan>.md` · `deductible_individual` · 750 [source: A] alongside 1000 [source: B]
```

### Step 7 — Report

Lead with the rate changes, because that is what someone ran this for.

1. **What moved**, as a table: plan, field, old, new, and the change as both an absolute
   figure and a percentage. A 2.3% premium increase across a carrier's whole line is a
   different story from one plan jumping 19%, and the percentage is what makes that
   visible at a glance.
2. **What got filled** — the `TBD`s that are now known, by plan. The quiet win.
3. **What is still unknown after an honest attempt**, and where you looked. This is what
   stops the next run repeating the same failed searches.
4. **New plan years found**, and the pages written and superseded.
5. **Dead sources**, and what now has no live origin.
6. **Every in-place overwrite**, explicitly, with the deciding rule. The user did not
   approve these before they landed.
7. **Confidence changes**, both directions.
8. **What a comparison would now say differently.** One or two sentences. *"Blue
   Shield's Gold plan is now $612.40 rather than $598.10, which puts it above Kaiser's
   Gold for the first time — any comparison run before today has the ranking the other
   way round."* That sentence is the reason the refresh was worth running, and nothing
   else in the report says it.

Then the caveat, once.

---

## Fan-out

**Two carriers or fewer: no fan-out** — the same threshold as every other skill in this
family. Above that, **one subagent per company folder** for the *diff*, never for the
write:

> You are the master of `companies/<slug>/`. Read `SCHEMA.md`, then read every plan page
> in your folder. Here is freshly fetched source text for this carrier: `<text or path>`.
> **Read nothing outside your own company folder. Write nothing.**
>
> For every plan page, compare every frontmatter field against what this source now
> says, and return JSON:
>
> ```json
> {"company":"<slug>","diffs":[{
>   "plan_id":"<verbatim>",
>   "unchanged": <count>,
>   "filled":   [{"field":"...","was":"TBD","now":"...","source_says":"<the exact phrase>"}],
>   "changed":  [{"field":"...","was":"...","now":"...","source_says":"<the exact phrase>"}],
>   "still_unknown": ["<field>"],
>   "new_plan_year": "<year or empty string>",
>   "suspect": [{"field":"...","why":"<why this looks like a mis-read rather than a change>"}]
> }]}
> ```
>
> Rules: **quote the source phrase for every filled and changed field** — the parent
> decides whether to write it and needs to see what it is deciding from; never fill a
> field the source does not state, and never carry a value across from a sibling plan;
> flag anything whose direction or magnitude looks like a mis-read into `suspect` rather
> than reporting it as a change; `plan_id` verbatim.

**Collect every result before writing anything.** The parent does all the writing, all
the conflict resolution, all the confidence re-evaluation and all the logging — one
change list, one log entry, auditable. **Fan out to read; funnel to write.**

---

## Files in this skill

No scripts of its own. It borrows four:

| Script | From | Used for |
|---|---|---|
| `lint-wiki.py` | `skills/hiw-lint/scripts/` | Step 1's work plan — sources, unknown costs, aging pages |
| `index-wiki.py` | `skills/hiw-lint/scripts/` | Step 6, after the tree moved |
| `extract-source.py` | `skills/hiw-ingest/scripts/` | Step 3, re-reading a file source |
| `new-page.py` | `skills/hiw-ingest/scripts/` | Step 5's new source record for a secondary source, and Step 6's new plan-year page |

Run all four by path; never inline or rewrite one. `new-page.py` refuses to overwrite and
exits 3 — which is exactly right here, because a refresh must never regenerate a page
from a partial fact set.

---

## Anti-patterns

- Do not fill a `TBD` with a market-typical value because it has been unknown for months. A `TBD` that survives a refresh is a successful outcome, recorded as re-checked.
- Do not treat a dead URL as licence to infer the current value. Mark the source superseded and report it.
- Do not invent a replacement URL for a source with no recorded origin. A different document with the same subject is a new source with its own authority, date and receipt.
- Do not set a plan to `superseded` because it vanished from a redesigned site. A site redesign is not a withdrawn plan. Report it as needing confirmation.
- Do not edit last year's page when a new plan year arrives. New page, old one superseded, successor named. Editing in place destroys the rate history.
- Do not overwrite a value without logging the old, the new, both sources and the deciding rule. This is the skill most likely to overwrite a number someone already read and trusted.
- Do not touch `last_updated` on a page that did not change. A refreshed timestamp on an unchanged page is a lie about when the fact was verified.
- Do not compare a post-subsidy figure against an unsubsidized one and call it a rate change. Different `premium_basis` means two different facts.
- Do not compare a quote-form figure against a differently-parameterised one. Record the parameters; treat it as a new source.
- Do not write a change whose direction or magnitude is surprising without re-reading the source. A premium down 40% is usually a monthly figure read off an annual column.
- Do not record the plan's coinsurance share as the member's. A carrier redesigning its brochure routinely flips the phrasing, and an inverted coinsurance arriving by refresh is harder to spot than one arriving at ingest, because the page already looked right.
- Do not overwrite an earlier `raw/` capture. Two dated captures are how a rate change becomes provable rather than asserted.
- Do not record an aggregator's copay as though it were the carrier's own figure. It is `authority: secondary`, it gets its own receipt, and it caps that page's confidence.
- Do not keep searching after two honest attempts. A `TBD` is more informative than a number from a source nobody would cite, because a comparison shows the TBD as unknown and the bad number as fact.
- Do not leave `confidence` stale on a page you improved. It is the one field a refresh should routinely raise.
- Do not fan out to write. One change list, one log entry, auditable.
- Do not accept a subagent's filled field without its quoted source phrase. The parent decides, and it needs to see what it is deciding from.
- Do not begin writing before every subagent has returned.
- Do not approximate a PDF you could not extract. Read it natively.
- Do not work from a WebFetch result that came back as a page shell. Switch to the Chrome tools.
- Do not bury the rate changes. That is what someone ran this for. Lead with them, with percentages.
- Do not omit the sentence about what a comparison would now say differently. Nothing else in the report says it, and it is the reason the refresh was worth running.
