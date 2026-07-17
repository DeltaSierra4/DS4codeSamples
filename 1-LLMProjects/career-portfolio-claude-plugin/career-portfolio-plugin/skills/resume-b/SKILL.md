---
name: resume-b
description: Produce Resume B — the AI/tech-adjacent résumé for AI community programs, technical conference/speaker programming, AI events program management, and AI education/learning-program roles. Use when the user wants a resume for an AI or tech-adjacent program/events/community/education job, "resume for an AI community programs manager role", "tech conference program manager resume", or picks Resume B. Keeps technical credibility but makes clear the next job is programs/people/education/events — not another engineering role. Tailors to a specific job posting when the user points to a folder containing the job description. Outputs .docx and .pdf.
---

# Resume B — AI/Tech-Adjacent Roles

Resume B keeps the candidate's AI credibility but signals a move toward **programs, people, education, and events — not another engineering job**. The central message: *"I understand AI well enough to work with technical speakers, customers, educators, and engineering teams — but my next job is about delivering excellent programs and experiences."* Do NOT let this become a standard engineering résumé stuffed with tools and no leadership evidence.

Read `reference.md` in this skill folder for the full master template, the "what it should not become" guidance, and the headline. Follow it and delete any sample bullet the user did not actually perform.

## Workflow

1. **Resolve source folder + inventory.** If not provided by the `career-portfolio` orchestrator, resolve the source folder via the three-option dialogue (current directory / a different path / something else). Read `Master-Accomplishment-Inventory.md` and any `Career_Advice_*` files. If no inventory exists, offer to run `accomplishment-inventory` first. When `Career_Advice_*` files disagree, `Career_Advice_New*` supersedes `Career_Advice_Old`; never reintroduce the public-relations or sales/quota roles that the New guidance removed.

2. **Identify the target role.** Ask which AI/tech-adjacent role this version targets (AI Community Programs Manager, Technical Conference/Speaker Programs Manager, AI Events Program Manager, AI Education/Learning Program Manager, Technical Community Operations Lead, or Global Events Manager at a tech company).

3. **Reference a specific job description (ask for its folder path).** Ask the user whether they have a specific job posting to tailor this résumé to. If yes, ask for the **path to the folder that contains the job-description file**, using the same three-option pattern as Step 1 (current directory / a different path / something else). Locate the posting in that folder — look for a `.txt`, `.md`, `.pdf`, or `.docx` file; if several plausible files exist, list them and ask which one (use the `pdf` or `docx` skill to extract text from those formats). Read it and pull out the role title, the must-have and nice-to-have requirements, the core responsibilities, and the exact keywords and phrasing the employer uses — these drive the tailoring in the next steps. If the user has no posting, skip this and tailor by target role alone. Never fabricate experience to match a posting — only surface and reorder what the inventory genuinely supports, mirroring the posting's language where it truthfully applies.

4. **Fill the template through dialogue.** Work section by section. Pre-fill every `[bracket]` from the inventory/folder, then ask only for gaps. Technical detail exists to establish credibility, not to dominate — keep the Selected Technical Competencies section tight. Never fabricate metrics. Treat the template's headline, professional summary, and bullet wording as **illustrative drafts, not final copy** — draft in the user's own voice, show them the wording (especially the summary and headline), and revise to their preference before finalizing. Nothing from `reference.md` should be printed verbatim just because it's there.

5. **Keep the balance right.** Technical experience stays, but framed around translation, coordination, stakeholder communication, program delivery, and enablement. The Community and Event Leadership section must remain prominent. When a job description was provided in Step 3, lead with the experience and keywords the posting prioritizes and mirror its terminology wherever it truthfully matches the candidate's background — without fabricating anything.

6. **Produce the files.** Read the `docx` skill and generate an ATS-friendly `Resume-B-[RoleShortName].docx`. Then create the `.pdf` **by converting that same .docx** so the two never diverge — e.g. `soffice --headless --convert-to pdf Resume-B-[RoleShortName].docx` (LibreOffice) in the sandbox. If LibreOffice is unavailable, fall back to the `pdf` skill but re-check that the PDF content matches the docx exactly. Save both to the output folder (default `generated_documents/`). Sanitize `[RoleShortName]` into a safe filename (letters, digits, hyphens).

7. **Verify.** Confirm both files exist, the headline matches the target role (and, when a posting was provided, that the résumé addresses its key requirements without any fabricated claims), the résumé does not read as an engineering CV (leadership/program evidence is front and center), volunteer labels are present, no unverifiable metric appears, and the .pdf matches the .docx. Report what was produced and where.

## Output format

`.docx` (ATS-friendly primary application file) **and** `.pdf` (for sharing).