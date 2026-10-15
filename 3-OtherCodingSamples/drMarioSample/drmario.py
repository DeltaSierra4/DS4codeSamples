#!/usr/bin/env python3
"""
Minimal Doctor-Mario-like game using Pygame.

Controls:
  Left / Right arrows  -> move capsule horizontally
  Down arrow           -> soft drop (faster fall)
  Z                    -> rotate counter-clockwise
  X or Up arrow        -> rotate clockwise
  Space                -> hard drop (instant)
  R                    -> restart
  Esc or Q             -> quit

Matching rule: 4 or more same-coloured blocks contiguous in a straight
horizontal or vertical line clears them. Viruses match pill halves of the same
colour. Clear every virus to win.

Rotation follows the arcade: a flat pill stands up into its own column,
growing into the row above, pivoting on its left half. Turning clockwise
swings the left half to the top, two turns swap the halves, and four restore
the pill. Standing up against the right wall or a block shifts the pill one
column left.

Layout:
  drmario/config.py   tunables and palette
  drmario/board.py    grid, matching, gravity          (no pygame)
  drmario/capsule.py  the active falling piece         (no pygame)
  drmario/engine.py   game rules and state             (no pygame)
  drmario/ui.py       rendering and input              (pygame)

Only ui.py needs pygame, so the rules can be tested headlessly: python -m pytest
"""

from drmario.ui import main

if __name__ == "__main__":
    main()
