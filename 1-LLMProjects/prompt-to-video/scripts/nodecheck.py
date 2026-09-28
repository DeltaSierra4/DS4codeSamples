#!/usr/bin/env python3
"""
Find node, wherever the user actually put it, and if it is not there yet, say
how to get it in words someone non-technical can act on.

WHY THIS EXISTS

This is `toolchain.py` for node rather than for ffmpeg, and `keycheck.py` for a
program rather than for a key. It exists for the same two reasons as both.

The first is the message. "Install Node 18+" names a concept rather than an
action, and the html pipeline is the one most likely to be run by someone who
has never installed a runtime. So the message below is numbered steps with one
line to copy, correct for the platform it is printed on.

The second is worse, because it happens to someone who did everything right.
On Windows the fix is:

    [Environment]::SetEnvironmentVariable("CLAUDE_VIDEO_NODE", "...", "User")

which writes to HKCU\\Environment. A process launched afterwards from Explorer
picks it up. A process launched by an *already running* Claude Code session does
not: it inherits that session's environment block, which was copied at launch
and is now stale. So the user pastes the command, says "done", the run retries,
and it fails again with the same message. That reads as a broken plugin.

RESOLUTION ORDER

  1. --node               the explicit flag, when a caller passes one.
  2. PATH                 the normal case, and the sandboxed case.
  3. CLAUDE_VIDEO_NODE    in this session's environment.
  4. Where it landed      win32: HKCU\\Environment, read through winreg.
                          darwin/linux: an `export` line in a shell profile.
  5. Known install dirs   the node installer, winget, chocolatey, scoop, nvm,
                          fnm, homebrew, apt, snap.

Step 4 is the whole point. It is what lets the run continue the moment they say
"done", with no restart, and it mirrors `keycheck.py` reading the registry and
`toolchain.py` looking into the install directories rather than trusting PATH.

PATH BEATS THE OVERRIDE HERE, AND THAT IS DELIBERATE

`toolchain.py` puts VIDEO_GEN_FFMPEG *ahead* of PATH, on the reasoning that
someone who sets the variable has a second ffmpeg they do not want used. Node
is the other way round on purpose: CLAUDE_VIDEO_NODE is set by the recovery flow
in `reference/node-setup.md`, by a user who had no node at all, so a real node
on PATH is the better answer whenever one exists. Changing this order changes
which install a user gets after they later install node properly.

THE SANDBOX IS NOT DETECTED, AND MUST NOT BE

There is no check for a harness name, a container, or a sandbox here.
Resolution succeeding *is* the sandboxed case: that environment ships node, step
2 finds it, and nothing is ever asked. Sniffing for a harness would put a
Windows PowerShell instruction inside a Linux container the first time someone
renamed an environment variable.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ENV_VAR = "CLAUDE_VIDEO_NODE"
MIN_MAJOR = 18
DOWNLOAD_URL = "https://nodejs.org/en/download"

# Read more profiles than we write to: someone may have set it by hand, years
# ago, somewhere else. Later files win, matching shell startup order loosely
# enough for this purpose. Same table as keycheck.py, kept local rather than
# imported so this file depends on nothing but the standard library.
_PROFILES = {
    "darwin": ("~/.profile", "~/.bash_profile", "~/.bashrc", "~/.zshrc", "~/.zprofile"),
}
_PROFILES_DEFAULT = ("~/.profile", "~/.bashrc", "~/.bash_profile", "~/.zshrc", "~/.zprofile")


def _exe(name: str = "node") -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


# ==========================================================================
# The two platform seams, as in keycheck.py. Keep them as module-level
# functions rather than inlining them: each one is dead on the other platform,
# so being able to substitute them is the only way to exercise both from one
# machine.
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
    if kind == getattr(winreg, "REG_EXPAND_SZ", 2):
        val = os.path.expandvars(val)
    return val.strip().strip('"').strip("'") or None


def _profile_scan(name: str) -> str | None:
    """Find `export NAME=value` in the user's shell profiles. Last one wins."""
    if sys.platform == "win32":
        return None
    pattern = re.compile(r"^\s*export\s+" + re.escape(name) + r"\s*=\s*(.*?)\s*$")
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
def _candidate_dirs() -> list[Path]:
    """Where the common installers put node, per platform."""
    out: list[Path] = []
    home = Path.home()

    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        prog = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        prog86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        out.append(prog / "nodejs")
        out.append(prog86 / "nodejs")
        out.append(local / "Programs" / "nodejs")
        out.append(local / "Microsoft" / "WinGet" / "Links")      # winget shims
        out.append(Path(r"C:\ProgramData\chocolatey\bin"))
        out.append(home / "scoop" / "shims")
        # nvm-windows and fnm both keep versioned folders. Newest first.
        nvm = Path(os.environ.get("NVM_HOME", home / "AppData" / "Roaming" / "nvm"))
        if nvm.is_dir():
            out.extend(sorted(nvm.glob("v*"), reverse=True))
        fnm = local / "fnm_multishells"
        if fnm.is_dir():
            out.extend(sorted(fnm.glob("*"), reverse=True))
    else:
        out.extend([Path("/opt/homebrew/bin"),                    # Apple silicon
                    Path("/usr/local/bin"),                       # Intel homebrew, apt
                    Path("/usr/bin"),
                    Path("/snap/bin")])
        nvm = Path(os.environ.get("NVM_DIR", home / ".nvm")) / "versions" / "node"
        if nvm.is_dir():
            out.extend(sorted((d / "bin" for d in nvm.glob("v*")), reverse=True))

    return out


def _resolve_raw(raw: str) -> Path | None:
    """Turn a user-supplied path into the node executable, or None.

    Accept either the folder or the binary itself; people pass both. Same rule
    as toolchain.py's _from_env, for the same reason. A `bin/` subfolder is
    also accepted, because that is what an unpacked standalone build looks like
    and it is what the install message tells them to download.
    """
    if not raw:
        return None
    p = Path(raw.strip().strip('"').strip("'")).expanduser()
    if p.is_file():
        return p
    for cand in (p / _exe(), p / "bin" / _exe()):
        if cand.is_file():
            return cand
    return None


def probe(exe: Path) -> tuple[int, str] | None:
    """(major, full version string) for a working node, else None."""
    try:
        r = subprocess.run([str(exe), "--version"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    ver = (r.stdout or "").strip()
    m = re.match(r"^v?(\d+)\.", ver)
    return (int(m.group(1)), ver) if m else None


# ==========================================================================
def _sources():
    """(raw path, human name) in search order, steps 2 to 5.

    Step 1, an explicit --node, is not here: resolve_node handles it by itself so
    that a path the user just typed can be rejected by name rather than silently
    falling through to PATH and reporting success for a different install.
    """
    on_path = shutil.which("node")
    if on_path:
        yield on_path, "PATH"

    yield os.environ.get(ENV_VAR, "").strip(), f"{ENV_VAR} in this session's environment"

    if sys.platform == "win32":
        yield (_win_user_env(ENV_VAR) or ""), f"{ENV_VAR} in your Windows user settings"
    else:
        yield (_profile_scan(ENV_VAR) or ""), f"{ENV_VAR} in your shell profile"

    for d in _candidate_dirs():
        yield str(d), f"a known install location ({d})"


def resolve_node(cli_node: str | None = None) -> tuple[str, Path | None, str]:
    """('ok' | 'old' | 'bad-path' | 'missing', exe, detail).

    Four outcomes rather than two, because the recovery differs for each:
      ok        a working node >= MIN_MAJOR. detail names the version and source.
      old       a working node, too old. detail names the version.
      bad-path  --node points somewhere that is not a node. Only ever returned
                for an explicit path, because a user who just typed one needs to
                hear that it was wrong rather than watch it be ignored.
      missing   nothing usable found anywhere.
    """
    if cli_node:
        exe = _resolve_raw(cli_node)
        if exe is None:
            return "bad-path", None, f"{cli_node}\n  is not a node executable, and holds no {_exe()}."
        got = probe(exe)
        if got is None:
            return "bad-path", exe, f"{exe}\n  exists but does not run as node."
        major, ver = got
        return ("ok" if major >= MIN_MAJOR else "old"), exe, f"{ver} (via the path you gave)"

    best_old: tuple[Path, str] | None = None
    for raw, where in _sources():
        if not raw:
            continue
        exe = _resolve_raw(raw)
        if exe is None:
            continue
        got = probe(exe)
        if got is None:
            continue
        major, ver = got
        if major >= MIN_MAJOR:
            return "ok", exe, f"{ver} (via {where})"
        if best_old is None:
            best_old = (exe, f"{ver} (via {where})")

    if best_old:
        return "old", best_old[0], best_old[1]
    return "missing", None, ""


# ==========================================================================
# The messages. Printed verbatim by the agent, never reworded. The install and
# register variants differ deliberately: install opens with the download and
# ends "say done", register has no download step and ends by naming the option
# to click. Do not converge them.
# ==========================================================================
def _opener() -> str:
    if sys.platform == "win32":
        return "Open Windows PowerShell: Press the Windows key, type powershell, press Enter."
    if sys.platform == "darwin":
        return "Open Terminal: Press Command and Space together, type terminal, press Enter."
    return "Open a terminal."


def _set_line() -> str:
    if sys.platform == "win32":
        return f'     [Environment]::SetEnvironmentVariable("{ENV_VAR}", "NODE-PATH-HERE", "User")'
    profile = "~/.zprofile" if sys.platform == "darwin" else "~/.profile"
    return f"""     echo 'export {ENV_VAR}="NODE-PATH-HERE"' >> {profile}"""


def install_message() -> str:
    """Five steps: download, open a shell, set the variable, enter, come back."""
    return (
        f"1. Download the Standalone Binary of Node.js from {DOWNLOAD_URL}\n"
        "\n"
        f"2. {_opener()}\n"
        "\n"
        "3. Copy the line below, paste it in, and replace NODE-PATH-HERE with "
        "the path to your Node.js binary installation. Keep the quote marks.\n"
        "\n"
        f"{_set_line()}\n"
        "\n"
        "4. Press Enter. Nothing is printed when it works. That is normal.\n"
        "\n"
        "5. Come back here and say done.\n"
    )


def register_message() -> str:
    """Four steps. They already have node; this only saves them the next ask."""
    return (
        f"1. {_opener()}\n"
        "\n"
        "2. Copy the line below, paste it in, and replace NODE-PATH-HERE with "
        "the path to your Node.js installation. Keep the quote marks.\n"
        "\n"
        f"{_set_line()}\n"
        "\n"
        "3. Press Enter. Nothing is printed when it works. That is normal.\n"
        "\n"
        '4. Come back here and selection the first option "done".\n'
    )


def too_old_message(detail: str) -> str:
    return (
        f"node {detail} was found, but this pipeline needs Node {MIN_MAJOR} or newer.\n"
        "\n"
        f"Install a current one from {DOWNLOAD_URL}, then point at it directly:\n"
        "\n"
        f"{_set_line()}\n"
    )


# ==========================================================================
def report(cli_node: str | None = None) -> int:
    """Print what was found. Exit code is the answer: 0 found, 1 not."""
    status, exe, detail = resolve_node(cli_node)

    if status == "ok":
        print(f"node found: {detail}")
        print(f"NODE_EXE={exe}")
        return 0

    if status == "old":
        print(too_old_message(detail))
        return 1

    if status == "bad-path":
        print("That is not a usable Node installation.\n"
              f"\n  {detail}\n"
              "\n  Point at the folder holding it, or at the executable itself.")
        return 1

    print("Node is not installed on this machine, and the html pipeline needs it\n"
          "to pack and check the deck. This is a one-time setup step.\n")
    print(install_message(), end="")
    return 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--help-install" in args:
        print(install_message(), end="")
        sys.exit(0)
    if "--help-register" in args:
        print(register_message(), end="")
        sys.exit(0)
    given = None
    if "--node" in args:
        i = args.index("--node")
        if i + 1 >= len(args):
            sys.exit("--node needs a path after it.")
        given = args[i + 1]
    sys.exit(report(given))
