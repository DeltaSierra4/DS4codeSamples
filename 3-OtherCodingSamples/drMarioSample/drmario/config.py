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
MATCH_LENGTH = 4
CLEAR_FRAMES = 18         # how long cleared blocks stay on screen before vanishing
CASCADE_FRAMES = 6        # frames per row while loose pills fall after a clear

# speed, modelled on the NES original: the level does not set the speed. The
# player picks a starting step in SPEED_TABLE (frames per row, lower is faster),
# the pill speeds up one step every PILLS_PER_SPEEDUP pills, and each new level
# starts back at the chosen speed. The table stops at 5 frames per row, about
# the fastest the original reaches in normal play.
SPEED_TABLE = (
    70, 68, 66, 64, 62, 60, 58, 56, 54, 52,
    50, 48, 46, 44, 42, 40, 38, 36, 34, 32,
    30, 28, 26, 24, 22, 20, 19, 18, 17, 16,
    15, 14, 13, 12, 11, 10, 9, 9, 8, 8,
    7, 7, 6, 6, 5,
)
SPEEDS = ("slow", "med", "fast")
SPEED_START = {"slow": 15, "med": 25, "fast": 31}   # 40, 20 and 14 frames per row
PILLS_PER_SPEEDUP = 10
# After level 20 comes infinity mode: level 20 again and again, each round
# starting this many steps faster than the last.
INFINITY_SPEED_STEP = 2

# levels, as in the original: four more viruses each level, and from level 15
# they are allowed to sit higher up the bottle so they still fit.
MAX_LEVEL = 20
VIRUSES_PER_LEVEL = 4


def virus_count_for_level(level):
    return VIRUSES_PER_LEVEL * level


def virus_height_for_level(level, rows=ROWS):
    """How many rows, counted up from the bottom, viruses may occupy."""
    if level >= 19:
        height = 13
    elif level >= 17:
        height = 12
    elif level >= 15:
        height = 11
    else:
        height = 10
    # Always leave the top three rows clear for the incoming capsule.
    return max(1, min(height, rows - 3))
