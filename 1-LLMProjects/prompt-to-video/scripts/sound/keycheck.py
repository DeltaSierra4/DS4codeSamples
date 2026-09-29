#!/usr/bin/env python3
"""
Find the narration key, wherever the user actually put it, and if it is not
there yet, say how to set it in words someone non-technical can act on.

WHY THIS EXISTS

This is `toolchain.py` for the gateway key rather than for ffmpeg, and it exists
for the same reason. Three failures, and each one is worse than the last.

The first is the message. "Set CLIENT_GENAI_KEY" names a concept rather than an
action. Most people who use this plugin have never set an environment variable
and should not have to learn what one is to narrate a video. So the message
below is four numbered steps with one line to copy, correct for the platform it
is printed on.

The second is worse, because it happens to someone who did everything right.
On Windows the fix is:

    [Environment]::SetEnvironmentVariable("CLIENT_GENAI_KEY", "...", "User")

which writes to HKCU\\Environment. A process launched afterwards from Explorer
picks it up. A process launched by an *already running* Claude Code session does
not: it inherits that session's environment block, which was copied at launch
and is now stale. So the user pastes the command, says "done", the run retries,
and it fails again with the same message. That reads as a broken plugin, and it
is the first thing a new user hits.

The third is worse again, and it is why --platform exists. Some harnesses run
this script inside a Linux sandbox while the person reading its output is
sitting at a Windows machine. Then sys.platform is the truth about the process
and a lie about the user, and both halves of the message break at once. They are
handed an `export` line for an operating system they are not using, and even the
correct line would not have helped: a variable set on their own machine is not
readable from inside that sandbox by any of the routes below. The instruction
gets followed correctly and fails anyway, with no way out of the loop.

THE PLATFORM DECLARATION

--platform is how the caller states which operating system the person reading
the output is on. It is a declaration, never a detection.

This is deliberately not the thing `reference/node-setup.md` forbids. That rule
bans inferring a sandbox from a harness name, a container marker, or an
environment variable that happens to be set in one place and not another, all of
which rot the first time somebody renames one. Nothing here sniffs for any of
those. The caller says what the user's machine is, this script compares that to
its own sys.platform, and the only thing that changes is which message prints.

  declared == running   the ordinary case. Nothing changes, nothing is written.
  declared is None      nobody said, so assume this process is on the user's
                        machine. That was the only behaviour before --platform
                        existed and it is right nearly always.
  declared != running   the steps below cannot work, because the variable would
                        be set somewhere this process cannot read. So do not
                        print them. Write key_settings.json and ask for the key
                        there instead.

RESOLUTION ORDER

  1. --key                the explicit flag, when a caller passes one.
  2. Process environment  the normal case: already set before launch.
  3. key_settings.json    the hand-off file, at the plugin root or the cwd.
  4. Where it landed      win32: HKCU\\Environment, read through winreg.
                          darwin/linux: an `export` line in a shell profile.

Step 4 is the whole point on a normal machine. It is what lets the run continue
the moment they say "done", with no restart, and it mirrors toolchain.py looking
into the install directories rather than trusting PATH. Step 3 is what replaces
it when step 4 would be looking at the wrong machine entirely.

Step 3 sits above step 4 because the file is written by hand for this run, while
a profile line may have been written years ago and forgotten. A file someone
just filled in should win over one they do not remember.

key_settings.json holds a live secret in plain text. It is in .gitignore, it is
never written over the top of an existing one, and `--forget` deletes it. Run
that at the end of any run that needed it. It must not outlive the run.

TWO VARIABLES

CLIENT_GENAI_KEY is checked before OPENAI_API_KEY, at every level. Someone with
both set has the Client one for a reason.

NOTHING HERE PRINTS A KEY

This module's stdout is read by an agent and lands in a conversation transcript.
Every path prints `redact(key)` and the name of the source, never the value.
`redact` lives here rather than in tts_narrate.py so that importing it cannot
become circular.

That applies to key_settings.json with full force, and it is the reason this
script reads the file rather than leaving it to a caller. No agent should ever
`cat` that file. The moment one does, the key is in the transcript, on disk, and
has to be rotated.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from pathlib import Path

# Primary first. Order matters at every level of the search.
ENV_VARS = ("CLIENT_GENAI_KEY", "OPENAI_API_KEY")

# The hand-off file, used only when this process is not on the user's machine.
KEY_FILE_NAME = "key_settings.json"

# scripts/sound/keycheck.py -> scripts/sound -> scripts -> the plugin root.
PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# Read more profiles than we write to: someone may have set it by hand, years
# ago, somewhere else. Later files win, matching shell startup order loosely
# enough for this purpose.
_PROFILES = {
    "darwin": ("~/.profile", "~/.bash_profile", "~/.bashrc", "~/.zshrc", "~/.zprofile"),
}
_PROFILES_DEFAULT = ("~/.profile", "~/.bashrc", "~/.bash_profile", "~/.zshrc", "~/.zprofile")

# The three platforms this plugin has instructions for, and the spellings a
# caller might reasonably hand us. An unrecognised value is rejected by name
# rather than guessed at, because guessing is the exact failure --platform is
# here to stop.
_PLATFORM_ALIASES = {
    "win32": "win32", "win": "win32", "windows": "win32", "nt": "win32",
    "cygwin": "win32", "msys": "win32",
    "darwin": "darwin", "mac": "darwin", "macos": "darwin", "osx": "darwin",
    "mac os": "darwin", "mac os x": "darwin",
    "linux": "linux", "linux2": "linux", "wsl": "linux", "unix": "linux",
}
_PLATFORM_NAMES = {"win32": "Windows", "darwin": "macOS", "linux": "Linux"}


def redact(key: str) -> str:
    """The only representation of a key this plugin ever prints."""
    if not key:
        return "(empty)"
    return f"{key[:6]}...{key[-4:]}  ({len(key)} chars)" if len(key) > 10 else key[:3] + "..."


# ==========================================================================
# Platform. Two functions that never do each other's job: one normalises what a
# caller said, one reports what this process is. Comparing them is the whole
# mechanism, and keeping them apart is what stops a detection creeping into the
# declaration.
# ==========================================================================
def normalize_platform(value: str) -> str:
    """One of win32, darwin, linux. Raises ValueError on anything else."""
    key = " ".join(value.strip().lower().replace("-", " ").replace("_", " ").split())
    try:
        return _PLATFORM_ALIASES[key]
    except KeyError:
        raise ValueError(
            f"unknown platform {value!r}. "
            "Use one of: auto, windows, macos, linux"
        ) from None


def running_platform() -> str:
    """What this process is on, folded to the three we have instructions for."""
    if sys.platform.startswith("win") or sys.platform in ("cygwin", "msys"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def platform_name(p: str) -> str:
    """The spelling a person recognises, for messages."""
    return _PLATFORM_NAMES.get(p, p)


# ==========================================================================
# The two platform seams. Keep them as module-level functions rather than
# inlining them into find_key: each one is dead on the other platform, so being
# able to substitute them is the only way to exercise both from one machine.
# ==========================================================================
def _win_user_env(name: str) -> str | None:
    """Read one value from HKCU\\Environment. Read-only, stdlib, no elevation."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:                                   # pragma: no cover
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            val, kind = winreg.QueryValueEx(k, name)
    except (FileNotFoundError, OSError):
        return None
    if not isinstance(val, str):
        return None
    # REG_EXPAND_SZ is unlikely for a key, but costs one call to handle.
    if kind == getattr(winreg, "REG_EXPAND_SZ", 2):
        val = os.path.expandvars(val)
    return val.strip().strip('"').strip("'") or None


def _profile_scan(name: str) -> str | None:
    """Find `export NAME=value` in the user's shell profiles. Last one wins."""
    if sys.platform == "win32":
        return None
    pattern = re.compile(
        r"^\s*export\s+" + re.escape(name) + r"\s*=\s*(.*?)\s*$")
    found = None
    for rel in _PROFILES.get(sys.platform, _PROFILES_DEFAULT):
        p = Path(rel).expanduser()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = pattern.match(line)
            if not m:                       # a commented line never matches,
                continue                    # because ^\s*export cannot start with #
            raw = m.group(1)
            # Strip a trailing inline comment only when the value is unquoted.
            if raw[:1] not in ("'", '"'):
                raw = raw.split("#", 1)[0].strip()
            val = raw.strip().strip('"').strip("'")
            if val:
                found = val
    return found


# ==========================================================================
# The hand-off file. Only ever written on a platform mismatch, but the reader
# runs unconditionally: a file somebody left behind should be found and reported
# rather than sitting there holding a live key that nothing admits to.
# ==========================================================================
def key_file_candidates() -> list[Path]:
    """Where the file is looked for. Plugin root first, then the cwd.

    Two locations because the plugin root is where this script writes it and
    where .gitignore covers it, while the cwd is where someone told "the working
    directory" may reasonably have put it instead.
    """
    seen: set[Path] = set()
    out: list[Path] = []
    for base in (PLUGIN_ROOT, Path.cwd()):
        try:
            p = (base / KEY_FILE_NAME).resolve()
        except OSError:                                   # pragma: no cover
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _key_file_scan() -> tuple[str, str, Path] | None:
    """Pull a key out of the file. Never returns, logs or raises its value."""
    for path in key_file_candidates():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue                # a broken file is key_file_state's problem
        if not isinstance(data, dict):
            continue
        for name in ENV_VARS:
            val = data.get(name)
            if isinstance(val, str) and val.strip():
                return val.strip(), name, path
    return None


def key_file_state() -> tuple[str, Path | None]:
    """absent, empty, broken or filled, and the file being described.

    Separate from _key_file_scan because someone who already made the file and
    left it blank needs a different sentence from someone who has never seen it,
    and someone whose hand-edit broke the JSON needs a third.
    """
    first: Path | None = None
    for path in key_file_candidates():
        if not path.exists():
            continue
        first = first or path
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return "broken", path
        if not isinstance(data, dict):
            return "broken", path
        if any(isinstance(data.get(n), str) and data[n].strip() for n in ENV_VARS):
            return "filled", path
    return ("empty", first) if first is not None else ("absent", None)


def ensure_key_file() -> tuple[Path, bool]:
    """Write the blank file if there is not one. Never overwrite.

    Returns the path and whether this call created it. Overwriting would throw
    away a key that had just been pasted in, which is exactly the state the
    file is in on the re-check after someone says done.
    """
    _, existing = key_file_state()
    if existing is not None:
        return existing, False
    path = PLUGIN_ROOT / KEY_FILE_NAME
    path.write_text(
        json.dumps({name: "" for name in ENV_VARS}, indent=2) + "\n",
        encoding="utf-8")
    return path, True


def forget_key_file() -> tuple[list[Path], list[str]]:
    """Delete every copy. Idempotent. Returns what went and what would not."""
    removed: list[Path] = []
    problems: list[str] = []
    for path in key_file_candidates():
        if not path.exists():
            continue
        try:
            path.unlink()
        except OSError as exc:
            problems.append(f"{path}: {exc}")
            continue
        removed.append(path)
    return removed, problems


# ==========================================================================
def find_key() -> tuple[str, str, str] | None:
    """The key, the variable it came from, and a human name for where it was.

    Returns None when no key is set anywhere this can see.
    """
    for name in ENV_VARS:
        val = os.environ.get(name, "").strip()
        if val:
            return val, name, "this session's environment"

    hit = _key_file_scan()
    if hit is not None:
        val, name, path = hit
        return val, name, f"{KEY_FILE_NAME} in {path.parent}"

    for name in ENV_VARS:
        val = _win_user_env(name)
        if val:
            return val, name, "your Windows user settings"

    for name in ENV_VARS:
        val = _profile_scan(name)
        if val:
            return val, name, "your shell profile"

    return None


# ==========================================================================
# Three messages, one per situation. All three are printed verbatim by callers
# and none of them is ever reworded, so the wording here is the interface.
# ==========================================================================
def steps_message(target: str) -> str:
    """The four steps, correct for `target`. The ordinary case."""
    if target == "win32":
        opener = ("  1. Open Windows PowerShell.\n"
                  "     Press the Windows key, type powershell, press Enter.\n")
        line = ('     [Environment]::SetEnvironmentVariable('
                f'"{ENV_VARS[0]}", "PASTE-YOUR-KEY-HERE", "User")\n')
    elif target == "darwin":
        opener = ("  1. Open Terminal.\n"
                  "     Press Command and Space together, type terminal, press Enter.\n")
        line = (f"     echo 'export {ENV_VARS[0]}=\"PASTE-YOUR-KEY-HERE\"'"
                " >> ~/.zprofile\n")
    else:
        opener = "  1. Open a terminal.\n"
        line = (f"     echo 'export {ENV_VARS[0]}=\"PASTE-YOUR-KEY-HERE\"'"
                " >> ~/.profile\n")

    return (
        "No narration key is set yet. This is a one-time setup step and it\n"
        "takes about a minute.\n"
        "\n"
        + opener +
        "\n"
        "  2. Copy the line below, paste it in, and replace PASTE-YOUR-KEY-HERE\n"
        "     with your own key. Keep the quote marks.\n"
        "\n"
        + line +
        "\n"
        "  3. Press Enter. Nothing is printed when it works. That is normal.\n"
        "\n"
        "  4. Come back here and say done.\n"
        "\n"
        "You do not need to restart anything, and you do not need to type your\n"
        "key into the chat.\n"
    )


def _blank_file_shape(indent: str) -> str:
    """The file as it is actually written, so message and file cannot drift."""
    body = json.dumps({name: "" for name in ENV_VARS}, indent=2)
    return "".join(f"{indent}{ln}\n" for ln in body.splitlines())


def handoff_message(declared: str, running: str, path: Path, created: bool) -> str:
    """What to print when this check is not running on the user's machine.

    No PowerShell line and no export line, on purpose. Either one would be
    followed correctly and fail anyway, because nothing set over there is
    readable from in here. Saying that plainly is the point of the message.
    """
    made = ("A file has been created for you:\n" if created
            else "There is already a file waiting for you:\n")
    # Wrapped rather than hand-broken: the two platform names are substituted
    # in, so any fixed line breaks go ragged the moment the pair changes.
    lead = textwrap.fill(
        "No narration key is set yet, and this check is not running on your own "
        f"machine. You are on {platform_name(declared)}. This check is running "
        f"on {platform_name(running)}, in a sandbox that cannot read anything "
        "you set over there. So the usual one-line fix would not reach it, and "
        "you are not being given one. Do this instead.",
        width=70)
    return (
        lead + "\n"
        "\n"
        + made +
        "\n"
        f"  {path}\n"
        "\n"
        "  1. Open it. It looks like this:\n"
        "\n"
        + _blank_file_shape("     ") +
        "\n"
        "  2. Paste your key between the empty quote marks on the\n"
        f"     {ENV_VARS[0]} line. Fill in one line, not both. Keep the\n"
        "     quote marks and the comma.\n"
        "\n"
        "  3. Save the file, come back here, and say done.\n"
        "\n"
        "Do not type your key into the chat. Nothing reads this file out loud,\n"
        "and it is deleted at the end of the run.\n"
    )


def broken_file_message(path: Path) -> str:
    """A hand-edited JSON file breaks in three places. Name all three."""
    return (
        f"{KEY_FILE_NAME} is there, but it can no longer be read as JSON.\n"
        "\n"
        f"  {path}\n"
        "\n"
        "A hand-edit usually breaks one of three things. Check all three:\n"
        "\n"
        "  - both quote marks around the key you pasted\n"
        "  - the comma at the end of the first line\n"
        "  - the braces at the top and the bottom\n"
        "\n"
        "It should look exactly like this, with your key in place of the first\n"
        "pair of empty quote marks:\n"
        "\n"
        + _blank_file_shape("  ") +
        "\n"
        "Fix it, save, and say done. Do not paste your key into the chat.\n"
    )


def missing_message(declared: str | None = None) -> str:
    """The right instruction for whoever is reading this. Never reworded.

    `declared` is the caller's statement of the user's own platform. None means
    nobody said, so assume this process is on it.

    On a mismatch this writes key_settings.json as a side effect, which a
    function named for a message should not normally do. It does it because the
    entire content of that message is "open this file", and a message naming a
    file that is not there is worse than a function doing two things.
    """
    running = running_platform()
    if declared is None or declared == running:
        return steps_message(running)

    state, existing = key_file_state()
    if state == "broken" and existing is not None:
        return broken_file_message(existing)
    path, created = ensure_key_file()
    return handoff_message(declared, running, path, created)


def resolve_key(cli_key: str | None = None, required: bool = True,
                declared: str | None = None) -> str:
    """The one entry point callers use. Exits with the right steps if required.

    On success the key is written back into os.environ, so anything downstream
    that reads the variable directly keeps working unchanged. That mirrors
    toolchain.py prepending its directory to PATH for the same reason.
    """
    if cli_key:
        return cli_key

    found = find_key()
    if found is None:
        if required:
            sys.exit("\n" + missing_message(declared))
        return ""

    key, name, _ = found
    os.environ[name] = key
    return key


def report_key(declared: str | None = None) -> int:
    """Print what was found, without the key. Exit code is the answer: 0 or 1."""
    found = find_key()
    if found is None:
        print(missing_message(declared))
        return 1
    key, name, where = found
    print(f"Narration key found in {name}, via {where}: {redact(key)}")

    # A live key sitting in a file is the one success worth interrupting for.
    # Silence here is how it gets left behind.
    state, path = key_file_state()
    if state == "filled" and path is not None:
        print(f"\nThat key is in {path}, which holds it in plain text.\n"
              f"Run `python {Path(__file__).name} --forget` when the run is "
              "finished.")
    return 0


# ==========================================================================
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Say whether a narration key is set, and how to set one if "
                    "it is not. Calls nothing. Never prints a key.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--platform", default="auto", metavar="OS",
        help="the operating system of the person reading this output: auto, "
             "windows, macos or linux. A declaration by the caller, never a "
             "detection. Pass it whenever this script may be running somewhere "
             "other than the user's own machine, such as a sandbox. Default "
             "auto, meaning assume this process is on it")
    ap.add_argument(
        "--forget", action="store_true",
        help=f"delete {KEY_FILE_NAME} and exit. Run this at the end of any run "
             "that used one. Safe when there is no file")
    args = ap.parse_args(argv)

    if args.forget:
        removed, problems = forget_key_file()
        for p in removed:
            print(f"Deleted {p}")
        for p in problems:
            print(f"Could not delete {p}", file=sys.stderr)
        if not removed and not problems:
            print(f"No {KEY_FILE_NAME} to delete.")
        return 1 if problems else 0

    declared = None
    if args.platform.strip().lower() != "auto":
        try:
            declared = normalize_platform(args.platform)
        except ValueError as exc:
            print(f"--platform: {exc}", file=sys.stderr)
            return 2
    return report_key(declared)


if __name__ == "__main__":
    sys.exit(main())
