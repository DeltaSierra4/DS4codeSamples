---
description: Clear the workspace between video runs. Empties input/ and sweeps output/ into output/archived/.
allowed-tools: ["Read", "Glob", "Bash", "AskUserQuestion"]
---

# Command: /refresh

## Purpose

Housekeeping between takes. Reference material from the last run is the most
common cause of a video that quietly borrows from the wrong deal, so clearing it
is not optional tidiness.

## Invocation

```
/refresh
```

## What this does

1. **List what is about to change, before changing anything.** Glob
   `${CLAUDE_PLUGIN_ROOT}/input/**` and `${CLAUDE_PLUGIN_ROOT}/output/*`
   (excluding `output/archived/`). Print both lists with file sizes.

2. **If both are already empty, stop and say so.** Do not create an empty
   archive folder.

3. **Confirm with `AskUserQuestion`** before touching anything, showing the
   counts:
   - *Archive outputs and clear inputs* — the normal path.
   - *Archive outputs only* — keep the reference material for another take.
   - *Cancel*.

   Deleting someone's reference files without showing them the list first is the
   one way this command can do real damage. Always show, always ask.

4. **Sweep `output/`.** Create `${CLAUDE_PLUGIN_ROOT}/output/archived/<UTC
   timestamp>/` as `YYYY-MM-DD-HHMM`, and move every file and folder sitting
   directly in `output/` into it. `output/archived/` itself never moves.

5. **Clear `input/`.** Delete its contents, keeping the folder.

6. **Report what moved and what was deleted**, by name. Never summarise this as
   "cleaned up" — say which files went where, so a mistake is visible
   immediately.

## Rules

- Write to `output/archived/` and delete from `input/`. Nothing else, ever.
- Never delete from `output/`. Archiving is a move, so a mistake is recoverable.
- Never touch `scripts/`, `reference/`, `skills/` or `commands/`.
- If a move fails because a file is open in another program, say which file and
  stop. Do not partially sweep and report success.
