 ---
name: update-career-skills
description: Populate or refresh the career-portfolio plugin's document templates from the Career_Advice_* source files. This is the REQUIRED first step — in the base plugin the resume and portfolio (and inventory) reference.md files ship blank, and this skill fills them in from the source files. Use it before generating any document, and again whenever a Career_Advice_* file is added or changed. Trigger on "set up the career skills", "populate the templates", "I added a new Career_Advice file, update the skills", "regenerate the career references", or "/career-update".
---

# Update Career Skills

This skill builds (first run) or refreshes (later runs) the bundled `reference.md` templates for the career-portfolio document skills, deriving them from the `Career_Advice_*` source files. In the base plugin every document `reference.md` ships **blank** — so this skill must be run **before** the inventory, resume, or portfolio skills can produce anything. Run it again whenever the source files change.

It is intentionally manual: run it only when the user asks, or when a document skill reports its reference is still blank.

## When to run

- **First-time setup (populate).** The five document `reference.md` files are blank stubs → run this to generate them from the source files.
- **Maintenance (refresh).** A `Career_Advice_*` file was added or edited → run this to update the affected references.

## Two rules that always apply

- **Top level only.** Consider only `Career_Advice_*` files at the **top level** of the source folder. Do NOT recurse into subdirectories — files inside subfolders are out of scope by design.
- **Source precedence.** When files disagree, newer/corrected guidance wins: `Career_Advice_New*` supersedes `Career_Advice_Old`. The Old file still contains public-relations and sales/sponsorship/quota roles that New removed — never re-derive those into any `reference.md`. Treat Old only as historical context.

## Workflow

1. **Resolve the source folder.** Use the same three-option dialogue as the orchestrator (current directory / a different path / something else). Confirm the folder and list its top-level contents.

2. **Locate the plugin.** Find the `career-portfolio-plugin` directory (its `.claude-plugin/plugin.json` identifies it). Ask the user to confirm the path if it isn't obvious.

3. **Read every top-level `Career_Advice_*` file** fully (e.g. `Career_Advice_Old.txt`, `Career_Advice_New.txt`, `Career_Advice_New_resume.txt`, `Career_Advice_New_portfolio.txt`, plus any newly added ones), applying the precedence rule above.

4. **Determine mode per reference.** For each document skill's `reference.md`: if it is empty or only the "populated by update-career-skills" stub → **POPULATE** (generate from scratch). If it already has real content → **UPDATE** (diff against the source and modify only what changed). Tell the user which references you'll populate vs. update.

5. **Generate / update each reference** using the source-to-reference mapping and the required structure below. Extract templates and structures faithfully from the source (the source files literally contain the resume text templates, portfolio page structures, and inventory columns).

6. **Summarize and confirm.** Before writing large changes, show the user a short summary of what will be populated/changed in which skill. After writing, list every file updated and note anything needing a human decision (e.g. a new document type).

## Source → reference mapping

Generate each reference from these sources (respecting precedence — prefer `Career_Advice_New*`):

- `accomplishment-inventory/reference.md` ← `Career_Advice_New_resume.txt`, "Create your accomplishment inventory": the column set, honesty rules, metrics families, and the Markdown output template.
- `resume-a/reference.md` ← `Career_Advice_New_resume.txt`, "Resume A: Nontechnical positions": the headline, the full master résumé template (verbatim text block), and the per-role tailoring rules (guest-experience, community, experiential/brand-event, fashion brand-education) plus universal rules.
- `resume-b/reference.md` ← `Career_Advice_New_resume.txt`, "Resume B: AI/Tech-adjacent positions": the headline/label, the full master résumé template, and the "What Resume B should not become" guidance plus universal rules.
- `portfolio-a/reference.md` ← `Career_Advice_New_portfolio.txt` (Portfolio A sections) and the portfolio case studies in `Career_Advice_New_resume.txt`: page-layout rules, default cover, the minimum-viable page structure, case-study rules, the five per-role customizations (A1–A5), testimonials/closing, and the include / do-not-include lists.
- `portfolio-b/reference.md` ← `Career_Advice_New_portfolio.txt` (Portfolio B sections): page-layout rules, default cover, the minimum-viable page structure, key page content, the four per-role customizations (B1–B4), testimonials/closing, and the include / do-not-include lists.

If the newest guidance changes titles, roles, salary/positioning, company lists, or templates, reflect those changes. If it removes something, remove it from the reference too (don't silently keep stale content).

## Required structure for every generated reference.md

Each populated reference must contain, in this order:

1. A `# <Document> — Template & …` H1 heading.
2. A `> Source:` citation line naming the exact source file(s) and section(s) used.
3. A `## How to use this reference (read first)` note stating that the templates, sample summaries, headlines, and case-study copy are **illustrative structure, not verbatim output** — drafts to reword in the user's own voice, with the structure, honesty labels, and the user's real data being what stays stable. This framing must always be present.
4. The extracted **template / structure** itself, kept faithful to the source: the résumé text templates (in a fenced code block), the portfolio page-by-page structure and per-role customizations, or the inventory columns + Markdown output template.
5. The **tailoring rules / per-role customizations** (Resume A per-role blocks; Portfolio A1–A5; Portfolio B1–B4).
6. For portfolios: the **honesty labels** (Actual Work — Volunteer/Paid, Reconstructed and Redacted Work Sample, Independent Concept Proposal, Illustrative Target — Not an Actual Result) and the **include / do-not-include** lists.

Keep `[bracket]` placeholders from the source intact — they mark where the user's real data goes. Never invent numbers or reintroduce removed PR/sales roles.

## Handling brand-new content

If a new `Career_Advice_*` file introduces:

- **a new template or document type** → propose adding a new document skill (a new folder under `skills/` with its own `SKILL.md` + blank `reference.md` stub), then populate it. If it should be routed, add it to the `career-portfolio` orchestrator's document list and delegation order, and consider a matching `commands/career-<name>.md`.
- **new tailoring rules, roles, salary/positioning guidance, or company lists** → update the affected `reference.md` (and the orchestrator's shared guardrails if the boundaries changed).
- **changes to existing templates** → update the corresponding `reference.md` sections.

## Note on the running session

Editing these plugin files updates the plugin **deliverable** in the folder. If the plugin is already installed into the user's Claude profile, they may need to reinstall/refresh it (Settings → Capabilities, or reinstall from the source folder in the CLI) for the newly populated references to take effect in a live session. Mention this when finishing.