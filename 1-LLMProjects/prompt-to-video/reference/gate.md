# The gate

Every `/video-quick` and `/video-full` run opens the same way. Read this file at
the start of either command and follow it exactly. It exists in one place so the
branch behaviour cannot drift between the two pipelines.

Ask both questions in a **single `AskUserQuestion` call**, before any other work:
no reading `input/`, no exploring, no drafting. The point of a gate is that it
comes first.

**`/video-generate` is the exception.** It asks its own questions, in its own
order, and then calls one of these two commands holding the answers. When you
were called that way, skip this file entirely. Asking a user the same question
twice is worse than not asking at all.

## Question 1 — Where are the reference materials?

| Option | Label | Meaning |
|---|---|---|
| 1 | In the `input/` folder | Read everything in `${CLAUDE_PLUGIN_ROOT}/input/` |
| 2 | Somewhere else, I will give you a path | A file path or a URL, typed into the free-text box |
| 3 | I will just describe it | No document exists yet |

## Question 2 — Do you want sound with the video?

| Option | Label | Meaning |
|---|---|---|
| 1 | Yes, my recording is in `input/` | An audio file, or a Teams `.mp4` to extract audio from |
| 2 | Yes, my recording is elsewhere | Path typed into the free-text box |
| 3 | Yes, generate a narration | Synthesised through the Client GenAI gateway. Needs network and a key |
| 4 | No sound | The clip is silent, but still budget-exact |

Question 2 exists at the gate rather than at the end because **the answer
changes the script**, not just the final mux. A clip that will carry narration
needs per-scene budgets a human can actually speak to; a silent clip does not.
Asking afterwards means rewriting the timing.

## The one branch

If the user picks **option 3 on question 1**, reply with exactly this line and
nothing else, then stop and wait:

> Please describe what you would like to make for the video.

No preamble, no suggestions, no follow-up questions in the same turn. They will
describe it, and the run continues from there.

Every other combination proceeds straight into the pipeline.

## What the answers set up

- **Q1 option 1 or 2** — read the material before writing a line of narration.
  Every figure that ends up on screen must trace to it. If the source flags a
  number as unattributed or uncorroborated, leave it out rather than repeating
  it.
- **Q2 options 1, 2 or 3** — write the narration to speakable budgets, then hand
  off to `/add-sound` once the silent cut exists. Do not reimplement `/add-sound`
  inside the video command.
- **Q2 option 3** — check for a key **now**, at the gate, not eleven minutes
  later at the mux:

  ```bash
  python scripts/sound/keycheck.py --platform windows   # or macos, or linux
  ```

  **`--platform` is the operating system of the person you are talking to**, not
  the one this command runs on. The two differ whenever the command runs in a
  sandbox, and then the four steps below are wrong and unfollowable. Omit the
  flag only if you genuinely do not know.

  Exit 0 and you carry on. Exit 1 and the script has printed the fix, correct
  for the operating system you declared. Print that message verbatim, then
  follow **When no key is set** in
  `${CLAUDE_PLUGIN_ROOT}/reference/voice-setup.md`, which holds the pause, the
  three ways out of it, and the separate hand-off path for a sandbox.
  Discovering the key is missing after a full render wastes the whole run.
- **Q2 option 4** — still budget every scene. The silent track is padded silence
  at exactly the budgets, which is what lets narration be dropped in later
  without shifting a single scene boundary.
