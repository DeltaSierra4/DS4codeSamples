#!/usr/bin/env python3
"""
Browser-free clip builder. Narration budgets in, verified mp4 out.

Why this exists
---------------
The Cornerstone method renders an HTML animation by driving headless Chrome with
puppeteer, then encodes the captured frames. That needs a real browser on a real
machine. The Cowork code sandbox has no browser and no network, so that pipeline
cannot run there at all.

This script does the same job without a browser. Frames are drawn directly with
Pillow and piped to ffmpeg. Nothing is fetched, nothing is installed.

It also implements the one improvement the Cornerstone handover recommended and
never built: every narration section is padded with silence up to its budget
before the sections are joined. Audio boundaries then equal the budgets by
construction, and the budgets already equal the animation holds. Sync stops
being something you hunt for and becomes arithmetic.

Usage
-----
    python3 build.py                 # render, mux, verify
    python3 build.py --frames-only   # skip audio and verification
    python3 build.py --scale 0.5     # half resolution, for a fast look
    python3 build.py --name out.mp4  # choose the output file name

Audio
-----
Silence is a placeholder, not the design. To get a voice track:

    python3 ../sound/tts_narrate.py --project . --install   # needs network and a key
    python3 build.py

tts_narrate.py reads this same narration.md, calls a text-to-speech service, and
writes audio/01.mp3 onward plus audio/provenance.json. It runs separately because
this builder needs neither network nor a licence, and speech synthesis needs both.

Recordings can also be dropped into audio/ by hand as 01.mp3 ... NN.mp3, or
.wav / .m4a / .aac / .flac / .ogg. Each file is padded up to its budget, so a
take that comes in under budget still lands the next scene on the right frame.
A take that runs over budget stops the build rather than silently shifting
everything after it.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# toolchain.py normally lives in scripts/, one level up. A caller may instead
# stage a copy of this file into a scratch tree with toolchain.py beside it, so
# look in both places rather than assuming the repository layout.
_HERE = Path(__file__).resolve().parent
for _cand in (_HERE, _HERE.parent):
    if (_cand / "toolchain.py").is_file():
        sys.path.insert(0, str(_cand))
        break
from toolchain import ensure_ffmpeg  # noqa: E402  the sys.path lines must run first

# ---------------------------------------------------------------- configuration

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
AUDIO_IN = ROOT / "audio"
NARRATION = ROOT / "narration.md"

W, H, FPS = 1920, 1080, 30

# Default output name. Override per run with --name.
OUT_NAME = "five-jobs.mp4"

BG = (11, 16, 32)
PANEL = (19, 26, 46)
TEXT = (242, 243, 247)
MUTED = (138, 147, 168)
ACCENT = (208, 74, 2)
ACCENT_DIM = (120, 46, 8)
OK = (108, 191, 132)

# Fonts ship with the plugin rather than being probed for on the host.
#
# Probing would work, but wrap() measures text against the loaded font, so a run
# that resolved Arial on Windows and DejaVu on Linux would wrap the same
# narration.md differently: copy that fits on one machine can overflow on
# another, silently. Bundling makes the render deterministic across operating
# systems. The system paths below are a fallback for the case where the bundled
# copy is missing, not a preference.
FONT_DIR = ROOT / "fonts"

_FONT_FALLBACKS = {
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/Library/Fonts/DejaVuSans-Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/Library/Fonts/DejaVuSans.ttf",
    ],
}


def _resolve_font(weight: str, filename: str) -> str:
    bundled = FONT_DIR / filename
    if bundled.is_file():
        return str(bundled)
    for candidate in _FONT_FALLBACKS[weight]:
        if Path(candidate).is_file():
            return candidate
    sys.exit(
        f"Font not found: {filename}\n"
        f"  Looked for the bundled copy at {bundled}\n"
        f"  and for a system DejaVu at:\n"
        + "".join(f"    {c}\n" for c in _FONT_FALLBACKS[weight])
        + "  Restore scripts/mp4/fonts/, or install DejaVu on this machine.\n"
        "  Do not substitute another face: the frames would wrap differently."
    )


FONT_BOLD = _resolve_font("bold", "DejaVuSans-Bold.ttf")
FONT_REG = _resolve_font("regular", "DejaVuSans.ttf")

MARGIN = 140

# Set by parse_narration so the on-screen counter reads the real total. This
# was hard-coded to "/ 6" and silently wrong for any script of another length.
SCENE_COUNT = 0


# ------------------------------------------------------------------- narration


@dataclass
class Scene:
    index: int
    title: str
    budget: float
    narration: str
    screen: str
    frames: int = 0
    start_frame: int = 0
    audio_file: Path | None = field(default=None)

    @property
    def start_s(self) -> float:
        return self.start_frame / FPS

    @property
    def end_s(self) -> float:
        return (self.start_frame + self.frames) / FPS


HEADING = re.compile(r"^##\s*(\d+)\s*-\s*(.+?)\s*-\s*~([\d.]+)s\s*$")


def parse_narration(path: Path) -> list[Scene]:
    """Read scenes and their per-scene time budgets out of the script."""
    scenes: list[Scene] = []
    current: dict | None = None
    body: list[str] = []

    def flush() -> None:
        if current is None:
            return
        narration_lines, screen = [], ""
        for line in body:
            s = line.strip()
            if not s or s == "---":
                continue
            if s.startswith("*Screen:*"):
                screen = s[len("*Screen:*") :].strip()
            else:
                narration_lines.append(s)
        scenes.append(
            Scene(
                index=current["index"],
                title=current["title"],
                budget=current["budget"],
                narration=" ".join(narration_lines),
                screen=screen,
            )
        )

    for raw in path.read_text(encoding="utf-8").splitlines():
        m = HEADING.match(raw)
        if m:
            flush()
            current = {
                "index": int(m.group(1)),
                "title": m.group(2),
                "budget": float(m.group(3)),
            }
            body = []
        elif current is not None:
            body.append(raw)
    flush()

    if not scenes:
        sys.exit(f"No scenes parsed from {path}. Expected '## N - Title - ~Ns' headings.")

    # Scenes play in file order, but the heading number drives the on-screen
    # counter and the audio/NN.mp3 lookup. If someone moves a block without
    # renumbering it, the clip plays in the new order while displaying the old
    # labels and pulling the wrong take, with nothing to indicate it. Refuse
    # rather than produce that quietly.
    got = [sc.index for sc in scenes]
    want = list(range(1, len(scenes) + 1))
    if got != want:
        sys.exit(
            f"Scene headings in {path.name} must be numbered 1..{len(scenes)} in the "
            f"order they appear. Found {got}.\n"
            "Playback follows file order, but the scene counter and the audio/NN.mp3 "
            "lookup follow the heading number, so the two have to agree.\n"
            "Renumber the headings to match their position, or move the blocks back."
        )

    global SCENE_COUNT
    SCENE_COUNT = len(scenes)

    frame = 0
    for sc in scenes:
        sc.frames = int(round(sc.budget * FPS))
        sc.start_frame = frame
        frame += sc.frames
    return scenes


# ------------------------------------------------------------------- utilities


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 3 * t * t - 2 * t * t * t


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1, c2, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


def fade(colour, bg, alpha: float):
    """Pillow has no per-draw alpha on RGB, so blend towards the background."""
    return mix(bg, colour, alpha)


class Fonts:
    def __init__(self, scale: float = 1.0):
        self._scale = scale
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, bold: bool, size: int) -> ImageFont.FreeTypeFont:
        path = FONT_BOLD if bold else FONT_REG
        px = max(8, int(round(size * self._scale)))
        key = (path, px)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(path, px)
        return self._cache[key]


def wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_block(draw, xy, text, font, fill, max_w, line_h, bg=BG, alpha=1.0):
    x, y = xy
    colour = fade(fill, bg, alpha)
    for line in wrap(draw, text, font, max_w):
        draw.text((x, y), line, font=font, fill=colour)
        y += line_h
    return y


# ------------------------------------------------------------- scene renderers


def chrome(draw, f: Fonts, scene: Scene, total_frames: int, abs_frame: int, s: float):
    """Persistent furniture: scene counter and an overall progress rule."""
    label = f"{scene.index} / {SCENE_COUNT}"
    fnt = f.get(False, 26)
    draw.text((W - MARGIN - draw.textlength(label, font=fnt), 70), label,
              font=fnt, fill=MUTED)
    y = H - 84
    draw.rectangle([MARGIN, y, W - MARGIN, y + 3], fill=(32, 40, 62))
    prog = abs_frame / max(1, total_frames - 1)
    draw.rectangle([MARGIN, y, MARGIN + int((W - 2 * MARGIN) * prog), y + 3], fill=ACCENT)


def scene_title(draw, f: Fonts, t: float, s: float):
    a = ease_out(t / 0.30) if t < 0.30 else 1.0
    rule = ease_out(min(1.0, max(0.0, (t - 0.12) / 0.35)))
    sub = ease_out(min(1.0, max(0.0, (t - 0.30) / 0.35)))

    y0 = 330 + int(28 * (1 - a))
    fnt = f.get(True, 118)
    draw.text((MARGIN, y0), "Five jobs,", font=fnt, fill=fade(TEXT, BG, a))
    draw.text((MARGIN, y0 + 132), "five toolchains.", font=fnt, fill=fade(ACCENT, BG, a))

    draw.rectangle([MARGIN, y0 + 300, MARGIN + int(360 * rule), y0 + 306], fill=ACCENT)

    draw_block(draw, (MARGIN, y0 + 356),
               "A field guide to making video without wasting a month on it.",
               f.get(False, 40), MUTED, W - 2 * MARGIN - 420, 56, alpha=sub)


FRAGMENTS = [
    "a person explaining",
    "prompt to footage",
    "narration",
    "a screen recording",
    "built from code",
]


def scene_problem(draw, f: Fonts, t: float, s: float):
    phrase_in = ease_out(min(1.0, t / 0.14))
    split = ease_in_out(min(1.0, max(0.0, (t - 0.34) / 0.40)))

    fnt = f.get(True, 92)
    txt = '"Make an AI video"'
    tw = draw.textlength(txt, font=fnt)
    cx = (W - tw) / 2
    draw.text((cx, 250 - int(30 * (1 - phrase_in))), txt,
              font=fnt, fill=fade(TEXT, BG, phrase_in * (1 - 0.45 * split)))

    small = f.get(False, 36)
    top = 470
    for i, frag in enumerate(FRAGMENTS):
        local = max(0.0, min(1.0, (split - i * 0.06) / 0.6))
        if local <= 0:
            continue
        y = top + i * 82
        x = MARGIN + int(120 * (1 - ease_out(local)))
        num = f.get(True, 30)
        draw.text((x, y), f"{i + 1}", font=num, fill=fade(ACCENT, BG, local))
        draw.text((x + 54, y - 2), frag, font=small,
                  fill=fade(TEXT, BG, local * 0.92))

    tail = ease_out(min(1.0, max(0.0, (t - 0.72) / 0.28)))
    if tail > 0:
        draw_block(draw, (MARGIN + 780, 470),
                   "Five jobs. Five toolchains. Five failure modes. "
                   "Most wasted effort here comes from treating them as one thing.",
                   f.get(False, 34), MUTED, W - MARGIN - 780 - MARGIN, 50, alpha=tail)


JOBS = [
    ("Presenter", "A person explains a policy, a process, a plan.", "buy"),
    ("Generative", "Footage from a text prompt. B-roll, never load bearing.", "garnish"),
    ("Voice", "Narration for any of the above. No longer the bottleneck.", "buy"),
    ("Screen demo", "A recording of a product that actually exists.", "record"),
    ("Code driven", "Software that cannot be filmed because it does not exist yet.", "build"),
]

VERDICT_COLOUR = {"buy": OK, "record": OK, "garnish": MUTED, "build": ACCENT}


def scene_jobs(draw, f: Fonts, t: float, s: float):
    head = ease_out(min(1.0, t / 0.10))
    draw.text((MARGIN, 150), "The five jobs", font=f.get(True, 62),
              fill=fade(TEXT, BG, head))

    row_h = 132
    top = 290
    name_f, desc_f, tag_f, idx_f = (
        f.get(True, 42), f.get(False, 32), f.get(True, 24), f.get(True, 34),
    )
    for i, (name, desc, verdict) in enumerate(JOBS):
        local = max(0.0, min(1.0, (t - 0.10 - i * 0.115) / 0.30))
        if local <= 0:
            continue
        e = ease_out(local)
        y = top + i * row_h
        x = MARGIN + int(90 * (1 - e))

        draw.rounded_rectangle([x, y, W - MARGIN, y + row_h - 26], 14,
                               fill=fade(PANEL, BG, e))
        draw.text((x + 34, y + 26), f"{i + 1}", font=idx_f,
                  fill=fade(ACCENT, PANEL, e))
        draw.text((x + 96, y + 18), name, font=name_f, fill=fade(TEXT, PANEL, e))
        draw.text((x + 96, y + 68), desc, font=desc_f, fill=fade(MUTED, PANEL, e))

        # Pill sized from the measured label so the widest tag still gets even
        # padding on both sides. Sizing it from the right edge instead leaves
        # RECORD and GARNISH almost touching the border.
        tag = verdict.upper()
        tw = draw.textlength(tag, font=tag_f)
        pad = 30
        col = VERDICT_COLOUR[verdict]
        bx = W - MARGIN - 34 - (tw + 2 * pad)
        draw.rounded_rectangle([bx, y + 34, bx + tw + 2 * pad, y + 78], 10,
                               fill=fade(mix(PANEL, col, 0.22), PANEL, e))
        draw.text((bx + pad, y + 44), tag, font=tag_f, fill=fade(col, PANEL, e))


RULES = [
    ("If a person can say it", "Buy a presenter tool", "hours", OK),
    ("If a screen can show it", "Record the screen", "hours", OK),
    ("If there is nothing to film", "Build it from code", "10x labour", ACCENT),
]


def scene_rule(draw, f: Fonts, t: float, s: float):
    head = ease_out(min(1.0, t / 0.10))
    draw.text((MARGIN, 150), "The decision rule", font=f.get(True, 62),
              fill=fade(TEXT, BG, head))
    draw_block(draw, (MARGIN, 236), "Short enough to remember without the deck.",
               f.get(False, 32), MUTED, 900, 46, alpha=head)

    top, row_h = 350, 178
    cond_f, act_f, cost_f = f.get(False, 38), f.get(True, 46), f.get(True, 34)
    for i, (cond, action, cost, col) in enumerate(RULES):
        local = max(0.0, min(1.0, (t - 0.14 - i * 0.19) / 0.32))
        if local <= 0:
            continue
        e = ease_out(local)
        y = top + i * row_h
        highlight = col is ACCENT
        panel = mix(PANEL, ACCENT_DIM, 0.42) if highlight else PANEL
        draw.rounded_rectangle([MARGIN, y, W - MARGIN, y + row_h - 32], 16,
                               fill=fade(panel, BG, e))
        draw.text((MARGIN + 40, y + 30), cond, font=cond_f,
                  fill=fade(MUTED, panel, e))
        draw.text((MARGIN + 40, y + 80), action, font=act_f,
                  fill=fade(TEXT, panel, e))
        cw = draw.textlength(cost, font=cost_f)
        draw.text((W - MARGIN - 46 - cw, y + 58), cost, font=cost_f,
                  fill=fade(col, panel, e))


def scene_quality(draw, f: Fonts, t: float, s: float):
    a = ease_out(min(1.0, t / 0.16))
    b = ease_out(min(1.0, max(0.0, (t - 0.30) / 0.30)))
    c = ease_out(min(1.0, max(0.0, (t - 0.58) / 0.30)))

    draw.rectangle([MARGIN, 240, MARGIN + int(6), 240 + int(150 * a)], fill=ACCENT)
    y = draw_block(draw, (MARGIN + 46, 236),
                   "One off-key moment writes off the whole asset.",
                   f.get(True, 76), TEXT, W - 2 * MARGIN - 46, 96, alpha=a)

    y = draw_block(draw, (MARGIN + 46, y + 44),
                   "Retention drops measurably against flat synthetic narration, "
                   "and viewers tend to trust everything or nothing.",
                   f.get(False, 40), MUTED, W - 2 * MARGIN - 300, 58, alpha=b)

    draw_block(draw, (MARGIN + 46, y + 52),
               "So read the script aloud before you render it.",
               f.get(True, 44), ACCENT, W - 2 * MARGIN - 300, 60, alpha=c)


def scene_end(draw, f: Fonts, t: float, s: float):
    a = ease_out(min(1.0, t / 0.28))
    b = ease_out(min(1.0, max(0.0, (t - 0.34) / 0.34)))
    y = draw_block(draw, (MARGIN, 380), "Identify the job first.",
                   f.get(True, 96), TEXT, W - 2 * MARGIN, 118, alpha=a)
    y = draw_block(draw, (MARGIN, y + 30),
                   "The tool list will be stale in six months. The judgement will not.",
                   f.get(False, 42), MUTED, W - 2 * MARGIN - 300, 58, alpha=b)
    draw.rectangle([MARGIN, y + 54, MARGIN + int(240 * b), y + 58], fill=ACCENT)


RENDERERS = {
    1: scene_title,
    2: scene_problem,
    3: scene_jobs,
    4: scene_rule,
    5: scene_quality,
    6: scene_end,
}


# --------------------------------------------------------------------- render


def render(scenes: list[Scene], scale: float) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    silent = OUT / "clip-silent.mp4"
    w, h = int(W * scale), int(H * scale)
    total = sum(sc.frames for sc in scenes)
    fonts = Fonts(scale)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(silent),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    t0 = time.time()
    abs_frame = 0
    for sc in scenes:
        fn = RENDERERS.get(sc.index)
        if fn is None:
            sys.exit(f"No renderer registered for scene {sc.index}")
        for i in range(sc.frames):
            img = Image.new("RGB", (w, h), BG)
            d = ImageDraw.Draw(img)
            # Scene-local progress, 0..1 across the whole budget.
            t = i / max(1, sc.frames - 1)
            _ScaledDraw(d, scale).run(fn, fonts, t, i / FPS)
            _ScaledDraw(d, scale).run_chrome(fonts, sc, total, abs_frame, i / FPS)
            proc.stdin.write(img.tobytes())
            abs_frame += 1
        print(f"  scene {sc.index}  {sc.title:<32} {sc.budget:>5.1f}s  "
              f"{sc.frames:>4} frames", flush=True)

    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        sys.exit(f"ffmpeg exited {rc} while encoding frames")
    el = time.time() - t0
    print(f"\n  {total} frames in {el:.1f}s  "
          f"({total / el:.1f} fps, {total / FPS / el:.2f}x realtime)")
    return silent


class _ScaledDraw:
    """Lets the scene renderers work in 1920x1080 coordinates at any scale."""

    def __init__(self, draw, scale: float):
        self._d = draw
        self._s = scale

    def run(self, fn, fonts, t, s):
        fn(self, fonts, t, s)

    def run_chrome(self, fonts, scene, total, abs_frame, s):
        chrome(self, fonts, scene, total, abs_frame, s)

    def _pt(self, xy):
        return tuple(int(round(v * self._s)) for v in xy)

    def text(self, xy, *a, **k):
        self._d.text(self._pt(xy), *a, **k)

    def rectangle(self, box, **k):
        self._d.rectangle(self._pt(box), **k)

    def rounded_rectangle(self, box, radius, **k):
        self._d.rounded_rectangle(self._pt(box), int(round(radius * self._s)), **k)

    def polygon(self, points, **k):
        self._d.polygon([self._pt(pt) for pt in points], **k)

    def line(self, points, width=1, **k):
        self._d.line([self._pt(pt) for pt in points],
                     width=max(1, int(round(width * self._s))), **k)

    def ellipse(self, box, **k):
        self._d.ellipse(self._pt(box), **k)

    def textlength(self, text, font=None):
        return self._d.textlength(text, font=font) / self._s


# ---------------------------------------------------------------------- audio

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")


def find_audio(scene: Scene) -> Path | None:
    for ext in AUDIO_EXTS:
        p = AUDIO_IN / f"{scene.index:02d}{ext}"
        if p.exists():
            return p
    return None


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def check_takes(scenes: list[Scene]) -> None:
    """
    Resolve every scene's take and reject over-budget ones before anything is
    rendered.

    This runs first, deliberately. Validating after the render means a rejected
    build still overwrites clip-silent.mp4 while leaving the previous run's
    five-jobs.mp4 and verification.json in place, so out/ ends up describing a
    state that no longer exists. Failing before any file is written keeps out/
    consistent with the last successful build.
    """
    over = []
    for sc in scenes:
        sc.audio_file = find_audio(sc)
        if sc.audio_file is None:
            continue
        take = probe_duration(sc.audio_file)
        if take > sc.budget + 0.02:
            over.append((sc.index, sc.audio_file.name, take, sc.budget))

    if not over:
        return

    print("  ERROR: narration takes exceed their budget. Nothing was rendered.")
    print("  Re-cut the take, or raise the budget in narration.md:")
    for idx, name, take, budget in over:
        print(f"    scene {idx} ({name}): take {take:.2f}s > budget {budget:.2f}s "
              f"(over by {take - budget:.2f}s)")
    sys.exit(1)


def build_audio(scenes: list[Scene]) -> tuple[Path, list[dict]]:
    """
    One track per scene, each padded with silence up to its budget, then joined.

    This is the whole trick. Because every section is exactly its budget long,
    the joined track's section boundaries equal the cumulative budgets, which
    equal the animation holds. Sync is arithmetic.
    """
    # Scratch goes to local temp, never to the output folder. The output folder
    # may be a mounted Windows share, where deleting from Linux is not permitted.
    tmp = Path(tempfile.mkdtemp(prefix="clip-audio-"))

    report, parts = [], []
    for sc in scenes:
        src = sc.audio_file
        dst = tmp / f"{sc.index:02d}.m4a"
        if src is None:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", f"{sc.budget:.6f}", "-c:a", "aac", "-b:a", "160k", str(dst)],
                check=True,
            )
            report.append({"scene": sc.index, "source": "silence",
                           "take_s": 0.0, "budget_s": sc.budget, "padded_s": sc.budget})
        else:
            take = probe_duration(src)
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                 "-af", f"aresample=48000,apad=whole_dur={sc.budget:.6f}",
                 "-t", f"{sc.budget:.6f}",
                 "-ac", "2", "-c:a", "aac", "-b:a", "160k", str(dst)],
                check=True,
            )
            report.append({"scene": sc.index, "source": src.name,
                           "take_s": round(take, 3), "budget_s": sc.budget,
                           "padded_s": sc.budget})
        parts.append(dst)

    listing = tmp / "list.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    joined = OUT / "narration.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(joined)],
        check=True, cwd=tmp,
    )
    shutil.rmtree(tmp, ignore_errors=True)
    return joined, report


def mux(silent: Path, audio: Path, name: str = OUT_NAME) -> Path:
    final = OUT / name
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(final)],
        check=True,
    )
    return final


# ----------------------------------------------------------------- verification


_FRAME_SYNC: list[str] | None = None


def frame_sync_flags() -> list[str]:
    """Pick the frame-timing flag this ffmpeg actually understands.

    ffmpeg renamed -vsync to -fps_mode in 5.0 and removed -vsync outright in
    8.0. The sandbox this was written in ships 4.4.2; a current winget or brew
    install ships 9.x. Without this, frame grabbing dies with "Unrecognized
    option 'vsync'" only at the verification step, after a full render.
    """
    global _FRAME_SYNC
    if _FRAME_SYNC is None:
        out = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True
        ).stdout
        m = re.search(r"ffmpeg version n?(\d+)", out)
        # Unparseable (git snapshots report a date) means recent, so prefer the
        # modern spelling.
        major = int(m.group(1)) if m else 99
        _FRAME_SYNC = ["-vsync", "0"] if major < 5 else ["-fps_mode", "passthrough"]
    return _FRAME_SYNC


def grab_frame(path: Path, n: int, dst: Path) -> Path:
    """Decode exactly frame n out of the encoded file."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
         "-vf", f"select='eq(n\\,{n})'", *frame_sync_flags(),
         "-frames:v", "1", str(dst)],
        check=True,
    )
    return dst


def frame_delta(a: Path, b: Path) -> float:
    """Mean absolute pixel difference, 0..1."""
    import numpy as np

    ia = np.asarray(Image.open(a).convert("L"), dtype=np.int16)
    ib = np.asarray(Image.open(b).convert("L"), dtype=np.int16)
    return float(np.abs(ia - ib).mean() / 255.0)


def verify(final: Path, scenes: list[Scene], audio_report: list[dict]) -> dict:
    """
    Verify timing by differencing the frames either side of every boundary.

    ffmpeg's own scene-score filter is the obvious tool here and it does not
    work on this material: the frames are mostly dark background, so the score
    never rises above about 0.04 even across a hard cut, and every threshold
    either catches nothing or catches noise. Differencing the specific frames we
    care about is both exact and cheap, so that is what this does.

    A boundary is confirmed when the frame pair straddling it differs far more
    than an adjacent pair from the middle of the same scene.
    """
    total_budget = sum(sc.frames for sc in scenes) / FPS
    measured = probe_duration(final)

    tmp = Path(tempfile.mkdtemp(prefix="clip-verify-"))

    controls = []
    for sc in scenes:
        mid = sc.start_frame + sc.frames // 2
        a = grab_frame(final, mid, tmp / f"ctl{sc.index}a.png")
        b = grab_frame(final, mid + 1, tmp / f"ctl{sc.index}b.png")
        controls.append(frame_delta(a, b))
    control = max(controls) if controls else 0.0

    boundaries = []
    for prev, sc in zip(scenes, scenes[1:]):
        n = sc.start_frame
        a = grab_frame(final, n - 1, tmp / f"b{sc.index}a.png")
        b = grab_frame(final, n, tmp / f"b{sc.index}b.png")
        delta = frame_delta(a, b)
        boundaries.append({
            "into_scene": sc.index,
            "expected_s": round(sc.start_s, 3),
            "frame": n,
            "delta_across_boundary": round(delta, 4),
            "confirmed": bool(delta > max(4 * control, 0.004)),
        })

    shutil.rmtree(tmp, ignore_errors=True)

    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,r_frame_rate,bit_rate,sample_rate",
         "-of", "json", str(final)],
        capture_output=True, text=True, check=True,
    ).stdout

    return {
        "file": final.name,
        "size_bytes": final.stat().st_size,
        "duration_measured_s": round(measured, 3),
        "duration_budgeted_s": round(total_budget, 3),
        "duration_error_s": round(abs(measured - total_budget), 3),
        "duration_exact": abs(measured - total_budget) <= 1.0 / FPS,
        "intra_scene_control_delta_max": round(control, 4),
        "scene_boundaries": boundaries,
        "all_boundaries_confirmed": all(b["confirmed"] for b in boundaries),
        "audio_sections": audio_report,
        "streams": json.loads(streams),
    }


# ---------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-only", action="store_true",
                    help="render video only, no audio and no verification")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="resolution scale, e.g. 0.5 for a fast preview")
    ap.add_argument("--name", default=OUT_NAME,
                    help=f"output file name (default {OUT_NAME})")
    args = ap.parse_args()

    # Resolves an installed-but-not-yet-on-PATH ffmpeg, which is the usual state
    # right after `winget install`, and exits with actionable advice otherwise.
    ensure_ffmpeg()

    scenes = parse_narration(NARRATION)
    budget = sum(sc.budget for sc in scenes)
    print(f"Parsed {len(scenes)} scenes from narration.md, "
          f"total budget {budget:.1f}s at {FPS}fps "
          f"({int(round(budget * FPS))} frames)\n")

    if not args.frames_only:
        check_takes(scenes)

    silent = render(scenes, args.scale)
    if args.frames_only:
        print(f"\nWrote {silent}")
        return

    audio, report = build_audio(scenes)
    final = mux(silent, audio, args.name)
    result = verify(final, scenes, report)

    (OUT / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("\nVerification")
    print(f"  duration budgeted {result['duration_budgeted_s']}s, "
          f"measured {result['duration_measured_s']}s "
          f"(error {result['duration_error_s']}s)")
    print(f"  duration exact to the frame: {result['duration_exact']}")
    print(f"  intra-scene control delta (max) {result['intra_scene_control_delta_max']}")
    print("  boundary          frame       time     delta   confirmed")
    for m in result["scene_boundaries"]:
        print(f"  into scene {m['into_scene']:<6} {m['frame']:>7}  "
              f"{m['expected_s']:>7.3f}s  {m['delta_across_boundary']:>8.4f}   "
              f"{'yes' if m['confirmed'] else 'NO'}")
    print(f"  all boundaries confirmed: {result['all_boundaries_confirmed']}")

    have_real_audio = any(r["source"] != "silence" for r in report)
    if not have_real_audio:
        print("\n  Audio track is silence padded to each budget. "
              f"Drop takes into audio/ as 01.mp3 ... {SCENE_COUNT:02d}.mp3, "
              "or run scripts/sound/tts_narrate.py, then re-run.")

    print(f"\nWrote {final}  ({result['size_bytes'] / 1e6:.1f} MB)")
    print(f"Wrote {OUT / 'verification.json'}")


if __name__ == "__main__":
    main()
