---
name: accomplishment-inventory
description: Build the master accomplishment inventory — the foundational record of every event, community, and professional accomplishment that all resumes and portfolios draw from. Use when the user wants to create, fill in, or update their accomplishment inventory, "log my events and results", "capture everything I've done for my resume", or start their career-transition documents. Produces a Markdown file. Usually the first document to build; the resume and portfolio skills reference it.
---

# Master Accomplishment Inventory

The inventory is the single source of truth the résumés and portfolios draw from. Its purpose is to capture, in one place and honestly, the scope and results of every role, event, community, and professional accomplishment — so later documents can be assembled and re-tailored without re-interviewing the user each time.

Read `reference.md` in this skill folder for the column set, honesty rules, and the output template before you build anything. Treat its template and any sample wording as **illustrative structure, not verbatim output** — the columns and honesty rules are what matter; adapt any phrasing to the user's voice and confirm before finalizing.

## Workflow

1. **Confirm the source folder and output location.** If invoked directly (not via the `career-portfolio` orchestrator), first resolve the source folder using the three-option dialogue described in the orchestrator skill (current directory / a different path / something else). Read any `Career_Advice_*` files and the user's own data files there to pre-fill what you can. When `Career_Advice_*` files disagree, `Career_Advice_New*` supersedes `Career_Advice_Old`. Default output location is `generated_documents/` inside the source folder.

2. **Pre-fill from what exists.** Scan the folder for event stats, spreadsheets, schedules, survey exports, social/Discord analytics, and notes. Populate every column you can from these before asking the user anything.

3. **Interview to fill gaps — one entry at a time.** For each role/event/community, walk through the columns in `reference.md`. Ask only for what you couldn't pre-fill. Keep questions grouped and light; use `AskUserQuestion` where a small set of choices fits, otherwise ask in plain text. Prompt the user to request historical data from AMP and TouhouFest (registration systems, schedules, surveys, Discord insights, social analytics, event reports) for anything unmeasured.

4. **Enforce honesty.** Never invent percentages or results. If a value was never measured, record the factual scope/deliverable instead (e.g., "Created a centralized guest schedule covering 24 appearances across two event days"). Mark each row's paid/volunteer status, whether photos/documents exist, whether there is permission to publish, and who can verify it.

5. **Write the Markdown file.** Follow the template in `reference.md`. Use one row per role/event in the main table, then an expandable notes block per entry for longer detail (problems solved, processes created). Save as `Master-Accomplishment-Inventory.md` in the output folder.

6. **Verify before finishing.** Re-read the file and confirm: every column is present, no fabricated metrics slipped in, volunteer rows are labeled, and unmeasured items are described as scope rather than as invented results. Then tell the user where the file is and what still needs data (flag empty cells they should chase down).

## Output format

Markdown only. The file must be easy to keep updating by hand, so prefer a clean table plus short per-entry note sections over dense prose.