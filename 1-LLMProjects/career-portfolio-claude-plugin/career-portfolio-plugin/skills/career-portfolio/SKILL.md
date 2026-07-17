---
name: career-portfolio
description: Orchestrator for producing tailored career-transition job-search documents from Career_Advice_* source files. Use this skill whenever the user wants to build, generate, or update any of their career documents — a master accomplishment inventory, a resume (Resume A non-technical or Resume B AI/tech-adjacent), or a work portfolio (Portfolio A events/guest-experience or Portfolio B AI/tech). Also trigger for vague requests like "help me build my job-search documents", "make my resume from the career advice files", "put together my portfolio", or "I want to start my career-change materials". This skill resolves the source folder, then routes to the correct document skill.
---

# Career Portfolio Builder — Orchestrator

This skill coordinates the production of five job-search documents for a career-changer, using the `Career_Advice_*` files as the source of truth for templates, tailoring rules, and candidate background:

1. **Master accomplishment inventory** → skill `accomplishment-inventory` (Markdown)
2. **Resume A** — non-technical events/guest-experience/community/fashion roles → skill `resume-a` (.docx + .pdf)
3. **Resume B** — AI/tech-adjacent events/community/education/programming roles → skill `resume-b` (.docx + .pdf)
4. **Portfolio A** — events, guest experience, community, fashion → skill `portfolio-a` (.pdf + .html)
5. **Portfolio B** — AI/tech events, community, education, conference programming → skill `portfolio-b` (.pdf + .html)

Your role is to run a short intake dialogue, then hand off to the right document skill(s). Do not produce the documents yourself here — the individual skills own their templates and tailoring rules.

## Step 1 — Resolve the source folder (ALWAYS do this first)

Every document is built from information in a source folder (the `Career_Advice_*` files plus any of the user's own background/data files). Before anything else, determine which folder to use by asking the user with the `AskUserQuestion` tool. Present exactly these three options:

- **"Current directory"** — the folder Claude is currently working in / the connected folder. Resolve this to the working directory or the user's selected folder.
- **"A different path"** — if chosen, in the **next step** ask the user to type the absolute path to the folder, then use it.
- **"Something else"** — if chosen, in the **next step** ask the user an open question ("How would you like to point me to your information?") and follow their free-form response (e.g., they may want to paste content directly, upload files, or name a connector location).

Phrase the question naturally, e.g.: *"Where is the folder with your Career_Advice files and background info?"* with those three options.

After you have a candidate folder, confirm it exists and list what is inside. Verify you can see at least one `Career_Advice_*` file. If the folder is missing or empty, tell the user plainly and re-ask rather than guessing.

## Step 2 — Load shared context

From the resolved folder, read the top-level `Career_Advice_*` files (do NOT recurse into subdirectories) to ground yourself in the candidate's background, positioning, salary guidance, target companies, and the "keep sales/PR out" boundaries. Also note any of the user's own data files (event stats, spreadsheets, notes) that could pre-fill document fields. Reading these lets you avoid asking the user for information the files already contain.

**Source precedence (important).** When files disagree, the newer/corrected guidance wins: `Career_Advice_New*` supersedes `Career_Advice_Old`. The Old file still lists public-relations and sales/sponsorship/quota roles that the New file *explicitly removed* — never reintroduce those role types or their framing, even though they appear in Old. If a brand-new `Career_Advice_*` file is present, treat the most recent guidance as authoritative and flag any genuine conflict to the user rather than silently merging.

## Step 3 — Choose the document(s) to produce

Ask the user which document(s) they want, using `AskUserQuestion` with `multiSelect: true`. Offer the five documents above. If the user hasn't yet built a master accomplishment inventory and wants a resume or portfolio, gently note that the inventory is the recommended first step (the source guidance treats it as the foundation the other documents draw from), but let them decide.

## Step 4 — Delegate

For each selected document, invoke the corresponding skill by name, in this recommended order when multiple are chosen: `accomplishment-inventory` → `resume-a` → `resume-b` → `portfolio-a` → `portfolio-b`. Pass along:

- the resolved source folder path,
- the output folder (default: a `generated_documents/` subfolder inside the source folder — create it if needed),
- any candidate facts you already gathered, so the sub-skill doesn't re-ask.

Each document skill runs its own tailoring dialogue and writes its output files. After each completes, briefly confirm what was produced and where.

## Guardrails carried through every document

These come straight from the source guidance and every downstream skill must honor them:

- **Never invent numbers or results.** If a metric was never measured, describe the scope/deliverable factually instead (e.g., "Created a centralized guest schedule covering 24 appearances across two event days").
- **Label honestly.** Keep "Volunteer" visible beside volunteer titles. Use the labels *Actual Work — Volunteer*, *Actual Work — Paid*, *Reconstructed and Redacted Work Sample*, *Independent Concept Proposal*, and *Illustrative Target — Not an Actual Result* consistently.
- **No sales or PR framing.** Exclude quota/pipeline/OTE/business-development language and public-relations/media-relations framing. Guest relations is an operational hospitality function, not PR.
- **Protect private information.** Never include private guest data, phone numbers, addresses, travel/hotel details, private messages, unpublished contracts, or client-confidential material.
- **Tailor, don't fabricate.** Adapt emphasis and ordering to the target role using each skill's tailoring rules; delete any sample bullet the user did not actually perform.
- **Reference copy is a sample, never verbatim output.** The templates, sample summaries, headlines, and case-study sentences in each skill's `reference.md` show structure and the kind of content expected — they are drafts to be reworded in the user's own voice, not text to print as-is. Always draft, show the user the wording, and revise to their preference before finalizing.

## Updating the plugin when source files change

If the user adds a new `Career_Advice_*` file to the folder and wants the skills refreshed, that is a separate, manually-invoked task — point them to (or invoke) the `update-career-skills` skill. This orchestrator does not auto-refresh templates.