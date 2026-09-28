---
description: Lay narration or a soundtrack over a video already in output/. Either splice in a recording the user supplies, or generate a voice track through the Client GenAI gateway. Works on both the mp4 and the self-contained HTML.
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "AskUserQuestion"]
---

# Command: /add-sound

## Purpose

Both video pipelines can ship silent. This is the skill that closes that gap
once, for both of them.

Two modes, because two genuinely different things are being asked for, and two
backends, because the target format differs. That is four paths. Pick
deliberately; do not guess.

## Invocation

```
/add-sound
```

Usually called automatically at the end of `/video-quick` or `/video-full` when
the gate's question 2 was answered anything but "No sound". Also runs standalone
against whatever is sitting in `output/`.

## What this does

### 1. Find the target

Glob `${CLAUDE_PLUGIN_ROOT}/output/`. If there is more than one candidate,
confirm which with `AskUserQuestion`. If there is nothing, say so and point at
`/video-quick` or `/video-full`.

The target's **format decides the backend**:

| Found in `output/<name>/` | Backend |
|---|---|
| `<name>.mp4`, plus its `clip-silent.mp4` and `narration.md` | section 4 |
| `<name>.html`, plus `narration-script.md` and the deck source in `scripts/html/src/` | section 5 |

Which narration file the clip folder holds is also what decides the shape of a
generated track: `narration.md` means per-scene mp3, `narration-script.md` means
one cue-laid wav. A folder holding both is an error, not a choice.

### 2. Ask which mode

`AskUserQuestion`, unless `/video-quick` or `/video-full` already carried the
answer through from the gate:

| Mode | Label | Means |
|---|---|---|
| A | I have a recording | An audio file, or a Teams `.mp4` to take the audio from |
| B | Generate a narration | Synthesised through the Client GenAI gateway. Needs network and a key |

### 3a. Mode A, a recording the user supplies

Accept `.mp3 .m4a .wav .flac .ogg .opus`, or any video container to extract
from. Teams hands people an `.mp4` far more often than a `.wav`.

Then ask one more thing, because it changes everything downstream:

- **One continuous take** covering the whole clip. The common case for a
  recorded voiceover or a music bed.
- **One file per scene**, already cut. Rarer, and much better: it is the only
  arrangement that puts each scene's speech on its own boundary by construction.

For per-scene files, rename them to `01.mp3 ... NN.mp3` in the clip's `audio/`
folder and go to section 4. For one continuous take, go to section 4 or 5 as the
format dictates.

### 3b. Mode B, generate a narration

**Check for a key before doing anything else:**

```bash
python scripts/sound/keycheck.py --platform windows   # or macos, or linux
```

**`--platform` is the operating system of the person you are talking to**, not
the one this command runs on. They differ whenever this runs in a sandbox, and
then the steps are for the wrong machine and cannot work. Omit the flag only if
you genuinely do not know.

Exit 0 and carry on. Exit 1 and the script has printed the fix, correct for the
operating system you declared. Print that message **exactly as the script
emitted it**, then follow **When no key is set** in
`${CLAUDE_PLUGIN_ROOT}/reference/voice-setup.md`: it holds the pause, the three
ways out of it, the separate hand-off path for a sandbox, and the rule that a
key is never typed into the chat.

**Then pace-check the script, which also needs no key:**

```bash
python scripts/sound/tts_narrate.py --project output/<name> --dry-run
```

`--dry-run` needs no key and no network. It reports words per second per scene,
which is the cheapest way to catch a script that will overrun its budget. Read
it. Anything above 2.5 w/s will overrun, and an over-budget take stops the
build.

Then, for an **mp4** clip:

```bash
python scripts/sound/tts_narrate.py --project output/<name> --install
```

Writes `audio/01.mp3 ... NN.mp3` plus `audio/provenance.json`, one take per
scene, each measured against its budget.

Or for an **HTML** clip:

```bash
python scripts/sound/tts_narrate.py --project output/<name> --aac --install
```

Writes one `narration.m4a`: every line synthesised and laid at its cue on a
silent track exactly as long as the timeline. `--aac` is worth passing. Without
it you get a 16-bit wav, which base64-inlines into the packed html at roughly
4 MB rather than 130 kB. It needs ffmpeg and degrades to a warning without it.

The key is `CLIENT_GENAI_KEY`, falling back to `OPENAI_API_KEY`, found by
`keycheck.py` wherever it actually got set. Voice defaults
to `onyx`; `--voice` takes any of alloy, ash, ballad, coral, echo, fable, nova,
onyx, sage, shimmer. `${CLAUDE_PLUGIN_ROOT}/reference/voice-setup.md` has the
voices, the budget rules and what each gateway error actually means.

**Three things that are not optional here:**

- **Keep `provenance.json`.** It records provider, model and voice. The
  Cornerstone clips did not record theirs and consequently cannot reproduce
  their own voice. Re-rendering meant re-choosing.
- **Degrade cleanly when the endpoint is unreachable.** The gateway sits behind
  the Client network, so off VPN it is unreachable rather than refusing, which is
  not the same as a bad key. A 404 usually means the model went to
  `/v1/chat/completions` instead of `/v1/audio/speech`. The script names all
  three cases in its own words; pass those on rather than guessing. Never leave
  a half-written `audio/` folder behind.
- **Say that narration text leaves the machine**, to
  `your-ai-client.com`. Once, plainly, the first time mode B
  is used in a session. On a client engagement the user should know.

Mode B produces whichever shape the clip folder implies, so it goes to section
4 for an mp4 and section 5 for an html deck.

### 4. Backend: mp4

**Per-scene takes, which is the preferred path.** Put them in the clip's
`audio/` as `01.mp3 ... NN.mp3` and re-run the clip's own driver:

```bash
python output/<name>/build_<name>.py
```

`build.py` pads every section with silence up to its scene budget before
joining, so section boundaries equal cumulative budgets equal the animation
holds. Sync is arithmetic, not an iterative hunt. It then muxes and re-runs the
frame-difference verifier, rewriting `verification.json`. Report from that file.

Watch for the **stale sibling**: `build.py` resolves `.mp3` before `.wav`, so a
leftover take from a previous provider silently wins over a new one. Before
re-running, list `audio/` and check for two files with the same number and
different extensions. If you find a pair, rename the loser to
`NN.mp3.superseded` rather than deleting it.

**One continuous take:**

```bash
python scripts/sound/mux_mp4.py --video output/<name>/clip-silent.mp4 \
                                --audio <the recording> \
                                --out   output/<name>/<name>.mp4
```

It extracts audio from a video container if given one, copies the video stream
untouched, pads a short take with silence so the picture keeps its full length,
and warns if the take runs long. Mux from `clip-silent.mp4`, never from an
already-muxed file.

### 5. Backend: HTML

```bash
cd scripts/html
node build/pack.mjs src/<name>.html ../../output/<name>/<name>.html --audio <track>
node build/check.mjs ../../output/<name>/<name>.html
```

`<track>` is one continuous file: the recording from mode A, or the
`narration.m4a` that mode B laid to the cue table. The html backend never takes
per-scene files, because the deck has no per-scene audio boundaries to hang them
on.

`pack.mjs` base64-inlines the audio and injects `<audio data-narration>`
immediately after `<body>`. That position matters: appending before `</body>`
puts the element after the player script, so `querySelector` finds nothing,
`hasAudio` stays false, and no unmute control is ever built. `check.mjs` fails
the build if that ordering regresses, so trust its exit code over your reading
of the file.

Two behaviours to explain to the user, both unavoidable:

- **It starts muted.** Every current browser refuses to autoplay with sound.
  The unmute click is itself the gesture that satisfies the policy. There is no
  way around this and no point trying. Press `m` or click the speaker.
- **Once audio is audible it becomes the master clock.** The timeline follows
  `audio.currentTime` rather than its own frame counter. Two independent clocks
  drift apart over a couple of minutes; slaving the visuals to the audio removes
  the problem instead of compensating for it.

Size: with `ffmpeg` on PATH and `--aac` passed, the track becomes AAC and the
file lands near 130 KB. Without either, a WAV inlines and the file is around
4 MB. Both pass `check.mjs`. Mention the difference if the result comes out
large.

To exercise the audio path without a real recording, synthesise a probe track of
the right length. The plugin ships no sample audio on purpose:

```bash
ffmpeg -f lavfi -i "sine=f=300:d=90" -c:a aac probe.m4a
```

### 6. Report

- **mp4** — from `verification.json`: measured duration, error, boundaries
  confirmed. Plus `ffprobe` showing two streams. Never a duration you worked out
  yourself.
- **HTML** — `check.mjs` exit 0 and its own summary line, plus the file size.
  Tell the user to open it and click the speaker, because no automated check in
  this pipeline has ever confirmed audible playback.

## Rules

- **A take that runs over its budget is an error, not a warning.** Padding can
  add silence but cannot shorten speech, so accepting one long take shifts every
  scene after it. Re-cut the copy or raise the budget in `narration.md` and let
  the scene follow.
- Never re-encode the video stream. `-c:v copy`, always.
- Never mux onto an already-muxed file. Go back to `clip-silent.mp4`.
- Never edit `scripts/mp4/build.py` or `scripts/html/src/player.js`.
- Write only into `output/`. `input/` is read-only.
