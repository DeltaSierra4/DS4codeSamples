# video-gen: rules for working inside this plugin

These apply to every command and skill here. They are inherited from two shipped
Cornerstone clips and two proofs of concept, and each one is load-bearing.

## The folder contract

| Folder | Rule |
|---|---|
| `commands/` | One file per user-invoked entry point. Commands own their bodies. |
| `skills/` | Behavioural guidance Claude applies unprompted. Never user-invoked. |
| `scripts/` | The only place executable code lives. |
| `reference/` | Long-form docs a command points at. Not loaded by default. |
| `input/` | Read-only to this plugin. Read it, never write to it. |
| `output/` | The current deliverable set, and nothing else. |
| `output/archived/` | Written by `/refresh` and nothing else. |

`scripts/html/src/` and `scripts/html/build/` must stay siblings. `check.mjs`
resolves `../src/player.js` from its own location and silently downgrades its
timeline check to a warning if that path breaks.

## Narration drives timing, not the other way round

Write the script first, budget each scene in seconds, then build the visuals to
the budget. A designed animation has no natural duration, so if you build first
and narrate second you are stuck speaking faster or slower than is comfortable
to fit holds you invented arbitrarily. Both Cornerstone clips had to be re-timed
roughly 3x slower after review for exactly this reason.

**Pad every take with silence up to its budget before joining.** Then section
boundaries equal cumulative budgets equal animation holds, by construction, and
sync stops being an iterative hunt.

**A take that runs over its budget is an error, not a warning.** Padding can add
silence; it cannot shorten speech. Accepting one long take shifts every scene
after it. Either re-cut the take or raise the budget and the matching hold.

## Never edit the engines

`scripts/mp4/build.py` and `scripts/html/src/player.js` carry the guarantees
that got these two pipelines selected over the other two. Extend them the way
`scripts/mp4/templates/build_driver.py` does: import the module and rebind its
globals. Generate a `narration.md` and a driver script; do not fork the builder.

## Nothing from an engagement ships in this plugin

`scripts/`, `skills/`, `reference/` and the templates are distributed to other
people. Worked examples in them must be invented content, and the one that ships
describes the plugin itself for exactly that reason.

Client and deal material belongs in `input/` and `output/`, which travel with an
engagement and not with the plugin. When adding an example, do not reach for the
last real deck you built.

## House rules for anything that appears on screen

- **No em dashes in visible copy.** Periods, commas, colons.
- Budget at roughly 2.2 words per second. Above 2.5 will overrun.
- 1920x1080, 30fps for mp4. 1280x720 stage for HTML.
- Sentence case for body copy.
- Every figure on screen traces to the source document. If the source flags a
  number as unattributed, leave it out rather than repeating it.

## Verify, do not assert

Every claim about a finished video should come from a command that produced it:
`verification.json` for the mp4, `check.mjs` exit 0 for the HTML. Do not report
a duration you calculated. Report the one ffprobe measured.
