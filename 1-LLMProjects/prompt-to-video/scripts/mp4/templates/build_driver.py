#!/usr/bin/env python3
"""
Driver template. Copy this into output/<name>/ and replace the renderers.

This is a driver, NOT a fork. It imports the verified builder in build.py
unchanged, swaps in its own narration script, its own scene renderers and its
own output directory, then hands control back. Nothing in build.py is edited, so
the parsing, budget arithmetic, silence padding, muxing and verification are the
same code that carries the guarantees.

    python3 build_driver.py                # full 1080p render, verified
    python3 build_driver.py --scale 0.5    # fast half resolution look
    python3 build_driver.py --frames-only  # video only, no audio, no verify

Two things to change before this runs anywhere real:

  1. ENGINE below, to wherever scripts/mp4 actually is.
  2. Every renderer, and OUT_NAME.

The three renderers here are deliberately plain. They exist to show the
signature and the timing convention, not to be good design.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# A generated driver lives in output/<name>/, so it cannot find the engine by
# walking up from itself. /video-full writes this line with an absolute path.
ENGINE = HERE.parent.parent / "scripts" / "mp4"
sys.path.insert(0, str(ENGINE))

import build  # noqa: E402  the sys.path line above has to run first
from build import (  # noqa: E402
    ACCENT,
    BG,
    MARGIN,
    MUTED,
    TEXT,
    W,
    Fonts,
    draw_block,
    ease_out,
    fade,
)

OUT_NAME = "example.mp4"


def _in(t: float, start: float, span: float) -> float:
    """Eased 0..1 for an element that begins at `start` and takes `span`.

    `t` is scene-local progress, 0 at the first frame of the scene and 1 at the
    last, so every timing here is a FRACTION of the scene rather than a frame
    count. That is what makes a budget change in narration.md re-time the scene
    automatically. Never hardcode frames.
    """
    return ease_out(max(0.0, min(1.0, (t - start) / span)))


# --------------------------------------------------------------- 1  title card


def scene_title(draw, f: Fonts, t: float, s: float):
    a = _in(t, 0.00, 0.30)
    rule = _in(t, 0.12, 0.35)
    sub = _in(t, 0.30, 0.35)

    y = 330 + int(28 * (1 - a))
    draw.text((MARGIN, y), "Your headline", font=f.get(True, 112),
              fill=fade(TEXT, BG, a))
    draw.rectangle([MARGIN, y + 150, MARGIN + int(240 * rule), y + 157],
                   fill=fade(ACCENT, BG, rule))
    draw_block(draw, (MARGIN, y + 196), "One line of subtitle underneath it.",
               f.get(False, 34), MUTED, W - 2 * MARGIN, 46, alpha=sub)


# ------------------------------------------------------------- 2  the substance


def scene_substance(draw, f: Fonts, t: float, s: float):
    head = _in(t, 0.00, 0.22)
    body = _in(t, 0.18, 0.30)
    count = _in(t, 0.30, 0.45)

    draw.text((MARGIN, 210), "The claim", font=f.get(True, 60),
              fill=fade(TEXT, BG, head))
    draw_block(draw, (MARGIN, 320),
               "The sentence that supports it, wrapped by draw_block so it "
               "never runs off the frame.",
               f.get(False, 34), MUTED, W - 2 * MARGIN, 50, alpha=body)

    # A counter, so the frame has something that moves with the words.
    draw.text((MARGIN, 470), f"{int(round(100 * count))}%",
              font=f.get(True, 150), fill=fade(ACCENT, BG, count))


# ------------------------------------------------------------------- 3  close


def scene_close(draw, f: Fonts, t: float, s: float):
    a = _in(t, 0.05, 0.35)
    draw_block(draw, (MARGIN, 380), "The line you want them to leave with.",
               f.get(True, 72), TEXT, W - 2 * MARGIN, 92, alpha=a)


# One renderer per scene index in narration.md. A missing index is a hard error,
# so this table and the headings have to stay in step.
RENDERERS = {
    1: scene_title,
    2: scene_substance,
    3: scene_close,
}


def main() -> None:
    # Point the inherited builder at this project without touching its source.
    build.NARRATION = HERE / "narration.md"
    build.OUT = HERE
    build.AUDIO_IN = HERE / "audio"
    build.RENDERERS = RENDERERS
    build.OUT_NAME = OUT_NAME

    if "--name" not in sys.argv:
        sys.argv += ["--name", OUT_NAME]
    build.main()


if __name__ == "__main__":
    main()
