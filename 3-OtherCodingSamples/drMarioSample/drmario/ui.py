"""Pygame rendering and input. The only module that imports pygame.

This layer never decides anything: it reads GameEngine state and forwards key
presses to it. Before a game there is a start menu for picking the starting
level and speed; ``self.engine`` is None while it is showing.
"""

import sys

import pygame
from pygame import Rect

from .config import CELL, COLORS, FPS, MAX_LEVEL, SCREEN_H, SCREEN_W, SPEEDS
from .engine import GameEngine

MOVE_REPEAT_FRAMES = 6
SOFT_DROP_REPEAT_FRAMES = 3


class GameUI:
    def __init__(self, virus_count=None):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Doctor-Mario-like (Pygame)")
        self.clock = pygame.time.Clock()
        # Fonts are expensive to build; the original made two of them every
        # single frame.
        self.font = pygame.font.SysFont("Arial", 16)
        self.big_font = pygame.font.SysFont("Arial", 32)

        self.virus_count = virus_count
        self.engine = None             # None while the start menu is showing
        self.start_level = 1
        self.speed = "med"
        self.menu_row = 0              # 0 = level, 1 = speed
        self.move_timer = 0
        self.drop_timer = 0

    def start_game(self):
        self.engine = GameEngine(virus_count=self.virus_count,
                                 level=self.start_level, speed=self.speed)
        self.move_timer = 0
        self.drop_timer = 0

    # ----- input ------------------------------------------------------------

    def handle_menu_key(self, key):
        if key in (pygame.K_UP, pygame.K_DOWN):
            self.menu_row = 1 - self.menu_row
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            step = 1 if key == pygame.K_RIGHT else -1
            if self.menu_row == 0:
                self.start_level = max(1, min(MAX_LEVEL, self.start_level + step))
            else:
                i = SPEEDS.index(self.speed)
                self.speed = SPEEDS[max(0, min(len(SPEEDS) - 1, i + step))]
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.start_game()

    def handle_events(self):
        # Pump the queue before sampling held keys, otherwise get_pressed()
        # reports the previous frame's state.
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type != pygame.KEYDOWN:
                continue
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            if self.engine is None:
                self.handle_menu_key(event.key)
                continue
            if event.key == pygame.K_r:
                self.engine = None     # back to the menu, keeping the choices
                continue
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.engine.next_level()
                continue
            if event.key == pygame.K_SPACE:
                self.engine.hard_drop()
            elif event.key == pygame.K_z:
                self.engine.rotate(clockwise=False)
            elif event.key in (pygame.K_x, pygame.K_UP):
                self.engine.rotate(clockwise=True)

        if self.engine is None:
            return True
        keys = pygame.key.get_pressed()
        if self.move_timer > 0:
            self.move_timer -= 1
        elif keys[pygame.K_LEFT] and not keys[pygame.K_RIGHT]:
            self.engine.move_left()
            self.move_timer = MOVE_REPEAT_FRAMES
        elif keys[pygame.K_RIGHT] and not keys[pygame.K_LEFT]:
            self.engine.move_right()
            self.move_timer = MOVE_REPEAT_FRAMES

        # Soft drop runs on its own timer so holding left and down at the same
        # time does not throttle both.
        if self.drop_timer > 0:
            self.drop_timer -= 1
        elif keys[pygame.K_DOWN]:
            self.engine.soft_drop()
            self.drop_timer = SOFT_DROP_REPEAT_FRAMES
        return True

    # ----- drawing ----------------------------------------------------------

    def draw_cell(self, x, y, cell, clearing=False):
        rect = Rect(x * CELL, y * CELL, CELL, CELL)
        pygame.draw.rect(self.screen, COLORS["grid"], rect)
        if cell is None:
            return
        color = COLORS.get(cell["color"], COLORS["text"])
        if clearing:
            self.draw_pop(rect, color)
        elif cell["kind"] == "virus":
            pygame.draw.ellipse(self.screen, color, rect.inflate(-6, -6))
            pygame.draw.ellipse(self.screen, (10, 10, 10), rect.inflate(-18, -12))
        else:
            self.draw_pill_half(rect, color, cell["half"])

    def draw_pop(self, rect, color):
        """A matched block about to vanish: a blinking starburst, drawn unlike
        any virus or pill so it cannot be mistaken for one."""
        if not (self.engine.phase_timer // 3) % 2:
            return
        cx, cy = rect.center
        r = CELL // 2 - 4
        d = int(r * 0.7)
        for (dx, dy) in ((r, 0), (0, r), (d, d), (d, -d)):
            pygame.draw.line(self.screen, color, (cx - dx, cy - dy), (cx + dx, cy + dy), 3)
        pygame.draw.circle(self.screen, COLORS["text"], (cx, cy), 3)

    # Which side of the cell a joined half reaches across to meet its partner.
    # The rounded corners go on the opposite (outer) end, so a capsule reads as
    # one piece; a single ("S") is rounded all round.
    _JOIN = {"L": "right", "R": "left", "U": "bottom", "D": "top"}

    def draw_pill_half(self, rect, color, half="S"):
        inner = rect.inflate(-4, -4)
        join = self._JOIN.get(half)
        radius = 10
        corners = {"border_top_left_radius": radius, "border_top_right_radius": radius,
                   "border_bottom_left_radius": radius, "border_bottom_right_radius": radius}
        if join == "right":
            inner.width += 2
            corners["border_top_right_radius"] = corners["border_bottom_right_radius"] = 0
        elif join == "left":
            inner.x -= 2
            inner.width += 2
            corners["border_top_left_radius"] = corners["border_bottom_left_radius"] = 0
        elif join == "bottom":
            inner.height += 2
            corners["border_bottom_left_radius"] = corners["border_bottom_right_radius"] = 0
        elif join == "top":
            inner.y -= 2
            inner.height += 2
            corners["border_top_left_radius"] = corners["border_top_right_radius"] = 0
        pygame.draw.rect(self.screen, color, inner, **corners)
        pygame.draw.rect(self.screen, COLORS["pill_border"], inner, width=2, **corners)

    def draw_menu(self):
        self.screen.fill(COLORS["empty"])
        cx = SCREEN_W // 2
        title = self.big_font.render("DR. MARIO", True, COLORS["text"])
        self.screen.blit(title, (cx - title.get_width() // 2, 70))
        rows = [f"Level:  < {self.start_level} >",
                f"Speed:  < {self.speed.capitalize()} >"]
        for i, text in enumerate(rows):
            color = COLORS["yellow"] if i == self.menu_row else COLORS["text"]
            surf = self.big_font.render(text, True, color)
            self.screen.blit(surf, (cx - surf.get_width() // 2, 170 + i * 60))
        for i, text in enumerate(("Up / Down: choose", "Left / Right: change",
                                  "Enter: start")):
            surf = self.font.render(text, True, COLORS["text"])
            self.screen.blit(surf, (cx - surf.get_width() // 2, 330 + i * 22))
        pygame.display.flip()

    def draw(self):
        if self.engine is None:
            self.draw_menu()
            return
        engine = self.engine
        board = engine.board
        self.screen.fill(COLORS["empty"])

        for x in range(board.cols):
            for y in range(board.rows):
                self.draw_cell(x, y, board.get(x, y), (x, y) in engine.clearing)

        if engine.active:
            for ((x, y), half, color_name) in engine.active.cells():
                if board.in_bounds(x, y):
                    self.draw_pill_half(Rect(x * CELL, y * CELL, CELL, CELL),
                                        COLORS[color_name], half)

        self.draw_hud()
        self.draw_overlay()
        pygame.display.flip()

    def draw_hud(self):
        hud_x = self.engine.board.cols * CELL + 12
        pygame.draw.rect(self.screen, (10, 10, 10),
                         (hud_x - 8, 8, SCREEN_W - hud_x - 12, SCREEN_H - 16),
                         border_radius=8)
        engine = self.engine
        level = (f"Infinity {engine.infinity}" if engine.infinity
                 else f"Level: {engine.level}/{MAX_LEVEL}")
        lines = [
            f"Score: {engine.score}",
            level,
            f"Speed: {engine.speed.capitalize()}",
            f"Viruses: {engine.viruses_remaining}",
            "Next:",
        ]
        for i, line in enumerate(lines):
            surf = self.font.render(line, True, COLORS["text"])
            self.screen.blit(surf, (hud_x + 8, 12 + i * 22))

        nx, ny = hud_x + 8, 12 + len(lines) * 22
        for i, color_name in enumerate(self.engine.next_colors):
            self.draw_pill_half(Rect(nx + i * CELL, ny, CELL, CELL), COLORS[color_name],
                                "LR"[i])

    def draw_overlay(self):
        if not self.engine.finished:
            return
        engine = self.engine
        if engine.level_cleared:
            name = f"INFINITY {engine.infinity}" if engine.infinity else f"LEVEL {engine.level}"
            text, color = f"{name} CLEAR", (120, 220, 120)
            if engine.level >= MAX_LEVEL:
                hint_text = f"Enter for Infinity {engine.infinity + 1}"
            else:
                hint_text = f"Enter for level {engine.level + 1}"
        else:
            text, color, hint_text = "GAME OVER", (220, 80, 80), "R for the menu"
        # A dark band keeps the text readable over a crowded board.
        band = pygame.Surface((SCREEN_W, 80), pygame.SRCALPHA)
        band.fill((0, 0, 0, 200))
        self.screen.blit(band, (0, SCREEN_H // 2 - 40))
        surf = self.big_font.render(text, True, color)
        self.screen.blit(surf, (SCREEN_W // 2 - surf.get_width() // 2, SCREEN_H // 2 - 30))
        hint = self.font.render(hint_text, True, COLORS["text"])
        self.screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, SCREEN_H // 2 + 10))

    # ----- main loop --------------------------------------------------------

    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            running = self.handle_events()
            if self.engine is not None:
                self.engine.tick()
            self.draw()
        pygame.quit()


def main():
    GameUI().run()
    sys.exit(0)
