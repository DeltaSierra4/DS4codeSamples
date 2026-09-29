# Node setup

The html pipeline packs and checks a deck with three Node scripts. Nothing else
in this plugin needs Node: `/video-full` renders an mp4 through Pillow and
ffmpeg and never touches it.

`scripts/nodecheck.py` owns every part of finding it, and the search goes deeper
than the environment this session was launched with:

| Order | Looked in |
|---|---|
| 1 | `--node` on the command line |
| 2 | `node` on PATH |
| 3 | `CLAUDE_VIDEO_NODE` in this session's environment |
| 4 | Windows: `HKCU\Environment`. macOS and Linux: an `export` line in a shell profile |
| 5 | Known install dirs: the node installer, winget, chocolatey, scoop, nvm, fnm, homebrew, apt, snap |

Step 4 is not a nicety. The fix a Windows user is given writes to the registry,
and an already running Claude Code session cannot see it, because a child
process inherits the environment block copied at launch. Without step 4 the user
follows the instruction correctly, the run retries, and it fails again with the
same message. That is the trap `scripts/toolchain.py` already defuses for ffmpeg
and `scripts/sound/keycheck.py` for the gateway key, in the same shape.

**PATH beats `CLAUDE_VIDEO_NODE` here**, which is the reverse of how
`toolchain.py` treats `VIDEO_GEN_FFMPEG`. The override exists for someone who
had no node at all, so once a real one is on PATH it is the better answer. The
docstring says so; do not "fix" the order to match ffmpeg.

## There is no sandbox check, and there must not be

On a machine that ships Node, step 2 finds it and nothing below this line ever
happens. That is the whole environment branch. Resolution succeeding **is** the
sandboxed case.

Do not add a check for a harness name, a container marker, or an environment
variable that happens to be set in one place and not another. The first time one
of those is renamed, a Windows PowerShell instruction gets printed inside a
Linux container.

## The check

Run it when `/video-quick` is invoked, not at pack time:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/nodecheck.py    # exit 0 found, exit 1 not
```

Exit 0 prints a final line `NODE_EXE=<absolute path>`. **Say nothing about Node
and carry straight on.** A user whose machine is set up correctly should never
learn this file exists.

Checking up front rather than at step 5 is the same rule `reference/gate.md`
applies to the narration key: discovering the problem after a deck has been
written and timed wastes the whole run.

## When node is not found

`nodecheck.py` prints numbered steps with a single line to copy, already correct
for the platform it ran on. **Print that message exactly as the script emitted
it.** Do not reword it, do not summarise it, do not add a second way of doing
it. It is one instruction on purpose, and a paraphrase is how someone ends up
holding two half-instructions and following neither.

Then stop and `AskUserQuestion`:

| Option | Means | Then |
|---|---|---|
| Install Node | They have no node and will get one | Print `nodecheck.py --help-install` verbatim, then stop and wait. See below |
| Provide path to a pre-existing installation | It is on the machine, just not findable | Ask for the path, then the second gate below |
| Abort the workflow | Not now | Stop. Write nothing, draft no deck, do not offer `/video-full` as a consolation unless they ask |

### Install Node

Print the message, stop, and wait for them to come back. When they say done,
re-run `nodecheck.py`. Step 4 reads the value they just set, so **this works
without restarting anything** and that is the entire reason the script exists.

Exit 0: carry on, and say nothing further about Node. Exit 1: say plainly that
the value did not come through, and offer the same three options again. If a
second attempt also fails they have most likely set it somewhere this cannot
reach, and the escape hatch that always works is to close Claude Code, open it
again, and run the command again.

### Provide path to a pre-existing installation

Ask for the path in free text. Either the folder or the `node` binary itself is
fine, and so is a folder with `bin/node` inside it, which is what an unpacked
standalone build looks like.

Validate it before going any further:

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/nodecheck.py --node "<their path>"
```

A path that is not a working Node 18 or newer is rejected by name, with the
reason. Say what the script said and ask again. Do not carry a bad path into the
build: it turns one clear message into three failing commands.

Once it validates, print `nodecheck.py --help-register` verbatim and
`AskUserQuestion` with exactly two options:

| Option | Then |
|---|---|
| `done` | Re-run `nodecheck.py` with no `--node`. It should now resolve on its own |
| `I do not wish to provide the path to the installation.` | Nothing further |

**Either answer continues the run with the path they gave.** This gate is an
optional convenience that saves them the question on the next run; it is never a
condition of proceeding. Do not re-ask, do not press the point, and do not treat
the second option as a refusal to continue.

## Using what was resolved

The build commands are written as the bare word `node`, which is right when it
is on PATH. When it was resolved any other way, **substitute the `NODE_EXE`
value for `node`** in all three:

```bash
"$NODE_EXE" build/test-player.mjs
"$NODE_EXE" build/pack.mjs src/<name>.html ../../output/<name>/<name>.html
"$NODE_EXE" build/check.mjs ../../output/<name>/<name>.html
```

Quote it. The usual answer on Windows is under `C:\Program Files\`, and an
unquoted path with a space in it fails in a way that looks like a broken script
rather than a quoting mistake.

## What is not covered

`/add-sound` runs `pack.mjs` and `check.mjs` too, and has no preflight of its
own. Reached the normal way, through `/video-quick` or `/video-generate`, node
has already been resolved and it is fine. Run standalone against an existing
html deck on a machine with no node, it still fails at the command itself.

## What was and was not tested

- Resolution order, both message variants on all three platforms, the bad-path
  rejection, and the registry read defeating a stale environment block are all
  verified against a machine with no node installed.
- **No deck has been packed through this.** The first run on a machine with node
  is the first real exercise of the html pipeline end to end.
