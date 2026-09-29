---
name: narration-budgets
description: Use when writing, timing or re-timing narration for a video in this plugin - writing narration.md, setting per-scene time budgets, deciding scene holds, judging whether a script will overrun, or diagnosing audio that drifts out of sync with the picture. Applies to both the mp4 and HTML pipelines. Do NOT use for general copywriting with no timing dimension.
---

# Narration budgets

The method that makes audio and video line up. It is inherited from two shipped
Cornerstone clips, and every part of it was learned by getting it wrong first.

## Write the narration before the animation

This sounds backwards. It is the opposite of how you would shoot a video. It is
also the single decision that most shapes everything downstream.

A designed animation has **no natural duration**. Every beat is a hold you
typed. So if you build the animation first and write narration second, you are
stuck trying to speak faster or slower than is comfortable to fit holds you
invented arbitrarily.

Both Cornerstone clips were built animation-first and had to be re-timed
afterwards, roughly 3x slower:

| Clip | First cut | After re-timing to the narration |
|---|---|---|
| Cowork | 0:33 | 1:47 |
| Integration | 0:59 | 2:24 |

The reviewer's note on both was the same: *"everything just needs to move a lot
slower... the visuals are just moving way too fast."* And critically, not *"add
more content"* — the fix was entirely in the hold durations.

**So: write the script, budget each section in seconds, then set each hold to
its budget.**

## The shape of a section

`scripts/mp4/build.py` parses exactly one line shape, in `narration.md`:

```
## <index> - <Title> - ~<seconds>s
```

matched by `^##\s*(\d+)\s*-\s*(.+?)\s*-\s*~([\d.]+)s\s*$`. Headings **must be
numbered 1..N in file order** or the build aborts: playback follows file order,
but the scene counter and the `audio/NN.mp3` lookup follow the heading number,
so a mismatch is a silent desync.

```markdown
## 4 - The sweep, with traceability - ~25s

Working out of the box, no special setup, Claude goes contract by contract
across all forty-seven, identifying and indexing each one and pulling the
clauses.

*Screen:* "Sweeping contracts," 47 total, rows land, traceability column right.
```

Three parts, all load-bearing:

- **`~25s`** is the spoken-time budget. It becomes the animation's hold and the
  audio section's padded length. One number, three jobs.
- **The prose** is the TTS input, verbatim. Every non-`*Screen:*` line is joined
  with spaces.
- **`*Screen:*`** is your contract with the renderer: what must be visible while
  those words are spoken. It exists to catch mismatches before anything renders.
  Check every one against what the scene actually shows at that moment.

A real trap this caught: an integration section opened with *"notice the three
tabs at the top left"* while the tabs were not on screen during that beat.

## The other shape: a cue table, for the HTML pipeline

`/video-quick` decks do not have per-scene audio files. Once audio is present it
becomes the deck's **master clock**, so narration arrives as one continuous
track that has to be exactly as long as the timeline, with every line starting
on its own cue. The script for that is `narration-script.md`, and
`scripts/sound/tts_narrate.py` parses exactly this table:

```markdown
| # | Cue | Scene | Line |
|---|---|---|---|
| 1 | 0:00.0 | Opening | Forty-seven contracts, and no index of what is in them. |
| 2 | 0:12.5 | The sweep | Claude goes contract by contract, pulling the clauses. |

Total runtime **90.00s**
```

Four things it will not forgive:

- **The cue is `mm:ss.s`**, not seconds. `12.5` does not match; `0:12.5` does.
- **Cues are derived from the deck's scene starts**, using the player's own
  arithmetic: `start[i+1] = start[i] + dur[i] - overlap[i]`. Change a `dur` and
  every cue after it moves.
- **The total must be stated**, either in a table row or on a line opening with
  "Total", "Runtime" or "Length". Without it the length is guessed from the last
  line plus a second, and a track shorter than the timeline stretches the deck.
  Passing `--total` explicitly is safer than relying on the parse.
- **A line that runs past the next cue still plays**, overlapping the following
  visual. The script warns; it cannot fix it. Trim the wording or widen the
  scene.

The two shapes are not interchangeable, and a clip folder holding both is an
error rather than a choice. Which file is present is what picks the output shape.

## Budget at 2.2 words per second

Above 2.5 the take will overrun. `scripts/sound/tts_narrate.py --dry-run` reports
words per second per scene, needs no API key and no network, and is the cheapest
possible check. It reads both shapes. Run it before generating anything.

## Pad every take to its budget

This is what turns sync from a hunt into arithmetic.

```
section 1 renders to  9.2s  ->  pad to 14s
section 2 renders to 16.1s  ->  pad to 17s
section 3 renders to 11.4s  ->  pad to 13s
join -> boundaries at exactly 14 / 31 / 44 ...
```

Now the audio's section boundaries are **by construction** the same numbers as
the budgets, which are already the same numbers as the animation's holds. The
padding is inaudible, because a pause at a scene change is what you want anyway.

`build.py` does this automatically. The Cornerstone build did not, and matched
audio to video by hand: nudge a hold, re-capture, compare, repeat, at twenty
minutes per re-capture. Its own knowledge-transfer document names this as the
first thing it would change.

## An over-budget take is an error, not a warning

Padding can add silence. It cannot shorten speech. Accepting one long take
shifts every scene after it, so `build.py` stops before rendering rather than
producing a clip that is quietly wrong.

Two fixes, both legitimate: **shorten the copy**, or **raise the budget** in
`narration.md`. Raising the budget re-times the scene automatically, because
renderers take normalised progress rather than frame counts. Never work around
the check.

## Measure, do not compute

Do not predict a scene's on-screen time by summing its holds. Typing loops,
cursor transitions and fade overlaps all add real time that a simple sum misses.
The frame-difference verifier in `build.py` measures the encoded file from the
outside and writes the result to `verification.json`. Report that.

For a clip built elsewhere, `ffmpeg -af silencedetect=noise=-45dB:d=0.9` finds a
voice track's section boundaries, which is exactly what you need to align
picture to it.

## House rules for spoken and on-screen copy

- **No em dashes in visible copy.** Periods, commas, colons. Harmless when
  spoken, but narration files feed on-screen card text too.
- Sentence case for body copy.
- Every figure that reaches the screen traces to the source document. If the
  source flags a number as unattributed, leave it out rather than hedging it.
- Aim at the payoff, not the plumbing. Cut context-setting beats that feel
  mechanical.
