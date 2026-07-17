 # Career Portfolio Builder — Plugin

A Claude plugin that turns the `Career_Advice_*` source files into an interactive, dialogue-driven document builder. It produces five tailored job-search documents for a career-changer moving from AI engineering into events / guest-experience / community / fashion / AI-program roles.

## What it builds

| Document | Skill | Output |
|---|---|---|
| Master accomplishment inventory | `accomplishment-inventory` | `.md` |
| Resume A — non-technical roles | `resume-a` | `.docx` + `.pdf` |
| Resume B — AI/tech-adjacent roles | `resume-b` | `.docx` + `.pdf` |
| Portfolio A — events / guest experience / community / fashion | `portfolio-a` | `.pdf` + `.html` |
| Portfolio B — AI/tech events / community / education / programming | `portfolio-b` | `.pdf` + `.html` |

## First: populate the templates (run once)

In the base plugin, each document's `reference.md` template ships **blank**. Before generating anything, run **`/career-update`** (the `update-career-skills` skill) once — it reads your top-level `Career_Advice_*` files and fills in the inventory, resume, and portfolio templates. Run it again whenever you add or change a `Career_Advice_*` file. If you start a document skill before this, it will tell you to run `/career-update` first.

## How to use it

After the templates are populated, run **`/career-portfolio`** (or just invoke the `career-portfolio` skill). It will:

1. Ask where your information lives, with three options — **current directory**, **a different path** (it then asks you for the path), or **something else** (it then asks how you'd like to point it to your info).
2. Read your top-level `Career_Advice_*` files and any of your own data to pre-fill what it can.
3. Ask which document(s) you want.
4. Hand off to the matching document skill, which runs a short tailoring dialogue and writes the files (default output: a `generated_documents/` subfolder).

### Commands

| Command | What it does |
|---|---|
| `/career-portfolio [doc]` | Orchestrator — resolves the folder, then routes to any document. |
| `/career-inventory` | Master accomplishment inventory (`.md`). |
| `/career-resume-a [role]` | Resume A — non-technical roles (`.docx` + `.pdf`). |
| `/career-resume-b [role]` | Resume B — AI/tech-adjacent roles (`.docx` + `.pdf`). |
| `/career-portfolio-a [role]` | Portfolio A — events/guest-experience/community/fashion (`.html` + `.pdf`). |
| `/career-portfolio-b [role]` | Portfolio B — AI/tech programs (`.html` + `.pdf`). |
| `/career-update` | **Run first.** Populates the blank templates from the `Career_Advice_*` files; also refreshes them after a source file changes. |

Each document skill can also be invoked directly by name; it will resolve the folder itself if needed.

### Sample copy is a draft, not verbatim

The templates, summaries, headlines, and case-study copy in each skill's `reference.md` are **illustrative structure, not final text**. The skills draft in your voice and confirm wording with you before finalizing — nothing is printed word-for-word from the reference.

## Setup and keeping it in sync

Templates and tailoring rules live in each skill's `reference.md`, which **ships blank** and is generated from the source files by the **`update-career-skills`** skill (`/career-update`). Run it once up front to populate the templates, and again whenever you add a new `Career_Advice_*` file (top level only) or change an existing one. This is deliberately manual — nothing auto-updates. When source files conflict, `Career_Advice_New*` supersedes `Career_Advice_Old`.

## Guardrails (enforced by every skill)

Never invent metrics; describe factual scope instead. Keep "Volunteer" labels visible. No sales/quota or public-relations framing. Protect private guest/community/client data. Label concepts and targets as such — never as actual results. **Source precedence:** `Career_Advice_New*` supersedes `Career_Advice_Old` — the removed public-relations and sales/quota roles are never reintroduced.

## Output fidelity

Resumes generate the `.docx` first, then produce the `.pdf` by converting that same file (LibreOffice) so the two never diverge. Portfolios build the `.html` deck first (landscape 16:9, WCAG-friendly contrast/headings/alt-text), then render that same HTML to `.pdf` with a headless browser so the PDF matches the deck page-for-page.

## Structure

```
career-portfolio-plugin/
├── .claude-plugin/plugin.json
├── README.md
├── commands/                     (slash commands: /career-portfolio, /career-resume-a, ...)
└── skills/
    ├── career-portfolio/         (orchestrator: folder dialogue + routing)
    ├── accomplishment-inventory/ (+ reference.md — blank until /career-update)
    ├── resume-a/                 (+ reference.md — blank until /career-update)
    ├── resume-b/                 (+ reference.md — blank until /career-update)
    ├── portfolio-a/              (+ reference.md — blank until /career-update)
    ├── portfolio-b/              (+ reference.md — blank until /career-update)
    └── update-career-skills/     (populates & refreshes the references from source files)
```