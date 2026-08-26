---
name: ai-lib-query
description: >-
  Answer a question from the ai-lib document library — the Agentic RAG search. Fans out one
  subagent per leaf topic, each the master of its own topic, and each returning only claims
  that carry a provenance marker. Merges the returns into an answer where every sentence
  traces to a document and a page, names what the library does not cover, and flags an answer
  resting on one source or on vendor material alone. Use when the user asks a question about
  what they have read, says "what do I have on X", "what do these sources say about Y",
  "search my library", or runs /ai-lib-query.
allowed-tools: Read Write Edit Bash Glob Grep Task AskUserQuestion
metadata:
  argument-hint: "<a question in plain language; omit for interactive>"
---

# /ai-lib-query — A Question into an Attributed Answer

The retrieval half of the Agentic RAG system. Everything upstream of this skill exists to
make its answers traceable.

**One rule governs everything here: every sentence of the answer traces to a document and a
page.** Not "the library suggests" — `[llm-claude__claude-4-5-system-card, p. 5]`. An
untraceable sentence in an answer is worse than no answer, because the user cannot tell it
from a traceable one and will act on it either way.

**The second rule is about what you do not know.** This library holds a personal collection,
not the literature. An answer must say what it is missing: which leaf has nothing, which
claim rests on one source, which sources are all the vendor talking about itself. A confident
answer from a thin library is the failure mode this skill is built to avoid.

Ladders, applied inline in every command block:

```bash
L="skills/ai-lib-lint";    [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
K="skills/ai-lib-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-compare"
```

---

## STOP conditions — check these first

1. **No documents → say so and stop.** *"The library has no documents yet, so there is
   nothing to answer from. Run `/ai-lib-ingest` with a PDF."* **Do not answer from your own
   knowledge of the subject.** The entire point of this library is that the answer is
   grounded in what the user chose to keep, and an ungrounded answer delivered in this
   skill's voice will be read as a grounded one. (Step 1)

2. **Every claim in the answer carries its source.** `[doc_id, locator]`, inline, at the end
   of the sentence it supports. A sentence you cannot attribute does not go in the answer —
   it goes in the "what the library does not cover" section as a gap, or into your own
   commentary clearly marked as such. (Step 5)

3. **Never present your own knowledge as the library's.** Where you know something the
   library does not contain and it materially changes the answer, say it in a clearly
   separated closing paragraph headed as outside the library. Never woven into the attributed
   body. (Step 5)

4. **Never fabricate a locator, and never repair one.** If a subagent returns a claim with
   no marker, that claim does not enter the answer — and the fact that it exists is reported,
   because it is a defect in the page. (Step 4)

5. **A `[link: ...]` claim is not the document's claim.** Attribute it to the linked page, by
   URL, and say so. Depth-1 material is one hop from something the user chose to keep, and
   folding it into the document's voice erases that distinction. (Step 4)

6. **Collect every subagent result before answering.** A partial fan-out silently omits a
   topic, and the answer will look complete. (Step 3)

7. **Never let the answer outrun the evidence.** One document is one source; say so. Three
   first-party sources agreeing is three sources with the same interest; say so. A stale
   document is a document about a field that has moved; say so. (Step 5)

---

## RULES — read before acting

- **Answer the question that was asked.** A question about "what do I have on X" wants an
  inventory; "what do these say about X" wants a synthesis; "is X true" wants the claims and
  their disagreements, not a verdict. Read the question's shape before choosing the shape of
  the answer.
- **Retrieve by the ladder, and stop when the question is answered.** `index.md` answers most
  "what do I have" questions on its own. Going to Layer 4 for a Layer 1 question wastes
  context that a harder question later in the conversation will need.
- **Fan out by leaf topic, never by document.** More than two leaves in scope: one subagent
  per leaf. Two or fewer: read inline. The threshold is the same number in every skill in
  this family.
- **A subagent reads its own leaf and nothing else.** That bound is what makes the fan-out
  safe, and it means no subagent can answer a cross-topic question — that synthesis is the
  parent's job and must be done after every return is in.
- **Do not restate the contract; apply it.** `SCHEMA.md` § 7.1 defines the four markers;
  § 2.2 defines what `authority` means. The subagent brief cites them.
- **Ask at most one clarifying question, and only when the question is genuinely ambiguous
  about scope.** Most questions are answerable as asked, and a clarifying question is a turn
  the user did not want to spend.

---

## Procedure

### Step 1 — Read the inventory, and check whether it can answer

```bash
L="skills/ai-lib-lint"; [ -d "$L/scripts" ] || L="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-lint"
python3 "$L/scripts/lint-library.py" --library . --out output/_library-data.json
```

From `output/_library-data.json`, establish four things before spending any real work:

- **Which leaves hold documents**, and how many. A question about cybersecurity against a
  leaf with zero documents has one honest answer, and it is short.
- **How much is untraceable.** `counts.claims_unmarked` bounds how much of the library can
  be cited at all. Non-zero means some pages cannot be quoted from, and the answer must say
  so if it touches them.
- **How much is stale**, by leaf. For `llm/*` at a 270-day threshold this is often most of
  it, and it changes what the answer can claim about the present.
- **Whether the audits ran.** `CAP-NO-PLANS` or a non-zero `captures_unauthorized` means the
  provenance of some linked material is unverified.

**Say what you have, in one or two lines, before answering.** *"You have 23 documents across
`ai` and `llm/claude`, nothing in `cybersecurity`, and 6 of the 23 are past their staleness
threshold."* That sentence lets the user redirect before you spend a fan-out, and it is the
honest frame for whatever follows.

### Step 2 — Scope the question to leaves

1. **Map the question onto leaves.** Most questions touch one to three. "What do I have on
   prompt injection" touches `math-sci-tech-cyber/cybersecurity` and probably `ai`. "How does
   Claude's training differ from GPT's" touches `llm/claude` and `llm/gpt`, and probably `ai`
   for the shared method.

2. **Do not scope to the whole library by default.** Fourteen subagents for a question about
   one model is fourteen contexts to merge and thirteen of them empty.

3. **Where the scope is genuinely ambiguous**, run **one AskUserQuestion call** — header
   `"Scope"`, question `"This could mean a few things. Which are you after?"`, options: up to
   4 readings of the question, each naming the leaves it would search. (multiSelect: false)
   Ask only when the readings would produce materially different answers.

4. **State the leaves you are searching, and why**, in one line. A user who meant something
   else can stop you now.

### Step 3 — Fan out, one subagent per leaf

**Threshold.** Two leaves or fewer: read the pages inline. More than two: fan out, one
subagent per leaf in scope.

**The brief.** Send each subagent this, substituting the leaf and the question:

> You are the master of one topic in a document library: `topics/<leaf>/`. Read
> `topics/<leaf>/topic.md` and every file in `topics/<leaf>/documents/`. Read `SCHEMA.md` at
> the library root first — § 7.1 on the four provenance markers, § 2.2 on what `authority`
> means. **Read nothing outside your own leaf folder. Write nothing.**
>
> The question is: **<the user's question, verbatim>**
>
> Return exactly this JSON and nothing else:
>
> ```json
> {
>   "topic": "<leaf path>",
>   "documents_read": <count>,
>   "relevant": [
>     {
>       "doc_id": "<verbatim from the page frontmatter>",
>       "title": "<verbatim>",
>       "authority": "<verbatim>",
>       "published": "<verbatim, or empty>",
>       "stale": true,
>       "claims": [
>         {"text": "<the claim, close to the page's own wording>",
>          "marker": "<the marker verbatim, e.g. p. 15, Fig 7>",
>          "marker_kind": "loc|unloc|link|infer",
>          "type": "<the claim's [type:] value>",
>          "bears_on": "<one clause: how this answers the question>"}
>       ],
>       "evidence": [
>         {"benchmark": "...", "metric": "...", "reported": "...", "locator": "..."}
>       ]
>     }
>   ],
>   "themes": "<what this leaf collectively says about the question, citing at least two doc_ids, or empty>",
>   "gaps": "<what the question needs that this leaf does not contain>",
>   "defects": ["<any claim relevant to the question that carries NO marker — report it, do not use it>"]
> }
> ```
>
> Hard rules:
>
> - **A claim with no marker does not go in `claims`.** Put it in `defects` instead. It cannot
>   be cited, and the parent needs to know the page has a hole rather than receiving an
>   uncitable claim it might use anyway.
> - **`marker` and `doc_id` verbatim.** A retyped locator is a fabricated locator, and a
>   retyped `doc_id` silently drops the citation.
> - **`marker_kind: "link"` is not this document's claim.** It came from a page the document
>   linked to. Return it — it is often useful — but the kind must be accurate, because the
>   parent attributes the two differently.
> - **Do not answer the question.** Return the claims that bear on it. Synthesis across topics
>   is the parent's job and you cannot see the other leaves.
> - **Do not add what you know.** If your own knowledge of the subject contradicts a page,
>   that is not your finding to make here — return the page's claim as the page makes it.
> - **`gaps` is as valuable as `relevant`.** "This leaf has three documents on the topic and
>   all three are vendor announcements" is exactly what the parent needs to caveat the answer.

**The barrier.** Collect every result before composing anything. A leaf missing from the merge
is a topic silently excluded, and the answer will read as complete.

**A subagent that fails** is named in the report and its leaf is read by the parent from the
linter's inventory alone. Say which leaf got the thinner treatment.

### Step 4 — Merge, and check every citation

1. **Build one claim pool** from every return, tagged with its leaf, `doc_id`, marker,
   marker kind and authority.

2. **Drop every claim whose `doc_id` is not in `output/_library-data.json`.** It was
   reconstructed rather than copied. Say so — a subagent that retypes an id is a subagent
   whose other returns need a second look.

3. **Drop every claim with no marker**, and collect the `defects` arrays. Those are reported,
   not used.

4. **Separate the marker kinds.** A `loc` claim is the document's, located. An `unloc` claim
   is the document's, unlocated — usable, cited without a page, and worth flagging. A `link`
   claim belongs to a linked page and is attributed to the URL. An `infer` claim is a previous
   reader's conclusion and is attributed as such, never as the document's finding.

5. **Look for disagreement, and prefer it to consensus.** Two documents on the same subject
   saying different things is the most useful thing this library can produce. Where the
   disagreement is a benchmark number, get it deterministically rather than by eye:

   ```bash
   K="skills/ai-lib-compare"; [ -d "$K/scripts" ] || K="$CLAUDE_PLUGIN_ROOT/skills/ai-lib-compare"
   python3 "$K/scripts/build-compare.py" --data output/_library-data.json \
     --docs "<id1>,<id2>,<id3>" --out output/_query-compare.html \
     --json output/_query-compare.json
   ```

   Read the `disagreements` array from the json. It joins on the exact (benchmark, metric)
   pair and reports both numbers with both locators — which is the difference between "these
   sources disagree" and "these sources disagree: 153 vs 138 Elo on HH-RLHF harmlessness,
   p. 15 Fig 7 and p. 4 Table 2."

6. **Assess the evidence base**, and these four questions are what the caveats come from:
   - How many **distinct documents** support the core of the answer? One is one source.
   - What are their **authorities**? All `first-party` means every source has the same
     interest in the answer.
   - How **old** are they? A `llm/*` answer resting on 2024 material is a historical answer.
   - What is **missing**? Merge the `gaps` from every leaf.

### Step 5 — Answer

Structure, adapted to the question's shape. Prose, not a table dump.

1. **The answer, in two or three sentences**, with citations inline. If the honest answer is
   "the library does not say", that is the first sentence.
2. **The substance**, organized by what the question needs — by claim, by source, by
   disagreement, whichever carries the argument. **Every sentence carries
   `[doc_id, locator]`.**
3. **Where the sources disagree**, with both numbers and both locators. Do not adjudicate:
   name the difference and what would settle it.
4. **What kind of evidence this is.** One short paragraph, and it is not optional:
   how many documents, what authorities, how old, and what that means for how far the answer
   should be trusted.
5. **What the library does not cover** — the merged gaps, as a short list. This is what turns
   an answer into a reading list, and it is the section that stops a thin answer reading as a
   complete one.
6. **Optionally, and clearly separated: what you know that the library does not.** Under its
   own heading, marked as outside the library. Never woven into the attributed body.

**Attribution format**, used consistently:

- `[ai__constitutional-ai, p. 15]` — the document, located
- `[ai__constitutional-ai, unlocated]` — the document, page not pinned
- `[link: arxiv.org/abs/2204.05862, via ai__constitutional-ai]` — a page the document linked to
- `[inference recorded on ai__constitutional-ai]` — a previous reader's conclusion

**Where nothing answers the question, say so plainly and usefully.** *"Nothing in the library
addresses this. The closest is X, which covers the adjacent problem of Y
[`doc_id`, p. 3]. Two leaves that would hold this material — `cybersecurity` and
`data-science` — are empty."* That is a better answer than a synthesis of tangential material.

### Step 6 — Offer to save it

Run **one AskUserQuestion call**, but only where the answer took real work — a fan-out, or
three or more documents — header `"Save"`, question `"Save this answer to the library so you
can come back to it?"`, options (exactly these three):
`["Save it as a synthesis page", "Save it and keep the comparison HTML", "No, chat is enough"]`.
(multiSelect: false)

On save, write `synthesis/answer-<YYYY-MM-DD>-<slug>.md` per `SCHEMA.md` § 5.1:

```yaml
---
title: <the question, as a title>
category: synthesis
doc_ids: ["<every doc_id cited>"]
topics: ["<every leaf searched>"]
question: <the question verbatim>
created: <YYYY-MM-DD>
last_updated: <YYYY-MM-DD>
updated_by: ai-lib-query
status: active
---
```

Body: **the question verbatim** first, then the answer with every citation intact, the
evidence assessment, the gaps, and the standing caveat. § 5.1 requires the question and the
caveat; the question especially, because **a conclusion recorded without the question it
answered is uninterpretable six months later, which is exactly when someone reads it.**

**Nothing generated ever lands inside a topic folder.** Topic folders hold attributed claims
about documents only.

Append to `log.md`:

```markdown
## [2026-08-26] ai-lib-query | <question summary> — <N> leaves searched, <M> documents cited, <K> claims, <D> disagreement(s)
```

---

## Files in this skill

No scripts of its own. It uses `lint-library.py` from `skills/ai-lib-lint/scripts/` for the
inventory and `build-compare.py` from `skills/ai-lib-compare/scripts/` when a benchmark
disagreement needs settling deterministically. Run both by path; never inline or rewrite
either. **Do not compare two benchmark numbers by eye** — pass `--json` and read the
`disagreements` array, which joins on the exact (benchmark, metric) pair and will not
mistake a 5-shot result for a 0-shot one.

---

## Anti-patterns

- Do not answer from your own knowledge when the library is empty or thin. An ungrounded answer in this skill's voice reads as a grounded one.
- Do not write a sentence you cannot attribute. It goes in the gaps section, or into clearly separated commentary, or nowhere.
- Do not weave your own knowledge into the attributed body. Separate heading, marked as outside the library.
- Do not fabricate or repair a locator. A subagent's unmarked claim is a defect to report, not a claim to use.
- Do not attribute a `[link: ...]` claim to the document. It belongs to the page the document linked to, and folding it in erases the distinction the whole quarantine exists to preserve.
- Do not present an `[inference: ...]` as a finding. It is a previous reader's conclusion.
- Do not retype a `doc_id` or a locator. Verbatim, or the citation silently breaks.
- Do not accept a `doc_id` that is not in the linter's inventory. It was reconstructed, and it casts doubt on that subagent's other returns.
- Do not scope to all fourteen leaves by default. Thirteen empty contexts to merge is not thoroughness.
- Do not fan out by document, or below the threshold of two leaves.
- Do not let a subagent read another leaf, answer the question, or add what it knows.
- Do not begin composing before every subagent has returned. A missing leaf reads as a complete answer.
- Do not compare benchmark numbers by eye. Run the script and read the disagreements array.
- Do not smooth over a disagreement. Two documents saying different things is the most useful thing this library produces.
- Do not adjudicate a disagreement the library cannot settle. Name the difference and what would settle it.
- Do not omit the evidence assessment. One document is one source; three first-party sources are three sources with the same interest; a stale answer is a historical answer.
- Do not omit the gaps. They are what turn an answer into a reading list, and what stop a thin answer reading as complete.
- Do not present a synthesis of tangential material when nothing answers the question. Say nothing does, name the closest thing, and name the empty leaves.
- Do not go to Layer 4 for a Layer 1 question. `index.md` answers most inventory questions on its own.
- Do not ask a clarifying question when the question is answerable as asked.
- Do not save an answer without the question verbatim. A conclusion without its question is uninterpretable in six months.
- Do not write a synthesis page into a topic folder.
- Do not drop the caveat because the answer felt well-sourced.
