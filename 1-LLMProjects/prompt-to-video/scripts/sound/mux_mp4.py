#!/usr/bin/env python3
"""
Lay a single continuous audio track over a finished mp4.

This is the /add-sound path for a recording the user supplies whole: a voiceover
they read in one take, a Teams recording, a music bed. It does not re-render the
video. The video stream is copied through byte for byte, so there is no
generation loss and the mux takes about a second.

    python3 mux_mp4.py --video out/clip-silent.mp4 --audio take.m4a --out out/clip.mp4
    python3 mux_mp4.py --video out/clip-silent.mp4 --audio meeting.mp4 --out out/clip.mp4

The audio input may itself be a video container. Teams hands people an .mp4 far
more often than a .wav, so the audio stream is extracted from whatever is given.

For narration written per scene, do NOT use this. Drop the takes into the clip's
audio/ folder as 01.mp3 ... NN.mp3 and re-run the clip's driver instead: build.py
pads every section to its budget, which puts each scene's speech on its own
boundary by construction. This script cannot do that, because one continuous
track has no section boundaries to pad.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from toolchain import ensure_ffmpeg  # noqa: E402  the sys.path line must run first

AUDIO_ONLY = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}


def probe(path: Path, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries,
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()


def duration(path: Path) -> float:
    raw = probe(path, "format=duration")
    try:
        return float(raw.splitlines()[0])
    except (ValueError, IndexError):
        sys.exit(f"Could not read a duration from {path}. Is it a media file?")


def has_audio(path: Path) -> bool:
    return "audio" in probe(path, "stream=codec_type").splitlines()


def extract(src: Path, scratch: Path) -> Path:
    """Pull the audio stream out of a video container."""
    dst = scratch / "extracted.m4a"
    print(f"  extracting audio from {src.name} ...", end="", flush=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-vn", "-c:a", "aac", "-b:a", "160k", str(dst)],
        check=True,
    )
    print(f" {duration(dst):.2f}s")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True, type=Path, help="the silent mp4")
    ap.add_argument("--audio", required=True, type=Path,
                    help="audio file, or a video to take the audio from")
    ap.add_argument("--out", required=True, type=Path, help="where to write the result")
    ap.add_argument("--bitrate", default="160k", help="aac bitrate (default 160k)")
    args = ap.parse_args()

    ensure_ffmpeg()
    for p in (args.video, args.audio):
        if not p.is_file():
            sys.exit(f"Not found: {p}")

    if args.out.resolve() == args.video.resolve():
        sys.exit("--out must differ from --video. Muxing in place would truncate the input.")

    v_dur = duration(args.video)
    print(f"video  {args.video.name}  {v_dur:.2f}s")

    scratch = args.out.parent
    scratch.mkdir(parents=True, exist_ok=True)

    track = args.audio
    if args.audio.suffix.lower() not in AUDIO_ONLY:
        if not has_audio(args.audio):
            sys.exit(f"{args.audio.name} carries no audio stream. Nothing to lay over the video.")
        track = extract(args.audio, scratch)

    a_dur = duration(track)
    print(f"audio  {track.name}  {a_dur:.2f}s")

    # The video length is the thing that must not move. `apad` extends a short
    # take with silence so the picture survives intact, and `-shortest` then
    # trims that infinite padding back to the video's own end. Using -shortest
    # alone would instead cut the VIDEO down to a short take's length, which
    # loses picture and is easy to miss on a first watch.
    #
    # Padding can add silence but cannot shorten speech, so an over-long take is
    # still a problem. Say so rather than quietly clipping the last sentence.
    drift = a_dur - v_dur
    if drift > 0.5:
        print(f"\n  WARNING  the audio runs {drift:.2f}s longer than the video.")
        print("           The last "
              f"{drift:.2f}s will be cut off, mid-sentence.")
        print("           Re-cut the take, or raise the clip's scene budgets.")
    elif drift < -0.5:
        print(f"\n  note     the audio is {abs(drift):.2f}s shorter than the video."
              " It is padded with silence, so the picture keeps its full length.")

    print(f"\nmuxing -> {args.out}")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", str(args.video), "-i", str(track),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", args.bitrate,
         "-af", "apad", "-movflags", "+faststart", "-shortest", str(args.out)],
        check=True,
    )

    if track != args.audio and track.exists():
        track.unlink()

    out_dur = duration(args.out)
    streams = probe(args.out, "stream=codec_type,codec_name").splitlines()
    print(f"\nwrote {args.out}  {out_dur:.2f}s  {args.out.stat().st_size / 1e6:.1f} MB")
    print(f"  streams: {', '.join(streams)}")
    print("  video stream was copied, not re-encoded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
