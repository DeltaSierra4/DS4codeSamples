# Voice setup

`scripts/sound/tts_narrate.py` is the only text-to-speech in this plugin. It
calls the Client GenAI shared-service gateway, needs no packages beyond the
standard library, and needs no ffmpeg unless you ask it for AAC.

```
POST https://your-ai-client.com/v1/audio/speech
Authorization: Bearer <key>
{"model": "openai.us.tts-1-hd", "voice": "onyx", "input": ..., "response_format": ...}
```

Run `python scripts/sound/tts_narrate.py --explain` to print this from the
script itself rather than trusting this file.

## The key

`scripts/sound/keycheck.py` owns every part of finding it, and the search goes
deeper than the environment this session was launched with:

| Order | Looked in |
|---|---|
| 1 | `--key` on the command line |
| 2 | `CLIENT_GENAI_KEY`, then `OPENAI_API_KEY`, in this session's environment |
| 3 | `key_settings.json`, at the plugin root or the cwd. See **When the check is not on the user's machine** |
| 4 | Windows: `HKCU\Environment`. macOS and Linux: an `export` line in a shell profile |

Step 4 is not a nicety. The fix a Windows user is given writes to the registry,
and an already running Claude Code session cannot see it, because a child
process inherits the environment block copied at launch. Without step 4 the user
follows the instruction correctly, the run retries, and it fails again with the
same message. That is the trap `scripts/toolchain.py` already defuses for
ffmpeg, in the same shape.

Step 3 sits above step 4 because that file is written by hand for this run,
while a profile line may have been written years ago and forgotten.

Check it at the start of a run, not at the end. **Pass `--platform`**, for the
reason in the next section:

```bash
python scripts/sound/keycheck.py --platform windows   # or macos, or linux
```

Exit 0 found, exit 1 not, exit 2 the flag was spelled wrong. It never prints the
key. Omitting `--platform` is the same as `--platform auto`, which assumes the
check is running on the user's own machine.

`tts_narrate.py --check-key` is the same check. **`--explain` is not** and never
was: it prints the endpoint docstring and returns before a key is looked for, so
it exits 0 whether or not one exists. `--dry-run` needs no key at all and is the
right first move every time.

You must be on the Client network or VPN. Off it, the gateway is unreachable rather
than refusing, which is a different failure from a bad key and the script says
which one it hit.

## `--platform` is a declaration, never a detection

Some harnesses run this check inside a Linux sandbox while the person reading
its output is at a Windows machine. `sys.platform` is then the truth about the
process and a lie about the user, and both halves of the message break at once.
They are handed an `export` line for an operating system they are not on, and
the correct line would not have helped either: nothing they set over there is
readable from in here, so they follow the instruction, the re-check fails, and
there is no way out of the loop.

**`--platform` is how you state which operating system the user is on.** Take it
from what you already know about the person you are talking to, not from
anything about where this command runs. Pass `windows`, `macos` or `linux`. If
you genuinely do not know, omit it rather than guessing.

This is **not** the sandbox check `reference/node-setup.md` forbids, and that
rule still stands. Nothing anywhere infers a sandbox from a harness name, a
container marker, or an environment variable that happens to be set in one place
and not another. You say what the user's machine is, and `keycheck.py` compares
that to its own `sys.platform`. The only thing that changes is which message
prints.

| | |
|---|---|
| Declared matches, or you passed nothing | The ordinary case. Nothing changes, no file is written |
| Declared differs | The four steps cannot work, so they are not printed. See below |

## When the check is not on the user's machine

On a mismatch, `keycheck.py` writes a blank `key_settings.json` at the plugin
root and prints a message pointing at it:

```json
{
  "CLIENT_GENAI_KEY": "",
  "OPENAI_API_KEY": ""
}
```

The user pastes their key between one pair of quote marks and says done.
`keycheck.py` reads the file at step 3 and the run continues. Then
`AskUserQuestion` exactly as in **When no key is set** below, with the first
option reading **`I filled in key_settings.json, please continue the workflow`**.

Four rules, and none of them is optional:

- **Never `cat`, `Read`, `grep` or echo that file.** `keycheck.py` reads it so
  that nothing else has to. The moment any other tool opens it, a live key is in
  the model context and in the session transcript on disk, which is the exact
  harm the no-key-in-chat rule exists to prevent.
- **Never write a key into it yourself**, and never offer to. The user fills it
  in, in their own editor, the same way they would type into their own terminal.
- **Run `--forget` when the run is finished**, on both the success and the
  abandoned path:

  ```bash
  python scripts/sound/keycheck.py --forget
  ```

  It deletes every copy, says which it deleted, and is safe to run when there is
  none. `report_key` prints a reminder whenever it resolved a key out of the
  file, so a run that used one says so on the way past.
- **It is in `.gitignore`**, which is a backstop for the run where somebody
  forgets, not a substitute for `--forget`.

If the JSON no longer parses after a hand-edit, the script says so and names the
three things a hand-edit usually breaks. Print that verbatim too.

**This is a stopgap.** A plaintext key on disk is worse than an environment
variable and better than a key in a transcript, and it exists because a sandbox
that cannot see the host environment leaves no third option. If a harness grows
a real secret hand-off, this should be retired for it.

## When no key is set

This is the part of the plugin most likely to be read out to someone who has
never set an environment variable, so it is worth being exact.

`keycheck.py` prints four numbered steps with a single line to copy, already
correct for the platform you declared. **Print that message exactly as the
script emitted it.** Do not reword it, do not summarise it, do not add a second
way of doing it. It is one instruction on purpose, and a paraphrase is how
someone ends up holding two half-instructions and following neither.

Then stop and `AskUserQuestion`. **Word the first option as the action they
took, not as the fact that they did something.** "I have run it" and "done" read
as acknowledgements rather than answers, and someone who half-followed the
instruction picks one just as readily as someone who finished it:

| Option | Means | Then |
|---|---|---|
| `I registered the Environment Variable, please continue the workflow` | They set it in their own terminal | Re-run `keycheck.py` with the same `--platform`. Exit 0: carry on, and say nothing further about keys. Exit 1: the fallback below |
| `Make it silent instead` | No narration | Still budget-exact, so narration drops in later without shifting a boundary |
| `I will record my own voice` | `/add-sound` mode A | A file they supply |

On the mismatch path the first option is the file rather than the variable:
**`I filled in key_settings.json, please continue the workflow`**. Everything
else about the question is the same.

**Never ask for the key in the chat, and never offer to set it for them.** The
instruction has them type it into their own terminal, or into
`key_settings.json` in their own editor, for a reason: a key pasted into the
conversation is in the model context and in the session transcript on disk, and
neither can be taken back. If they paste one anyway, do not write it anywhere
and do not use it. Say plainly that it is now in the conversation history and
should be rotated.

If the re-check still fails, the escape hatch depends on which path they were
on, and offering the wrong one wastes a restart:

- **No mismatch.** They have most likely set it somewhere this cannot reach.
  Close Claude Code, open it again, and run the command again.
- **Mismatch.** A restart will not help, because the sandbox never had access to
  their environment in the first place. Check that the file is where the message
  said, is saved, and still parses. `keycheck.py` will name a broken hand-edit
  itself. If it is filled in correctly and still not found, that is a real bug
  in the hand-off and the honest move is to say so and offer the silent track.

`output/<name>/plan.md` is on disk and survives either way, so a sign-off
already given is not lost.

## Voices

`--voice`, defaulting to `onyx`. Ten stock voices:

```
alloy   ash   ballad   coral   echo   fable   nova   onyx   sage   shimmer
```

Audition one without touching a clip:

```bash
python scripts/sound/tts_narrate.py --say "Measured, factual, unhurried." \
                                    --voice sage --out audition.mp3
```

`tts-1-hd` has no `instructions` parameter, so there is no way to ask the model
for a tone. Tone comes from the writing and the voice choice. Write it measured
and unhurried and it reads that way.

**Stock voices only.** Cloning a real person's voice requires that person's
recorded consent and is a policy question rather than a technical one.

## The two output shapes

Which one you get is decided by the clip folder, not by a flag.

| File in `output/<name>/` | Shape | Consumed by |
|---|---|---|
| `narration.md` | `audio/01.mp3 ... NN.mp3`, one take per scene | `build.py`, which pads each to its budget |
| `narration-script.md` | one `narration.wav`, every line laid at its cue | `pack.mjs --audio` |

A folder holding both is an error rather than a choice, and the script says so
rather than picking one.

The asymmetry is not an oversight. The mp4 pads each scene's take to its own
budget, so boundaries equal budgets by construction. The html deck has no such
boundaries: once audio is audible it becomes the master clock, so the track has
to be exactly as long as the timeline with each line starting on its own cue.

## Fitting takes to their budgets

**An over-budget take is an error, not a warning.** Padding can add silence; it
cannot shorten speech. One long take shifts every scene after it.

`--dry-run` reports words per second per scene and costs nothing:

```bash
python scripts/sound/tts_narrate.py --project output/<name> --dry-run
```

Above 2.5 w/s will overrun. Two legitimate fixes, and no third: **shorten the
copy**, or **raise the budget** in the narration file and let the scene re-time
itself. There is no speed control here, deliberately — a take sped up to fit is
a take that sounds sped up.

For the cue-laid shape the equivalent failure is a line running past the next
cue. It still plays, overlapping the following visual. The script lists every
clash and exits non-zero.

## AAC, for the html pipeline only

A 16-bit wav base64-inlines into the packed html at roughly 4 MB for 90s. Pass
`--aac` and it lands nearer 130 kB:

```bash
python scripts/sound/tts_narrate.py --project output/<name> --aac --install
```

This is the one step that wants ffmpeg, resolved through `scripts/toolchain.py`.
Without ffmpeg it prints a warning and keeps the wav, which still works and
still passes `check.mjs`.

## Provenance is not optional

Every run writes `provenance.json` beside its takes: provider, endpoint, model,
voice, and the per-take durations, with up to five levels of superseded history.

Keep it. The Cornerstone clips did not record theirs and consequently cannot be
re-recorded in the same voice today. Re-rendering meant re-choosing.

## The one real trap

`build.py` resolves `.mp3` before `.wav`, so a leftover take from an earlier run
silently wins over a new one. Before re-running a driver, list `audio/` and look
for two files with the same number and different extensions. If you find a pair,
rename the loser to `NN.mp3.superseded` rather than deleting it.

`tts_narrate.py` never overwrites. An existing file is renamed to
`<name>_removed.<ext>` and the move is recorded in `moved_files.txt`. That is
safe, but it does mean the stale sibling is still sitting there.

## What was and was not tested

- `--dry-run` parses both shapes, costs them and reports pace. Verified against
  fixtures for scenes, cues, the both-files error and the neither-file error.
- The endpoint settings are carried over from a gateway test on 17 September
  2026 and are documented in the script's own header.
- **No take has been synthesised from inside this plugin.** The first real call
  is the first real call. `--dry-run` is the cheap thing to do before it.
