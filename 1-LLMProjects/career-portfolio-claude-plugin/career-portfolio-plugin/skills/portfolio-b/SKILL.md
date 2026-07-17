---
name: portfolio-b
description: Produce Portfolio B — the 8–12 page work portfolio for AI/tech events, community, education, and conference programming roles (AI Events/Community Programs Manager, Technical Conference/Speaker Programs Manager, AI Learning/Education Program Manager, Technical Community Operations Lead). Use when the user wants an AI/tech-adjacent work portfolio, "build my AI programs portfolio", "portfolio for a technical conference programming role", "case studies for an AI community manager job", or picks Portfolio B. Shows technical fluency plus human-centered program delivery — NOT another engineering portfolio. Outputs .pdf and .html.
---

# Portfolio B — AI/Tech Events, Community, Education, and Programming

Portfolio B shows that the candidate's engineering background gives **technical credibility** while their desired function is events, community, learning, or programming. It does not position them for another engineering job. Same physical form as Portfolio A: 8–12 landscape (16:9) pages, one central point per page, legible from headings/captions/metrics alone. Do not fill pages with model architecture or code screenshots.

Read `reference.md` in this skill folder for the page-by-page structure, the four per-role customizations (B1–B4), the case-study content, the honesty labels, and the include/do-not-include lists. Follow it closely.

## Workflow

1. **Resolve source folder + inventory.** If not provided by the `career-portfolio` orchestrator, resolve the source folder via the three-option dialogue (current directory / a different path / something else). Read `Master-Accomplishment-Inventory.md`, any `Career_Advice_*` files, and available approved images/work samples. If no inventory exists, offer to run `accomplishment-inventory` first. When `Career_Advice_*` files disagree, `Career_Advice_New*` supersedes `Career_Advice_Old`; never reintroduce the public-relations or sales/quota roles that the New guidance removed.

2. **Pick the target role and page order.** Ask which role this portfolio targets, then apply the matching B1–B4 customization from `reference.md`. If the user wants the general version, use the default 8-page minimum-viable structure.

3. **Build case studies through dialogue.** Walk the content in `reference.md` for each page/case study (interdisciplinary profile; value-you-bring table; AI project/stakeholder case; technical translation sample; guest/speaker operations reframed from TouhouFest; community leadership; proposed Responsible-AI roadshow; technical program toolkit). Pre-fill from the inventory; ask for gaps. Treat the cover text, profile copy, tables, titles, and all sample sentences in `reference.md` as **illustrative drafts, not final copy** — draft in the user's own voice, show them the wording, and revise to their preference before finalizing. Reframe fandom guest-relations as transferable to technical speaker programs WITHOUT implying fandom guests were conference speakers. Never include client-confidential AI information, proprietary data, model outputs, or employer/client source code.

4. **Enforce honesty and privacy.** Label concepts and targets clearly (*Independent Concept Proposal — Not Yet Produced*, *Illustrative Target — Not an Actual Result*). Redact private and confidential material.

5. **Produce the files.** Build the portfolio as a clean, on-brand `.html` deck first — landscape 16:9 pages (use CSS `@page { size: 1280px 720px; margin: 0 }` and one `.page` per slide). Follow **WCAG** basics: sufficient colour contrast, real heading structure, descriptive `alt` text on every image, and meaningful link text. Then render the **same HTML** to `Portfolio-B-[RoleShortName].pdf` with a headless browser so the PDF matches the deck exactly — e.g. `chromium --headless --no-sandbox --print-to-pdf=Portfolio-B-[RoleShortName].pdf --no-pdf-header-footer Portfolio-B-[RoleShortName].html` (or Playwright's `page.pdf({ landscape: true, printBackground: true })`). If no headless browser is available, fall back to the `pdf` skill and verify the result matches page-for-page. Keep the PDF tagged/selectable, not a flat image. Save both `.html` and `.pdf` to the output folder (default `generated_documents/`). Keep it 8–12 pages. Sanitize `[RoleShortName]` into a safe filename (letters, digits, hyphens).

6. **Verify.** Confirm both files exist and open, page count is 8–12, the deck reads as a program/events portfolio (not an engineering one), every project carries an honesty label, no confidential/private data appears, and the PDF matches the HTML. Report what was produced and where.

## Output format

`.html` (styled landscape deck) **and** `.pdf` (export for applications). 8–12 pages.