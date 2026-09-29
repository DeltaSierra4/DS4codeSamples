---
description: One command from a prompt to a finished, narrated video. Asks what you want, which format, and whether it should speak, writes a plan for you to sign off, then builds it. Wraps /video-quick, /video-full and /add-sound so you do not have to run them yourself.
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "AskUserQuestion"]
---

# Command: /video-generate

## Purpose

Take a description and return a video that speaks. This is the front door.
`/video-quick` and `/video-full` still work standalone for anyone who already
knows which one they want; this command exists so nobody has to know.

It owns the conversation and delegates the building. It does not reimplement
either pipeline.

## Invocation

```
/video-generate [optional: a one-line brief]
```

## What this does

### 1. Ask what they want to make

If the invocation carried a brief, acknowledge it and go straight to the
follow-ups. Otherwise ask, in your own words, what they would like to make.

Then get to the point where you could write a script. Usually two things are
missing and both are worth one question each:

- **Who is watching.** A leadership audience wants the payoff, not the plumbing.
- **Roughly how long.** Ninety seconds is the house default and a good answer
  when they have no view.

Ask about the reference material here too, as part of the same exchange rather
than as a separate gate: is there a document, a path, a URL, or is the
description all there is? If they point at `input/`, read everything in it. If
they point at a path or URL, read that. If the description is all there is, say
so back to them plainly and carry on. Do not stall waiting for a document that
does not exist.

Stop asking once you could write the script. Three questions is plenty.

### 2. Ask which format

`AskUserQuestion`. Two options, and give them the real trade-off rather than the
file extensions:

| Option | Say this about it |
|---|---|
| Quick HTML video | One file that plays in any browser, around 57 KB. Better looking, because it is real CSS. Will not go into PowerPoint or onto LinkedIn. |
| Full mp4 | A real video file, 1920x1080. Goes anywhere a video goes. Frames are drawn with Pillow, so the design ceiling is lower. |

### 3. Ask about narration

`AskUserQuestion`. Three options:

| Option | Means |
|---|---|
| I have audio, here is the path | A file they supply. Ask the follow-up below. |
| Generate a narration | Synthesised through the Client GenAI gateway. Needs network and a key. |
| No sound | Silent, but still budget-exact. |

For **I have audio**, ask one more thing, because it changes the whole
downstream path: is it **one continuous take** covering the clip, or **one file
per scene**, already cut? Per-scene is rarer and much better, because it puts
each scene's speech on its own boundary by construction.

For **generate**, check for a key **now**, before writing anything:

```bash
python scripts/sound/keycheck.py --platform windows   # or macos, or linux
```

**`--platform` is the operating system of the person you are talking to**, not
the one this command runs on. They differ whenever this runs in a sandbox, and
then the steps below are for the wrong machine and cannot work. Omit the flag
only if you genuinely do not know.

Exit 0 means a key is there and you carry on without mentioning it. Exit 1 means
it is not, and the script has already printed the fix, correct for the operating
system you declared. **Print that message exactly as the script emitted it**,
then follow **When no key is set** in
`${CLAUDE_PLUGIN_ROOT}/reference/voice-setup.md`, which holds the pause, the
three ways out of it, the separate hand-off path for a sandbox, and the rule
that a key is never typed into the chat.

Discovering this after a full render wastes the run, which is why the check is
here and not at the mux.

`${CLAUDE_PLUGIN_ROOT}/reference/voice-setup.md` also has the voice list, the
budget rules and what each gateway error actually means.

Say once, plainly, that **narration text leaves the machine** and goes to
`your-ai-client.com`. On a client engagement the user should
know before it happens, not after.

### 4. Write the plan, then stop

Pick a short kebab-case `<name>` from the brief. Create `output/<name>/` and
write `output/<name>/plan.md`:

- One line on the audience and the point the video makes.
- The scene list. For each: number, title, the beat it carries, and its budget
  in seconds at roughly **2.2 words per second**.
- The total, which is the sum of the budgets.
- Chosen format and narration decision, stated back so a wrong answer is visible.
- Where the figures come from. Every number that will reach the screen traces to
  the source. Numbers the source flags as unattributed stay off the screen.

**Show it and wait.** Nothing renders until they approve. This is the whole
point of the command: the cheap thing to change is a plan, and the expensive
thing to change is a render.

If they ask for changes, edit `plan.md` and show it again. Do not start
building on a maybe.

### 5. Build

Read the command file for the chosen pipeline and follow its body from its
section 2 onward. **Skip its section 1, the gate** — its two questions are
already answered, and asking again is the exact failure this command exists to
prevent.

- Quick HTML → `commands/video-quick.md`
- Full mp4 → `commands/video-full.md`

Both write into `output/<name>/`. The mp4 lands at `output/<name>/<name>.mp4`,
the packed html at `output/<name>/<name>.html`.

Then take the narration branch:

| Format | Narration | What to run |
|---|---|---|
| mp4 | generate | `tts_narrate.py --project output/<name> --dry-run`, read the words per second, then the same without `--dry-run` plus `--install`. Re-run the clip's driver: it pads each take to its budget, concatenates, muxes and re-verifies. |
| mp4 | per-scene files | Rename to `audio/01.mp3 ... NN.mp3` in the clip folder, then re-run the driver. |
| mp4 | one continuous take | `scripts/sound/mux_mp4.py --video output/<name>/clip-silent.mp4 --audio <file> --out output/<name>/<name>.mp4`. Mux from the silent cut, never from an already-muxed file. |
| mp4 | none | Driver only. The track is silence padded to each budget, so narration drops in later without shifting a boundary. |
| HTML | generate | `tts_narrate.py --project output/<name> --aac --install`, then re-pack with `--audio output/<name>/narration.m4a` and re-run `check.mjs`. |
| HTML | one continuous take | Re-pack with `--audio <file>`, then `check.mjs`. |
| HTML | none | `pack.mjs` and `check.mjs` as `/video-quick` describes. |

Note the asymmetry, and do not try to smooth it out: the mp4 wants **one mp3 per
scene** because `build.py` pads each one to its own budget, while the html wants
**one continuous track** because once audio is audible it becomes the deck's
master clock. `tts_narrate.py` produces whichever shape the clip folder implies,
which is why the narration file goes in the clip folder rather than beside the
deck.

### 6. Report measured numbers

- **mp4** — from `output/<name>/verification.json`: `duration_measured_s` against
  `duration_budgeted_s`, `duration_error_s`, `all_boundaries_confirmed` with the
  count, and the boundary deltas against `intra_scene_control_delta_max`.
- **HTML** — `check.mjs` exit 0 and its own summary line, plus the file size.

**Never state a duration you worked out yourself.** State the one that was
measured.

Then tell them to open it, and say what to look for. Nothing in this pipeline
has ever confirmed audible playback or browser rendering, so thirty seconds of
their attention is the only thing that does. For the html: double-click it,
click the speaker to unmute, scrub the bar, press `f`.

## Rules

- **Do not skip the plan sign-off.** A render costs minutes and a plan costs
  seconds. The sign-off is the feature.
- **Do not reimplement the pipelines.** Read their command files and follow them.
  If something needs to change in how an mp4 is built, it changes in
  `video-full.md`, not here.
- **Do not ask the gate's questions again** in the delegated command. You already
  hold the answers.
- Never edit `scripts/mp4/build.py` or `scripts/html/src/player.js`.
- An over-budget take is an error, not a warning. Re-cut the copy or raise the
  budget in the narration file and let the scene follow.
- Write only into `output/` and `scripts/html/src/`. `input/` is read-only.
