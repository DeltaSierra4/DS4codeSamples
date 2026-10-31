"""The active falling capsule. No pygame import on purpose.

Rotation follows the arcade. (self.x, self.y) is the anchor and never moves
when the pill turns: it is the LEFT half when the pill lies flat and the
BOTTOM half when it stands upright, so standing a pill up grows it into the
row above rather than the row below.

Orientation is a quarter-turn index, counted clockwise on screen:

    0  flat,     color1 left                 1  upright, color1 on top
    2  flat,     color1 right                3  upright, color1 on the bottom

Turning clockwise swings the left half to the top, which is what a rigid
capsule physically does; four quarter-turns restore the pill exactly, and two
swap its halves.
"""

from .board import Board, random_color_name


class Capsule:
    _id_counter = 1

    def __init__(self, board: Board, x=None, y=0, color1=None, color2=None, rng=None):
        self.board = board
        self.id = Capsule._id_counter
        Capsule._id_counter += 1
        self.x = x if x is not None else board.cols // 2 - 1
        self.y = y
        self.orientation = 0
        self.color1 = color1 if color1 is not None else random_color_name(rng)
        self.color2 = color2 if color2 is not None else random_color_name(rng)
        self.settled = False

    def cells(self):
        """[((x, y), half_name, color), ...] for the two halves."""
        if self.orientation == 0:
            return [((self.x, self.y), "L", self.color1),
                    ((self.x + 1, self.y), "R", self.color2)]
        if self.orientation == 1:
            return [((self.x, self.y - 1), "U", self.color1),
                    ((self.x, self.y), "D", self.color2)]
        if self.orientation == 2:
            return [((self.x, self.y), "L", self.color2),
                    ((self.x + 1, self.y), "R", self.color1)]
        return [((self.x, self.y - 1), "U", self.color2),
                ((self.x, self.y), "D", self.color1)]

    @property
    def upright(self):
        return self.orientation % 2 == 1

    def positions(self):
        return [cell[0] for cell in self.cells()]

    # ----- movement ---------------------------------------------------------

    def try_move(self, dx, dy):
        moved = [(x + dx, y + dy) for (x, y) in self.positions()]
        if self.board.can_place_capsule(moved):
            self.x += dx
            self.y += dy
            return True
        return False

    def move_left(self):
        return self.try_move(-1, 0)

    def move_right(self):
        return self.try_move(1, 0)

    def move_down(self):
        return self.try_move(0, 1)

    def hard_drop(self):
        dropped = 0
        while self.move_down():
            dropped += 1
        return dropped

    def rotate(self, clockwise=True):
        """Turn one quarter-step.

        Either the requested orientation is reached or nothing changes at all:
        a turn that will not fit fails outright rather than settling for some
        other orientation.
        """
        old_orientation, old_x, old_y = self.orientation, self.x, self.y
        self.orientation = (self.orientation + (1 if clockwise else -1)) % 4

        if self.upright:
            # Standing up keeps the column and grows into the row above. The
            # only give is against the ceiling; a settled block overhead
            # refuses the turn, as the arcade does.
            overhead = min(y for (_x, y) in self.positions())
            offsets = [(0, -overhead)] if overhead < 0 else [(0, 0)]
        else:
            # Lying flat grows to the right, so the arcade shifts the pill one
            # column left when the wall or a settled block is in the way.
            offsets = [(0, 0), (-1, 0)]

        for (dx, dy) in offsets:
            self.x, self.y = old_x + dx, old_y + dy
            if self.board.can_place_capsule(self.positions()):
                return True

        self.orientation, self.x, self.y = old_orientation, old_x, old_y
        return False

    # ----- locking ----------------------------------------------------------

    def lock_to_board(self):
        """Write both halves into the grid as settled pill blocks."""
        placed = [(pos, half, color) for (pos, half, color) in self.cells()
                  if self.board.in_bounds(*pos)]
        # A half that fell off the board would leave its partner holding a pair
        # id that matches nothing, so the survivor becomes a single instead.
        joined = len(placed) == 2
        for ((x, y), half, color) in placed:
            self.board.set(x, y, {
                "kind": "pill",
                "color": color,
                "pair": self.id if joined else None,
                "half": half if joined else "S",
            })
        self.settled = True
