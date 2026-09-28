#!/usr/bin/env python3
"""
Find ffmpeg and ffprobe, wherever the installer actually put them.

WHY THIS EXISTS

`winget install Gyan.FFmpeg` prints "Path environment variable modified; restart
your shell to use the new value." Almost nobody restarts their shell. So the
first-run sequence is: run a video command, be told ffmpeg is missing, install
ffmpeg, run it again, and be told ffmpeg is missing a second time. That reads as
a broken plugin rather than a stale PATH, and it is the first thing a new user
hits.

So rather than trusting PATH, look in the places the three common installers put
things, and if it still is not found, say both halves of the answer: how to
install it, and that an existing terminal will not see it until it is restarted.

RESOLUTION ORDER

  1. $VIDEO_GEN_FFMPEG    explicit wins. A directory, or the binary itself.
  2. PATH                 the normal case.
  3. Known install dirs   winget, chocolatey, scoop, homebrew, MacPorts, apt.

An explicit override beats PATH deliberately: someone who sets the variable has
a reason, usually a second ffmpeg they do not want used.

Whatever is found is prepended to this process's PATH, so every existing
subprocess call spelled ["ffmpeg", ...] keeps working unchanged.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ENV_VAR = "VIDEO_GEN_FFMPEG"

_INSTALL_HINT = {
    "win32": "winget install Gyan.FFmpeg",
    "darwin": "brew install ffmpeg",
}
_INSTALL_DEFAULT = "apt-get install -y ffmpeg   (or your distribution's equivalent)"


def _candidate_dirs() -> list[Path]:
    """Where the common installers put ffmpeg, per platform."""
    out: list[Path] = []
    home = Path.home()

    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        # winget's Gyan build unpacks under a versioned folder, so glob it.
        pkgs = local / "Microsoft" / "WinGet" / "Packages"
        if pkgs.is_dir():
            out.extend(sorted(pkgs.glob("Gyan.FFmpeg*/ffmpeg-*/bin"), reverse=True))
        out.append(local / "Microsoft" / "WinGet" / "Links")   # winget shims
        out.append(Path(r"C:\ffmpeg\bin"))
        out.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin")
        out.append(Path(r"C:\ProgramData\chocolatey\bin"))
        out.append(home / "scoop" / "shims")
    elif sys.platform == "darwin":
        out.append(Path("/opt/homebrew/bin"))                   # Apple silicon
        out.append(Path("/usr/local/bin"))                      # Intel homebrew
        out.append(Path("/opt/local/bin"))                      # MacPorts
    else:
        out.extend([Path("/usr/bin"), Path("/usr/local/bin"), Path("/snap/bin")])

    return out


def _exe(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _dir_has(d: Path, names: tuple[str, ...]) -> bool:
    return d.is_dir() and all((d / _exe(n)).is_file() for n in names)


def _from_env(names: tuple[str, ...]) -> Path | None:
    raw = os.environ.get(ENV_VAR, "").strip().strip('"')
    if not raw:
        return None
    p = Path(raw).expanduser()
    # Accept either the folder or the binary itself; people pass both.
    d = p.parent if p.is_file() else p
    if _dir_has(d, names):
        return d
    sys.exit(
        f"{ENV_VAR} is set to {raw}\n"
        f"  but {', '.join(names)} are not both there.\n"
        f"  Point it at the folder containing them, or at {_exe(names[0])} itself,\n"
        f"  or unset it to fall back to PATH."
    )


def find_ffmpeg_dir(names: tuple[str, ...] = ("ffmpeg", "ffprobe")) -> Path | None:
    """The directory holding all of `names`, or None."""
    override = _from_env(names)
    if override:
        return override

    if all(shutil.which(n) for n in names):
        found = Path(shutil.which(names[0])).parent
        return found

    for d in _candidate_dirs():
        if _dir_has(d, names):
            return d
    return None


def missing_message(names: tuple[str, ...]) -> str:
    hint = _INSTALL_HINT.get(sys.platform, _INSTALL_DEFAULT)
    return (
        f"{' and '.join(names)} not found.\n"
        f"\n"
        f"  Install it:   {hint}\n"
        f"\n"
        f"  Already installed? An open terminal does not pick up a new PATH.\n"
        f"  Close this one and run the command in a fresh terminal.\n"
        f"\n"
        f"  Installed somewhere unusual? Point at it directly:\n"
        + (f"      set {ENV_VAR}=C:\\path\\to\\ffmpeg\\bin\n"
           if sys.platform == "win32"
           else f"      export {ENV_VAR}=/path/to/ffmpeg/bin\n")
    )


def ensure_ffmpeg(names: tuple[str, ...] = ("ffmpeg", "ffprobe"),
                  required: bool = True) -> Path | None:
    """Put ffmpeg on this process's PATH. Exit with advice if it is not found.

    Returns the directory, or None when `required` is False and nothing was
    found. Callers that already spell subprocess args as "ffmpeg" need no other
    change: prepending the directory to PATH is what makes those resolve.
    """
    d = find_ffmpeg_dir(names)
    if d is None:
        if required:
            sys.exit(missing_message(names))
        return None
    current = os.environ.get("PATH", "")
    if str(d) not in current.split(os.pathsep):
        os.environ["PATH"] = str(d) + os.pathsep + current
    return d


if __name__ == "__main__":
    found = find_ffmpeg_dir()
    if found is None:
        print(missing_message(("ffmpeg", "ffprobe")))
        sys.exit(1)
    src = "override" if os.environ.get(ENV_VAR) else (
        "PATH" if shutil.which("ffmpeg") else "known install location")
    print(f"ffmpeg and ffprobe found in {found}  (via {src})")
