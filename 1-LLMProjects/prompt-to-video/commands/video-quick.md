---
description: Build a short animated explainer as a single self-contained HTML file that plays in any browser. Roughly 57 KB, no player, no codec, no network. Use when the deliverable will be screenshared, emailed, dropped in SharePoint, embedded in a page, or looped on a screen.
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "AskUserQuestion"]
---

# Command: /video-quick

## Purpose

Produce **one HTML file with the video playing inside it**, unattended, in about
eleven minutes. Around 57 KB for a 90 second piece, roughly a fiftieth the size
of the equivalent mp4, and it looks markedly better than `/video-full` because
it is real CSS rather than Pillow-drawn frames.

Inherited limit, and it is a hard one: **it is not an mp4.** It will not go into
a PowerPoint slide or onto LinkedIn. If the deliverable has to be a video file,
use `/video-full`.

## Invocation

```
/video-quick [optional: a one-line brief]
```

## The one idea

**Everything visible is a track on one timeline, and the player owns the clock.**

Nothing uses `setTimeout`, nothing uses a CSS `transition`. The player creates
every animation paused, then advances a single clock and seeks all of them
together. That is what makes the scrub bar work, what makes `?t=12.5` work, and
what lets audio take over as master clock without drift.

Read `${CLAUDE_PLUGIN_ROOT}/reference/html-authoring.md` before writing a deck.

## What this does

### 1. The gate

Read `${CLAUDE_PLUGIN_ROOT}/reference/gate.md` and follow it exactly, before
anything else.

**Unless you were called from `/video-generate`**, which has already asked these
questions and holds the answers. Asking them twice is the exact thing that
command exists to prevent. Start at section 2.

### 2. Node preflight

The three build commands in section 6 are Node scripts, so on a machine without
Node the run is already dead. Find out now rather than eleven minutes in, for
the same reason the gate checks the narration key up front:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/nodecheck.py
```

**Exit 0** prints a `NODE_EXE=` line. Keep it for section 6, say nothing about
Node, and carry on. Someone whose machine is set up correctly should never learn
this step exists.

That is also the entire environment branch. An environment that ships Node
resolves it on PATH and never reaches the next paragraph, which is why nothing
here looks for a sandbox, a container or a harness name.

**Exit 1** means stop and follow
`${CLAUDE_PLUGIN_ROOT}/reference/node-setup.md`, which holds the three ways out
and the two messages to print verbatim. Do not improvise the recovery, and do
not start drafting the deck while you wait for them.

`/video-full` has no equivalent step, because the mp4 pipeline needs no Node.

### 3. Read the reference material, then write the narration first

Even for a silent deck. Scene durations should be times a human could speak to,
because that is what makes a clip watchable rather than frantic. Budget at
roughly 2.2 words per second.

Write the script to `${CLAUDE_PLUGIN_ROOT}/output/<name>/narration-script.md`,
in the clip folder rather than beside the deck. `scripts/` is distributed and
must not carry engagement text, and `scripts/sound/tts_narrate.py` picks its
output shape from which narration file it finds in the clip folder.

The parser recognises exactly one table:

```markdown
| # | Cue | Scene | Line |
|---|---|---|---|
| 1 | 0:00.0 | Opening | Forty-seven contracts, and no index of what is in them. |
| 2 | 0:12.5 | The sweep | Claude goes contract by contract, pulling the clauses. |

Total runtime **90.00s**
```

`tts_narrate.py` matches a row with
`^\|\s*(\d+)\s*\|\s*(\d{1,2}):(\d{2}(?:\.\d+)?)\s*\|([^|]*)\|(.+)\|\s*$`.
Three things follow from that and each one silently breaks the track if you get
it wrong:

- **The cue is `mm:ss.s`.** `12.5` does not match. `0:12.5` does.
- **Cues come from the scene arithmetic below**, not from taste. One line may
  span several cues, but no cue may sit outside the timeline.
- **State the total**, in a table row or on a line opening with "Total". Without
  it the track length is guessed from the last line plus a second, and a track
  shorter than the timeline stretches the whole deck.

Every figure on screen traces to the source. Numbers the source flags as
unattributed stay off the screen.

### 4. Write the deck

Copy `${CLAUDE_PLUGIN_ROOT}/scripts/html/src/example-deck.html` as the starting
point, not `template.html`. The 60 second example exercises compute tracks,
additive composition, proportional bars and a staggered cascade, and it is the
worked example of every rule below. Write to `scripts/html/src/<name>.html`.

**Replace all of its copy.** It describes the plugin itself, which makes it safe
to ship but wrong for any real deliverable. Nothing from an engagement belongs
in `scripts/`; that folder is distributed.

Authoring needs **no build step**: the source deck loads `./player.js` from
beside it, so save and refresh is the whole loop.

Scene arithmetic, which the player enforces:

```
start[0]   = 0
start[i+1] = start[i] + dur[i] - overlap[i]
total      = sum(dur) - sum(overlap)
```

`dur` is a scene's own on-screen time, fades included. Consecutive scenes
cross-dissolve by `fade`, default 500ms. Eight scenes totalling 93.5s of scene
time with seven 500ms dissolves lands on 90.00s exactly. **Changing a `dur`
changes the total**, so re-derive the cue times in `narration-script.md` when
you retime.

### 5. Authoring rules, all six load-bearing

- **No CSS `transition`.** Transitions fire on property change in real time and
  cannot be seeked. The scrub bar would lie.
- **No `setTimeout`, `setInterval` or `requestAnimationFrame`** for anything
  visible. The player owns the clock.
- **Anything that is not a CSS property** (text, counters, canvas, SVG dash
  offsets) is a `compute` track: a pure function of progress.
- **No webfonts, no remote images.** The packed file must reach nothing.
- **Two tracks animating one property on one element:** mark the second
  `additive: true`, or it masks the first for the whole timeline. This is the
  one that costs people an hour.
- **No em dashes in visible copy.** Periods, commas, colons.

### 6. Pack and check

```bash
node build/test-player.mjs                                       # 77 checks, no browser
node build/pack.mjs src/<name>.html ../../output/<name>/<name>.html
node build/check.mjs ../../output/<name>/<name>.html             # exit 0 = safe to send
```

Run these from `${CLAUDE_PLUGIN_ROOT}/scripts/html/`. Section 2 already resolved
node and printed a `NODE_EXE=` line; **if it resolved anywhere other than PATH,
substitute that value, quoted, for the bare word `node` above.** Quoted because
the usual answer on Windows sits under `C:\Program Files\`, and an unquoted path
with a space in it fails in a way that looks like a broken script.

Node 18 or newer, and **no npm install** — the packer has zero
dependencies on purpose, because it has to run on the machine where
`npm install` is the thing that fails.

`pack.mjs` inlines the script, stylesheets, images and audio as data URLs.
`check.mjs` is the one that matters: it asserts there are no external references
at all, re-parses the packed config through the real schedule builder to prove
the timeline survived, and confirms the file will travel. **Exit 0 means the
file can be emailed, opened from a USB stick, or viewed on a plane with no
wifi.**

A remote URL is an error, not something `pack.mjs` will fetch for you. Download
the asset next to the deck and reference it locally.

### 7. Sound

If the gate's question 2 was answered anything but "No sound", hand off to
`/add-sound`. Do not reimplement it here. When `/video-generate` called you, it
owns that step and will run it itself.

### 8. Open it

The deck has never been verified in a browser by any automated check, because
there is no browser in the pipeline. Tell the user to double-click the file, and
say what to look for: playback, the scrub bar, `f` for fullscreen, `0` to
restart, and scale-to-fit at their window size. Thirty seconds, and it is the
only thing that confirms the visual result.

Controls: space plays and pauses, arrows scrub, `f` fullscreen, `m` mute, `0`
restart. URL parameters: `?autoplay=0`, `?loop=1`, `?controls=0`, `?embed=1`,
`?t=12.5`.

## Rules

- Never edit `scripts/html/src/player.js` or anything in `scripts/html/build/`.
- Never separate `scripts/html/src/` from `scripts/html/build/`. `check.mjs`
  resolves `../src/player.js` from its own location, and if that breaks its
  timeline check silently downgrades to a warning.
- Edit the source deck in `src/`, never the packed file in `output/`. The deck
  is the one piece of engagement content that has to live under `scripts/`,
  because it loads `./player.js` from beside it; `.gitignore` keeps it from
  being distributed.
- Write only into `output/` and `scripts/html/src/`. `input/` is read-only.
- Report `check.mjs`'s own output. Do not claim self-containment it did not
  confirm.
