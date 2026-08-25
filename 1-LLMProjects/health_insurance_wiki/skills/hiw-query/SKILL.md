---
name: hiw-query
description: >-
  Interactive needs assessment, then a ranked plan recommendation from the
  health-insurance-wiki. Asks what the person actually needs — budget shape, expected
  usage, doctors they want to keep, prescriptions, HMO vs PPO tolerance — then fans out
  one subagent per carrier to find that carrier's best matches, merges the returns, and
  recommends with the reasoning and the caveats attached. Use when the user says "which
  plan should I get", "help me pick", "what's best for someone with a chronic
  condition", "recommend a plan", or runs /hiw-query.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion
metadata:
  argument-hint: "(no arguments — interactive; or a free-text need to seed the assessment)"
---

# /hiw-query — Needs Assessment into a Ranked Recommendation

Two halves that must not be collapsed into one:

**The assessment** is a conversation. Health insurance decisions turn on facts the
person has not thought to volunteer — a specialist they see quarterly, a drug that is
tier 4 on one formulary and tier 2 on another, a spouse's employer plan that changes the
whole calculation. Asking well is most of the value here.

**The ranking** is arithmetic plus judgement, in that order. The arithmetic is
delegated to `build-comparison.py` when it comes to annual cost. The judgement is
yours, and it must be visible: every recommendation names the numbers it rests on and
the assumptions it could not verify.

Ladders, applied inline in every command block:

```bash
L="skills/hiw-lint";    [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
K="skills/hiw-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/hiw-compare"
```

---

## STOP conditions — check these first

1. **No plans in the wiki → say so and stop.** *"There are no plans stored yet, so
   there is nothing to recommend from. Run `/hiw-ingest` with a plan document or a
   carrier URL first."* Do not answer from general knowledge of the insurance market.
   The whole point of this wiki is that the answer is grounded in stored, sourced
   facts, and an ungrounded recommendation delivered in this skill's voice will be
   read as a grounded one.

2. **This is not advice, and the deliverable says so every time.** Not a quote, not an
   eligibility determination, not a substitute for a broker or the carrier's own plan
   documents. The caveat goes on the recommendation, not only in chat, and no step
   removes it. (Step 6)

3. **Never rank on a number that is not in the wiki.** A plan with `TBD` in a field
   being ranked is shown as unknown and named as unknown. It is never treated as zero,
   never quietly dropped from consideration, and never assigned a market-typical value
   so the ranking can proceed. A ranking that silently excluded the cheapest plan
   because its deductible was unrecorded is a wrong answer wearing the shape of a
   right one. (Step 4)

4. **Never ask for information you do not need and cannot protect.** No name, no
   address, no date of birth, no medical record, no member id, no income figure. Age
   band and ZIP-level geography, only if the person offers them and only because they
   determine which plans are even available. Say why you are asking. This skill
   produces a recommendation, not an application.

5. **Collect every subagent result before ranking anything.** A partial fan-out silently
   omits a carrier from consideration, and the recommendation will look complete.
   (Step 3)

6. **Seven questions maximum: six in the assessment across two calls, plus the save
   offer.** A needs assessment that becomes an interrogation gets abandoned, and an
   abandoned assessment produces no recommendation at all. (Step 2, Step 6)

---

## RULES — read before acting

This is a **rigid, prescribed procedure** for the mechanics. The wording of the
questions adapts to the person; the **canonical dimensions** in Step 2 do not, because
the subagent brief keys on them.

- **Ask through AskUserQuestion when you have it, in plain text when you do not, and
  never by assuming.** Every question here is blocking in the sense that guessing the
  answer produces a recommendation for a different person.
- **At most 4 options per question.** The UI auto-appends a free-text path; never add
  your own "type it" / "other" option.
- **One consolidated question naming the candidates, not a sequence of narrowing
  ones.** Where two dimensions are independent, put both in the same call.
- **Adapt the question to the wiki you actually have.** Do not ask "HMO or PPO?" when
  every stored plan is an HMO. Do not ask about Medicare when the wiki holds only
  individual-market plans. Read the inventory first; that is why Step 1 precedes
  Step 2.
- **Numbers over adjectives, in every claim you make.** "Suits a household expecting a
  planned surgery — the $750 deductible and $8,700 OOP max cap exposure earlier than
  any Silver plan here" is useful. "Good coverage for families" is not, and it is the
  kind of sentence that makes a recommendation feel authoritative without being
  checkable.
- **Name the losing case.** Every recommendation states the circumstance under which
  the recommended plan is the wrong choice. A recommendation with no downside is a
  sales pitch.
- **Do not restate the contract; apply it.** `SCHEMA.md` § 3.1 defines what
  `## Fit Notes` holds; § 2.4 defines what `TBD` means. The subagent brief cites them.

---

## Procedure

### Step 1 — Read the inventory before asking anything

```bash
L="skills/hiw-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/hiw-lint"
python3 "$L/scripts/lint-wiki.py" --wiki . --out output/_wiki-data.json
```

From `output/_wiki-data.json`, establish four things, because each one changes which
questions are worth asking:

- **Which markets exist** — individual, group, Medicare, dental. A wiki of Medicare
  Advantage plans gets a different assessment from a wiki of ACA marketplace plans.
- **Which network types exist.** If they are all PPO, the HMO-tolerance question is
  noise.
- **Which states and service areas.** If everything is California, do not ask for a ZIP
  code to establish eligibility — ask only if a plan's `service_area` excludes
  counties.
- **How much is unknown.** The count of plans with a `TBD` core cost, because it bounds
  how confident the eventual ranking can be, and you will say so.

**Say what you have, in one short paragraph, before the first question.** "There are 19
plans across 3 carriers, all California individual-market, spanning Bronze to Platinum,
$288 to $841 a month. Four have a cost field nobody has recorded yet." That paragraph
lets the person correct your framing before they answer six questions inside it.

### Step 2 — The assessment

Up to six questions, in **two calls**. Two calls, not six turns.

**Call 1 — the shape of the need.** Four questions in one call:

- header `"Budget shape"`, question `"Which matters more to you — a low monthly premium, or a low bill when you actually use care?"`, options (exactly these four): `["Lowest monthly premium — I rarely use care", "Balanced — moderate premium, moderate costs", "Lowest cost when I use care, even at a higher premium", "Lowest worst case — cap what a bad year can cost me"]`. (multiSelect: false)
- header `"Expected use"`, question `"How much care do you expect this year?"`, options (exactly these four): `["Very little — checkups and maybe one illness", "Some — a few specialist visits, routine prescriptions", "A lot — ongoing condition, regular specialist care", "Something planned — surgery, pregnancy, a known procedure"]`. (multiSelect: false)
- header `"Network"`, question `"Do you have doctors or a hospital you want to keep?"`, options (exactly these four): `["Yes, and that's non-negotiable", "Yes, but I'd switch to save real money", "No — I'll use whoever is in network", "I don't know who's in which network"]`. (multiSelect: false)
- header `"Coverage for"`, question `"Who needs covering?"`, options (exactly these four): `["Just me", "Me and a partner", "A family with children", "Me, but coordinating with a partner's employer plan"]`. (multiSelect: false)

**Call 2 — the specifics, and only the ones the wiki can actually answer.** Two
questions, chosen from these four by what Step 1 found:

- header `"Prescriptions"`, question `"Any regular prescriptions? Naming them lets me check the formulary tiers. (type them in the field)"`, options (exactly these three): `["None regularly", "Generics only", "At least one brand-name or specialty drug"]`. (multiSelect: false)
- header `"Plan type"`, question `"How do you feel about a plan that requires a referral to see a specialist? An HMO usually costs less and gates access; a PPO costs more and doesn't."`, options (exactly these three): `["Fine with referrals if it's cheaper", "I want to self-refer to specialists", "No preference — rank on cost"]`. (multiSelect: false) — **skip entirely if the wiki holds only one network type.**
- header `"Must-haves"`, question `"Anything that would rule a plan out?"`, `multiSelect: true`, options (exactly these four): `["Must cover out-of-network care", "Must include dental", "Must include vision", "Must be HSA-eligible"]`.
- header `"Geography"`, question `"Which county or ZIP? Some plans exclude counties. (type it in the field)"`, options (exactly these two): `["Anywhere in the stored service area", "I'll check availability myself"]`. (multiSelect: false) — **ask only if a stored plan's `service_area` excludes territory.**

**Then stop asking.** Take what you have. An assessment missing one dimension produces
a recommendation with a stated gap, which is a fine outcome; an assessment that asked
nine questions produces nothing, because the person left.

**Write the profile back to the person in three or four lines and let them correct
it** before the fan-out spends real work on it.

### Step 3 — Fan out, one subagent per carrier

**Threshold.** Two carriers or fewer: read the plan pages inline. More than two: fan
out, **one subagent per company folder**. One agent per carrier, however many plans that
carrier has. Never one agent per plan, never a fixed number of agents dividing the list.

**The brief.** Send each subagent this, with the profile substituted:

> You are the master of one health insurance carrier: `companies/<slug>/`. Read
> `companies/<slug>/company.md` and every file in `companies/<slug>/plans/`. Read
> `SCHEMA.md` at the wiki root first — § 2.4 on what `TBD` means, § 3.1 on what each
> section holds. **Read nothing outside your own company folder. Write nothing.**
>
> Here is the person's profile:
>
> ```
> Budget shape:   <answer>
> Expected use:   <answer>
> Network needs:  <answer>
> Covering:       <answer>
> Prescriptions:  <answer or "not asked">
> Plan type:      <answer or "not asked">
> Must-haves:     <answers or "none">
> Geography:      <answer or "not asked">
> ```
>
> Find **your carrier's best two or three matches** for that profile, and the one clear
> non-match, and return exactly this JSON:
>
> ```json
> {
>   "company": "<slug>",
>   "candidates": [
>     {
>       "plan_id": "<verbatim from the page frontmatter>",
>       "fit": "strong | plausible | poor",
>       "why": "<two or three sentences. Every claim anchored to a number or a sentence on that plan's page, and say which. 'The $750 deductible is the lowest in this carrier's PPO line, so a planned surgery hits the OOP max sooner' — not 'good for planned procedures'.>",
>       "against": "<the circumstance under which this is the wrong plan for THIS person, anchored the same way. Never empty for a plan you rate strong.>",
>       "blocking": "<a must-have this plan fails, verbatim from the profile, or empty string>",
>       "unknown": ["<frontmatter fields reading TBD that bear on THIS profile>"],
>       "confidence": "<the plan page's own confidence value, verbatim>"
>     }
>   ],
>   "carrier_note": "<one sentence on how this carrier as a whole fits this profile — network model, price position>",
>   "gaps": "<what you could not assess because your pages do not record it. Empty string if nothing.>"
> }
> ```
>
> Hard rules:
>
> - **Never state a cost figure that is not on the page.** The parent has the
>   frontmatter and will contradict you visibly.
> - **A `TBD` field goes in `unknown`. It never becomes a number.** Not from the tier,
>   not from a sibling plan, not from what such a plan usually costs. If a `TBD` field is
>   central to this profile, say so in `why` — "the specialist copay is unrecorded, so
>   the cost of the ongoing care this person described cannot be estimated from this
>   page" is a genuinely useful return.
> - **Never compare to another carrier.** You cannot see their pages. Rank within your
>   own folder only.
> - **Honour a must-have as a hard filter.** A plan failing one is returned with
>   `blocking` filled and `fit: "poor"`, not silently dropped — the parent needs to be
>   able to tell "no match" from "not examined".
> - **If your carrier has no plausible match, return an empty `candidates` array and say
>   why in `gaps`.** That is a real and useful answer. Do not promote a poor fit to fill
>   the slot.
> - **`plan_id` verbatim.** It is the join key.

**The barrier.** Collect every subagent result before ranking anything. Do not begin
Step 4 until every task has returned. A carrier missing from the merge is a carrier
silently excluded from the recommendation.

**A subagent that fails** is named in the report and its carrier is assessed by the
parent from the linter's frontmatter alone. Say which carrier got the thinner
treatment.

### Step 4 — Rank, with the arithmetic delegated

1. **Discard nothing silently.** Build one list of every candidate every subagent
   returned, plus every plan blocked by a must-have, marked as such.

2. **Get the annual cost numbers from the script**, not from your own addition. Take
   the top five or six candidates across all carriers and run:

   ```bash
   K="skills/hiw-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/hiw-compare"
   python3 "$K/scripts/build-comparison.py" --data output/_wiki-data.json \
     --plans "<id1>,<id2>,<id3>,<id4>,<id5>" \
     --out output/_query-shortlist.html \
     --json output/_query-shortlist.json
   ```

   **Read the totals out of `output/_query-shortlist.json`**, not out of the HTML. The
   json carries every scenario total, every ranking with its comparable/total counts, and
   the named missing inputs for anything uncomputable. Three scenarios — healthy year,
   moderate year, bad year — and which one governs comes straight from the profile's
   **Expected use** answer. A "very little" answer is decided by the healthy-year
   column; an "ongoing condition" answer is decided by the moderate and bad-year
   columns, and often the bad year is the only honest basis.

3. **A scenario reported as not computable stays not computable.** It means one of its
   inputs is `TBD`. Rank that plan on the scenarios that did compute, and say plainly
   that it could not be compared on the others.

4. **Apply the qualitative dimensions the arithmetic cannot see**, in this order,
   because a cheaper plan that fails a hard requirement is not cheaper:
   1. A must-have failure removes a plan from the recommendation. It stays in the
      report, named, with the requirement it failed.
   2. A network requirement the wiki cannot verify — "my doctor" — is a **stated
      unknown**, never an assumption. Say: "whether Dr. X is in the Tandem PPO network
      is not something this wiki records; check the carrier's provider directory before
      you decide."
   3. Referral and PCP rules against the plan-type answer.
   4. Formulary tier for a named drug, if the pages record it. Where they do not, say
      so — a brand-name drug on tier 4 rather than tier 2 can outweigh a $60/month
      premium difference, and that is exactly the kind of thing that decides a real
      choice.

5. **Rank on the governing scenario, then break ties on the thing the profile said
   mattered.** Say which scenario you ranked on and why. A ranking whose basis is
   unstated cannot be argued with, and this one should be arguable.

### Step 5 — Recommend

Structure, in this order. Prose, not a wall of tables — the tables are in the HTML.

1. **The recommendation, in two sentences**, naming the plan, its carrier, and the one
   number that decided it.
2. **Why, in three or four bullets**, each anchored to a number and its source page.
3. **When this is the wrong choice.** Not optional. The specific circumstance —
   "if you end up needing imaging, this plan's imaging copay is unrecorded and Blue
   Shield's Gold plan charges $75 for it."
4. **The runner-up, and what would make it the winner instead.** This is the most useful
   paragraph in the whole output, because it tells the person which of their own answers
   the decision was actually sensitive to.
5. **What could not be checked** — the unknowns, as a short list: `TBD` fields that
   bear on this profile, network membership the wiki does not record, subsidy
   eligibility, and anything blocked by a must-have.
6. **The three annual-cost scenarios for the shortlist**, as one compact table, read
   from `output/_query-shortlist.json` and with the assumptions printed. Link
   `output/_query-shortlist.html` for the full matrix.
7. **The caveat.** Verbatim in substance: this records what published sources say; it is
   not advice, not a quote, not an eligibility determination; premiums are list values
   and will differ once age, ZIP, tobacco use, household size and subsidy eligibility
   are applied; check the carrier's plan documents and provider directory before
   enrolling.

**Where nothing fits, say so.** "None of the 19 stored plans covers out-of-network care,
which you said was non-negotiable" is the correct answer, and it is more useful than the
least-bad plan presented as a recommendation.

### Step 6 — Offer to save it

Run **one AskUserQuestion call** — header `"Save"`, question `"Save this
recommendation to the wiki so you can come back to it and see what changes?"`, options
(exactly these three):
`["Save it — I'll want to revisit this", "Save it and keep the comparison HTML", "No, chat is enough"]`.
(multiSelect: false)

On save, write `synthesis/recommendation-<YYYY-MM-DD>-<slug>.md`:

```yaml
---
title: Recommendation — <short description of the need>
category: synthesis
plan_ids: ["<id1>", "<id2>", "<id3>"]
recommended: "<id1>"
profile: <one-line summary of the assessment>
governing_scenario: moderate
created: <YYYY-MM-DD>
last_updated: <YYYY-MM-DD>
updated_by: hiw-query
status: active
---
```

Body: the assessment answers verbatim, the recommendation, the reasoning, the
unknowns, the scenario table, and the caveat. **The assessment answers are the most
important thing on the page** — in six months, the recommendation is only interpretable
next to the need it answered.

**Nothing generated ever lands inside a company folder.** Company folders hold sourced
facts only.

Append to `log.md`:

```markdown
## [YYYY-MM-DD] hiw-query | <need summary> — recommended <plan_id>, <N> candidates from <M> carriers
```

---

## Files in this skill

No scripts of its own. It uses `lint-wiki.py` from `skills/hiw-lint/scripts/` for the
inventory and `build-comparison.py` from `skills/hiw-compare/scripts/` for the annual
cost arithmetic. Run both by path; never inline or rewrite either. **Do not add up a
premium, a deductible and four copays yourself** — that is what the script is for, and
an LLM doing money arithmetic is right most of the time, which is the problem.

---

## Anti-patterns

- Do not answer from general knowledge of the insurance market when the wiki is empty. An ungrounded recommendation delivered in this skill's voice will be read as a grounded one.
- Do not ask a question before reading the inventory. Asking "HMO or PPO?" of a wiki holding only HMOs wastes the person's one useful answer.
- Do not ask more than six questions, and do not spread them over more than two calls. An abandoned assessment produces no recommendation at all.
- Do not ask for a name, an address, a date of birth, a medical record, a member id, or an income figure. This skill produces a recommendation, not an application.
- Do not treat a `TBD` as zero, and do not fill it with a market-typical value so the ranking can proceed. Name it as unknown.
- Do not silently drop a plan whose cost fields are incomplete. A ranking that excluded the cheapest plan because its deductible was unrecorded is a wrong answer wearing the shape of a right one.
- Do not add up the annual cost yourself. Run the script with `--json` and read the file. Arithmetic on money belongs in code that can be read once and trusted thereafter.
- Do not scrape the totals out of the HTML. That is what `--json` is for, and two readers of one number means the second one drifting.
- Do not present a not-computable scenario as an estimate. It means an input is TBD; say which.
- Do not fan out by plan page, and do not fan out below the threshold.
- Do not let a subagent read another carrier's folder or make a cross-carrier claim. It cannot see the other pages.
- Do not begin ranking before every subagent has returned. A carrier missing from the merge is a carrier silently excluded from the recommendation.
- Do not accept a subagent's cost figure over the frontmatter. Keep the number, drop the claim, report the page.
- Do not promote a poor fit to fill a slot. An empty candidate list from a carrier is a real answer.
- Do not assert that a specific doctor is in a network. This wiki does not record provider directories. Say so and point at the carrier's.
- Do not recommend without naming the losing case. A recommendation with no downside is a sales pitch.
- Do not omit the runner-up and what would flip the decision. It is the paragraph that tells the person which of their own answers actually mattered.
- Do not present the least-bad plan as a recommendation when a hard requirement fails everything. "Nothing here covers out-of-network care" is the correct answer.
- Do not use "good coverage", "great value", "solid choice", or any adjective where a number belongs.
- Do not drop the caveat, shorten it to nothing, or move it somewhere the reader will not see it. No step removes it.
- Do not write a synthesis page into a company folder. Company folders hold sourced facts only.
- Do not save the recommendation without the assessment answers. In six months the recommendation is uninterpretable without the need it answered.
