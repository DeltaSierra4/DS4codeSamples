---
name: hiw-ingest
description: >-
  Read health insurance plan details out of files (PDF, DOCX, TXT, XLSX, PPTX, HTML) or
  a carrier URL and write them into the health-insurance-wiki as structured plan pages,
  one company folder per carrier. Extracts every cost, copay, premium, network and
  exclusion it can source; writes TBD rather than guessing at the rest; resolves
  conflicts against what is already stored and logs every in-place change; mirrors the
  original into raw/. Use when the user says "ingest this plan document", "add this
  carrier", "here's a link to their plans", "read this SBC", or runs /hiw-ingest.
allowed-tools: Read Write Edit Bash Glob Grep AskUserQuestion WebFetch Task mcp__claude-in-chrome__navigate mcp__claude-in-chrome__get_page_text
metadata:
  argument-hint: "<one or more file paths, or a URL to a page listing plan details; omit for interactive>"
---

# /hiw-ingest — Sources into Structured Plan Pages

The engine of this wiki. Everything else reads what this skill writes.

One run handles one carrier. Two carriers is two runs — the company folder is the unit
of everything here, and a run that writes into two of them cannot report cleanly on
either.

Self-contained skill. Its two scripts are resolved with the two-rung ladder, which
every command block below applies inline:

```bash
S="skills/hiw-ingest"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-ingest"
```

---

## STOP conditions — check these first

Short list, at the top, because this is a long file and the rules that matter get read
last. Each of these ends the run or bounds it, and each is expanded below.

1. **No wiki → HALT and create nothing.** If there is no `SCHEMA.md` and no
   `companies/` at the target root, say: *"There is no wiki here, so there is no
   structure to file this source against. Run `/hiw-setup` first — it creates the
   contract and the directories this skill fills."* Do not create an empty
   `companies/`, do not invent a layout, and do not scaffold from the source document.
   (Step 1)

2. **`TBD` over a guess, always, without exception.** A cost the source did not state
   is written as the literal `TBD`. Never infer a number from the metal tier, from a
   sibling plan, from the carrier's other plans, or from what such a plan typically
   costs. A fabricated `deductible_individual` is worse than an absent one, because
   `/hiw-compare` will rank on it, `/hiw-query` will recommend on it, and nothing
   downstream can tell it apart from a number read off an SBC. **If you find yourself
   reasoning toward a plausible value, that is the signal to write `TBD`.** (Step 6)

3. **Never overwrite a plan page you have not read.** An existing page is updated
   under the resolution policy in `SCHEMA.md` § 7.2. `new-page.py` refuses to
   overwrite and exits 3; that refusal is correct — read the page and edit it.
   (Step 5, Step 7)

4. **All decisions before any write.** Steps 5 and 6 exist so that Step 7 is
   mechanical. You cannot decide what to overwrite until you know what the page
   already says, and you cannot decide that one field at a time while the source
   scrolls past. (Step 5)

5. **A PDF that cannot be extracted is read natively, never approximated.**
   `extract-source.py` exits 2 rather than return partial text. Read the PDF with the
   Read tool. A plausible mis-read of a benefits grid is worse than no read, because
   either way the number lands in the wiki. (Step 3)

6. **Never delete, never rename.** A withdrawn plan gets `status: superseded`. A new
   plan year is a new page. (Step 7)

---

## RULES — read before acting

This is a **rigid, prescribed procedure**, not a set of suggestions.

- **This skill is the wiki's autonomous writer.** Where a source settles a question,
  it settles it — it does not defer to a human, and it does not leave two values on the
  page hoping `/hiw-lint` will sort them out. The division of labour with `/hiw-lint`
  is deliberate and it is the opposite of what you might assume: **ingest resolves and
  logs; lint flags and never picks a winner.** Every in-place overwrite is logged with
  the old value, the new value, both sources and the rule that decided it, because the
  user did not approve that edit before it landed and the log is the only place they
  can catch it.
- **Percentages are the share the MEMBER pays.** `coinsurance_in_network: 20` means
  the member pays 20% and the plan pays 80%. Carrier marketing states the plan's share
  ("this plan pays 80%") at least as often as the member's. Read which one the source
  means, every time, and invert it if you must. An inverted coinsurance is the single
  most consequential silent error available in this domain.
- **Money is a bare number** in the wiki's currency. No symbol, no separators, no
  quotes. A quoted number is invisible to the comparison math.
- **Ask through AskUserQuestion when you have it, in plain text when you do not, and
  never by taking a default.** Every question in this skill is blocking and none has a
  safe default.
- **Every non-obvious claim carries `[source: ...]`.** A URL-sourced claim carries the
  access date too, because a web page changes and an undated web claim cannot be
  re-verified.
- **Do not restate the contract; apply it.** `SCHEMA.md` at the wiki root defines the
  frontmatter keys (§ 2), the nine sections (§ 3), the tags (§ 6) and the resolution
  policy (§ 7). Read it before writing your first page of the run. This file cites its
  sections and deliberately does not copy them — a second copy would drift out of
  agreement with the first.
- **Capture everything of substance.** Where a fact will not fit one of the eight fixed
  sections, it goes under `## Additional capture` with a `###` heading of your
  choosing and a `[source:]` marker. Never drop detail to fit a section. Without that
  escape hatch the only alternative is silent discard, and that loss is unrecoverable —
  the point of this wiki is that it is the thing you did not have to re-read the PDF
  for.

---

## Procedure

### Step 1 — Readiness gate, cheap-first

This skill runs many times per wiki, so the common case must cost a directory check,
not a parse.

1. **`SCHEMA.md` and `companies/` both present → go to Step 2.** Do not parse
   `SCHEMA.md` here.
2. **`companies/` present, `SCHEMA.md` absent →** proceed, and note in the closing
   report that the contract file is missing and `/hiw-setup` should be re-run to
   restore it. A missing contract is a degraded run, not a blocked one.
3. **Neither present → HALT** with the STOP-1 message. Create nothing.

Read `_config/wiki-config.md` if it exists: `currency`, `plan_year`, `geography`. If
it does not exist, note that you are using `USD` and the current year, and say so.

### Step 2 — Determine the source, and what kind it is

Three modes. If the argument names a path or a URL, take it; otherwise ask.

Run **one AskUserQuestion call** — header `"Source"`, question `"What should I ingest?
Paste a file path or a URL in the field."`, options (exactly these three):
`["I have files — plan documents, SBCs, brochures", "I have a URL to a carrier's plan page", "I have both for the same carrier"]`.
(multiSelect: false)

Then, whatever the answer, name back what you resolved — the absolute file paths, or
the URL — before touching any of it. A wrong path caught here costs a sentence; caught
in Step 7 it costs a company folder.

### Step 3 — Get the text

#### 3a — Files

```bash
S="skills/hiw-ingest"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-ingest"
python3 "$S/scripts/extract-source.py" "<path>" --out "output/_extract-<slug>.txt"
```

Handles `.txt .md .csv .tsv .json .html .docx .xlsx .pptx` with the standard library
only, and tries `pdftotext -layout` for a PDF.

**Exit 2 is a normal outcome, not a failure.** It means the format needs the agent's
own reader: `.pdf` where `pdftotext` is absent, `.doc`, `.xls`, `.ppt`, an image, an
email. Read the file with the **Read** tool — it reads PDFs and images natively — and
work from what you see. Do not retry the script, and do not approximate.

**Read the whole document.** A Summary of Benefits and Coverage puts the deductible on
page 1 and the exclusions and the visit limits on page 5, and the exclusions are the
section most often skipped during ingest and most often decisive during a comparison.

**Read the tables as tables.** A benefits grid whose columns have collapsed will pair
a copay with the wrong service, and the result reads perfectly. If the extracted text
looks column-scrambled, go back and read the file natively instead.

#### 3b — URLs

Use **WebFetch** first. If what comes back is a page shell, a loading spinner, an
"enable JavaScript" notice, or navigation boilerplate with no plan data, the page is
client-rendered — do not retry and do not work from the fragment. Switch to the Chrome
tools (`navigate`, then `get_page_text`), which execute JavaScript and see the real
content.

**Where neither is available**, say so plainly and ask the user to open the page and
paste the plan details, or to save it and hand you the file. That is a degraded run, not
a blocked one — but it is the only remaining path, because the alternative is writing a
carrier's plan line-up from a navigation menu.

Carrier plan pages are usually behind a quote form: a ZIP code, an age, sometimes a
household size. Two consequences, and both belong in the report:

- **The premium you get back is for the parameters that form was carrying.** Record
  them. If the page shows a post-subsidy rate, `premium_basis: post-subsidy` — do not
  reverse-engineer the unsubsidized figure.
- **Note the access date on every claim**, in the tag:
  `[source: https://example.com/plans, accessed 2026-08-25]`.

Mirror what you fetched into `raw/<company-slug>/` as `<slug>-<YYYY-MM-DD>.html` or
`.md`. A URL that changes next week is why `raw/` exists.

#### 3c — Mirror the originals

```bash
mkdir -p "raw/<company-slug>"
cp "<original path>" "raw/<company-slug>/"
```

Copy, never move. The user's file stays where the user put it.

### Step 4 — Identify the carrier, and check for its folder

1. **The carrier name comes from the document**, not from the filename. A file called
   `plans_final_v3.pdf` is a Blue Shield SBC if the SBC says so.

2. **Slug it** per `SCHEMA.md` § 1.1: lowercase, `&` to `and`, everything else
   non-alphanumeric to a hyphen, collapsed.

3. **Look for the folder**, and note which case you are in:
   ```bash
   ls -d "companies/<company-slug>" 2>/dev/null && echo EXISTS || echo NEW
   ```
   - **NEW** — you will create `company.md` in Step 7. This is the normal first ingest
     for a carrier.
   - **EXISTS** — read `companies/<company-slug>/company.md` and list
     `companies/<company-slug>/plans/`. You are adding to a carrier you already know
     something about, and Step 5 needs to know what.

4. **Check for a near-miss before creating anything.** `ls companies/` and compare.
   `blue-shield-ca` and `blue-shield-california` as two folders is the worst outcome
   this skill can produce: it splits one carrier's plans across two folders, and every
   subagent fan-out, every catalog section and every comparison then sees half a
   carrier. If a close match exists, run **one AskUserQuestion call** — header
   `"Carrier"`, question `"companies/<near-match> already exists. Is this the same carrier?"`, options (exactly these two):
   `["Same carrier — use the existing folder", "Different carrier — create a new folder"]`.
   (multiSelect: false)

5. **De-duplicate the source.** Check `companies/<slug>/sources/` for a record whose
   `source_ref` matches this document. If one exists, run **one AskUserQuestion call**
   — header `"Re-ingest"`, question `"<source> has been ingested before. Re-read it?"`,
   options (exactly these two):
   `["Re-read it — the document may have been revised", "Skip it — nothing has changed"]`.
   (multiSelect: false) On a freshly created company folder the directory is absent;
   that is a miss, not an error — skip the check and move on.

### Step 5 — Extract, then compare against what is already stored

**This is where the run's decisions get made. Nothing is written yet.**

1. **Enumerate the plans in the source.** One page per plan, per plan year. A source
   listing seven plans produces seven plan pages, not one page with seven tables.

2. **For each plan, fill the frontmatter from `SCHEMA.md` § 2**, field by field,
   reading the value off the source. Then apply the two rules that decide the quality
   of this whole wiki:

   - **Anything the source did not state → `TBD`.** Not a market-typical value, not
     the sibling plan's value, not a value implied by the tier.
   - **Anything that does not apply to this plan → omit the key.** A dental-only plan
     has no `metal_tier`; a Medigap plan has no `copay_specialist`. `TBD` and an absent
     key mean different things (§ 2.4) and the linter counts them separately.

3. **Set `confidence` from the evidence, not from your effort** (§ 2.2). An official
   SBC for the stated plan year is `high`. A broker site, an aggregator, or an
   official document for a prior year is `medium`. A partial extraction, a source that
   never stated the plan year, or more than half the cost fields `TBD` is `low`.

4. **Two numbers that are easy to get backwards, so check both explicitly:**
   - `deductible_type` — `embedded` means an individual in a family hits their own
     deductible and starts getting benefits before the family deductible is met;
     `aggregate` means nobody gets benefits until the whole family deductible is met.
     It is a required SBC disclosure and it materially changes the cost of a family of
     three. Extract it.
   - `oop_max_*` is the out-of-pocket maximum **including** the deductible unless the
     source explicitly says otherwise. Where a source states an exclusive figure, add
     the deductible and record the adjustment inline as
     `[assumption: OOP max stated exclusive of deductible; deductible added]`.

5. **Read the existing page, if there is one, and compare semantically —
   whole page, not just the section you intend to write.** A claim in
   `## Exclusions & Limits` can contradict one in `## Additional capture`.

6. **Classify every match, and be strict about what counts as a conflict:**
   - Differing detail, added detail, or a change over time is **not** a conflict. It is
     two facts, and both stay. A source that adds a specialist copay to a page that had
     none is a refinement — write it.
   - **A different plan year is not a conflict.** It is a different page.
   - A genuine conflict is two claims about the **same field, same plan, same plan
     year** that cannot both be true. `$65` where the page says `$55` is a conflict.
   - **`TBD` never conflicts with anything.** It is not a claim.

7. **Resolve each genuine conflict now, by the policy in `SCHEMA.md` § 7.2:**
   1. Higher `authority` wins — an official SBC beats a broker site regardless of date.
   2. At equal authority, the newer `retrieved` date wins — except that a source for an
      *earlier* plan year never overwrites a later one, however recently retrieved.
   3. At equal authority and the same date, **keep the existing value**, write the new
      one beside it under `## Additional capture` as `### Unresolved`, and log it.

8. **Build the change list** that Step 7 will execute and Step 8 will log: page path,
   `plan_id`, field or section, old value with its source, new value with its source,
   and the rule that decided it.

### Step 6 — Sanity-check the numbers before they land

Six checks, all cheap, all catching a mis-read rather than a bad plan:

| Check | Why it matters |
|---|---|
| `oop_max_individual` ≥ `deductible_individual` | The reverse is impossible. It means one of the two was mis-read, or an exclusive OOP max was recorded without adding the deductible. |
| family figures ≥ individual figures | Same. |
| `coinsurance_in_network` is the member's share, and ≤ 100 | `80` on a Gold plan almost always means the plan pays 80%. Re-read the source. |
| a premium in the plausible range for the market | A monthly premium of `7348` is an annual figure in a monthly field. |
| `metal_tier` consistent with the cost structure | A "Bronze" plan with a $0 deductible is possible but rare enough to re-read. |
| every money field is bare, unquoted, no symbol | A quoted number is invisible to the comparison math. |

A check that fires is a signal to **re-read the source**, not to adjust the number.
Where the source genuinely says the surprising thing, write it and note why in
`## Additional capture` under `### Data notes`. Strangeness in the source is signal.

### Step 7 — Write

Now it is mechanical.

**7a — The company page, if the folder is NEW:**

```bash
S="skills/hiw-ingest"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-ingest"
python3 "$S/scripts/new-page.py" company --wiki . --company "<slug>" \
  --company-name "<Carrier Name>" --set 'markets=[individual]' --set 'states=[CA]' \
  --set 'networks=[...]' --set website=<url> --source "<source_ref>"
```

Then fill its six sections and its `## Plans Offered` roster. The roster is a
**mirror**, not a second source of truth: every number in it must match that plan's
frontmatter, and `plan_count` must equal the number of `.md` files in `plans/`. The
linter checks all three against each other, because a company page that disagrees with
its own plan folder is how a comparison quietly drops a plan.

**7b — Each plan page.** For a NEW plan, emit the skeleton and then fill it:

```bash
S="skills/hiw-ingest"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-ingest"
python3 "$S/scripts/new-page.py" plan --wiki . --company "<slug>" \
  --company-name "<Carrier Name>" --title "<Plan Title>" \
  --set market=individual --set network_type=PPO --set metal_tier=Gold \
  --set premium_monthly_individual=612.40 --set deductible_individual=750 \
  --source "<source_ref>" --source-url "<url>"
```

The script guarantees the shape: every required key present, the nine sections in
contract order, and `plan_id` agreeing with the path. Pass every value you actually
extracted via `--set`; then write the section bodies with Edit.

**Know what it writes as `TBD` and what it leaves absent.** Every field the cost model
needs — premium, deductible, OOP max, primary care, specialist, imaging, tier-1 generic —
plus tier, premium basis and network name, are written as `TBD` when you do not supply
them, so the linter counts them and `/hiw-refresh` targets them. The rest —
`copay_urgent_care`, `copay_lab`, `copay_telehealth`, `rx_deductible`, the upper Rx
tiers, `coinsurance_out_of_network`, the dental and vision flags — are left **absent**,
which under § 2.4 asserts the dimension does not apply. **If one of those does apply to
this plan and you simply do not know it, pass it explicitly as `--set copay_lab=TBD`.**
The script cannot know the difference; you can.

For an **existing** plan page, the script exits 3 and prints the path. That refusal is
correct — and note that `--force` exists to override it. **Do not use `--force`.** It is
there for a human repairing a corrupted page by hand, not for this skill; every legitimate
update to an existing page goes through Edit, under the resolution policy.

Edit the page instead:

- **A section holding only `_TBD._` is a placeholder — replace the stub**, do not write
  beneath it.
- **New substance appends**, tagged `[<date> via hiw-ingest]`.
- **A superseded value is edited in place**, tagged
  `[<date> updated via hiw-ingest]`, and it appears in the Step 8 log. An unlogged
  overwrite is the one genuinely destructive outcome available here.
- Update `last_updated`, set `updated_by: hiw-ingest`, and append the new `source_ref`
  to `sources`.
- **Leave `plan_id` and `company` alone.** A frontmatter id that disagrees with its
  path is a finding for `/hiw-lint`, not something to fix by editing whichever one
  looks wrong.

**A new plan year is a new page, never an edit** (§ 7.1). Write
`<plan-slug>-<year>.md`, and set the prior year's page to `status: superseded` with a
line in its `## Additional capture` naming the successor. Rate history is the most
useful thing this wiki accumulates, and editing last year's page in place destroys it.

**7c — The source record**, one per document or URL:

```bash
S="skills/hiw-ingest"; [ -d "$S/scripts" ] || S="$CLAUDE_PLUGIN_ROOT/skills/hiw-ingest"
python3 "$S/scripts/new-page.py" source --wiki . --company "<slug>" \
  --title "<Source Title>" --set source_type=pdf --set source_ref="<file>" \
  --set authority=official --set source_url="<url>" --set publisher="<carrier>" \
  --set plan_year=2026
```

Then fill its three sections. `## Key extractions` names each fact set's destination
**page and section** by wiki-relative path, so a later reader can retrace any number to
its origin. On a re-ingest, this record is **append-only**: add to `## Key extractions`
and `## Coverage`, never rewrite `## Metadata`.

### Step 8 — Index and log

**Leave `index.md` alone.** It is a derived catalog and `/hiw-lint` rebuilds it
wholesale from the tree; hand-patching it here creates a second writer of one file, and
the two eventually disagree about what the wiki contains. **The index is now stale, and a
stale index is a normal condition rather than an error** — say so in the Step 9 report
and point at `/hiw-lint`.

**Append one entry to `log.md`.** Omit any subsection with no entries; if every change
was a plain append, the header line alone is enough.

```markdown
## [YYYY-MM-DD] hiw-ingest | <Carrier> — <N> plan pages created, <M> updated, <U> values overwritten, <K> not adopted, <X> unresolved

### Values updated in place
- `companies/<slug>/plans/<plan>.md` · `premium_monthly_individual` · 598.10 [source: blue-2025-rates.pdf] -> 612.40 [source: blue-2026-sbc.pdf] — newer plan year

### Not adopted (incoming source older)
- `companies/<slug>/plans/<plan>.md` · `copay_specialist` · kept 65 [source: blue-2026-sbc.pdf]; incoming 55 [source: blue-2025-rates.pdf] not adopted

### Unresolved (same authority, same date — left for /hiw-lint to mark)
- `companies/<slug>/plans/<plan>.md` · `deductible_individual` · 750 [source: A] alongside 1000 [source: B]
```

### Step 9 — Report

1. **What was created and what was updated**, by path.
2. **Every in-place overwrite**, explicitly: old value, new value, and which rule
   decided it. The user did not approve these edits before they landed; this report and
   `log.md` are how they audit them.
3. **What is `TBD`, grouped by plan**, and which fields are core comparison fields.
   This is the most actionable part of the report — it is the list `/hiw-refresh` will
   work from.
4. **Every `[assumption: ...]` you wrote**, and why.
5. **What the source did not cover at all** — a source that never mentioned exclusions
   leaves that section a stub, and saying so is what stops someone treating the page
   as complete.
6. **Next steps:** `/hiw-lint` to health-check and rebuild `index.md` — say that the
   index is stale until it runs; `/hiw-ingest` again for the next carrier;
   `/hiw-list-plan` once two or more carriers are in.

Close with the standing caveat, once.

---

## Fan-out

**This skill does not fan out, and that is deliberate.** One run, one carrier, one
company folder. Subagents are how `/hiw-list-plan`, `/hiw-query`, `/hiw-compare` and
`/hiw-lint` read many carriers at once; ingest is the writer, and a writer split across
subagents produces a change list nobody can audit and a `log.md` entry that is a
guess. **Fan out to read; funnel to write.**

The one exception, and it is a read: a source document covering **more than five plans**
may be parsed by one subagent per plan. Brief each with the source text and this return
contract:

```json
{"plan_title": "<verbatim from the source>",
 "frontmatter": {"<schema key>": "<value read off the source, or TBD>"},
 "sections": {"Snapshot": "<text>", "Covered Services": "<table>", "...": "..."},
 "source_phrases": {"<schema key>": "<the exact phrase the value came from>"},
 "not_stated": ["<schema key the source is silent on>"],
 "does_not_apply": ["<schema key this kind of plan has no dimension for>"]}
```

`source_phrases` is what makes the fan-out auditable: the parent decides what to write
and needs to see what it is deciding from. `not_stated` and `does_not_apply` are separate
lists because they become `TBD` and an absent key respectively (§ 2.4), and no subagent
may collapse them.

**Collect every subagent result before writing anything** — a partial fan-out produces a
company folder missing a plan, and nothing downstream can tell that from a carrier that
only offers four. The parent still does all the writing, all the conflict resolution and
all the logging.

---

## Files in this skill

| File | What it does |
|---|---|
| `scripts/extract-source.py` | plain text out of docx/xlsx/pptx/html/txt/csv/json, and pdf via `pdftotext` if present. Stdlib only. Exit 2 means "read it natively instead" |
| `scripts/new-page.py` | emits a schema-conformant plan, company or source skeleton. Refuses to overwrite (exit 3). Unsupplied cost fields land as `TBD` |

Executed, never loaded into context. Run them by path; never inline, retype or rewrite
one. The shipped file is the single source of truth for what gets emitted, and an
edited copy silently changes the result. If a script is missing, say so and stop — do
not reconstruct it.

---

## Anti-patterns

- Do not infer a cost from the metal tier, from a sibling plan, from the carrier's other plans, or from what such a plan typically costs. Write `TBD`. If you are reasoning toward a plausible value, that is the signal.
- Do not write `TBD` for a dimension that does not apply to this plan. Omit the key. `TBD` and absent mean different things and the linter counts them separately.
- Do not record the plan's coinsurance share as the member's. "This plan pays 80%" is `coinsurance_in_network: 20`. An inverted coinsurance is the most consequential silent error available in this domain.
- Do not put a currency symbol, a thousands separator, or quotes around a money value. A quoted number is invisible to the comparison math, and invisible is indistinguishable from absent.
- Do not create a second folder for a carrier you already have. Check `ls companies/` for a near-miss first. Split carriers break every fan-out, every catalog section and every comparison.
- Do not ingest two carriers in one run. The change list and the log entry both stop being auditable.
- Do not write one plan page holding seven plans' tables. One page per plan, per plan year.
- Do not edit last year's page when a new plan year arrives. A new plan year is a new page; the old one becomes `status: superseded`. Editing in place destroys the rate history that is the most useful thing this wiki accumulates.
- Do not overwrite a plan page you have not read. `new-page.py` exiting 3 is correct behaviour, not an obstacle.
- Do not write beneath a `_TBD._` placeholder. Replace it.
- Do not perform an in-place overwrite without logging the old value, the new value, both sources and the deciding rule. An unlogged overwrite is the one genuinely destructive outcome available here.
- Do not treat differing detail, added detail, or a different plan year as a conflict. Two facts stay as two facts.
- Do not leave a genuine same-date conflict silently resolved by recency. Keep the existing value, record the other under `### Unresolved`, and log it.
- Do not approximate a PDF you could not extract. Read it natively. A plausible mis-read of a benefits grid is worse than no read, because either way the number lands in the wiki.
- Do not work from a WebFetch result that came back as a page shell. Switch to the Chrome tools. A fragment of a client-rendered page reads like a carrier with two plans.
- Do not record a post-subsidy premium as unsubsidized, and do not reverse-engineer the unsubsidized figure from it. Set `premium_basis` and move on.
- Do not omit the access date from a URL source tag. A web page changes and an undated web claim cannot be re-verified.
- Do not stop reading at the deductible. Exclusions, visit limits and prior-authorization rules are the sections most often skipped here and most often decisive in a comparison.
- Do not drop a fact because no fixed section fits it. `## Additional capture` exists for exactly that, and silent discard is unrecoverable.
- Do not invent a `##` heading. The nine are the whole machine contract for a plan page; a free-form heading goes under `## Additional capture` as a `###`.
- Do not adjust a number because a Step 6 check fired. Re-read the source. Where the source really says the surprising thing, write it and note why.
- Do not fan out to write. One writer, one change list, one log entry.
- Do not begin analysis before every fan-out subagent has returned. Collect first.
- Do not hand-patch `index.md`. `/hiw-lint` rebuilds it wholesale, and a second writer of one file means the two eventually disagree about what the wiki contains.
- Do not leave a cost key absent when the plan has that dimension and you simply do not know it. Absent asserts "does not apply"; pass `--set <key>=TBD` instead.
- Do not let a subagent collapse "the source did not state it" into "this plan does not have it". They become `TBD` and an absent key, and the difference is the whole of § 2.4.
- Do not write a carrier's plan line-up from a navigation menu because WebFetch returned a shell and the Chrome tools are unavailable. Ask for a paste or a saved file.
- Do not skip the source record because the extraction was small. A number with no receipt cannot be retraced, and in a year nobody will remember where it came from.
