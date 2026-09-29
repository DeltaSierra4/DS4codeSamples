#!/usr/bin/env python3
"""
Render a narration track for a video-gen clip, through the Client GenAI
shared-service gateway. Point it at a clip folder under output/:

    python tts_narrate.py --project output/my-clip --dry-run   # cost it, call nothing
    python tts_narrate.py --project output/my-clip --install

It also works standalone, with no clip at all. Give it text and it hands back
one audio file:

    python tts_narrate.py --say "Any text you want spoken." --out intro.mp3
    python tts_narrate.py --say-file script.txt --voice sage
    type script.txt | python tts_narrate.py --say -          # stdin also works

That mode reads no narration script, so it is the quick way to audition a voice.

Settings
--------
    POST https://your-ai-client.com/v1/audio/speech
    Authorization: Bearer <key>
    {"model": "openai.us.tts-1-hd", "voice": "onyx", "input": ..., "response_format": ...}

The /v1/chat/completions URL is wrong for this and the gateway says so:
litellm returns 404 "This is not a chat model and thus not supported in the
v1/chat/completions endpoint". Audio lives on /v1/audio/speech. See --explain.

Two output shapes, because the two pipelines consume narration differently
--------------------------------------------------------------------------
narration.md          per-scene mp3, for /video-full. Carries the
  -> scenes mode      '## N - Title - ~Ns' headings; build.py reads
                      audio/01.mp3 ... NN.mp3 and pads each scene to its budget.
                      So: one mp3 per scene, plus a duration report against each
                      budget.

narration-script.md   one continuous wav, for /video-quick. Carries a
  -> cues mode        '| # | mm:ss.s | Scene | Line |' table. Once audio is
                      present it becomes the deck's master clock, so the track
                      has to be exactly as long as the timeline and each line
                      has to start on its cue. So: synthesise each line, lay it
                      at its cue on a silent track of the right length, and
                      write a single narration.wav.

A cue-laid wav base64-inlines into the packed html at roughly 4 MB for 90s.
Pass --aac to transcode it and it lands nearer 130 kB. That is the only step
here that wants ffmpeg, and it degrades to a warning when ffmpeg is absent.

Nothing is overwritten. Output goes to <project>/tts-out/ and you copy it into
place, or pass --install to have it placed for you, which backs up anything
already there as <name>_removed.<ext> and records the move rather than deleting.

No third-party packages. mp3 durations are read by parsing frame headers and
wav stitching uses the stdlib wave module.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keycheck import (normalize_platform, redact,  # noqa: E402  sys.path first
                      report_key, resolve_key)

# --------------------------------------------------------------------------
# Gateway settings. Override any of them from the command line.
# --------------------------------------------------------------------------
TTS_URL = "https://your-ai-client.com/v1/audio/speech"
MODEL = "openai.us.tts-1-hd"
VOICE = "onyx"

# tts-1-hd has no "instructions" parameter, so there is no way to ask this
# model for a tone. Tone has to come from the writing and the voice choice
# instead. Write it measured and unhurried and it will read that way.

TIMEOUT = 120
RETRIES = 3               # 429 and 5xx only; 4xx is a real answer, not a blip
HERE = Path(__file__).resolve().parent

SCENE_HEADING = re.compile(r"^##\s*(\d+)\s*-\s*(.+?)\s*-\s*~([\d.]+)s\s*$")
CUE_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d{1,2}):(\d{2}(?:\.\d+)?)\s*\|([^|]*)\|(.+)\|\s*$")
TOTAL_HINT = re.compile(r"\*\*([\d.]+)s\*\*")


# ==========================================================================
# HTTP
# ==========================================================================

def synth(text: str, voice: str, key: str, url: str, model: str,
          fmt: str) -> bytes:
    """
    One synthesis call. Returns audio bytes or exits with the gateway's own
    words, which are specific enough to act on.
    """
    payload = {"model": model, "voice": voice, "input": text,
               "response_format": fmt}
    body = json.dumps(payload).encode()

    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "*/*",
                     "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                blob = r.read()
                ctype = r.headers.get("Content-Type", "")
                if blob[:1] == b"{" or "json" in ctype:
                    sys.exit(f"\nExpected audio, got {ctype}:\n"
                             f"{blob.decode('utf-8', 'replace')[:400]}\n")
                return blob
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            if e.code in (429, 500, 502, 503, 504) and attempt < RETRIES:
                wait = 2 ** attempt
                print(f"\n    HTTP {e.code}, retrying in {wait}s "
                      f"({attempt}/{RETRIES - 1}) ", end="", flush=True)
                time.sleep(wait)
                continue
            hint = ""
            if e.code == 404:
                hint = ("\nA 404 here usually means the model is being sent to the "
                        "wrong endpoint.\nTTS belongs on /v1/audio/speech, not "
                        "/v1/chat/completions.")
            elif e.code in (401, 403):
                hint = ("\nKey rejected or not entitled to this model. Note that "
                        "/v1/models returns\n403 'fault filter abort' on this "
                        "gateway even with a working key, so that\nis not a useful "
                        "signal either way.")
            elif e.code == 400:
                hint = ("\nPayload or model id rejected. The message above usually "
                        "names the bad field.")
            sys.exit(f"\n{url} returned {e.code}.\n{detail}{hint}\n")
        except (urllib.error.URLError, socket.timeout) as e:
            reason = getattr(e, "reason", e)
            if attempt < RETRIES:
                print(f"\n    {reason}, retrying ", end="", flush=True)
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"\nCould not reach {url}: {reason}\n"
                     "Are you on the Client network or VPN?\n")
    raise AssertionError("unreachable")


# ==========================================================================
# Audio measurement, without ffmpeg
# ==========================================================================
_MP3_RATES = {
    3: {1: [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
        2: [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
        3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]},
    2: {1: [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
        2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
        3: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]},
}
_MP3_SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_duration(blob: bytes) -> float | None:
    """
    Sum the frame headers. Accurate for CBR and VBR alike, and needs nothing
    installed. Returns None if the bytes do not parse as mp3.
    """
    i = 0
    if blob[:3] == b"ID3":                      # skip the ID3v2 tag
        size = 0
        for b in blob[6:10]:
            size = (size << 7) | (b & 0x7F)
        i = 10 + size
    total, frames = 0.0, 0
    n = len(blob)
    while i + 4 <= n:
        if blob[i] != 0xFF or (blob[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        h = struct.unpack(">I", blob[i:i + 4])[0]
        ver = (h >> 19) & 0x3                   # 3=MPEG1, 2=MPEG2, 0=MPEG2.5
        layer = 4 - ((h >> 17) & 0x3)
        br_idx = (h >> 12) & 0xF
        sr_idx = (h >> 10) & 0x3
        pad = (h >> 9) & 0x1
        if ver == 1 or layer not in (1, 2, 3) or br_idx in (0, 15) or sr_idx == 3:
            i += 1
            continue
        try:
            bitrate = _MP3_RATES[3 if ver == 3 else 2][layer][br_idx] * 1000
            sr = _MP3_SR[ver][sr_idx]
        except (KeyError, IndexError):
            i += 1
            continue
        if layer == 1:
            length = (12 * bitrate // sr + pad) * 4
            spf = 384
        else:
            spf = 1152 if (layer == 3 and ver == 3) else (576 if layer == 3 else 1152)
            length = 144 * bitrate // sr + pad if ver == 3 else 72 * bitrate // sr + pad
        if length <= 0:
            i += 1
            continue
        total += spf / sr
        frames += 1
        i += length
    return total if frames else None


def wav_read(blob: bytes) -> tuple[int, int, bytes]:
    """
    Pull (sample_rate, channels, pcm_bytes) out of a RIFF/WAVE blob by walking
    the chunks. The wave module cannot read from bytes without a file, and some
    gateways emit extra chunks, so this is done by hand.
    """
    if blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    i, sr, ch, bits, data = 12, None, None, None, None
    while i + 8 <= len(blob):
        cid = blob[i:i + 4]
        size = struct.unpack("<I", blob[i + 4:i + 8])[0]
        payload = blob[i + 8:i + 8 + size]
        if cid == b"fmt ":
            _, ch, sr, _, _, bits = struct.unpack("<HHIIHH", payload[:16])
        elif cid == b"data":
            data = payload
        i += 8 + size + (size & 1)              # chunks are word aligned
    if sr is None or data is None:
        raise ValueError("wav has no fmt or no data chunk")
    if bits != 16:
        raise ValueError(f"expected 16-bit pcm, got {bits}-bit")
    if ch == 2:                                 # downmix, speech is mono anyway
        out = bytearray(len(data) // 2)
        for s in range(0, len(data) - 3, 4):
            l, r = struct.unpack_from("<hh", data, s)
            struct.pack_into("<h", out, s // 2, (l + r) // 2)
        data, ch = bytes(out), 1
    return sr, ch, data


# ==========================================================================
# Parsing the two narration formats
# ==========================================================================
def parse_scenes(path: Path) -> list[dict]:
    """scenes mode: '## N - Title - ~Ns' with the spoken text beneath."""
    scenes: list[dict] = []
    current: dict | None = None
    body: list[str] = []

    def flush() -> None:
        if current is None:
            return
        spoken = [t for t in (l.strip() for l in body)
                  if t and t != "---" and not t.startswith("*Screen:*")]
        current["text"] = " ".join(spoken)
        scenes.append(current)

    for raw in path.read_text(encoding="utf-8").splitlines():
        m = SCENE_HEADING.match(raw)
        if m:
            flush()
            current = {"index": int(m.group(1)), "title": m.group(2),
                       "budget": float(m.group(3))}
            body = []
        elif current is not None:
            body.append(raw)
    flush()
    return [s for s in scenes if s["text"]]


def _states_total(raw: str) -> bool:
    """
    Is this line stating the timeline length, rather than just happening to
    contain a bolded number? A table row qualifies, and so does a line that
    opens by naming the total. Anything else is prose, and prose that mentions
    "**90s**" should not silently become the track length.
    """
    if "|" in raw:
        return True
    head = raw.lstrip().lstrip("*_# ").lower()
    return head.startswith(("total", "runtime", "length"))


def parse_cues(path: Path) -> tuple[list[dict], float | None]:
    """
    cues mode: the '| # | Cue | Scene | Line |' table. The second table in
    that file (scene arithmetic) does not match, because its cue cell reads
    '0.0s' rather than 'mm:ss.s', so it is skipped without special handling.
    """
    lines: list[dict] = []
    total = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = CUE_ROW.match(raw.rstrip())
        if m:
            cue = int(m.group(2)) * 60 + float(m.group(3))
            text = m.group(5).strip().strip("|").strip()
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)        # drop bold marks
            if text:
                lines.append({"index": int(m.group(1)), "cue": cue,
                              "title": m.group(4).strip(), "text": text})
            continue
        t = TOTAL_HINT.search(raw)
        if t and total is None and _states_total(raw):
            total = float(t.group(1))
    return lines, total


def detect_project(explicit: str | None) -> tuple[Path, str]:
    """Return (project_dir, mode) where mode is 'scenes' or 'cues'.

    A clip folder under output/ holds narration.md for the mp4 pipeline or
    narration-script.md for the html one. /video-generate writes both into the
    same place, so which file is present is what picks the output shape.
    """
    if not explicit:
        sys.exit("Pass --project <clip folder>, or --say for standalone text.")

    p = Path(explicit)
    if not p.is_absolute():
        p = (Path.cwd() / explicit).resolve()
    if not p.is_dir():
        sys.exit(f"--project {p} is not a directory.")

    has_scenes = (p / "narration.md").is_file()
    has_cues = (p / "narration-script.md").is_file()

    if has_scenes and has_cues:
        sys.exit(f"{p} holds both narration.md and narration-script.md, so the\n"
                 "output shape is ambiguous. A clip belongs to one pipeline or\n"
                 "the other. Remove whichever does not belong.")
    if has_scenes:
        return p, "scenes"
    if has_cues:
        return p, "cues"
    sys.exit(f"{p} has neither narration.md nor narration-script.md, so there\n"
             "is nothing to read.")


# ==========================================================================
# Writing, without deleting
# ==========================================================================
def place(src: Path, dst: Path, log: Path) -> None:
    """
    Copy src over dst, preserving anything already there. Existing files are
    renamed to <stem>_removed<suffix> and recorded, never deleted.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        backup = dst.with_name(f"{dst.stem}_removed{dst.suffix}")
        n = 1
        while backup.exists():
            n += 1
            backup = dst.with_name(f"{dst.stem}_removed_{n}{dst.suffix}")
        dst.rename(backup)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"{dst.name}: {dst}  ->  {backup}\n")
        print(f"      kept existing as {backup.name}")
    shutil.copy2(src, dst)


def to_aac(src: Path) -> Path | None:
    """
    Transcode the cue-laid wav to aac. A 16-bit wav base64-inlines into the
    packed html at roughly 4 MB for 90s; aac lands nearer 130 kB. Optional on
    purpose: every other step here runs without ffmpeg, and that guarantee is
    worth more than the file size. Returns None on any failure, having said
    why, so the caller keeps the wav rather than losing the take.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from toolchain import ensure_ffmpeg
    except ImportError:
        print("  (!) --aac wants scripts/toolchain.py, which is not where this "
              "script expects it. Keeping the wav.")
        return None
    if ensure_ffmpeg(("ffmpeg",), required=False) is None:
        print("  (!) --aac needs ffmpeg and it was not found. Keeping the wav.")
        print("      The packed html will be around 4 MB rather than 130 kB.")
        return None

    dst = src.with_suffix(".m4a")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-c:a", "aac", "-b:a", "96k", str(dst)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  (!) ffmpeg could not transcode: {r.stderr.strip()[:200]}")
        print("      Keeping the wav.")
        return None
    print(f"  aac      {dst.name}, {dst.stat().st_size / 1000:.0f} kB "
          f"(from {src.stat().st_size / 1_000_000:.1f} MB of wav)")
    return dst


def provenance(out: Path, record: dict) -> None:
    """
    Append-only history. Without it the Cornerstone videos could not be
    re-recorded in the same voice, which is exactly what happened. Keep it.
    """
    prov = out / "provenance.json"
    if prov.exists():
        try:
            old = json.loads(prov.read_text(encoding="utf-8"))
            history = old.get("superseded", [])
            history.append({k: v for k, v in old.items() if k != "superseded"})
            record["superseded"] = history[-5:]
        except Exception:
            pass
    prov.write_text(json.dumps(record, indent=2), encoding="utf-8")


# ==========================================================================
# Mode: per-scene mp3, for /video-full
# ==========================================================================
def run_scenes(project: Path, args, key: str) -> int:
    src = project / "narration.md"
    scenes = parse_scenes(src)
    if not scenes:
        sys.exit(f"No scenes in {src}. Expected '## N - Title - ~Ns'.")
    if args.scene is not None:
        scenes = [s for s in scenes if s["index"] == args.scene]
        if not scenes:
            sys.exit(f"No scene {args.scene} in {src}")

    out = project / "tts-out"
    words = sum(len(s["text"].split()) for s in scenes)
    budget = sum(s["budget"] for s in scenes)
    chars = sum(len(s["text"]) for s in scenes)

    print(f"source      {src}")
    print(f"shape       per-scene mp3, for build.py")
    print(f"script      {len(scenes)} scene(s), {words} words, {budget:.0f}s of "
          f"budget ({words / budget:.2f} w/s)")
    print(f"billable    {chars} characters\n")

    if args.dry_run:
        for s in scenes:
            n = len(s["text"].split())
            print(f"  scene {s['index']:>2}  budget {s['budget']:>5.1f}s  "
                  f"{n:>3} words  ({n / s['budget']:.2f} w/s)  {s['title']}")
            print(f"      {s['text']}\n")
        print("Dry run. Nothing was sent and nothing was written.")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    written, over = [], []
    for s in scenes:
        dst = out / f"{s['index']:02d}.mp3"
        print(f"  scene {s['index']:>2} {s['title'][:28]:<30} ", end="", flush=True)
        blob = synth(s["text"], args.voice, key, args.url, args.model, "mp3")
        dst.write_bytes(blob)
        took = mp3_duration(blob)
        if took is None:
            print(f"written, {len(blob) / 1000:.0f} kB, duration unreadable")
        else:
            slack = s["budget"] - took
            flag = "OVER BUDGET" if slack < 0 else f"{slack:>4.1f}s spare"
            print(f"{took:>5.1f}s / {s['budget']:>4.0f}s   {flag}")
            if slack < 0:
                over.append((s["index"], took, s["budget"]))
        written.append({"scene": s["index"], "file": dst.name,
                        "seconds": took, "budget": s["budget"]})

    provenance(out, {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": "your-ai-client-shared-service",
        "endpoint": args.url,
        "model": args.model,
        "voice": args.voice,
        "source_script": src.name,
        "note": "Keep this file. Without it a re-render cannot reproduce the "
                "same voice. Stock voice only, no cloning.",
        "takes": written,
    })
    print(f"\nWrote {len(written)} file(s) + provenance.json to {out}")

    if args.install:
        log = out / "moved_files.txt"
        print(f"\nInstalling into {project / 'audio'}")
        for w in written:
            print(f"  {w['file']}")
            place(out / w["file"], project / "audio" / w["file"], log)
        place(out / "provenance.json", project / "audio" / "provenance.json", log)
    else:
        print(f"\nTo use them:  copy them into {project / 'audio'}")
        print("              or rerun with --install")

    if over:
        print("\nSome takes run past their budget. The build will refuse these:")
        for idx, took, bud in over:
            print(f"  scene {idx}: {took:.1f}s > {bud:.0f}s (over by {took - bud:.1f}s)")
        print("Trim the wording in narration.md or raise that scene's budget.")
        return 1

    print(f"\nNow re-run the driver:  python {project}/build_<name>.py")
    return 0


# ==========================================================================
# Mode: one cue-laid wav, for /video-quick
# ==========================================================================
def run_cues(project: Path, args, key: str) -> int:
    src = project / "narration-script.md"
    lines, total_hint = parse_cues(src)
    if not lines:
        sys.exit(f"No cue rows in {src}. Expected '| # | mm:ss.s | Scene | Line |'.")
    if args.scene is not None:
        sys.exit("--scene applies to the per-scene layout only. The cue-laid "
                 "track has to be rendered whole, because it is the deck's "
                 "master clock and a partial track would reset the pacing.")

    total = args.total or total_hint
    words = sum(len(l["text"].split()) for l in lines)
    chars = sum(len(l["text"]) for l in lines)

    print(f"source      {src}")
    print(f"shape       single cue-laid wav, for build/pack.mjs --audio")
    print(f"script      {len(lines)} line(s), {words} words")
    print(f"timeline    {f'{total:.2f}s' if total else 'not stated, will derive'}"
          f"   last cue {lines[-1]['cue']:.1f}s")
    print(f"billable    {chars} characters\n")

    if args.dry_run:
        for i, l in enumerate(lines):
            nxt = lines[i + 1]["cue"] if i + 1 < len(lines) else total
            room = (nxt - l["cue"]) if nxt else None
            n = len(l["text"].split())
            room_s = f"{room:>5.1f}s room" if room else "  (last)"
            pace = f"{n / room:.2f} w/s" if room else ""
            print(f"  {l['index']:>2}  cue {l['cue']:>6.1f}s  {room_s}  "
                  f"{n:>3} words  {pace}  {l['title'][:22]}")
            print(f"      {l['text']}\n")
        print("Dry run. Nothing was sent and nothing was written.")
        return 0

    out = project / "tts-out"
    out.mkdir(parents=True, exist_ok=True)

    # Synthesise every line first, then lay them down. Wav is requested rather
    # than mp3 because the takes have to be stitched sample-accurately onto one
    # timeline, and decoding mp3 would mean ffmpeg.
    takes = []
    sr = None
    for i, l in enumerate(lines):
        print(f"  line {l['index']:>2} cue {l['cue']:>6.1f}s "
              f"{l['title'][:22]:<24} ", end="", flush=True)
        blob = synth(l["text"], args.voice, key, args.url, args.model, "wav")
        try:
            rate, _, pcm = wav_read(blob)
        except ValueError as e:
            kept = out / f"line-{l['index']:02d}.bin"
            kept.write_bytes(blob)
            sys.exit(f"\nThe gateway returned something this script cannot "
                     f"stitch: {e}\nIt was asked for wav. The raw bytes are "
                     f"kept at {kept} so you can see what arrived.")
        if sr is None:
            sr = rate
        elif rate != sr:
            sys.exit(f"\nTake {l['index']} came back at {rate} Hz but earlier "
                     f"takes were {sr} Hz. Mixed rates cannot be laid on one "
                     "timeline without resampling. Flagging rather than guessing.")
        dur = len(pcm) / 2 / sr
        takes.append({**l, "pcm": pcm, "dur": dur})
        print(f"{dur:>5.1f}s")

    # Length of the finished track. Audio is the master clock once present, so
    # a track shorter than the timeline would stretch the deck.
    tail = takes[-1]["cue"] + takes[-1]["dur"]
    if total is None:
        total = round(tail + 1.0, 2)
        print(f"\n  timeline length not stated in the script, using "
              f"{total:.2f}s (last line + 1s tail)")
    elif tail > total:
        print(f"\n  (!) the last line ends at {tail:.1f}s, past the "
              f"{total:.2f}s timeline")

    frames = int(round(total * sr))
    track = bytearray(frames * 2)               # zero-filled is digital silence
    clashes = []
    for i, t in enumerate(takes):
        start = int(round(t["cue"] * sr))
        end = start + len(t["pcm"]) // 2
        nxt = takes[i + 1]["cue"] if i + 1 < len(takes) else total
        if t["cue"] + t["dur"] > nxt + 0.05:
            clashes.append((t["index"], t["cue"] + t["dur"], nxt))
        if end > frames:
            cut = (end - frames) / sr
            print(f"  (!) line {t['index']} is cut short by {cut:.1f}s at the "
                  "end of the track")
            end = frames
        track[start * 2:end * 2] = t["pcm"][:(end - start) * 2]

    dst = out / "narration.wav"
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(track))

    provenance(out, {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": "your-ai-client-shared-service",
        "endpoint": args.url,
        "model": args.model,
        "voice": args.voice,
        "source_script": str(src.relative_to(project)),
        "track": {"file": dst.name, "seconds": round(frames / sr, 3),
                  "sample_rate": sr, "channels": 1, "bits": 16},
        "note": "Keep this file. Without it a re-render cannot reproduce the "
                "same voice. Stock voice only, no cloning.",
        "takes": [{"line": t["index"], "cue": t["cue"],
                   "seconds": round(t["dur"], 3), "title": t["title"]}
                  for t in takes],
    })

    print(f"\nWrote {dst}")
    print(f"      {frames / sr:.2f}s, {sr} Hz mono 16-bit, "
          f"{dst.stat().st_size / 1_000_000:.1f} MB")

    if clashes:
        print("\nLines that run into the next cue:")
        for idx, ends, nxt in clashes:
            print(f"  line {idx}: ends {ends:.1f}s, next cue {nxt:.1f}s "
                  f"(over by {ends - nxt:.1f}s)")
        print("They still play, but the line overlaps the following visual.")
        print("Trim the wording, or widen that scene's duration in the deck.")

    final = dst
    if args.aac:
        converted = to_aac(dst)
        if converted is not None:
            final = converted

    target = project / final.name
    if args.install:
        place(final, target, out / "moved_files.txt")
        print(f"\nInstalled to {target}")
    else:
        print(f"\nTo use it:  copy it to {target}")
        print("            or rerun with --install")

    print("\nThen, from scripts/html/:")
    print(f"  node build/pack.mjs src/<name>.html "
          f"../../output/{project.name}/<name>.html --audio {target}")
    print(f"  node build/check.mjs ../../output/{project.name}/<name>.html")
    if final.suffix == ".wav":
        print("\nThe packed html inlines this wav as base64, which costs about a")
        print("third on top of its size. Rerun with --aac if that lands too big.")
    return 1 if clashes else 0


# ==========================================================================
# Mode: free text in, one audio file out. No project involved.
# ==========================================================================
EXT_FORMAT = {".mp3": "mp3", ".wav": "wav", ".opus": "opus",
              ".aac": "aac", ".flac": "flac", ".pcm": "pcm"}
CHAR_LIMIT = 4000        # tts-1 family rejects much past 4096 in one call


def split_for_limit(text: str, limit: int = CHAR_LIMIT) -> list[str]:
    """
    Break long text on sentence ends so no single call exceeds the model's
    input limit. Splitting mid-sentence would put an audible seam in the
    middle of a clause, so sentence boundaries are the only cut points, and a
    single sentence longer than the limit is cut on whitespace as a last resort.
    """
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        while len(sentence) > limit:            # pathological single sentence
            cut = sentence.rfind(" ", 0, limit) or limit
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if len(current) + len(sentence) + 1 > limit:
            if current:
                chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if c]


def unique(path: Path) -> Path:
    """Never overwrite. Walk to the next free name instead."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        if not candidate.exists():
            print(f"      {path.name} exists, writing {candidate.name} instead")
            return candidate
        n += 1


def run_say(args, key: str) -> int:
    # ------------------------------------------------------------ the text
    if args.say_file:
        src = Path(args.say_file)
        if not src.is_file():
            sys.exit(f"--say-file {src} not found.")
        text = src.read_text(encoding="utf-8").strip()
        origin = str(src)
    elif args.say == "-":
        text = sys.stdin.read().strip()
        origin = "stdin"
    else:
        text = (args.say or "").strip()
        origin = "command line"
    if not text:
        sys.exit("Nothing to say. Pass --say \"text\", --say-file, or pipe to --say -")

    # ---------------------------------------------------------- the target
    out = Path(args.out) if args.out else Path.cwd() / "tts-out" / "narration.mp3"
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    fmt = args.format or EXT_FORMAT.get(out.suffix.lower())
    if fmt is None:
        sys.exit(f"Cannot tell the format from '{out.suffix}'. Use --format, or "
                 f"name the file {'/'.join(EXT_FORMAT)}")

    chunks = split_for_limit(text)
    words = len(text.split())

    print(f"source      {origin}")
    print(f"shape       one {fmt} file, standalone")
    print(f"text        {words} words, {len(text)} characters"
          + (f", split into {len(chunks)} call(s)" if len(chunks) > 1 else ""))
    print(f"target      {out}\n")

    if args.dry_run:
        for i, c in enumerate(chunks, 1):
            print(f"  call {i}  {len(c)} chars\n      {c[:300]}"
                  + ("..." if len(c) > 300 else "") + "\n")
        print("Dry run. Nothing was sent and nothing was written.")
        return 0

    if len(chunks) > 1 and fmt not in ("mp3", "wav", "pcm"):
        sys.exit(f"The text needs {len(chunks)} calls, and {fmt} files cannot "
                 "simply be joined end to end the way mp3 and wav can.\n"
                 "Use mp3 or wav, or shorten the text.")

    # --------------------------------------------------------- synthesise
    blobs = []
    for i, c in enumerate(chunks, 1):
        label = f"  call {i}/{len(chunks)}" if len(chunks) > 1 else "  synthesising"
        print(f"{label}  {len(c):>5} chars ", end="", flush=True)
        blob = synth(c, args.voice, key, args.url, args.model, fmt)
        blobs.append(blob)
        print(f"-> {len(blob) / 1000:>7.1f} kB")

    out.parent.mkdir(parents=True, exist_ok=True)
    out = unique(out)

    if fmt == "wav" and len(blobs) > 1:
        # wav carries a header per file, so joining the bytes would embed a
        # header mid-stream. Decode and rewrite as one.
        sr, pcm = None, bytearray()
        for b in blobs:
            rate, _, data = wav_read(b)
            if sr is None:
                sr = rate
            elif rate != sr:
                sys.exit(f"Mixed sample rates ({sr} and {rate} Hz) cannot be "
                         "joined without resampling.")
            pcm += data
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(bytes(pcm))
    else:
        out.write_bytes(b"".join(blobs))

    # ------------------------------------------------------------- report
    blob = out.read_bytes()
    if fmt == "mp3":
        secs = mp3_duration(blob)
    elif fmt == "wav":
        rate, _, data = wav_read(blob)
        secs = len(data) / 2 / rate
    else:
        secs = None

    print(f"\nWrote {out}")
    print(f"      {len(blob) / 1000:.1f} kB"
          + (f", {secs:.1f}s, {words / secs * 60:.0f} words per minute"
             if secs else ", duration not measured for this format"))

    provenance(out.parent, {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": "your-ai-client-shared-service",
        "endpoint": args.url,
        "model": args.model,
        "voice": args.voice,
        "source_script": origin,
        "track": {"file": out.name, "seconds": secs, "format": fmt},
        "note": "Keep this file. Without it a re-render cannot reproduce the "
                "same voice. Stock voice only, no cloning.",
        "text": text if len(text) <= 2000 else text[:2000] + " ...[truncated]",
    })
    print(f"      provenance.json written alongside it")
    return 0


# ==========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None,
                    help="a clip folder under output/ holding narration.md "
                         "or narration-script.md")
    ap.add_argument("--key", default=None,
                    help="gateway key. Otherwise CLIENT_GENAI_KEY or OPENAI_API_KEY, "
                         "found through scripts/sound/keycheck.py. See --check-key")
    ap.add_argument("--platform", default="auto", metavar="OS",
                    help="the operating system of the person reading this "
                         "output: auto, windows, macos or linux. Only changes "
                         "what a missing key says. See keycheck.py --help")
    ap.add_argument("--url", default=TTS_URL)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--voice", default=VOICE,
                    help="alloy ash ballad coral echo fable nova onyx sage shimmer")
    ap.add_argument("--say", default=None, metavar="TEXT",
                    help="standalone: speak this text. '-' reads stdin")
    ap.add_argument("--say-file", default=None, metavar="PATH",
                    help="standalone: speak the contents of a text file")
    ap.add_argument("--out", default=None, metavar="PATH",
                    help="standalone: where to write "
                         "(default tts-out/narration.mp3)")
    ap.add_argument("--format", default=None,
                    choices=["mp3", "wav", "opus", "aac", "flac", "pcm"],
                    help="standalone: override the format implied by --out")
    ap.add_argument("--scene", type=int, default=None,
                    help="per-scene layout only: render one scene")
    ap.add_argument("--total", type=float, default=None,
                    help="cue layout only: timeline length in seconds")
    ap.add_argument("--aac", action="store_true",
                    help="cue layout only: transcode the wav to aac, which "
                         "packs to roughly 130 kB instead of 4 MB. Needs ffmpeg")
    ap.add_argument("--install", action="store_true",
                    help="place the output where the builder expects it, "
                         "backing up anything already there")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse, cost and pace-check the script, call nothing")
    ap.add_argument("--explain", action="store_true",
                    help="print the endpoint finding and exit")
    ap.add_argument("--check-key", action="store_true",
                    help="say whether a key is set, and how to set one if not. "
                         "Calls nothing. Exits 0 when found, 1 when not")
    args = ap.parse_args()

    if args.explain:
        print(__doc__)
        return 0

    # A declaration by the caller, never a detection. It changes nothing but
    # the wording of a missing-key message. See keycheck.py's header.
    declared = None
    if args.platform.strip().lower() != "auto":
        try:
            declared = normalize_platform(args.platform)
        except ValueError as exc:
            sys.exit(f"--platform: {exc}")

    # --explain returns above without ever looking for a key, which is why
    # it was never a key check however it read. --check-key is the one that is.
    if args.check_key:
        return report_key(declared)

    # --dry-run stays keyless on purpose. It is the recommended first move
    # everywhere in this plugin, and it must never start needing a key.
    key = resolve_key(args.key, required=not args.dry_run, declared=declared)

    standalone = bool(args.say or args.say_file)
    if standalone and args.project:
        sys.exit("--say and --project are different jobs. --say voices the text "
                 "you hand it;\n--project reads that project's narration script. "
                 "Pick one.")

    project = mode = None
    if not standalone:
        project, mode = detect_project(args.project)

    print("=" * 74)
    print("Narration render - Client GenAI shared service")
    print("=" * 74)
    print(f"project     {project if project else '(none, standalone text)'}")
    print(f"endpoint    {args.url}")
    print(f"model       {args.model}    voice {args.voice}")
    print(f"key         {redact(key)}")
    if standalone:
        return run_say(args, key)
    return run_scenes(project, args, key) if mode == "scenes" \
        else run_cues(project, args, key)


if __name__ == "__main__":
    sys.exit(main())
