# ai-lib — Taxonomy

The authority on which topic paths exist. `/ai-lib-setup` copies this file to
`_config/taxonomy.md`; every skill reads that runtime copy, and `lint-library.py` validates
every document's `topic:` against it.

**A path not in the table below does not exist.** A document filed at an undefined path is
a lint error, not a new topic. Adding a topic is a deliberate edit to this file followed by
a `/ai-lib-lint` run — never a side effect of an ingest that met something unfamiliar.

---

## The tree

The block below is the machine-readable form. `lint-library.py` parses it and nothing else,
so keep the format exact: `path | node_type | expected_share`, one per line, `-` where a
share does not apply. Do not add columns, do not reorder within a parent, do not indent.

```taxonomy
ai                                  | leaf   | 0.35
llm                                 | branch | 0.35
llm/claude                          | leaf   | -
llm/gpt                             | leaf   | -
llm/gemini                          | leaf   | -
llm/grok                            | leaf   | -
llm/qwen                            | leaf   | -
llm/kimi                            | leaf   | -
llm/other-models                    | leaf   | -
data-science                        | leaf   | 0.15
math-sci-tech-cyber                 | branch | 0.10
math-sci-tech-cyber/math            | leaf   | -
math-sci-tech-cyber/science         | leaf   | -
math-sci-tech-cyber/technology      | leaf   | -
math-sci-tech-cyber/cybersecurity   | leaf   | -
misc                                | leaf   | 0.05
```

**Fourteen leaves.** They are the unit of parallelism: one subagent per leaf, and the tree
was shaped to that number rather than the other way round. `expected_share` is set on
top-level topics only and is a **weight for reporting drift, never a quota** — no skill
refuses an ingest because a topic is over its share.

---

## What belongs where

### `ai` — model-agnostic AI · expected ~35%

Techniques, theory and practice not tied to one model. Architectures and attention
variants, training and fine-tuning methods, RLHF/RLAIF and alignment, interpretability
and mechanistic analysis, agent design and tool use, evaluation methodology, scaling laws,
inference optimization, safety research, prompt engineering as a general discipline.

**The test:** would this document still be about something if you deleted every model name
from it? If yes, it is `ai`. A paper on RLHF that uses one model as its experimental
subject is `ai` — the method is the subject.

### `llm/<model>` — model-specific · expected ~35% across the seven leaves

Material *about a particular model or model family*: launch announcements, model and
system cards, capability and limitation write-ups, pricing and availability, prompting
guidance for that model, third-party evaluations of it, incident write-ups, deprecation
notices.

Expect this to be mostly blog posts and announcements rather than papers, and expect it to
go stale fastest of anything in the library.

| Leaf | Covers |
|---|---|
| `llm/claude` | Anthropic's Claude family |
| `llm/gpt` | OpenAI's GPT and o-series family |
| `llm/gemini` | Google's Gemini family, and Bard/PaLM as its predecessors |
| `llm/grok` | xAI's Grok family |
| `llm/qwen` | Alibaba's Qwen family |
| `llm/kimi` | Moonshot's Kimi family |
| `llm/other-models` | every other named model — Llama, Mistral, DeepSeek, Command, Phi, Nova, and any model whose family has no leaf of its own |

**`llm/other-models` is a real topic, not a dumping ground.** It holds model-specific
material for models without a dedicated leaf. It does *not* hold model-agnostic AI work —
that is `ai` — and a subagent mastering it should be able to say what it covers in a
sentence. When one family in it accumulates enough material to be worth its own leaf, add
the leaf deliberately and move the pages, logging the move.

**A document comparing several models** goes in the leaf of the model it is *primarily*
about, or `llm/other-models` where it is genuinely even-handed across many, with the others
in `related:` and `models:`. Do not duplicate it across leaves.

### `data-science` — expected ~15%

Statistics and inference, classical ML, feature engineering, data pipelines and
engineering, experiment and A/B design, causal inference, visualization, MLOps and
deployment practice, notebooks-to-production, dataset construction and quality.

The boundary with `ai`: `data-science` is the practice of getting value out of data;
`ai` is the study of the models. A post about serving a model at scale is
`data-science`; a post about the model's architecture is `ai`.

### `math-sci-tech-cyber` — expected ~10% across four leaves

Four distinct literatures sharing one parent because each is a minority interest here.

| Leaf | Covers |
|---|---|
| `math-sci-tech-cyber/math` | pure and applied mathematics, proofs, optimization theory, probability, linear algebra, numerical methods |
| `math-sci-tech-cyber/science` | physics, chemistry, biology, neuroscience, climate, medicine, and scientific method itself |
| `math-sci-tech-cyber/technology` | hardware, chips and accelerators, systems and infrastructure, networking, programming languages, developer tooling, standards |
| `math-sci-tech-cyber/cybersecurity` | vulnerabilities and exploits, threat intelligence, incident reports, cryptography, security architecture, privacy engineering, AI-specific security such as prompt injection and model extraction |

`cybersecurity` ages faster than its siblings and carries a shorter staleness threshold
(`SCHEMA.md` § 8.3) — a threat landscape write-up from three years ago describes a
different world.

**AI security sits in two places by design.** A prompt-injection *technique* is
`cybersecurity`; a specific model's *susceptibility* to it is that model's `llm/` leaf.
Cross-reference rather than duplicate.

### `misc` — expected ~5%

Real-life material that is none of the above and is still worth keeping: business and
economics, productivity and process, health, finance, law and policy that is not
tech-specific, hobbies, long-form journalism, reference material.

**`misc` is the smallest topic and should stay that way.** A `misc` page that would fit
one of the four topics above belongs there instead — the whole point of the taxonomy is
that a subagent assigned `ai` sees everything about AI. When a theme in `misc` accumulates
five or more documents, that is the signal to consider a new leaf.

---

## Adding, renaming and moving

**Adding a leaf.** Add its line to the block above, keeping it inside its parent's group;
where the new leaf's parent was previously a leaf, change the parent to `branch` and move
its documents down into an appropriate child. Run `/ai-lib-lint` afterwards: a branch that
still holds `documents/` is an error, and it is how a half-finished restructure gets
caught.

**Renaming a path is a breaking change.** Every `doc_id` under it changes, and every
`doc_id` cited in `synthesis/` and in `builds_on:` goes stale. Prefer adding an `aka` on
the topic page to renaming the path. Where a rename is genuinely necessary, do it in one
pass, rewrite every affected `doc_id`, and log the mapping.

**Moving a document between topics** is a normal correction, not a breaking change to
anything but that one `doc_id`: move the file, move its captures, move its `raw/`
original, update `doc_id` and `topic`, fix any `builds_on:` that referenced it, and log
the move with both paths. `/ai-lib-lint` will report the old `doc_id` as an orphaned
reference until you do.

**Never invent a path mid-ingest.** Where a document fits nothing, file it in the closest
leaf, say so plainly in the ingest report, and raise the taxonomy question separately.
A topic created in passing gets no `## What Belongs Here` written for it, and a leaf whose
boundary was never stated is a leaf whose subagent cannot do its job.
