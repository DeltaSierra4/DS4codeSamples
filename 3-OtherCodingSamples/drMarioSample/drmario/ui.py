"""Pygame rendering and input. The only module that imports pygame.

This layer never decides anything: it reads GameEngine state and forwards key
presses to it.
"""

import sys

import pygame
from pygame import Rect

from .config import CELL, COLORS, FPS, SCREEN_H, SCREEN_W
from .engine import GameEngine

MOVE_REPEAT_FRAMES = 6
SOFT_DROP_REPEAT_FRAMES = 3
VIRUS_COUNT = 4


class GameUI:
    def __init__(self, virus_count=VIRUS_COUNT):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Doctor-Mario-like (Pygame)")
        self.clock = pygame.time.Clock()
        # Fonts are expensive to build; the original made two of them every
        # single frame.
        self.font = pygame.font.SysFont("Arial", 16)
        self.big_font = pygame.font.SysFont("Arial", 32)

        self.virus_count = virus_count
        self.engine = GameEngine(virus_count=virus_count)
        self.move_timer = 0
        self.drop_timer = 0

    # ----- input ------------------------------------------------------------

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
            if event.key == pygame.K_r:
                self.engine = GameEngine(virus_count=self.virus_count)
                continue
            if event.key == pygame.K_SPACE:
                self.engine.hard_drop()
            elif event.key == pygame.K_z:
                self.engine.rotate(clockwise=False)
            elif event.key in (pygame.K_x, pygame.K_UP):
                self.engine.rotate(clockwise=True)

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

    def draw_cell(self, x, y, cell):
        rect = Rect(x * CELL, y * CELL, CELL, CELL)
        pygame.draw.rect(self.screen, COLORS["grid"], rect)
        if cell is None:
            return
        color = COLORS.get(cell["color"], COLORS["text"])
        if cell["kind"] == "virus":
            pygame.draw.ellipse(self.screen, color, rect.inflate(-6, -6))
            pygame.draw.ellipse(self.screen, (10, 10, 10), rect.inflate(-18, -12))
        else:
            self.draw_pill_half(rect, color)

    def draw_pill_half(self, rect, color):
        inner = rect.inflate(-4, -4)
        pygame.draw.rect(self.screen, color, inner, border_radius=6)
        pygame.draw.rect(self.screen, COLORS["pill_border"], inner, width=2, border_radius=6)

    def draw(self):
        engine = self.engine
        board = engine.board
        self.screen.fill(COLORS["empty"])

        for x in range(board.cols):
            for y in range(board.rows):
                self.draw_cell(x, y, board.get(x, y))

        if engine.active:
            for ((x, y), _half, color_name) in engine.active.cells():
                if board.in_bounds(x, y):
                    self.draw_pill_half(Rect(x * CELL, y * CELL, CELL, CELL),
                                        COLORS[color_name])

        self.draw_hud()
        self.draw_overlay()
        pygame.display.flip()

    def draw_hud(self):
        hud_x = self.engine.board.cols * CELL + 12
        pygame.draw.rect(self.screen, (10, 10, 10),
                         (hud_x - 8, 8, SCREEN_W - hud_x - 12, SCREEN_H - 16),
                         border_radius=8)
        lines = [
            f"Score: {self.engine.score}",
            f"Level: {self.engine.level}",
            f"Viruses: {self.engine.viruses_remaining}",
            "Next:",
        ]
        for i, line in enumerate(lines):
            surf = self.font.render(line, True, COLORS["text"])
            self.screen.blit(surf, (hud_x + 8, 12 + i * 22))

        nx, ny = hud_x + 8, 12 + len(lines) * 22
        for i, color_name in enumerate(self.engine.next_colors):
            self.draw_pill_half(Rect(nx + i * 32, ny, CELL, CELL), COLORS[color_name])

    def draw_overlay(self):
        if not self.engine.finished:
            return
        text, color = (("YOU WIN", (120, 220, 120)) if self.engine.won
                       else ("GAME OVER", (220, 80, 80)))
        surf = self.big_font.render(text, True, color)
        self.screen.blit(surf, (SCREEN_W // 2 - surf.get_width() // 2, SCREEN_H // 2 - 30))
        hint = self.font.render("R to restart", True, COLORS["text"])
        self.screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, SCREEN_H // 2 + 10))

    # ----- main loop --------------------------------------------------------

    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            running = self.handle_events()
            self.engine.tick()
            self.draw()
        pygame.quit()


def main():
    GameUI().run()
    sys.exit(0)
