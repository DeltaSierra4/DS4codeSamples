---
name: resume-a
description: Produce Resume A — the non-technical résumé for guest-experience, event-operations, community/fan-engagement, experiential/brand-event, fashion brand-education, and global-events-program roles. Use when the user wants a resume for a non-technical events/community/fashion job, "make my events resume", "resume for a guest experience director role", "tailor my resume for a fan engagement manager job", or picks Resume A. Leads with Event and Community Leadership, keeps AI experience as transferable support. Tailors to a specific job posting when the user points to a folder containing the job description. Outputs .docx and .pdf.
---

# Resume A — Non-Technical Roles

Resume A positions the candidate as a **guest-relations and community-events leader**, not "an AI engineer who wants to try events." Event and Community Leadership comes first; the AI consulting role stays on the résumé but is described in transferable terms (client management, program delivery, executive presentations, cross-functional coordination, process improvement, analytical decision-making).

Read `reference.md` in this skill folder for the full master template, the per-role tailoring rules, and the headline. It is the authority for structure and wording — follow it, and delete any sample bullet the user did not actually perform.

## Workflow

1. **Resolve source folder + inventory.** If not already provided by the `career-portfolio` orchestrator, resolve the source folder via the three-option dialogue (current directory / a different path / something else). Read the `Master-Accomplishment-Inventory.md` if present, plus any `Career_Advice_*` files, to pull facts. If no inventory exists, offer to run the `accomplishment-inventory` skill first — the résumé is only as strong as the evidence behind it. When `Career_Advice_*` files disagree, `Career_Advice_New*` supersedes `Career_Advice_Old`; never reintroduce the public-relations or sales/quota roles that the New guidance removed.

2. **Identify the target role.** Ask which target role this version is for (Director of Guest Experience, Senior Event Operations Manager, Senior Community/Fan Engagement Manager, Experiential/Brand Experience Manager, Fashion Brand Education Manager, or Global Events Program Manager). The target selects which tailoring block in `reference.md` to apply.

3. **Reference a specific job description (ask for its folder path).** Ask the user whether they have a specific job posting to tailor this résumé to. If yes, ask for the **path to the folder that contains the job-description file**, using the same three-option pattern as Step 1 (current directory / a different path / something else). Locate the posting in that folder — look for a `.txt`, `.md`, `.pdf`, or `.docx` file; if several plausible files exist, list them and ask which one (use the `pdf` or `docx` skill to extract text from those formats). Read it and pull out the role title, the must-have and nice-to-have requirements, the core responsibilities, and the exact keywords and phrasing the employer uses — these drive the tailoring in the next steps. If the user has no posting, skip this and tailor by target role alone. Never fabricate experience to match a posting — only surface and reorder what the inventory genuinely supports, mirroring the posting's language where it truthfully applies.

4. **Fill the template through dialogue.** Work section by section through the Resume A template. Fill every `[bracket]` from the inventory/folder first, then ask the user only for what's missing. Use `AskUserQuestion` for bounded choices (e.g., which capabilities to foreground). Never fabricate metrics — use factual scope where a number wasn't measured. Treat the template's headline, professional summary, and bullet wording as **illustrative drafts, not final copy** — draft in the user's own voice, show them the wording (especially the summary and headline), and revise to their preference before finalizing. Nothing from `reference.md` should be printed verbatim just because it's there.

5. **Apply the tailoring rules.** Reorder Core Capabilities and bullets, and adjust the headline/summary emphasis, according to the matching per-role block in `reference.md` **and the job description from Step 3 when one was provided** — lead with the experience and keywords the posting prioritizes, and mirror its terminology wherever it truthfully matches the candidate's background. Keep "Volunteer" visible beside the two director titles.

6. **Produce the files.** First read the `docx` skill and generate a clean, ATS-friendly `Resume-A-[RoleShortName].docx` (standard headings, simple formatting, no tables/columns that break parsers). Then create the `.pdf` **by converting that same .docx** so the two never diverge — e.g. `soffice --headless --convert-to pdf Resume-A-[RoleShortName].docx` (LibreOffice) in the sandbox. If LibreOffice is unavailable, fall back to the `pdf` skill but re-check that the PDF content matches the docx exactly. Save both to the output folder (default `generated_documents/`). Sanitize `[RoleShortName]` into a safe filename (letters, digits, hyphens).

7. **Verify.** Confirm both files exist, the headline matches the target role (and, when a posting was provided, that the résumé addresses its key requirements without any fabricated claims), volunteer labels are present, no unverifiable metric appears, and the .pdf visually matches the .docx. Report what was produced and where.

## Output format

`.docx` (ATS-friendly, the primary application file) **and** `.pdf` (for sharing). Keep the résumé visually simple — visuals belong in the portfolio, not here.