# health-insurance-wiki — Page Contract (SCHEMA)

The contract every page in this wiki obeys. `/hiw-setup` copies this file into the wiki root as
`SCHEMA.md`; that runtime copy is the only one downstream skills read. Skills cite section numbers
(`§ 3.1`, `§ 7`) verbatim, so **copy this file byte-for-byte — never summarize, re-flow, re-number,
or paraphrase it.**

This wiki is the retrieval layer for an Agentic RAG system that compares health insurance plans
within and across carriers. Every rule below exists to make one of two things possible: a subagent
answering a question about **one carrier** without reading any other carrier's pages, or a
deterministic script producing a **comparison table** without an LLM re-reading prose.

---

## § 1 — Architecture

Five directories at the wiki root, five roles:

| Path | Holds | Written by | Read by |
|---|---|---|---|
| `companies/` | one folder per insurance carrier — the knowledge | `/hiw-ingest`, `/hiw-refresh`, `/hiw-lint` | everything |
| `raw/` | immutable originals, mirrored by company | `/hiw-ingest`, `/hiw-refresh` | `/hiw-ingest`, `/hiw-refresh` |
| `synthesis/` | saved comparisons, recommendations, briefs | `/hiw-query`, `/hiw-compare` | humans |
| `output/` | generated HTML, reports, and the scripts' intermediate json | every skill | humans, and the scripts |
| `_config/` | wiki-level settings | `/hiw-setup` | every skill |

Three files at the wiki root:

- `SCHEMA.md` — this contract. Copied in at setup; **never edited in place**.
- `index.md` — the catalog of every plan, grouped by company (§ 8). Regenerated, holds no knowledge of its own.
- `log.md` — append-only chronological record (§ 9).

**The company folder is the unit of parallelism.** Everything a subagent needs to become the master
of one carrier is inside `companies/<company-slug>/` and nowhere else. Never store a plan's facts
outside its own company folder, and never make one company's page depend on another company's page.

```
<wiki-root>/
├── SCHEMA.md
├── index.md
├── log.md
├── _config/
│   └── wiki-config.md
├── companies/
│   └── <company-slug>/
│       ├── company.md
│       ├── plans/
│       │   └── <plan-slug>.md
│       └── sources/
│           └── <source-slug>.md
├── raw/
│   └── <company-slug>/
├── synthesis/
└── output/
```

### § 1.1 — Slugs

`<company-slug>` and `<plan-slug>` are kebab-case: lowercase, spaces to hyphens, ampersands to
`and`, every other non-alphanumeric character dropped, collapsed hyphens, no leading or trailing
hyphen. `Blue Cross Blue Shield of California` → `blue-cross-blue-shield-of-california`.
`Gold 80 PPO 750/35 + Child Dental` → `gold-80-ppo-750-35-child-dental`.

A slug is **durable identity**. Once a plan page exists at a path, that path does not change
because a marketing name changed — record the new name in `title` and add the old one to
`aka`. Renaming a page breaks every cross-reference, every saved comparison, and every
`plan_id` cited in a synthesis page.

---

## § 2 — Plan page frontmatter (`companies/<company>/plans/<plan>.md`)

This is the machine-readable core. `/hiw-compare` and `/hiw-list-plan` read these keys and nothing else
when building tables, so a value here is a **contract**, not a note.

```yaml
---
title: Gold 80 PPO 750/35
plan_id: "blue-shield-ca__gold-80-ppo-750-35"
aka: []
company: blue-shield-ca
company_name: Blue Shield of California
plan_year: 2026
market: individual
network_type: PPO
metal_tier: Gold
hsa_eligible: false
carrier_plan_code: "40513CA1230004"
states: [CA]
service_area: Statewide except Alpine County

premium_monthly_individual: 612.40
premium_monthly_family: 1837.20
premium_basis: unsubsidized
deductible_individual: 750
deductible_family: 1500
deductible_type: embedded
oop_max_individual: 8700
oop_max_family: 17400
coinsurance_in_network: 20
coinsurance_out_of_network: 50

copay_primary_care: 35
copay_specialist: 65
copay_urgent_care: 35
copay_emergency_room: 350
copay_telehealth: 0
copay_lab: 35
copay_imaging: 75
inpatient_cost_share: "20% after deductible"

rx_deductible: 0
rx_tier1_generic: 15
rx_tier2_preferred_brand: 55
rx_tier3_nonpreferred_brand: 90
rx_tier4_specialty: "20% up to $250"

network_name: Tandem PPO
pcp_required: false
referral_required: false
out_of_network_covered: true
dental_included: false
vision_included: false

sources: [blue-shield-2026-sbc.pdf]
source_urls: ["https://www.example.com/plans/gold-80-ppo"]
effective_date: 2026-01-01
created: 2026-08-25
last_updated: 2026-08-25
updated_by: hiw-ingest
confidence: high
status: active
---
```

### § 2.1 — Required keys

Present on every plan page, always: `title`, `plan_id`, `company`, `company_name`, `plan_year`,
`market`, `network_type`, `sources`, `created`, `last_updated`, `updated_by`, `confidence`,
`status`. `aka`, `states`, and `source_urls` must **exist** and may be empty lists.

Every other key is optional in the sense that it may be absent when the source never covered that
dimension — but see § 2.4, which is the rule that actually matters.

### § 2.2 — Controlled vocabularies

| Key | Allowed values |
|---|---|
| `market` | `individual` · `family` · `small-group` · `large-group` · `medicare-advantage` · `medicare-supplement` · `medicare-part-d` · `medicaid` · `student` · `short-term` · `dental` · `vision` |
| `network_type` | `HMO` · `PPO` · `EPO` · `POS` · `HDHP` · `Indemnity` · `Other` |
| `metal_tier` | `Bronze` · `Expanded Bronze` · `Silver` · `Gold` · `Platinum` · `Catastrophic` · `n/a` |
| `premium_basis` | `unsubsidized` · `post-subsidy` · `employer-contribution-net` · `employee-share` · `TBD` |
| `deductible_type` | `aggregate` · `embedded` · `none` · `TBD` |
| `updated_by` | `hiw-setup` · `hiw-ingest` · `hiw-refresh` · `hiw-list-plan` · `hiw-query` · `hiw-compare` · `hiw-lint` · `practitioner` |
| `confidence` | `high` · `medium` · `low` |
| `status` | `active` · `superseded` · `draft` |

`confidence` is about the *evidence*, not the writer:

- `high` — every required cost field came from an official carrier document (SBC, plan brochure, carrier site) for the stated `plan_year`.
- `medium` — a secondary source (broker site, comparison aggregator, news article), or an official source from a prior plan year.
- `low` — partial extraction, a source that did not state the plan year, or more than half the cost fields are `TBD`.

`plan_id` is `<company-slug>__<plan-slug>` with a **double** underscore. It is globally unique
across the wiki and is the join key used by `/hiw-compare`, `/hiw-list-plan`, and every synthesis page.
Always quote it.

### § 2.3 — Types and units

- Money is a **bare number** in the wiki's currency (`_config/wiki-config.md`, default USD): `750`, `612.40`. No `$`, no thousands separators, no quotes.
- Percentages are a **bare number meaning the share the member pays**: `coinsurance_in_network: 20` means the member pays 20% and the plan pays 80%. Never write `"20%"` and never invert it.
- Booleans are `true` / `false`, never `yes` / `Yes` / `"true"`.
- Dates are `YYYY-MM-DD`.
- Lists are inline flow style: `states: [CA, NV]`, `sources: [a.pdf, b.pdf]`, empty as `[]`.
- A cost share that genuinely is not a single number is a **quoted string**: `inpatient_cost_share: "20% after deductible"`, `rx_tier4_specialty: "20% up to $250"`. Prefer a number wherever the source gives one — a string is invisible to the
  comparison math, because `/hiw-compare` sums bare numbers and reports a scenario as
  not computable rather than parsing prose.

### § 2.4 — `TBD` over a guess, always

A field the source did not state is written as the literal `TBD`:

```yaml
copay_specialist: TBD
```

**Never infer a number.** Not from the metal tier, not from a sibling plan, not from "typical"
market values, not from the carrier's other plans. A fabricated `deductible_individual` is worse
than an absent one, because `/hiw-compare` will rank on it, `/hiw-query` will recommend on it, and nothing
downstream can tell it apart from a number read off an SBC. If you find yourself reasoning toward a
plausible value, that is the signal to write `TBD`.

Omitting a key and writing `TBD` mean different things. **`TBD` means "this plan has this dimension
and we do not know it"** — the linter counts it and `/hiw-refresh` targets it. **An absent key means
"this dimension does not apply to this plan"** — a dental-only plan has no `metal_tier`, a
Medigap plan has no `copay_specialist`. Do not write `TBD` for a dimension that does not exist.

### § 2.5 — Two coverage numbers that are easy to get backwards

- `deductible_type: embedded` means an individual within a family hits their own individual deductible and starts getting benefits before the family deductible is met. `aggregate` means the whole family deductible must be met first, by anyone, before anyone gets benefits. This materially changes cost for a family of three and is a required disclosure on every SBC — extract it.
- `oop_max_*` is the **out-of-pocket maximum including the deductible** unless the source explicitly says otherwise. If a source states an OOP max that excludes the deductible, add the deductible and note the adjustment inline with `[assumption: ...]`.

---

## § 3 — Plan page sections

Exactly these nine `##` headings, in this order, **all present on every plan page**, matched
case-insensitively and exactly. Do not invent, rename, merge, reorder, or omit one.

```
## Snapshot
## Cost Structure
## Covered Services
## Pharmacy
## Network & Access
## Exclusions & Limits
## Extras & Riders
## Fit Notes
## Additional capture
```

The title line is `# <title> — <company_name> (<plan_year>)`.

An empty section holds the placeholder `_TBD._` on its own line. It is never omitted, and content
**replaces** the placeholder rather than being written beneath it.

### § 3.1 — What each section holds

**`## Snapshot`** — three to five bullets, and the first one states why someone would pick this
plan, not what it is. "Lowest deductible in Blue Shield's individual PPO line, at the cost of the
second-highest premium" beats "A Gold-tier PPO plan." Retrieval quality depends on this section
more than any other; it is what a subagent quotes when the question is broad.

**`## Cost Structure`** — a table restating the frontmatter cost keys in human form, plus anything
numeric the frontmatter cannot hold (tiered deductibles, family-size premium bands, age-banded
rates, employer contribution splits). The frontmatter is the machine truth; this section is where a
person checks it.

**`## Covered Services`** — a table, one row per service, three columns:

```
| Service | In-network | Out-of-network |
|---|---|---|
| Primary care visit | $35 copay | 50% after deductible |
| Preventive care | No charge | Not covered |
```

Use the carrier's own service names. Where a service has a visit limit or requires prior
authorization, say so in the row.

**`## Pharmacy`** — formulary tiers and their cost shares, the pharmacy deductible if separate,
mail-order terms, and specialty drug handling. Name specific drugs only if the source does.

**`## Network & Access`** — the network name, size if stated, PCP and referral rules, geographic
service area, telehealth vendor, and whether out-of-network care is covered at all. For an
HMO or EPO, state plainly what happens out of network — usually "emergency only."

**`## Exclusions & Limits`** — what is not covered, waiting periods, visit caps, prior
authorization requirements, pre-existing condition terms where they legally apply. This is the
section most often skipped during ingest and most often decisive during `/hiw-compare`.

**`## Extras & Riders`** — dental, vision, hearing, wellness credits, gym benefits, OTC
allowances, transportation, and anything bundled or purchasable as a rider. Medicare Advantage
plans live or die here.

**`## Fit Notes`** — the reasoning layer, and the section `/hiw-query` reads most heavily. Two
sub-bullets minimum: **who this plan suits** and **who should look elsewhere**, each grounded in a
specific number from the page. "Suits a household expecting a planned surgery — the $750 deductible
and $8,700 OOP max cap exposure earlier than any Silver plan here" is useful; "good for families"
is not. This is interpretation, and it is allowed here because this section is explicitly for it —
but every claim must trace to a number on this page.

**`## Additional capture`** — the last section of every page and the only place free-form `###`
headings are allowed. Use it for anything real that the eight fixed sections cannot hold:
`### Rate history`, `### Regulatory notes`, `### Open questions`, `### Broker commentary`,
`### Comparison notes`. Tools stop reading the contract here. It is not an overflow bin for content
that belongs in a fixed section above.

---

## § 4 — Company page (`companies/<company>/company.md`)

Frontmatter:

```yaml
---
title: Blue Shield of California
company: blue-shield-ca
category: company
plan_year: 2026
markets: [individual, small-group]
states: [CA]
networks: [Tandem PPO, Trio HMO, Access+ HMO]
plan_count: 7
website: "https://www.blueshieldca.com"
sources: [blue-shield-2026-sbc.pdf]
created: 2026-08-25
last_updated: 2026-08-25
updated_by: hiw-ingest
status: active
---
```

Sections, in order, all present:

```
## Snapshot
## Plans Offered
## Networks
## Service Area
## Enrollment & Service
## Additional capture
```

`## Plans Offered` is a table with **one row per plan page in this company folder**, and it is a
mirror, not a second source of truth — every number in it must match that plan's frontmatter:

```
| Plan | Tier | Network | Premium/mo | Deductible | OOP max | Page |
|---|---|---|---|---|---|---|
| Gold 80 PPO 750/35 | Gold | PPO | 612.40 | 750 | 8700 | `plans/gold-80-ppo-750-35.md` |
```

`plan_count` in the frontmatter must equal the number of `.md` files in `plans/`. The linter checks
all three against each other, because a company page that disagrees with its own plan folder is how
a comparison quietly drops a plan.

---

## § 5 — Source records (`companies/<company>/sources/<source-slug>.md`)

One record per ingested document or URL. It is a receipt, not a summary: it records **what was
extracted and where it went**, so a later reader can retrace any number back to its origin.

Frontmatter carries only these keys — never plan keys:

```yaml
---
title: Blue Shield 2026 Individual SBC — Gold 80 PPO
category: sources
company: blue-shield-ca
source_type: pdf
source_ref: blue-shield-2026-sbc.pdf
source_url: "https://www.example.com/sbc/gold-80-ppo.pdf"
retrieved: 2026-08-25
publisher: Blue Shield of California
plan_year: 2026
authority: official
created: 2026-08-25
last_updated: 2026-08-25
updated_by: hiw-ingest
status: active
---
```

`source_type`: `pdf` · `docx` · `txt` · `xlsx` · `pptx` · `html` · `url` · `image` · `verbal`.
`authority`: `official` (the carrier itself, or a government exchange) · `secondary` (broker,
aggregator, press) · `unofficial` (forum, hearsay). `authority` drives conflict resolution (§ 7.2)
and feeds each plan's `confidence`.

Exactly three sections:

**`## Metadata`** — bullets: Source ref · Type · URL · Retrieved · Publisher · Plan year ·
Authority · Pages or sections read.

**`## Key extractions`** — one line per fact set, each naming its destination page and section by
**wiki-relative path**:

```
- Gold 80 PPO cost-share grid → `companies/blue-shield-ca/plans/gold-80-ppo-750-35.md` `## Covered Services`
- 2026 rate table, all 7 individual plans → 7 plan pages, `premium_monthly_individual`
```

**`## Coverage`** — a table of what this source touched:

```
| Plan page | Sections touched |
|---|---|
| `plans/gold-80-ppo-750-35.md` | frontmatter, `## Cost Structure`, `## Covered Services` |
```

Source records are **append-only**. Re-ingesting the same document appends to `## Key extractions`
and `## Coverage`; it never rewrites `## Metadata`.

### § 5.1 — Synthesis pages (`synthesis/<slug>.md`)

Saved analysis — a comparison or a recommendation a human will come back to. Written by
`/hiw-query` and `/hiw-compare`, read by humans, and **never** read as a source of plan
facts by anything. A synthesis page is a snapshot of a conclusion, so it goes stale by
design and that is not a defect.

```yaml
---
title: Recommendation — household of three, ongoing specialist care
category: synthesis
plan_ids: ["blue-shield-ca__gold-80-ppo-750-35", "kaiser-permanente__gold-80-hmo-0-30"]
recommended: "blue-shield-ca__gold-80-ppo-750-35"
profile: Moderate use, one specialist quarterly, wants to keep current doctor
governing_scenario: moderate
created: 2026-08-25
last_updated: 2026-08-25
updated_by: hiw-query
status: active
---
```

`plan_ids` and `recommended` cite plans by `plan_id`, never by marketing name — that is
what makes a saved conclusion re-checkable a year later, when three of the plans have been
renamed. `governing_scenario` is one of `healthy` · `moderate` · `bad`, or the empty
string where the conclusion did not rest on cost. `recommended` may be empty.

Sections are free-form: this is the one page type with no fixed section grammar, because a
recommendation and a rate-change brief are not the same shape. Two contents are required
regardless — **the question that was asked** (for a recommendation, the assessment answers
verbatim) and **the standing caveat from § 11**. A conclusion recorded without the question
it answered is uninterpretable six months later, which is exactly when someone reads it.

**Nothing generated ever lands inside a company folder.** Company folders hold sourced
facts only.

---

## § 6 — Provenance and cross-references

### § 6.1 — Inline tags

Every non-obvious claim carries its origin:

- `[source: blue-shield-2026-sbc.pdf]` — a document in `raw/<company>/` or a `source_ref`.
- `[source: https://www.example.com/plans, accessed 2026-08-25]` — a URL, always with the access date, because web pages change and an undated web claim cannot be re-verified.
- `[assumption: OOP max stated exclusive of deductible; deductible added]` — a derivation you performed. State the derivation, not just that one occurred.
- `[verify: rate shown is post-subsidy; unsubsidized rate not published]` — a known weakness a human should resolve. `/hiw-lint` reports these; nothing auto-clears them.

### § 6.2 — Cross-references are paths, never wikilinks

Write `companies/blue-shield-ca/plans/gold-80-ppo-750-35.md`, wiki-relative, in backticks.
**Do not use `[[wikilink]]` syntax.** Plan names collide constantly — three carriers in one wiki
will each have a "Gold PPO", and `[[Gold PPO]]` cannot resolve. The path is the identity.

**Write every cross-reference as an inline path in the body**, not only in a
frontmatter list. Orphan detection scans bodies, so a path living solely in frontmatter is
never link-checked — and a reference nothing checks is a reference that rots.

### § 6.3 — Currency and units

`_config/wiki-config.md` sets `currency` (default `USD`). Every money field in the wiki is in that
currency. A source quoting a different currency is converted at ingest, with the rate and date
recorded as an `[assumption: ...]`, or the plan is `TBD` — never mixed.

---

## § 7 — Updates, conflicts, and supersession

### § 7.1 — Never delete

No skill deletes a plan page. A plan that is withdrawn or replaced gets `status: superseded` and a
line in `## Additional capture` naming what replaced it. Rate history is the single most useful
thing this wiki accumulates, and deleting last year's page destroys it.

A new plan year is a **new page**, not an edit: `plan_year: 2027` gets its own file
(`gold-80-ppo-750-35-2027.md`), and the 2026 page moves to `status: superseded`. Comparing this
year's rates against last year's is only possible if both pages exist.

### § 7.2 — Resolution policy at write time

When a new source disagrees with what is already on a page:

1. **Higher `authority` wins.** An official SBC beats a broker site regardless of date.
2. **At equal authority, the newer `retrieved` date wins** — with one exception: a source for an *earlier* `plan_year` never overwrites a later one, however recently it was retrieved.
3. **At equal authority and the same date, keep the existing value**, write the new one beside it in `## Additional capture` under `### Unresolved`, and log it. `/hiw-lint` marks it.

Every in-place overwrite is logged with old value, new value, both sources, and the rule that
decided it (§ 9). The practitioner did not approve that edit before it landed, so the log is the
only place they can catch it.

**Elaboration is not conflict.** A source adding a specialist copay to a page that had none is a
refinement — write it. A source stating `$65` where the page says `$55` is a conflict — run the
policy. Different plan years are not a conflict; they are different pages.

### § 7.3 — Contradiction markers

`/hiw-ingest` and `/hiw-refresh` resolve what they can and log it. What they cannot settle, `/hiw-lint`
marks on the page itself, immediately below the newer claim:

```
**CONTRADICTION:** deductible_individual 750 [source: blue-shield-2026-sbc.pdf] vs. 1000 [source: healthplanfinder.example.com, accessed 2026-08-20] — equal date, unresolved. [2026-08-25 via hiw-lint]
```

The marker names both values and both sources. It never picks a winner, and it never edits either
claim.

---

## § 8 — `index.md`

The catalog. It holds no knowledge of its own and is fully rebuildable from `companies/` at any
time, so a stale index is a normal condition rather than an error.

```markdown
# Index

_Generated 2026-08-25 · 3 companies · 19 plans_

## Blue Shield of California — `companies/blue-shield-ca/`

| Plan | Tier | Network | Market | Premium/mo | Deductible | OOP max | Conf. | Page |
|---|---|---|---|---|---|---|---|---|
| Gold 80 PPO 750/35 | Gold | PPO | individual | 612.40 | 750 | 8700 | high | `plans/gold-80-ppo-750-35.md` |
```

One `##` section per company, in alphabetical order by `company_name`, each header naming the
company folder path. Superseded plans are listed in a separate `### Superseded` subsection under
their company, never mixed into the main table.

---

## § 9 — `log.md`

Append-only. Never edit an existing entry. Every entry opens with the date, then the skill name in
the second position, then a one-line detail:

```markdown
## [2026-08-25] hiw-ingest | Blue Shield of California — 7 plan pages created, 1 updated, 0 unresolved
### Values updated in place
- `companies/blue-shield-ca/plans/gold-80-ppo-750-35.md` · `premium_monthly_individual` · 598.10 [source: blue-shield-2025-rates.pdf] -> 612.40 [source: blue-shield-2026-sbc.pdf] — newer plan year
```

The skill vocabulary is the same as `updated_by` (§ 2.2). `###` subsections are optional and
omitted when empty. These are the sanctioned ones — a skill may add a subsection its work
needs, but it may not rename one of these:

| Subsection | Written by | Holds |
|---|---|---|
| `### Values updated in place` | `/hiw-ingest`, `/hiw-refresh` | every in-place overwrite: old value, new value, both sources, the deciding rule |
| `### Not adopted` | `/hiw-ingest`, `/hiw-refresh` | an incoming claim the policy rejected, and why |
| `### Unresolved` | `/hiw-ingest`, `/hiw-refresh` | equal authority, same date, both values kept |
| `### Held` | any | substance deliberately not written, named but not quoted |
| `### TBDs filled` | `/hiw-refresh` | a field that was `TBD` and is now known |
| `### Still unknown after re-check` | `/hiw-refresh` | a `TBD` re-checked against its source and still unstated, so nobody re-checks it next week for nothing |
| `### Dead sources` | `/hiw-refresh` | a source that no longer resolves, and what now has no live origin |

A parenthetical after the heading is fine (`### Not adopted (incoming source older)`); a
different heading is not.

---

## § 10 — Writing standards

1. **Significance first.** Every `## Snapshot` opens with why the plan matters relative to its siblings, not with what it is.
2. **One claim per sentence.** A sentence carrying two numbers is two sentences.
3. **Numbers over adjectives.** "Low deductible" is unusable in a comparison; "$750 deductible, lowest of the seven" is.
4. **Tables over prose** anywhere the content is naturally tabular. Cost data is always tabular.
5. **Attribute anything contested.** A rate from a broker site and a rate from an SBC are not the same kind of fact, and the reader must be able to see which they are looking at.
6. **Literal Unicode, never HTML entities**, in `.md` files. Write `—` and `·`, not `&mdash;` and `&middot;`.

---

## § 11 — What this wiki is not

It is a structured record of what published sources say about health insurance plans. It is not a
quoting engine, not an eligibility determination, and not advice. Premiums here are list values for
a stated basis (§ 2.2) and will differ from what a specific person is actually offered once age,
ZIP code, tobacco use, household size, and subsidy eligibility are applied. Every deliverable this
wiki produces — `/hiw-list-plan` catalogs, `/hiw-compare` matrices, `/hiw-query` recommendations — carries that
caveat visibly, and no skill removes it. Coverage decisions rest on the carrier's official plan
documents, not on this wiki.
