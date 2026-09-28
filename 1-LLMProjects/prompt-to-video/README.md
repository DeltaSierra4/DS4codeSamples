# video-gen

Turn a document, or just a description, into a finished video without opening a
terminal.

Point it at a deal review, a one-pager, a set of notes, and it writes the
narration, builds the visuals to that narration's timing, renders, and verifies
the result. About eight minutes for an mp4, eleven for the HTML.

**Start with `/video-generate`.** It asks what you want, which format, and
whether it should speak, shows you a plan to sign off, and then runs the rest
itself. The commands below still work on their own if you already know which
one you want.

## Which one do I want?

| | `/video-full` | `/video-quick` |
|---|---|---|
| Output | `output/<name>/<name>.mp4` | `output/<name>/<name>.html` |
| Size, 90 seconds | ~2.7 MB | ~56 KB |
| Goes where | Anywhere. Slides, LinkedIn, Teams upload | Screenshare, email, SharePoint, an `<iframe>`, a kiosk screen |
| Does not go | — | **A PowerPoint slide or LinkedIn.** It is not a video file |
| Looks like | Pillow-drawn frames. Plain | Real CSS. Markedly better |
| Runtime | ~8 min | ~11 min |

Rough rule: **if it has to be a file, `/video-full`. If it has to be opened,
`/video-quick`.** When in doubt, run both. They share the narration, so the
second is cheap.

## Commands

| | |
|---|---|
| `/video-generate` | **The front door.** Prompt in, narrated video out, with a plan to sign off in between |
| `/video-full` | Render an mp4. 1920x1080, 30fps, h264 + aac, verified frame-exact |
| `/video-quick` | Render one self-contained HTML file that plays in any browser |
| `/add-sound` | Lay narration over either. Your recording, or generated |
| `/refresh` | Clear `input/`, sweep `output/` into `output/archived/` |

Run standalone, both video commands open with the same two questions: where the
reference material is, and whether you want sound. `/video-generate` asks those
itself and then skips them, so you are never asked twice.

## Requirements

| | |
|---|---|
| Python 3.10+ | with Pillow and numpy |
| Node 18+ | `/video-quick` only. **no `npm install`** — the packer has zero dependencies on purpose |
| ffmpeg and ffprobe | on PATH |

Install ffmpeg with `winget install Gyan.FFmpeg` on Windows, `brew install
ffmpeg` on macOS, or `apt-get install -y ffmpeg` on Linux. Fonts ship with the
plugin, so nothing else is needed.

**You do not have to restart your terminal after installing ffmpeg.** winget
tells you to, because it changes PATH and an open shell will not see it. The
plugin looks in the places winget, chocolatey, scoop, Homebrew, MacPorts and apt
actually install to, so it finds ffmpeg whether or not PATH caught up.

If yours lives somewhere unusual, point at it directly and that wins over
everything else:

```
set    VIDEO_GEN_FFMPEG=C:\path\to\ffmpeg\bin     # Windows
export VIDEO_GEN_FFMPEG=/path/to/ffmpeg/bin       # macOS, Linux
```

Either the folder or the `ffmpeg` binary itself works. To see what the plugin
resolves:

```
python scripts/toolchain.py
```

Node is needed by `/video-quick` alone, which packs the html deck. `/video-full`
never touches it. To see whether yours is found:

```
python scripts/nodecheck.py
```

If it is not, that command prints the steps to get one, already correct for your
operating system, and `/video-quick` stops to ask whether you want to install
Node, point at one you already have, or abort. It does not guess. If yours lives
somewhere unusual:

```
set    CLAUDE_VIDEO_NODE=C:\path\to\nodejs        # Windows
export CLAUDE_VIDEO_NODE=/path/to/nodejs          # macOS, Linux
```

Either the folder or the `node` binary itself works, as does a folder with
`bin/node` inside it. Unlike `VIDEO_GEN_FFMPEG`, this one does **not** beat
PATH: a real node on PATH wins, because the variable exists for people who had
none. See `reference/node-setup.md`.

Generating a narration additionally needs the Client network or VPN and a key in
`CLIENT_GENAI_KEY`, falling back to `OPENAI_API_KEY`. Nothing else here touches the
network. To see whether yours is set:

```
python scripts/sound/keycheck.py
```

If it is not, that command prints the one line to copy to set it, already
correct for your operating system. You do not have to know what an environment
variable is to follow it, and it never prints or asks for the key itself.

**You do not have to restart anything after setting a key**, for the same reason
you do not after installing ffmpeg: the plugin looks where the value actually
landed rather than trusting the environment it was started with. On Windows that
means reading your user settings directly, and on macOS your shell profile.

The exception is a harness that runs the plugin in a sandbox, where nothing you
set on your own machine is visible. There you are asked to paste the key into a
`key_settings.json` the plugin writes for you, and it is deleted at the end of
the run. You are never asked for a key in the chat, on either path.

See `reference/voice-setup.md` for voices, budgets and troubleshooting.

## How it works, in one paragraph

Narration is written first, with a time budget per scene. Those budgets drive
everything: the frame count for each scene, and the length each audio section is
padded to. Because both come from the same number, scene boundaries and speech
boundaries land on the same second by construction rather than by adjustment.
The mp4 build then measures its own output by frame-differencing across each
boundary and writes what it found to `verification.json`. The HTML build proves
its packed file references nothing external and that its timeline survived
packing. Neither reports a number it did not measure.

## Folders

```
input/                  drop reference material and recordings here
output/                 your deliverables
output/archived/        where /refresh moves the previous set
scripts/                all executable code
reference/              the long-form docs commands point at
skills/                 guidance Claude applies without being asked
```

`input/` is read-only to the plugin. It reads from there and never writes back.

## Two things that will surprise you

**The HTML deck starts muted.** Every current browser refuses to autoplay with
sound, so the unmute click is itself the gesture that satisfies the policy.
Press `m` or click the speaker. There is no way around this.

**An over-budget narration take stops the build.** That is deliberate. Padding
can add silence but cannot shorten speech, so one long take would shift every
scene after it. Shorten the copy, or raise the budget in `narration.md` and the
scene re-times itself.

## Before you send anything to a client

- **Open the HTML file yourself.** `check.mjs` proves it is self-contained and
  that its timeline is intact, but nothing in this pipeline has ever rendered a
  page. Playback, the scrub bar, fullscreen and scale-to-fit are confirmed by
  you double-clicking it, and that takes thirty seconds.
- **Watch the mp4 through once.** The verifier proves timing, not taste.
- **In generate mode, narration text leaves your machine** and goes to
  `your-ai-client.com`. On a client engagement, decide whether
  that is acceptable before you run it, not after.
- **No take has ever been synthesised from inside this plugin.** The wiring is
  tested against fixtures; the first live call is still the first live call. Run
  `--dry-run` first, every time.

## Performance note

Rendering is roughly five times slower on Windows than in the Linux sandbox the
engine was built in: about 12 fps against 59. A 90 second clip takes around four
minutes of render rather than under one. Still inside the eight minute figure,
but do not be surprised by the wait, and use `--scale 0.5` for the look-see pass.
