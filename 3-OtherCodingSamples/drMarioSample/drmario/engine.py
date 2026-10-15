"""Game rules and state. No pygame import on purpose.

The engine owns everything that decides what happens; the UI only reads this
state and forwards player input to it. One call to ``tick()`` is one frame.
"""

import random

from .board import Board, random_color_name
from .capsule import Capsule
from .config import (COLUMNS, ROWS, CLEAR_FRAMES, CASCADE_FRAMES, MAX_LEVEL,
                     SPEED_TABLE, SPEED_START, PILLS_PER_SPEEDUP, INFINITY_SPEED_STEP,
                     virus_count_for_level, virus_height_for_level)


class GameEngine:
    """One run through the levels. Clearing every virus sets ``level_cleared``;
    ``next_level()`` then deals a fresh, randomly seeded board with more
    viruses. After level ``MAX_LEVEL`` the game enters infinity mode: the
    level number keeps counting (21, 22, ...) but every board is dealt as
    level ``MAX_LEVEL``, and each round starts a little faster.

    ``speed`` is "slow", "med" or "fast" and picks the starting fall speed.
    The pill speeds up one step every PILLS_PER_SPEEDUP pills and resets to
    the starting speed on every new level, as in the NES original.

    ``virus_count`` overrides the per-level virus count (handy for tests).

    After a piece locks, matches resolve over several frames like the arcade:
    the matched blocks are shown in ``clearing`` for CLEAR_FRAMES, then vanish,
    then loose pills fall one row every CASCADE_FRAMES, and any new match the
    cascade makes starts the cycle again. ``resolving`` is True throughout and
    no capsule spawns until it ends.
    """

    def __init__(self, cols=COLUMNS, rows=ROWS, virus_count=None, rng=None,
                 level=1, speed="med"):
        self.rng = rng or random.Random()
        self.cols = cols
        self.rows = rows
        self.virus_override = virus_count
        if speed not in SPEED_START:
            raise ValueError(f"unknown speed {speed!r}")
        self.speed = speed

        self.score = 0
        self.lines_cleared = 0
        self.game_over = False
        self._start_level(max(1, min(level, MAX_LEVEL)))

    @property
    def finished(self):
        """True whenever play is paused: game over or a level clear."""
        return self.game_over or self.level_cleared

    @property
    def infinity(self):
        """Infinity-mode round (1, 2, ...), or 0 before level 20 is beaten."""
        return max(0, self.level - MAX_LEVEL)

    @property
    def speed_step(self):
        """Index into SPEED_TABLE for the current pill."""
        step = (SPEED_START[self.speed]
                + self.infinity * INFINITY_SPEED_STEP
                + self.pills_dealt // PILLS_PER_SPEEDUP)
        return min(step, len(SPEED_TABLE) - 1)

    @property
    def fall_interval(self):
        """Frames per row for the falling pill."""
        return SPEED_TABLE[self.speed_step]

    # ----- levels -----------------------------------------------------------

    def _start_level(self, level):
        self.level = level
        self.level_cleared = False
        self.board = Board(self.cols, self.rows)
        board_level = min(level, MAX_LEVEL)    # infinity mode reuses level 20
        count = (self.virus_override if self.virus_override is not None
                 else virus_count_for_level(board_level))
        self.virus_count = self.board.spawn_viruses(
            count, self.rng, max_height=virus_height_for_level(board_level, self.rows))
        self.viruses_remaining = self.virus_count

        self.active = None
        self.next_colors = (random_color_name(self.rng), random_color_name(self.rng))
        self.pills_dealt = 0       # this level; drives the gradual speed-up
        self.fall_timer = 0

        self.phase = None          # None, "clearing" or "falling"
        self.phase_timer = 0
        self.clearing = set()
        self.chain = 0

    @property
    def resolving(self):
        return self.phase is not None

    def next_level(self):
        """Advance after a level clear. Score carries over."""
        if not self.level_cleared:
            return False
        self._start_level(self.level + 1)
        return True

    # ----- frame ------------------------------------------------------------

    def tick(self):
        """Advance one frame. Safe to keep calling after the game ends."""
        if self.finished:
            return
        if self.resolving:
            self._advance_resolve()
            return
        if self.active is None:
            self._spawn()
            return
        self.fall_timer += 1
        if self.fall_timer >= self.fall_interval:
            self.fall_timer = 0
            if not self.active.move_down():
                self._lock()

    # ----- player input -----------------------------------------------------

    def move_left(self):
        return bool(self._controllable() and self.active.move_left())

    def move_right(self):
        return bool(self._controllable() and self.active.move_right())

    def rotate(self, clockwise=True):
        return bool(self._controllable() and self.active.rotate(clockwise))

    def soft_drop(self):
        if not self._controllable():
            return False
        if not self.active.move_down():
            return False
        # Reset the timer so a manual nudge is not immediately followed by the
        # automatic one, which used to drop the piece two cells in one frame.
        self.fall_timer = 0
        self.score += 1
        return True

    def hard_drop(self):
        if not self._controllable():
            return False
        self.score += self.active.hard_drop()
        self._lock()
        return True

    def _controllable(self):
        return self.active is not None and not self.finished

    # ----- internals --------------------------------------------------------

    def _spawn(self):
        capsule = Capsule(self.board, x=self.board.cols // 2 - 1, y=0,
                          color1=self.next_colors[0], color2=self.next_colors[1],
                          rng=self.rng)
        if not self.board.can_place_capsule(capsule.positions()):
            self.game_over = True
            return False
        self.active = capsule
        # Only draw the next pair once this one is really on the board, so the
        # preview always shows the piece the player is actually promised.
        self.next_colors = (random_color_name(self.rng), random_color_name(self.rng))
        self.fall_timer = 0
        return True

    def _lock(self):
        self.active.lock_to_board()
        self.active = None
        self.fall_timer = 0
        self.pills_dealt += 1
        # Resolve before the next capsule exists, so the player never sees a
        # new piece land on a board that still owes them a clear.
        self.chain = 0
        self._find_matches()

    def _find_matches(self):
        """Start a clear if the board has a match, otherwise end resolving."""
        to_clear = self.board.find_line_clears()
        if not to_clear:
            self.phase = None
            return
        self.chain += 1
        self.lines_cleared += 1
        self.score += len(to_clear) * 10 * self.chain
        self.clearing = to_clear
        self.phase = "clearing"
        self.phase_timer = CLEAR_FRAMES

    def _advance_resolve(self):
        self.phase_timer -= 1
        if self.phase_timer > 0:
            return
        if self.phase == "clearing":
            self.viruses_remaining -= sum(
                1 for (x, y) in self.clearing if self.board.get(x, y)["kind"] == "virus"
            )
            self.board.remove_cells(self.clearing)
            self.clearing = set()
            if self.viruses_remaining <= 0:
                self.phase = None
                self.level_cleared = True
                return
            self.phase = "falling"
            self.phase_timer = CASCADE_FRAMES
        elif self.board.gravity_step():
            self.phase_timer = CASCADE_FRAMES
        else:
            # Settled: the cascade may have lined up a new match (a combo).
            self._find_matches()
