---
description: Build an mp4 from reference material. 1920x1080, 30fps, h264 + aac, frame-exact and verified. Use when the deliverable has to be a file - a slide, a LinkedIn post, anything that expects a video.
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "AskUserQuestion"]
---

# Command: /video-full

## Purpose

Produce an **mp4** from a reference document, unattended, in about eight
minutes. Reach for it when the deliverable has to be a file. For a Teams
screenshare, an email or SharePoint, `/video-quick` produces something a
fiftieth the size that looks better.

Inherited limit worth saying out loud: frames are drawn with Pillow, not CSS.
The design ceiling is low. If the user wants designed motion, tell them so and
offer `/video-quick`.

## Invocation

```
/video-full [optional: a one-line brief]
```

## What this does

### 1. The gate

Read `${CLAUDE_PLUGIN_ROOT}/reference/gate.md` and follow it exactly, before
anything else.

**Unless you were called from `/video-generate`**, which has already asked these
questions and holds the answers. Asking them twice is the exact thing that
command exists to prevent. Start at section 2.

### 2. Read the reference material

Whatever the gate pointed at. Every figure that reaches the screen must trace to
it. Where the source flags a number as unattributed or uncorroborated, leave it
out; do not repeat it with a hedge.

Decide the altitude before writing: a leadership audience wants the payoff, not
the plumbing. Cut context-setting beats that feel mechanical.

### 3. Write `narration.md` first

This is the pivot of the whole method and the one step not to rush. Create
`${CLAUDE_PLUGIN_ROOT}/output/<name>/narration.md`. The parser recognises
exactly one line shape:

```
## <index> - <Title> - ~<seconds>s
```

`scripts/mp4/build.py` matches it with
`^##\s*(\d+)\s*-\s*(.+?)\s*-\s*~([\d.]+)s\s*$`, and **headings must be numbered
1..N in file order or the build aborts**. Playback follows file order but the
scene counter and the `audio/NN.mp3` lookup follow the heading number, so a
mismatch is a silent desync.

Under each heading:

- The narration itself, as prose. Every non-`*Screen:*` line is joined with
  spaces and becomes the TTS input.
- One `*Screen:* ...` line describing what must be visible while those words are
  spoken. This is your contract with the renderer, and it is how mismatches get
  caught before anything renders.

Budget at roughly **2.2 words per second**. Above 2.5 the take will overrun its
budget, and an over-budget take stops the build. Copy the shape from
`${CLAUDE_PLUGIN_ROOT}/scripts/mp4/templates/narration.md`.

### 4. Write a driver, never touch the engine

Copy `${CLAUDE_PLUGIN_ROOT}/scripts/mp4/templates/build_driver.py` to
`output/<name>/build_<name>.py` and adapt it. The pattern it demonstrates is the
whole point: it imports `build.py` as a module and rebinds four globals rather
than forking it.

Replace **every** renderer in the template. Its three are deliberately plain and
exist to show the signature and the timing convention. Set `ENGINE` to an
absolute path to `scripts/mp4`, because a driver in `output/<name>/` cannot find
the engine by walking up from itself.

```python
HERE = Path(__file__).resolve().parent
sys.path.insert(0, r"<absolute path to scripts/mp4>")
import build

build.NARRATION = HERE / "narration.md"
build.OUT       = HERE
build.AUDIO_IN  = HERE / "audio"
build.RENDERERS = RENDERERS          # {1: scene_title, 2: ..., N: ...}
build.OUT_NAME  = "<name>.mp4"
build.main()
```

Import the palette and helpers from `build` (`ACCENT`, `BG`, `PANEL`, `TEXT`,
`MUTED`, `OK`, `MARGIN`, `W`, `Fonts`, `draw_block`, `ease_in_out`, `ease_out`,
`fade`, `mix`) so every clip looks like it came from the same house. Add colours
only when the content genuinely needs one.

Each renderer has the signature `fn(draw, f: Fonts, t: float, s: float)` where
`t` is scene-local progress from 0 to 1. **Register one renderer per scene
index.** A missing index exits with `No renderer registered for scene N`.

Because `t` is normalised progress rather than wall-clock, changing a budget in
`narration.md` re-times the scene automatically. Do not hardcode frame counts.

### 5. Render

```bash
python build_<name>.py --scale 0.5    # fast look first, roughly 35s
python build_<name>.py                # full 1080p, roughly 90s
```

Always do the half-resolution pass first and read it. It catches overflowing
text and dead space for a third of the wait.

Requires `ffmpeg` and `ffprobe`. They do not have to be on PATH:
`scripts/toolchain.py` also checks `$VIDEO_GEN_FFMPEG` and the standard winget,
chocolatey, scoop, Homebrew, MacPorts and apt locations, and it exits with the
right install command for the platform if it finds nothing.

If a user reports ffmpeg missing right after installing it, run
`python scripts/toolchain.py` to see what resolves before suggesting anything
else. Do not tell them to restart their terminal as a first move; the resolver
exists precisely so they do not have to.

### 6. Sound

If the gate's question 2 was answered anything but "No sound", hand off to
`/add-sound` now. Do not reimplement it here. When `/video-generate` called you,
it owns that step and will run it itself.

Silent runs are still budget-exact: every section is silence padded to its
budget, so narration can be dropped in later without shifting a single scene
boundary.

### 7. Report measured numbers, not calculated ones

Read `output/<name>/verification.json`, which the run produced, and report from
it:

- `duration_measured_s` against `duration_budgeted_s`, and `duration_error_s`
- `all_boundaries_confirmed`, with the count
- the boundary deltas against `intra_scene_control_delta_max`

A boundary is confirmed when its frame-to-frame delta exceeds
`max(4 * control, 0.004)`. Healthy output puts boundary deltas an order of
magnitude above the control. **Never state a duration you worked out yourself.**
State the one ffprobe measured.

## Rules

- Never edit `scripts/mp4/build.py`. The verification guarantees are the reason
  this pipeline was selected; a fork forfeits them.
- Never edit `scripts/mp4/fonts/`. Frames are deterministic across operating
  systems only because that font ships with the plugin.
- An over-budget take is an error. Re-cut the copy or raise the budget and the
  scene will follow. Do not work around it.
- Write only into `output/`. `input/` is read-only.
