"""Tunables and palette. Deliberately free of pygame so the rules engine
can be imported (and tested) without a display."""

CELL = 28               # pixel size of a cell
COLUMNS = 8
ROWS = 16
SCREEN_W = COLUMNS * CELL + 200
SCREEN_H = ROWS * CELL
FPS = 60

COLORS = {
    "empty": (18, 18, 18),
    "grid": (30, 30, 30),
    "red": (220, 50, 50),
    "blue": (60, 140, 240),
    "yellow": (240, 200, 50),
    "pill_border": (50, 50, 50),
    "text": (230, 230, 230),
}
COLOR_LIST = ["red", "blue", "yellow"]

# mechanics
FALL_INTERVAL_BASE = 48   # frames per cell at level 1 (lower -> faster)
LEVEL_UP_SCORE = 1000
MATCH_LENGTH = 4
