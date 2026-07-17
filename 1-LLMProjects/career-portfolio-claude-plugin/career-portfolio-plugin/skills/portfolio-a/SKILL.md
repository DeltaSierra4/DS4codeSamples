---
name: portfolio-a
description: Produce Portfolio A — the 8–12 page work portfolio for events, guest experience, community, and fashion roles (Director of Guest Experience, Senior Event Operations/Community/Fan Engagement Manager, Experiential/Brand Experience Manager, Fashion Brand Education Manager, Global Events Program Manager). Use when the user wants a non-technical work portfolio, "build my events portfolio", "portfolio for a guest experience role", "case studies deck for fashion/community jobs", or picks Portfolio A. A clean business presentation of case studies, evidence, and metrics — not a résumé and not a photo album. Outputs .pdf and .html.
---

# Portfolio A — Events, Guest Experience, Community, and Fashion

Portfolio A shows **how** the candidate plans and delivers events, manages guests and communities, solves problems, and measures results — the evidence behind the résumé. It is an 8–12 page landscape (16:9) business presentation, understandable even if someone only reads the headings, captions, and metrics.

Read `reference.md` in this skill folder for the page layout rules, the default page-by-page structure, the five per-role customizations (A1–A5), the case-study rules, the honesty labels, and the include/do-not-include lists. Follow it closely.

## Workflow

1. **Resolve source folder + inventory.** If not provided by the `career-portfolio` orchestrator, resolve the source folder via the three-option dialogue (current directory / a different path / something else). Read `Master-Accomplishment-Inventory.md`, any `Career_Advice_*` files, and available photos/work samples (respect permission flags). If no inventory exists, offer to run `accomplishment-inventory` first. When `Career_Advice_*` files disagree, `Career_Advice_New*` supersedes `Career_Advice_Old`; never reintroduce the public-relations or sales/quota roles that the New guidance removed.

2. **Pick the target role and page order.** Ask which role this portfolio targets, then apply the matching A1–A5 customization from `reference.md` (cover text, page order, emphasis, and the extra artifact to add). If the user just wants the general version, use the default 8-page minimum-viable structure.

3. **Build case studies through dialogue.** For each case study (TouhouFest flagship, AMP community outreach, AniMarketPlace/other, proposed EGL experience, plus any role-specific artifact), walk the case-study question set in `reference.md`. Pre-fill from the inventory; ask the user for what's missing and for which approved photos/work samples to include. Treat the cover text, profile copy, titles, and all sample sentences in `reference.md` as **illustrative drafts, not final copy** — draft in the user's own voice, show them the wording, and revise to their preference before finalizing. Label every item (*Actual Work — Volunteer/Paid*, *Reconstructed and Redacted Work Sample*, *Independent Concept Proposal*, *Illustrative Target — Not an Actual Result*). Redact private information.

4. **Enforce honesty and privacy.** Never present concept proposals or targets as actual results. Never include private guest data, contracts, private messages, or unpermitted photos.

5. **Produce the files.** Build the portfolio as a clean, on-brand `.html` deck first — landscape 16:9 pages (use CSS `@page { size: 1280px 720px; margin: 0 }` and one `.page` per slide), one central point per page, headings/captions/metrics legible on their own. Follow **WCAG** basics: sufficient colour contrast, real heading structure, descriptive `alt` text on every image, and meaningful link text. Then render the **same HTML** to `Portfolio-A-[RoleShortName].pdf` with a headless browser so the PDF matches the deck exactly — e.g. `chromium --headless --no-sandbox --print-to-pdf=Portfolio-A-[RoleShortName].pdf --no-pdf-header-footer Portfolio-A-[RoleShortName].html` (or Playwright's `page.pdf({ landscape: true, printBackground: true })`). If no headless browser is available, fall back to the `pdf` skill and verify the result matches page-for-page. Keep the PDF tagged/selectable, not a flat image. Save both `.html` and `.pdf` to the output folder (default `generated_documents/`). Keep it 8–12 pages. Sanitize `[RoleShortName]` into a safe filename (letters, digits, hyphens).

6. **Verify.** Confirm both files exist and open, page count is 8–12, every project carries an honesty label, no private data appears, concepts/targets are clearly marked, and the PDF matches the HTML. Report what was produced and where.

## Output format

`.html` (styled landscape deck) **and** `.pdf` (export for applications). 8–12 pages. A business presentation, not a résumé and not a photo album.