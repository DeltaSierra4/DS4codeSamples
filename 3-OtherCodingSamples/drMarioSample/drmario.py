#!/usr/bin/env python3
"""
Minimal Doctor-Mario-like game using Pygame.

Start menu:
  Up / Down            -> choose Level or Speed
  Left / Right         -> change it (level 1-20; speed Slow, Med or Fast)
  Enter                -> start

Controls:
  Left / Right arrows  -> move capsule horizontally
  Down arrow           -> soft drop (faster fall)
  Z                    -> rotate counter-clockwise
  X or Up arrow        -> rotate clockwise
  Space                -> hard drop (instant)
  Enter                -> start the next level after a clear
  R                    -> back to the start menu
  Esc or Q             -> quit

Matching rule: 4 or more same-coloured blocks contiguous in a straight
horizontal or vertical line clears them. Viruses match pill halves of the same
colour. Clear every virus to finish a level. There are 20 levels: level N
starts with 4 x N viruses at random positions. Beating level 20 enters
infinity mode: level 20 again and again, each round starting a little faster.

Speed works like the NES original: the menu picks the starting speed, the pill
falls one step faster every 10 pills, and each new level starts back at the
chosen speed.

After a clear, the matched blocks flash, vanish, and loose pills cascade down
one row at a time, as in the arcade. A flat capsule is held up by either half,
so one half can overhang a gap until its partner is cleared; joined halves are
drawn as one piece so this is visible.

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
