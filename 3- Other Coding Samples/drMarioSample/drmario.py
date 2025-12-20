#!/usr/bin/env python3
"""
Minimal Doctor-Mario-like game using Pygame.

Controls:
  Left / Right arrows  -> move capsule horizontally
  Down arrow           -> soft drop (faster fall)
  Z                    -> rotate counter-clockwise
  X or Up arrow        -> rotate clockwise
  Space                -> hard drop (instant)
  Esc or Q             -> quit

Notes:
- Uses simple drawn shapes for capsules and viruses.
- Matching rule: 4 or more same-colored blocks contiguous in a straight horizontal or vertical line clears them.
- After clears, gravity applies to floating pill halves and viruses remain static until cleared.
"""

import random
import sys
import pygame
from pygame import Rect
import time

# ----- Config -----
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
    "virus": (40, 40, 40),
    "text": (230, 230, 230)
}
COLOR_LIST = ["red", "blue", "yellow"]

# mechanics
FALL_INTERVAL_BASE = 48   # frames per cell at level 1 (lower -> faster)
LEVEL_UP_SCORE = 1000

# block types
EMPTY = None

# block tuple: (kind, color)
# kind: "virus" or "pill"
# pill will also have a "half_id" and an id to pair halves (we track pair by id in grid)
# to keep it simple in grid we store dictionaries for occupied cells:
# e.g.: {"kind":"pill","color":"red","pair": 123, "half": "L"} or {"kind":"virus","color":"blue"}


# ----- Helpers -----
def random_color_name():
    return random.choice(COLOR_LIST)


def in_bounds(x, y):
    return 0 <= x < COLUMNS and 0 <= y < ROWS


# ----- Game Board -----
class Board:
    def __init__(self, cols=COLUMNS, rows=ROWS):
        self.cols = cols
        self.rows = rows
        self.grid = [[EMPTY for _ in range(rows)] for _ in range(cols)]

    def clear(self):
        self.grid = [[EMPTY for _ in range(self.rows)] for _ in range(self.cols)]

    def get(self, x, y):
        if not in_bounds(x, y):
            return None
        return self.grid[x][y]

    def set(self, x, y, value):
        if not in_bounds(x, y):
            return
        self.grid[x][y] = value

    def spawn_viruses(self, count):
        """Place viruses randomly across the lower part of the board (not too high)."""
        placed = 0
        attempts = 0
        while placed < count and attempts < count * 100:
            x = random.randrange(self.cols)
            y = random.randrange(self.rows // 2, self.rows)  # viruses in bottom half
            if self.get(x, y) is EMPTY:
                self.set(x, y, {"kind": "virus", "color": random_color_name()})
                placed += 1
            attempts += 1

    def find_line_clears(self):
        """Find horizontal or vertical contiguous segments of same color length >=4.
        Return set of coordinates to clear.
        """
        to_clear = set()

        # Horizontal
        for y in range(self.rows):
            x = 0
            while x < self.cols:
                cell = self.get(x, y)
                if cell is EMPTY:
                    x += 1
                    continue
                color = cell["color"]
                run = [(x, y)]
                x2 = x + 1
                while x2 < self.cols:
                    c = self.get(x2, y)
                    if c is not None and c["color"] == color:
                        run.append((x2, y)); x2 += 1
                    else:
                        break
                if len(run) >= 4:
                    to_clear.update(run)
                x = x2

        # Vertical
        for x in range(self.cols):
            y = 0
            while y < self.rows:
                cell = self.get(x, y)
                if cell is EMPTY:
                    y += 1
                    continue
                color = cell["color"]
                run = [(x, y)]
                y2 = y + 1
                while y2 < self.rows:
                    c = self.get(x, y2)
                    if c is not None and c["color"] == color:
                        run.append((x, y2)); y2 += 1
                    else:
                        break
                if len(run) >= 4:
                    to_clear.update(run)
                y = y2
        return to_clear

    def apply_gravity(self):
        """Make unsupported pill halves fall down until they land."""
        moved = False
        # columns individually bottom-up
        for x in range(self.cols):
            # for each column compress down pill halves/viruses; viruses don't fall
            write_row = self.rows - 1
            read_row = self.rows - 1
            while read_row >= 0:
                cell = self.get(x, read_row)
                if cell is None:
                    read_row -= 1
                    continue
                # viruses stay in place: we copy them to their same spot
                if cell["kind"] == "virus":
                    # if read_row != write_row, we must move stuff above down onto viruses? no, viruses act as solid anchors
                    # So we set write_row to virus position and skip moving
                    write_row = read_row - 1
                    read_row = read_row - 1
                    continue
                else:
                    """ 
                        First, check if this is a full horizontal pill or a pill half.
                        If it is a pill half, simply cascade it down as normal.
                        But if it is a full pill, drop it down to whichever pill half
                        has the higher anchor point.
                    """
                    left_neighbor = self.get(x - 1, read_row)
                    right_neighbor = self.get(x + 1, read_row)
                    left_neighbor_id = -1
                    right_neighbor_id = -1
                    if left_neighbor and left_neighbor["kind"] == "pill":
                        left_neighbor_id = left_neighbor["pair"]
                    if right_neighbor and right_neighbor["kind"] == "pill":
                        right_neighbor_id = right_neighbor["pair"]
                    
                    left_full_pill = (cell["pair"] == left_neighbor_id)
                    right_full_pill = (cell["pair"] == right_neighbor_id)
                    modifier = 0
                    if left_full_pill:
                        modifier = -1
                    elif right_full_pill:
                        modifier = 1
                    if modifier:
                        neighbor_x = x + modifier
                        orig_neighbor = self.get(neighbor_x, read_row)
                        read_row_2 = read_row + 1
                        write_row_2 = read_row_2
                        while read_row_2 <= self.rows - 1:
                            cell_2 = self.get(neighbor_x, read_row_2)
                            if cell_2 is None:
                                read_row_2 += 1
                                continue
                            else:
                                # Greedy process: If any object is found, treat this as the landing point.
                                write_row_2 = read_row_2 - 1
                                break

                        write_row = min(write_row, write_row_2)
                        if write_row != read_row:
                            # move both pairs
                            self.set(x, write_row, cell)
                            self.set(x, read_row, EMPTY)
                            self.set(neighbor_x, write_row, orig_neighbor)
                            self.set(neighbor_x, read_row, EMPTY)
                            moved = True
                    else:
                        # pill halves should fall to the next empty slot above write_row
                        # find next empty position
                        if write_row != read_row:
                            # move
                            self.set(x, write_row, cell)
                            self.set(x, read_row, EMPTY)
                            moved = True
                    write_row -= 1
                    read_row -= 1
            # done column
        return moved

    def remove_cells(self, coords):
        for (x, y) in coords:
            cell = self.get(x, y)
            if cell is None:
                continue

            # If removing a pill half, and the other half still exists, break the pair (remove pair linking)
            if cell["kind"] == "pill":
                pair_id = cell.get("pair")
                # find and set any matching pair halves to pill single (we leave the other half but with no pair reference)
                if pair_id is not None:
                    for xx in range(self.cols):
                        for yy in range(self.rows):
                            c2 = self.get(xx, yy)
                            if c2 and c2.get("pair") == pair_id:
                                # if this cell is also being cleared, it will be set to EMPTY below
                                # so skip; otherwise remove pair reference (becomes single block)
                                if (xx, yy) in coords:
                                    continue
                                # set pair reference to None for the surviving half
                                c2["pair"] = None
                                c2["half"] = "S"  # single
            self.set(x, y, EMPTY)

    def can_place_capsule(self, positions):
        """positions: list of (x,y) to check empty and in-bounds"""
        for (x, y) in positions:
            if not in_bounds(x, y):
                return False
            if self.get(x, y) is not EMPTY:
                return False
        return True
    
    def draw_board(self):
        empty_row = ["000"] * self.cols
        board = [list(empty_row), list(empty_row), list(empty_row)]
        for y in range(self.rows - 3, self.rows):
            for x in range(self.cols):
                cell = self.get(x, y)
                if cell is None:
                    continue
                if cell["kind"] == "virus":
                    board[y - (self.rows - 3)][x] = cell["color"][0] + "Vi"
                else:
                    if cell["pair"] is None:
                        board[y - (self.rows - 3)][x] = cell["color"][0] + "N" + cell["half"][0]
                    else:
                        board[y - (self.rows - 3)][x] = cell["color"][0] + str(cell["pair"]) + cell["half"][0]

        board_str = ""
        for r in board:
            row = ""
            for s in r:
                row += s + " "
            board_str += row.strip() + "\n"
        print(board_str.strip())


# ----- Capsule (active piece) -----
class Capsule:
    _id_counter = 1

    def __init__(self, board: Board, x=None, y=0, color1=None, color2=None):
        self.board = board
        self.id = Capsule._id_counter; Capsule._id_counter += 1
        # spawn near top center
        self.x = x if x is not None else board.cols // 2 - 1
        self.y = y
        # orientation: 0=horizontal (colors left/right), 1=vertical with color1 above, 2=horizontal flipped, 3=vertical with color1 below
        self.orientation = 0
        self.color1 = color1 if color1 is not None else random_color_name()
        self.color2 = color2 if color2 is not None else random_color_name()
        # active positions will be computed; we track whether it's settled
        self.settled = False

    def cells(self):
        """Return list of ((x,y), half_name, color) for the two halves according to orientation"""
        if self.orientation % 2 == 0:
            # horizontal: left (color1) at (x,y), right (color2) at (x+1,y)
            if self.orientation == 0:
                return [((self.x, self.y), "L", self.color1), ((self.x + 1, self.y), "R", self.color2)]
            else:
                # orientation 2 (flipped): left (color2), right (color1)
                return [((self.x, self.y), "L", self.color2), ((self.x + 1, self.y), "R", self.color1)]
        else:
            # vertical
            if self.orientation == 1:
                # color1 above at (x,y), color2 below at (x, y+1)
                return [((self.x, self.y), "U", self.color1), ((self.x, self.y + 1), "D", self.color2)]
            else:
                # orientation 3: color2 above, color1 below
                return [((self.x, self.y), "U", self.color2), ((self.x, self.y + 1), "D", self.color1)]

    def try_move(self, dx, dy):
        new_positions = [ (x+dx, y+dy) for ((x,y),_,_) in [(p[0],p[1],p[2]) for p in [((0,0),0,0)]] ]  # dummy to satisfy structure
        # compute properly:
        positions = [(x+dx, y+dy) for ((x, y), _, _) in self.cells()]
        if self.board.can_place_capsule(positions):
            self.x += dx; self.y += dy
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
        old_o = self.orientation
        new_o = (self.orientation + (1 if clockwise else -1)) % 4
        # rotation pivot rules: we'll pivot around the first block returned by cells()
        # compute new top-left candidate x,y to preserve approximate position
        # naive approach: attempt rotations around current x,y and also allow simple wall-kicks
        original_x, original_y = self.x, self.y
        candidate_orientations = [new_o, (new_o + 1) % 4, (new_o - 1) % 4]
        for o in candidate_orientations:
            self.orientation = o
            # adjust x,y if cell positions go out of bounds: try simple kicks
            pos = [p[0] for p in self.cells()]
            minx = min(px for px, py in pos)
            maxx = max(px for px, py in pos)
            miny = min(py for px, py in pos)
            maxy = max(py for px, py in pos)
            kickx = 0
            kicky = 0
            if minx < 0:
                kickx = -minx
            if maxx >= self.board.cols:
                kickx = (self.board.cols - 1) - maxx
            if miny < 0:
                kicky = -miny
            if maxy >= self.board.rows:
                kicky = (self.board.rows - 1) - maxy
            # try applying kick
            old_x, old_y = self.x, self.y
            self.x += kickx; self.y += kicky
            pos2 = [p[0] for p in self.cells()]
            if self.board.can_place_capsule(pos2):
                return True
            # revert and try next
            self.x, self.y = old_x, old_y
        # if no orientation works, revert
        self.orientation = old_o
        return False

    def lock_to_board(self):
        """Place pill halves into the board grid as static pill blocks."""
        for ((x, y), half, color) in self.cells():
            if not in_bounds(x, y):
                continue
            # store pill half with pair id
            self.board.set(x, y, {"kind": "pill", "color": color, "pair": self.id, "half": half})
        self.settled = True


# ----- Game -----
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Doctor-Mario-like (Pygame)")
        self.clock = pygame.time.Clock()

        self.board = Board()
        # spawn a moderate number of viruses
        self.board.spawn_viruses(4)

        # active capsule
        self.active = None
        self.next_capsule_colors = (random_color_name(), random_color_name())
        self.spawn_new_capsule()

        self.frame = 0
        self.level = 1
        self.score = 0
        self.lines_cleared = 0
        self.fall_interval = max(6, FALL_INTERVAL_BASE - (self.level - 1) * 4)

        # input repeat timing
        self.move_cooldown = 6
        self.move_timer = 0
        
        # handles hard drops
        self.spaced = False


    def spawn_new_capsule(self):
        c = Capsule(self.board, x=self.board.cols // 2 - 1, y=0,
                    color1=self.next_capsule_colors[0], color2=self.next_capsule_colors[1])
        # prepare next
        self.next_capsule_colors = (random_color_name(), random_color_name())
        
        # If the capsule cannot be placed at spawn -> game over
        positions = [p[0] for p in c.cells()]
        if not self.board.can_place_capsule(positions):
            self.active = None
            return False
        self.active = c
        return True

    def settle_active_if_needed(self):
        # check if the active piece can move down; if not, lock it
        if self.active is None:
            return
        positions_below = [ (x, y+1) for ((x, y), _, _) in self.active.cells() ]
        can_fall = True
        for (x, y) in positions_below:
            if not in_bounds(x, y) or self.board.get(x, y) is not EMPTY:
                can_fall = False; break
        if not can_fall:
            # lock
            self.active.lock_to_board()
            self.active = None

    def update(self):
        self.frame += 1
        if not self.spaced:
            if self.active is None:
                # attempt to spawn
                ok = self.spawn_new_capsule()
                if not ok:
                    # game over handled in draw loop
                    return

            # handle automatic gravity tick
            if self.frame % self.fall_interval == 0:
                if self.active:
                    moved = self.active.move_down()
                    if not moved:
                        self.active.lock_to_board()
                        self.active = None

        # Reset space key trigger if triggered
        self.spaced = False

        # after locking, attempt resolves: find clears, apply gravity, cascade
        if self.active is None:
            while True:
                to_clear = self.board.find_line_clears()
                if not to_clear:
                    break
                # score
                self.score += len(to_clear) * 10
                self.board.remove_cells(to_clear)
                # gravity until stable
                while self.board.apply_gravity():
                    pass
                    #self.draw()

    def handle_events(self):
        keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit(); sys.exit(0)
                if self.active:
                    if event.key == pygame.K_SPACE:
                        self.active.hard_drop()
                        self.active.lock_to_board()
                        self.active = None
                        self.spaced = True
                    if event.key == pygame.K_z:
                        self.active.rotate(clockwise=False)
                    if event.key in (pygame.K_x, pygame.K_UP):
                        self.active.rotate(clockwise=True)

        # continuous movement (left/right/down)
        if self.active:
            if keys[pygame.K_LEFT] and self.move_timer <= 0:
                self.active.move_left(); self.move_timer = self.move_cooldown
            if keys[pygame.K_RIGHT] and self.move_timer <= 0:
                self.active.move_right(); self.move_timer = self.move_cooldown
            if keys[pygame.K_DOWN] and self.move_timer <= 0:
                self.active.move_down(); self.move_timer = self.move_cooldown

        if self.move_timer > 0:
            self.move_timer -= 1

    def draw_cell(self, x, y, cell):
        screen_x = x * CELL
        screen_y = y * CELL
        rect = Rect(screen_x, screen_y, CELL, CELL)
        pygame.draw.rect(self.screen, COLORS["grid"], rect)  # cell background

        if cell is EMPTY:
            return
        color = COLORS.get(cell["color"], COLORS["text"])
        # virus drawn as rounded circle/ellipse
        if cell["kind"] == "virus":
            pygame.draw.ellipse(self.screen, color, rect.inflate(-6, -6))
            # little dark pupil
            pygame.draw.ellipse(self.screen, (10, 10, 10), rect.inflate(-18, -12))
        else:
            # pill half: draw rounded rect and dividing line for halves (we ignore pair shape continuity)
            inner = rect.inflate(-4, -4)
            pygame.draw.rect(self.screen, color, inner, border_radius=6)
            # border
            pygame.draw.rect(self.screen, COLORS["pill_border"], inner, width=2, border_radius=6)

    def draw(self):
        self.screen.fill(COLORS["empty"])

        # draw board background grid cells
        for x in range(self.board.cols):
            for y in range(self.board.rows):
                cell = self.board.get(x, y)
                self.draw_cell(x, y, cell)

        # draw active capsule
        if self.active:
            for ((x, y), half, color_name) in self.active.cells():
                if not in_bounds(x, y):
                    continue
                rect = Rect(x * CELL, y * CELL, CELL, CELL)
                inner = rect.inflate(-4, -4)
                pygame.draw.rect(self.screen, COLORS[color_name], inner, border_radius=6)
                pygame.draw.rect(self.screen, COLORS["pill_border"], inner, width=2, border_radius=6)

        # HUD / score area
        hud_x = self.board.cols * CELL + 12
        pygame.draw.rect(self.screen, (10, 10, 10), (hud_x - 8, 8, SCREEN_W - hud_x - 12, SCREEN_H - 16), border_radius=8)
        font = pygame.font.SysFont("Arial", 16)
        lines = [
            f"Score: {self.score}",
            f"Level: {self.level}",
            f"Next: ",
        ]
        for i, line in enumerate(lines):
            surf = font.render(line, True, COLORS["text"])
            self.screen.blit(surf, (hud_x + 8, 12 + i * 22))

        # draw next capsule preview
        nx = hud_x + 8
        ny = 12 + len(lines) * 22
        # draw two small squares for next color pair
        pygame.draw.rect(self.screen, COLORS[self.next_capsule_colors[0]], (nx, ny, 28, 28), border_radius=6)
        pygame.draw.rect(self.screen, COLORS[self.next_capsule_colors[1]], (nx + 36, ny, 28, 28), border_radius=6)

        # game over overlay if active is None and board has no space to spawn
        if self.active is None:
            # check if spawn would fail
            temp = Capsule(self.board, x=self.board.cols // 2 - 1, y=0,
                           color1=self.next_capsule_colors[0], color2=self.next_capsule_colors[1])
            if not self.board.can_place_capsule([p[0] for p in temp.cells()]):
                font2 = pygame.font.SysFont("Arial", 32)
                surf = font2.render("GAME OVER", True, (220, 80, 80))
                self.screen.blit(surf, (SCREEN_W // 2 - surf.get_width() // 2, SCREEN_H // 2 - 20))

        pygame.display.flip()

    def run(self):
        while True:
            dt = self.clock.tick(FPS)
            self.handle_events()
            if not self.active and self.spaced:
                self.draw()
            self.update()
            if self.active is None:
                pass
                # gravity until stable
                #stable = not self.board.apply_gravity()
                #while not stable:
                #    self.draw()
                #    stable = not self.board.apply_gravity()
            self.draw()


if __name__ == "__main__":
    Game().run()
