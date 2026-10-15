"""Game rules and state. No pygame import on purpose.

The engine owns everything that decides what happens; the UI only reads this
state and forwards player input to it. One call to ``tick()`` is one frame.
"""

import random

from .board import Board, random_color_name
from .capsule import Capsule
from .config import COLUMNS, ROWS, FALL_INTERVAL_BASE, LEVEL_UP_SCORE


class GameEngine:
    def __init__(self, cols=COLUMNS, rows=ROWS, virus_count=4, rng=None):
        self.rng = rng or random.Random()
        self.board = Board(cols, rows)
        self.virus_count = self.board.spawn_viruses(virus_count, self.rng)
        self.viruses_remaining = self.virus_count

        self.active = None
        self.next_colors = (random_color_name(self.rng), random_color_name(self.rng))

        self.score = 0
        self.level = 1
        self.lines_cleared = 0
        self.fall_interval = self._interval_for_level(self.level)
        self.fall_timer = 0

        self.game_over = False
        self.won = False

    @property
    def finished(self):
        return self.game_over or self.won

    # ----- frame ------------------------------------------------------------

    def tick(self):
        """Advance one frame. Safe to keep calling after the game ends."""
        if self.finished:
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
        # Resolve before the next capsule exists, so the player never sees a
        # new piece land on a board that still owes them a clear.
        self._resolve()

    def _resolve(self):
        chain = 0
        while True:
            to_clear = self.board.find_line_clears()
            if not to_clear:
                break
            chain += 1
            self.lines_cleared += 1
            self.viruses_remaining -= sum(
                1 for (x, y) in to_clear if self.board.get(x, y)["kind"] == "virus"
            )
            self.score += len(to_clear) * 10 * chain
            self.board.remove_cells(to_clear)
            self.board.apply_gravity()
        self._refresh_level()
        if self.viruses_remaining <= 0:
            self.won = True

    def _refresh_level(self):
        self.level = 1 + self.score // LEVEL_UP_SCORE
        self.fall_interval = self._interval_for_level(self.level)

    @staticmethod
    def _interval_for_level(level):
        return max(1, FALL_INTERVAL_BASE - (level - 1) * 4)
