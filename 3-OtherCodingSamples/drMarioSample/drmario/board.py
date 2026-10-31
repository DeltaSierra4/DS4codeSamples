"""Board state plus the matching and gravity rules.

Deliberately free of pygame: everything here is plain data, so the rules can
be exercised without a display.

A cell is either EMPTY or a dict:
    {"kind": "virus", "color": "red"}
    {"kind": "pill",  "color": "red", "pair": 12, "half": "L"}

``pair`` links the two halves of one capsule. It becomes None (and ``half``
becomes "S") when the other half is cleared, leaving a free-falling single.
"""

import random

from .config import COLUMNS, ROWS, COLOR_LIST, MATCH_LENGTH

EMPTY = None


def random_color_name(rng=None):
    return (rng or random).choice(COLOR_LIST)


class Board:
    def __init__(self, cols=COLUMNS, rows=ROWS):
        self.cols = cols
        self.rows = rows
        self.grid = [[EMPTY for _ in range(rows)] for _ in range(cols)]

    def clear(self):
        self.grid = [[EMPTY for _ in range(self.rows)] for _ in range(self.cols)]

    def in_bounds(self, x, y):
        return 0 <= x < self.cols and 0 <= y < self.rows

    def get(self, x, y):
        if not self.in_bounds(x, y):
            return None
        return self.grid[x][y]

    def set(self, x, y, value):
        if not self.in_bounds(x, y):
            return
        self.grid[x][y] = value

    def occupied_cells(self):
        for x in range(self.cols):
            for y in range(self.rows):
                cell = self.grid[x][y]
                if cell is not EMPTY:
                    yield x, y, cell

    # ----- virus placement -------------------------------------------------

    def spawn_viruses(self, count, rng=None, max_height=None):
        """Place up to ``count`` viruses at random in the bottom ``max_height``
        rows (the lower half by default).

        Colours are dealt evenly, as in the arcade: each colour gets
        ``count // 3`` viruses and any remainder goes to randomly chosen
        colours, so no two counts differ by more than one.

        Never places a virus that would complete a match, so the opening board
        cannot hand the player a free clear. Returns the number actually
        placed, which may be short of ``count`` on a cramped board.
        """
        rng = rng or random
        if max_height is None:
            max_height = self.rows // 2
        top = self.rows - max(1, min(max_height, self.rows))

        quota = {color: count // len(COLOR_LIST) for color in COLOR_LIST}
        for color in rng.sample(COLOR_LIST, count % len(COLOR_LIST)):
            quota[color] += 1

        placed = 0
        attempts = 0
        limit = max(count, 1) * 200
        while placed < count and attempts < limit:
            attempts += 1
            x = rng.randrange(self.cols)
            y = rng.randrange(top, self.rows)
            if self.get(x, y) is not EMPTY:
                continue
            # Offer the colour that is furthest behind its quota first (ties in
            # random order), falling back to the others if it would match.
            colors = [c for c in COLOR_LIST if quota[c] > 0]
            rng.shuffle(colors)
            colors.sort(key=lambda c: -quota[c])
            for color in colors:
                self.set(x, y, {"kind": "virus", "color": color})
                if not self._completes_match(x, y):
                    quota[color] -= 1
                    placed += 1
                    break
                self.set(x, y, EMPTY)
        return placed

    def _completes_match(self, x, y):
        """Is the cell at (x, y) part of a run long enough to clear?"""
        cell = self.get(x, y)
        if cell is None:
            return False
        color = cell["color"]
        for (dx, dy) in ((1, 0), (0, 1)):
            run = 1
            for step in (1, -1):
                nx, ny = x + dx * step, y + dy * step
                while True:
                    c = self.get(nx, ny)
                    if c is None or c["color"] != color:
                        break
                    run += 1
                    nx, ny = nx + dx * step, ny + dy * step
            if run >= MATCH_LENGTH:
                return True
        return False

    # ----- matching ---------------------------------------------------------

    def find_line_clears(self):
        """Coordinates of every horizontal or vertical same-colour run of at
        least MATCH_LENGTH. Viruses and pill halves match each other."""
        to_clear = set()
        for horizontal, outer, inner in (
            (True, self.rows, self.cols),    # horizontal runs
            (False, self.cols, self.rows),   # vertical runs
        ):
            for a in range(outer):
                b = 0
                while b < inner:
                    x, y = (b, a) if horizontal else (a, b)
                    cell = self.get(x, y)
                    if cell is EMPTY:
                        b += 1
                        continue
                    color = cell["color"]
                    run = [(x, y)]
                    step = b + 1
                    while step < inner:
                        nx, ny = (step, a) if horizontal else (a, step)
                        c = self.get(nx, ny)
                        if c is None or c["color"] != color:
                            break
                        run.append((nx, ny))
                        step += 1
                    if len(run) >= MATCH_LENGTH:
                        to_clear.update(run)
                    b = step
        return to_clear

    def remove_cells(self, coords):
        """Clear ``coords``. Any capsule that loses one half leaves the other
        behind as a free-falling single."""
        coords = set(coords)
        orphaned_pairs = set()
        for (x, y) in coords:
            cell = self.get(x, y)
            if cell is None:
                continue
            if cell["kind"] == "pill" and cell.get("pair") is not None:
                orphaned_pairs.add(cell["pair"])
            self.set(x, y, EMPTY)
        if not orphaned_pairs:
            return
        for _x, _y, cell in self.occupied_cells():
            if cell.get("pair") in orphaned_pairs:
                cell["pair"] = None
                cell["half"] = "S"

    # ----- gravity ----------------------------------------------------------

    def _rigid_bodies(self):
        """Partition the movable cells into rigid bodies.

        A joined capsule is one body of two cells, so both halves fall together
        or not at all. A half whose partner was cleared is a body of one.
        Viruses never move and are excluded.
        """
        bodies = []
        claimed = set()
        for x, y, cell in self.occupied_cells():
            if (x, y) in claimed or cell["kind"] == "virus":
                continue
            body = [(x, y)]
            pair = cell.get("pair")
            if pair is not None:
                for (nx, ny) in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
                    other = self.get(nx, ny)
                    if other is not None and other.get("pair") == pair:
                        body.append((nx, ny))
                        break
            claimed.update(body)
            bodies.append(body)
        return bodies

    def gravity_step(self):
        """Drop every unsupported body by one row. Returns True if anything
        moved. The engine calls this on a timer to animate a cascade."""
        falling = []
        for body in self._rigid_bodies():
            cells = set(body)
            if all(
                (x, y + 1) in cells or
                (self.in_bounds(x, y + 1) and self.get(x, y + 1) is EMPTY)
                for (x, y) in body
            ):
                falling.append(body)
        for body in falling:
            payload = [(x, y, self.get(x, y)) for (x, y) in body]
            for (x, y, _cell) in payload:
                self.set(x, y, EMPTY)
            for (x, y, cell) in payload:
                self.set(x, y + 1, cell)
        return bool(falling)

    def apply_gravity(self):
        """Drop every unsupported body until the board is stable.

        Returns True if anything moved. One call always leaves the board at a
        fixed point, so callers do not need to loop.
        """
        moved_any = False
        while self.gravity_step():
            moved_any = True
        return moved_any

    # ----- misc -------------------------------------------------------------

    def can_place_capsule(self, positions):
        """True when every (x, y) is on the board and unoccupied."""
        for (x, y) in positions:
            if not self.in_bounds(x, y):
                return False
            if self.get(x, y) is not EMPTY:
                return False
        return True

    def render_text(self):
        """Debug view of the whole board, one line per row."""
        lines = []
        for y in range(self.rows):
            row = []
            for x in range(self.cols):
                cell = self.get(x, y)
                if cell is None:
                    row.append("...")
                elif cell["kind"] == "virus":
                    row.append(cell["color"][0] + "Vi")
                else:
                    pair = cell["pair"]
                    tag = "N" if pair is None else str(pair % 10)
                    row.append(cell["color"][0] + tag + cell["half"][0])
            lines.append(" ".join(row))
        return "\n".join(lines)
