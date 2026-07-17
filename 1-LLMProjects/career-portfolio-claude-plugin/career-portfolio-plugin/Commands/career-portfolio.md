---
description: Start the Career Portfolio Builder — resolve your source folder, then build a tailored inventory, resume, or portfolio.
argument-hint: [optional: which document, e.g. "resume A" or "portfolio B"]
---

Invoke the `career-portfolio` skill and begin its workflow now.

Follow the skill exactly:
1. First run the folder-path dialogue with the three options (current directory / a different path / something else).
2. Load context from the top-level `Career_Advice_*` files.
3. Ask which document(s) to build, then delegate to the matching document skill.

If the user provided an argument after the command ("$ARGUMENTS"), treat it as their preliminary answer to "which document(s)" — but still run the folder-path dialogue first, since every document needs a resolved source folder.

Remember: the sample copy in any skill's `reference.md` is an illustrative starting draft, not verbatim output. Draft in the user's own voice and confirm wording with them before finalizing.