# Changelog

## 0.4.0 — 24 September 2026

The key check assumed the machine it was running on was the machine the user was
sitting at. On a harness that runs the plugin in a sandbox, it is not.

### Added

- **`--platform` on `scripts/sound/keycheck.py` and `scripts/sound/tts_narrate.py`.**
  Run from VS Code the key gate was fine. Run from Cowork, which executes the
  script inside a Linux sandbox, a Windows user was handed
  `echo 'export CLIENT_GENAI_KEY=...' >> ~/.profile` and told to open a terminal.
  Two problems, and the second is the one that mattered.

  *The message.* `sys.platform` is the truth about the process and a lie about
  the user, and the four steps are printed for whoever is reading them. So the
  caller now states which operating system that is. It is a declaration, never
  a detection: nothing sniffs for a harness name, a container marker, or an
  environment variable that happens to be set in one place and not another, and
  the prohibition in `reference/node-setup.md` stands unchanged. `keycheck.py`
  compares what it was told to its own `sys.platform`, and the only thing that
  changes is which message prints. Default `auto`, which is the old behaviour
  exactly, so every existing caller is unaffected.

  *The dead end.* Fixing only the wording would have produced a politer loop.
  When the declared platform differs from the running one, no environment
  variable the user sets is readable from inside the sandbox by **any** of the
  routes in the resolution order, including the registry read that exists to
  defeat exactly this class of problem on a normal machine. They would follow a
  correct instruction, say done, and fail again, forever. The escape hatch the
  docs offered, restart Claude Code, does not help either: the sandbox never had
  their environment to inherit.

- **`key_settings.json`, a hand-off file, and `--forget` to delete it.** The
  mismatch branch writes a blank `{"CLIENT_GENAI_KEY": "", "OPENAI_API_KEY": ""}`
  at the plugin root and asks the user to paste their key into it. It resolves
  at step 3, above the OS fallbacks, because a file filled in by hand for this
  run should beat a profile line written years ago and forgotten.

  A plaintext key on disk is worse than an environment variable and better than
  a key in a transcript, and it is a stopgap for a sandbox that leaves no third
  option. Four guards, because the failure mode is a leaked credential:
  `keycheck.py` reads the file so no agent ever has to, and no other tool may
  open it; it is never written over the top of an existing one, which would
  discard a key just pasted in; `--forget` deletes every copy and `report_key`
  prints a reminder whenever it resolved a key out of one; and it is in
  `.gitignore` as a backstop, not as a substitute.

  Nothing about it prints a key. Every path still reports `redact(key)` and the
  name of the source.

### Changed

- **The first `AskUserQuestion` option after a missing key is now worded as the
  action, not the acknowledgement.** "I have run it" is a reply to being spoken
  to rather than an answer to the question, and someone who half-followed the
  instruction picks it as readily as someone who finished. It now reads
  `I registered the Environment Variable, please continue the workflow`, or
  `I filled in key_settings.json, please continue the workflow` on the mismatch
  path. `reference/voice-setup.md` carries the rule as well as the strings, so
  the next option added is worded the same way.

- **The re-check fallback in `reference/voice-setup.md` now branches.** "Close
  Claude Code and open it again" is right when the check is on the user's
  machine and useless when it is not. Offering it on the mismatch path costs a
  restart and fixes nothing.

- `scripts/sound/keycheck.py` gained a real argument parser. Exit codes are 0
  found, 1 not found, 2 the flag was spelled wrong.

## 0.3.0 — 23 September 2026

`/video-quick` now finds node the way the rest of the plugin already finds
ffmpeg and the gateway key, and when there is none it asks rather than
improvising.

### Added

- **`scripts/nodecheck.py`**, which is `toolchain.py` for node. The html
  pipeline was the one dependency with no resolver behind it. `video-quick.md`
  said to resolve `node` from PATH, then check `$CLAUDE_VIDEO_NODE`, then "fail
  with a clear message", and nothing implemented any of it: a bare PATH lookup
  was the whole story and the recovery was left to whoever was reading. Two
  problems, and the second is the one that mattered.

  *The message.* "Install Node 18+" names a concept rather than an action, and
  the html path is the one most likely to be run by someone who has never
  installed a runtime. It now prints numbered steps with one line to copy,
  correct for the platform it ran on: `[Environment]::SetEnvironmentVariable(...)`
  on Windows, an `export` appended to `~/.zprofile` on macOS or `~/.profile` on
  Linux.

  *The recovery.* Same trap as the key, same fix. That PowerShell command writes
  to `HKCU\Environment`, which an already running Claude Code session cannot
  see, because a child process inherits the environment block copied at launch.
  So the registry is read directly on Windows and the shell profiles on macOS
  and Linux, and the run continues the moment the user says done.

  Four outcomes rather than two, because the recoveries differ: found, found but
  older than 18, an explicit path that is not a node, and nothing anywhere. The
  third exists because the new flow accepts a path typed by a user, and a typo
  should produce one clear message rather than three failing commands.

  **PATH beats `CLAUDE_VIDEO_NODE`**, which is the reverse of how `toolchain.py`
  treats `VIDEO_GEN_FFMPEG`, and deliberate. The override is set by someone who
  had no node at all, so a real one on PATH is the better answer once it exists.

- **`reference/node-setup.md`**, the `voice-setup.md` analog: the resolution
  table, the three ways out when node is missing, the two messages to print
  verbatim, and the rule that **both** answers to the follow-up question
  continue the run. Registering the path is a convenience for next time, never a
  condition of proceeding.

- **A node preflight, as `/video-quick` section 2.** It runs when the command is
  invoked rather than at pack time, for the reason `gate.md` already gives about
  the narration key: finding out after a deck has been written and timed wastes
  the run. `/video-generate` inherits it for free, because it enters at section
  2. `/video-full` has no such step and needs none.

### Changed

- `/video-quick` sections 2 through 7 are now 3 through 8.
- README, `skills/deck-authoring` and `reference/html-authoring.md` point at the
  resolver rather than stating the requirement and stopping there.

### Nothing about the environment is detected, on purpose

An environment that ships node resolves it at PATH and is never asked anything.
That is the whole of the sandbox branch. There is no check for a harness name, a
container marker or a sandbox flag, because the first time one of those is
renamed a Windows PowerShell instruction gets printed inside a Linux container.

### Verified on Windows 11, Python 3.13.0, with no node installed

| Check | Result |
|---|---|
| Both Windows messages against the supplied text | Byte-identical once line endings are normalised. md5 match on each |
| macOS and Linux variants | Correct opener and `export` target for each of the four |
| No node anywhere | exit 1, the five-step install message |
| Explicit path that is not a node | exit 1, rejected by name, no traceback |
| **Stale environment recovery** | A value written by `SetEnvironmentVariable(...,"User")` in a separate shell was read back inside this already running session from `HKCU\Environment`, while `os.environ` still showed nothing. That is the failure this file exists to prevent |

### Not verified in this build

- **Node is still not installed on this machine**, so `test-player.mjs`,
  `pack.mjs` and `check.mjs` still have not run, and no `.mjs` or `.js` file was
  touched. The gap flagged in 0.2.0 stands: the first run on a machine with node
  is the first real exercise of the html pipeline end to end.
- **No deck has been packed through the new preflight.** The resolver is tested;
  the path from a green preflight into `pack.mjs` is not.
- `/add-sound` still runs `pack.mjs` and `check.mjs` with no preflight of its
  own. Reached through `/video-quick` or `/video-generate` node is already
  resolved; run standalone against an html deck it fails at the command itself.

## 0.2.1 — 22 September 2026

A missing narration key now stops the run with something a non-technical user
can act on, and the run carries on without a restart once they have acted on it.

### Added

- **`scripts/sound/keycheck.py`**, which is `toolchain.py` for the gateway key.
  Two problems, and the second was the one that mattered.

  *The message.* "Set CLIENT_GENAI_KEY" names a concept rather than an action, and
  most people who use this plugin have never set an environment variable. It now
  prints four numbered steps with one line to copy, correct for the platform it
  ran on: `[Environment]::SetEnvironmentVariable(...)` on Windows, an `export`
  appended to `~/.zprofile` on macOS.

  *The recovery.* On Windows that command writes to `HKCU\Environment`, and an
  already running Claude Code session cannot see it, because a child process
  inherits the environment block copied at launch. So the user did everything
  right, the run retried, and it failed again with the same message. Now the
  registry is read directly on Windows, and the shell profiles on macOS and
  Linux, so the run continues the moment they say done. Same trap and same fix
  as `toolchain.py` looking past PATH into the install directories.

  It never prints a key. `redact` moved here from `tts_narrate.py`, so that
  reporting a key that was found cannot become a circular import.

- **`tts_narrate.py --check-key`**, which reports and exits 0 or 1 without
  calling the gateway.

### Fixed

- **The early key check never checked for a key.** `commands/video-generate.md`
  and `commands/add-sound.md` both told the agent to verify a key before
  building, and both handed it a command that could not do so: `--explain`
  returns before key resolution and exits 0 either way, and `--dry-run` is a
  pace check that deliberately needs no key. So a missing key surfaced at the
  first synthesis call instead, which is the wasted render both files warn
  about. Both now run `keycheck.py` and branch on its exit code.

### Removed

- **The offline test scripts are no longer distributed.** They were developer
  tooling that nothing in the plugin ever invoked: no command, skill or script
  referenced them, and none was documented anywhere a user would look. They are
  kept outside the plugin rather than deleted.

### Changed

- `reference/voice-setup.md` gains **When no key is set**, the one place the
  pause is specified. `/video-generate`, `/add-sound` and the gate all point at
  it rather than restating it, so the three cannot drift apart. It requires the
  script's message be printed verbatim, offers silent and bring-your-own
  recording as the two ways out, and forbids asking for the key in the chat: a
  key pasted into the conversation is in the model context and in the session
  transcript on disk, and neither can be taken back.

## 0.2.0 — 21 September 2026

One command from a prompt to a narrated video, and one text-to-speech engine
instead of two.

### Added

- **`/video-generate`.** The front door. Asks what you want to make, then the
  format, then whether it should speak; writes `output/<name>/plan.md` and waits
  for sign-off; then delegates to `/video-quick` or `/video-full` and runs the
  narration step itself. It reads those command files and follows them rather
  than calling them, because calling them would re-trigger the gate and ask the
  user the same questions twice.

  The plan sign-off is the point. A render costs minutes; a plan costs seconds.

- **`scripts/sound/tts_narrate.py`**, replacing `scripts/mp4/make_narration.py`.
  Adapted from the `tts-playground` script. Two things the old one could not do:

  - **It speaks for `/video-quick`.** The html deck has no per-scene audio
    boundaries, so per-scene mp3s were useless to it and `pack.mjs --audio` takes
    exactly one file. The cue-laid mode synthesises each line and lays it at its
    cue on a silent track exactly as long as the timeline, which is the one shape
    the deck can use. **`/video-quick` could not be narrated by TTS at all before
    this.**
  - **It points at the Client GenAI gateway**, `openai.us.tts-1-hd`, keyed on
    `$CLIENT_GENAI_KEY` falling back to `$OPENAI_API_KEY`. The old script pointed at
    `api.openai.com` and ElevenLabs, neither of which had ever returned a byte.

  Which shape you get is decided by the clip folder, not a flag: `narration.md`
  means per-scene mp3, `narration-script.md` means one cue-laid track. A folder
  holding both is an error rather than a guess.

- **`--aac`**, resolved through `scripts/toolchain.py`. A cue-laid wav
  base64-inlines into the packed html at roughly 4 MB for 90s; aac lands nearer
  130 kB. Optional on purpose, and degrades to a warning without ffmpeg, because
  every other step in that script runs without it.

### Changed

- **The cue-table format is now a contract, not a suggestion.** `/video-quick`
  said to keep "a cue time per line" and nothing more, so anything it wrote would
  have failed to parse. `video-quick.md` now pins the exact
  `| # | mm:ss.s | Scene | Line |` table, and `narration-budgets` documents it
  beside the `## N - Title - ~Ns` shape.
- **`narration-script.md` moved** from beside the deck in `scripts/html/src/` to
  the clip folder in `output/<name>/`. `scripts/` is distributed and should not
  carry engagement text, and the narration file has to sit where `tts_narrate.py`
  looks for it.
- **Both pipelines now write to `output/<name>/`.** `/video-quick` used to emit a
  flat `output/<name>.html`, which left nowhere for a narration workspace to live
  without colliding with the clip's own name.
- **`.gitignore` now excludes generated decks.** `video-quick.md` already said
  nothing from an engagement belongs in `scripts/`, but `scripts/html/src/*.html`
  was not ignored, so a deck written there would have been distributed. The two
  shipped examples are kept.
- **`reference/voice-setup.md` rewritten.** It documented four providers, two of
  which (kokoro, qwen3) were never in the shipped code, and a `requirements.txt`
  that does not exist. It now documents what is actually there.
- **`scripts/mp4/build.py`: two strings**, both naming the deleted script. The
  docstring's "how to get a voice track" recipe and the no-audio hint at the end
  of a silent run. No arithmetic, no verifier logic, no behaviour.

### Removed

- **`scripts/mp4/make_narration.py`.** Nothing imported it. Its ElevenLabs route
  and its direct-to-OpenAI route go with it; both were untested and neither had
  a key on this network.

### Verified on Windows 11, Python 3.13.0, ffmpeg 9.0.1

Every line below is a command's own output.

| Check | Result |
|---|---|
| Narration engine, offline | PASS, 17 checks. No key, no network |
| Cue-laid track length | 30.00s against a 30.00s stated timeline, from takes summing to 12.0s. The silence between cues is the point |
| `--aac` transcode | 144,044 byte wav to 9,449 byte m4a, 3.000000s preserved |
| Over-budget take, scenes mode | exit 1, nothing written |
| Line overrunning its cue, cues mode | exit 1, every clash named |
| No-overwrite guarantee | previous take kept byte-identical as `01_removed.mp3`, move recorded |
| mp4 sync, after deleting `make_narration.py` | PASS. 72.000s against a 72.000s budget, over-budget take still rejected |
| `--dry-run` on both shapes | parses, costs and paces. Both-files and neither-file cases each exit with their own message |
| ffmpeg resolver | ffmpeg 9.0.1 found via PATH |

### Not verified in this build

- **Node is not installed on this machine**, so `test-player.mjs`, `pack.mjs` and
  `check.mjs` did not run. The html path changes are documentation and file
  locations only; no `.mjs` or `.js` file was touched. **Run the Node checks
  before trusting the html pipeline.**
- **Still no live gateway call.** `--dry-run`, key handling, both parsers, the
  cue laying, the transcode and the install are all exercised against fixtures.
  No real take has been synthesised.

## 0.1.0 — 17 September 2026

First build. Packages `poc-raw` and `poc-html-nomp4` as one plugin, per
`battle_plan.md` (9 September).

### Added

- Four commands: `/video-full`, `/video-quick`, `/add-sound`, `/refresh`.
- A shared gate in `reference/gate.md`, referenced by both video commands so the
  branch behaviour is defined once.
- Two skills: `deck-authoring` (the timeline model and its six rules) and
  `narration-budgets` (the budget doctrine from the Cornerstone clips).
- `scripts/sound/mux_mp4.py` — lays a continuous take over a finished mp4,
  extracting audio from a video container when given one.
- `scripts/html/build/selector-audit.mjs` — **new capability.** The battle plan
  listed a 58-track selector audit as carrying over from the POC; it did not
  exist, it was a prose claim. Now it is a hard check inside `check.mjs`.
- `scripts/toolchain.py` — finds ffmpeg and ffprobe wherever they actually are.
  Resolution order is `$VIDEO_GEN_FFMPEG`, then PATH, then the standard winget,
  chocolatey, scoop, Homebrew, MacPorts and apt locations; whatever it finds is
  prepended to the process PATH so existing `["ffmpeg", ...]` calls need no
  change. An explicit override beats PATH deliberately.

  This exists because `winget install Gyan.FFmpeg` prints "restart your shell"
  and almost nobody does, so the first-run sequence was: told ffmpeg is missing,
  install ffmpeg, told ffmpeg is missing again. That reads as a broken plugin.
  Wired into `build.py`, `mux_mp4.py`, and optionally into
  `make_narration.py`, which must still run where ffprobe is absent.
  `python scripts/toolchain.py` prints what resolves and how.

### Changed, in the lifted engines

Three edits, all portability. The verified arithmetic is untouched.

- **`build.py`: fonts now ship with the plugin.** It hardcoded
  `/usr/share/fonts/truetype/dejavu/...` and raised `OSError: cannot open
  resource` on the first frame on Windows. Bundled DejaVu under
  `scripts/mp4/fonts/` and resolved relative to the script, with system
  fallbacks and a readable error. Bundling rather than probing is deliberate:
  `wrap()` measures against the loaded font, so falling back to Arial on Windows
  would wrap the same script differently and overflow copy that fits elsewhere.
- **`build.py`: ffmpeg 8 removed `-vsync`.** The POCs were written against the
  sandbox's 4.4.2; a current install is 9.x. `frame_sync_flags()` now picks
  `-fps_mode passthrough` on 5+ and `-vsync 0` below. This failed *after* a full
  render, at verification, which made it look intermittent.
- **`make_narration.py`: `--project DIR`** so one copy can target any clip
  folder instead of only its own, and **`--replace`** plus a stale-sibling
  warning ported from `poc-raw - Voice`. `build.py` resolves `.mp3` before
  `.wav`, so a leftover take from a previous provider wins silently.

### Verified on Windows 11, Python 3.13.0, ffmpeg 9.0.1, Node 24.20.0

Every line below is a command's own output, not an estimate.

| Check | Result |
|---|---|
| mp4 sync, offline | PASS. 72.000s against a 72.000s budget; six speech stops within 0.05s; over-budget take correctly rejected |
| `test-player.mjs` | PASS, 77 checks |
| Full mp4 render | 90.000s budgeted, 90.000s measured, error 0.0s, exact to the frame |
| Boundaries | 7 of 7 confirmed. Deltas 0.0224–0.0476 against a 0.0008 control, so 28x to 60x |
| HTML pack + check | pass. 8 scenes, 90.00s, 56.1 KB, nothing external |
| Selector audit | 66 selectors resolve. On a deck with a typo and a wrong-scene reference: 2 failures, exit 1 |
| `mux_mp4.py` | 90.00s out, video stream copied. Short take padded, long take clamped with a warning, in-place mux refused |
| ffmpeg resolver | **With ffmpeg absent from PATH entirely**, the mp4 pipeline, `mux_mp4.py` and `make_narration.py` all run. Override accepted as a folder or as the binary; a bad override and a not-installed case each explain themselves |

### Fixed during the build

`mux_mp4.py` used `-shortest` alone, which truncated a 72s video to 70s when the
audio was shorter, while the script claimed the tail would play silent. Now
`-af apad` extends the take and `-shortest` trims the padding back to the
video's own length. The picture never shortens.

### Removed before any distribution

The first cut of this plugin lifted the POCs' example decks wholesale into
`scripts/`, which is the folder that gets distributed. Those examples carried
engagement material. All of it is gone:

| Removed | Why |
|---|---|
| `scripts/html/src/shein-everlane.html` | Deal deck, ~40 KB of figures and narrative |
| `scripts/html/src/shein-everlane-90s.html` | Deal deck, ~28 KB |
| `scripts/html/src/la-rebuild-teaser.html` | Engagement content, provenance unclear |
| `scripts/mp4/templates/build_deal.py` | Deal figures baked into the scene renderers |
| `scripts/html/assets/placeholder-ambient.m4a` | 366 KB of audio, unreferenced, provenance and licence unverifiable |

Replaced by invented worked examples that exercise the same features:

- `scripts/html/src/example-deck.html` — 60.00s, six scenes, 32 selectors.
  Covers stagger, additive composition, compound scene-scoped selectors, three
  compute tracks and proportional bars. Verified: packs to 41.5 KB, `check.mjs`
  passes.
- `scripts/mp4/templates/build_driver.py` and a rewritten
  `templates/narration.md` — three scenes, 30s. Verified: 30.0s budgeted, 30.0s
  measured, error 0.0s, both boundaries confirmed.

Both describe the plugin itself rather than any subject matter, so there is
nothing to leak. `CLAUDE.md` now states the rule: worked examples in distributed
folders are invented content, and engagement material lives in `input/` and
`output/`, which travel with the engagement rather than the plugin.

One hazard existed briefly and is worth recording. `templates/narration.md` was
replaced before `build_deal.py` was, and `build.py` errors only on a *missing*
renderer, never a surplus one. For a short window, following the documented
steps would have rendered deal copy onto the screen against neutral narration,
with no error raised. Anyone who copied the templates in that window should
check what their frames actually say.

## Known gaps

- **No browser has ever rendered these decks.** `check.mjs` proves
  self-containment and timeline integrity. Playback, the scrub bar, fullscreen,
  scale-to-fit and the unmute gesture are unconfirmed by anything automated.
- **Generate mode has not been run against a live API.** As of 0.2.0 the key
  handling, `--dry-run`, both parsers, the cue laying, the transcode and the
  install are all exercised offline; no real take has been synthesised. The
  gateway sits behind the Client network, so off VPN it is unreachable rather than
  refusing.
- **The selector audit does not prove nesting.** `.card .nm` passes when both
  exist in the scene but are not nested. Closing that needs a DOM, which needs
  an npm dependency, which the packer exists to avoid.
- **`input/` and `output/` live inside the plugin folder**, per the battle plan's
  folder contract. That suits a per-engagement install. A marketplace install
  would put them in the plugin cache, which is the wrong place to write. The
  distribution decision is still open.
- **Local TTS (Kokoro, Qwen3) is out.** Python here is 3.13 and kokoro requires
  `<3.13`; the weight download is blocked by policy. 0.2.0 removed the last
  references to it, since documenting a route that does not exist cost more than
  it saved.
- **`/video-full`'s layout templates are the known ceiling.** Scene renderers are
  bespoke per clip, and Pillow leaves dead space. A content problem, not an
  engineering one.
