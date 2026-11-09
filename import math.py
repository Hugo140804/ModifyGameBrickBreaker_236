import array
import math
import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

import pygame
from pygame.math import Vector2


# =====================================================================
# CONFIGURATION & CONSTANTS
# =====================================================================

@dataclass(frozen=True)
class Config:
    WIDTH: int = 850
    HEIGHT: int = 650
    HUD_HEIGHT: int = 60
    FPS: int = 120  # Mendukung monitor high-refresh-rate dengan Delta-Time

    # Palet Warna (RGB)
    BG_COLOR: Tuple[int, int, int] = (11, 15, 25)
    HUD_BG: Tuple[int, int, int] = (22, 30, 46)
    GRID_LINE: Tuple[int, int, int] = (20, 27, 45)
    TEXT_MAIN: Tuple[int, int, int] = (248, 250, 252)
    TEXT_MUTED: Tuple[int, int, int] = (148, 163, 184)
    PADDLE_COLOR: Tuple[int, int, int] = (34, 211, 238)
    BALL_COLOR: Tuple[int, int, int] = (250, 204, 21)

    # Fisika Paddle (Piksel per detik)
    PADDLE_WIDTH: int = 115
    PADDLE_HEIGHT: int = 16
    PADDLE_SPEED: float = 620.0
    PADDLE_Y: int = 595

    # Fisika Bola (Piksel per detik)
    BALL_RADIUS: int = 8
    BALL_BASE_SPEED: float = 420.0
    BALL_MAX_SPEED: float = 780.0
    BALL_ACCEL: float = 8.0
    MAX_BOUNCE_ANGLE: float = math.radians(65)

    # Susunan Balok
    BRICK_ROWS: int = 6
    BRICK_COLS: int = 10
    BRICK_PAD: int = 7
    BRICK_TOP: int = 95
    BRICK_HEIGHT: int = 26


class GameState(Enum):
    READY = auto()
    PLAYING = auto()
    PAUSED = auto()
    LEVEL_CLEAR = auto()
    GAME_OVER = auto()


class PowerUpType(Enum):
    WIDE_PADDLE = ((74, 222, 128), "WIDE")
    MULTI_BALL = ((192, 132, 252), "MULTI")
    EXTRA_LIFE = ((251, 113, 133), "+1 UP")
    LASER_BALL = ((249, 115, 22), "PIERCE")

    def __init__(self, color: Tuple[int, int, int], label: str) -> None:
        self.color = color
        self.label = label


# Tier Balok: HP -> (Warna Utama, Warna Outline, Skor Dasar)
BRICK_TIERS: Dict[int, Tuple[Tuple[int, int, int], Tuple[int, int, int], int]] = {
    1: ((56, 189, 248), (2, 132, 199), 15),    # Cyan
    2: ((168, 85, 247), (126, 34, 206), 35),   # Purple
    3: ((244, 63, 94), (190, 18, 60), 60),     # Rose
    4: ((245, 158, 11), (180, 83, 9), 100),    # Amber
}


# =====================================================================
# PROCEDURAL SOUND SYNTHESIZER (NO EXTERNAL ASSETS REQUIRED)
# =====================================================================

class RetroSynth:
    """Menghasilkan efek suara 16-bit PCM secara prosedural di memori."""

    def __init__(self) -> None:
        self.enabled = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self.enabled = True
            self._build_sound_bank()
        except pygame.error:
            self.enabled = False

    def _generate_tone(
        self, start_freq: float, end_freq: float, duration: float, volume: float = 0.25
    ) -> Optional[pygame.mixer.Sound]:
        if not self.enabled:
            return None
        init_info = pygame.mixer.get_init()
        if not init_info:
            return None

        sample_rate, _, channels = init_info
        num_samples = int(sample_rate * duration)
        buf = array.array("h")

        for i in range(num_samples):
            t = i / sample_rate
            progress = i / num_samples
            freq = start_freq + (end_freq - start_freq) * progress
            envelope = (1.0 - progress) ** 1.5
            sample_val = int(32767 * volume * envelope * math.sin(2 * math.pi * freq * t))
            for _ in range(channels):
                buf.append(sample_val)

        return pygame.mixer.Sound(buffer=buf)

    def _build_sound_bank(self) -> None:
        self.sounds["paddle"] = self._generate_tone(340, 480, 0.07, 0.25)
        self.sounds["wall"] = self._generate_tone(240, 200, 0.05, 0.20)
        self.sounds["brick_hit"] = self._generate_tone(520, 680, 0.06, 0.22)
        self.sounds["brick_break"] = self._generate_tone(680, 190, 0.14, 0.28)
        self.sounds["powerup"] = self._generate_tone(400, 950, 0.22, 0.25)
        self.sounds["lose_life"] = self._generate_tone(300, 90, 0.45, 0.35)

    def play(self, name: str) -> None:
        if self.enabled and name in self.sounds and self.sounds[name]:
            self.sounds[name].play()


# =====================================================================
# GAME ENTITIES
# =====================================================================

class Paddle:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.width = float(cfg.PADDLE_WIDTH)
        self.height = float(cfg.PADDLE_HEIGHT)
        self.pos = Vector2(cfg.WIDTH / 2, cfg.PADDLE_Y)

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.pos.x - self.width / 2),
            int(self.pos.y - self.height / 2),
            int(self.width),
            int(self.height),
        )

    def update(self, dt: float, move_dir: float) -> None:
        self.pos.x += move_dir * self.cfg.PADDLE_SPEED * dt
        half_w = self.width / 2
        self.pos.x = max(half_w, min(self.cfg.WIDTH - half_w, self.pos.x))

    def draw(self, surface: pygame.Surface, offset: Vector2) -> None:
        r = self.rect.move(int(offset.x), int(offset.y))
        pygame.draw.rect(surface, self.cfg.PADDLE_COLOR, r, border_radius=6)
        pygame.draw.rect(surface, (255, 255, 255), r, width=2, border_radius=6)


class Ball:
    def __init__(self, x: float, y: float, cfg: Config, angle: Optional[float] = None) -> None:
        self.cfg = cfg
        self.pos = Vector2(x, y)
        self.radius = cfg.BALL_RADIUS
        self.speed = cfg.BALL_BASE_SPEED
        self.piercing = False

        launch_angle = angle if angle is not None else random.uniform(-0.35, 0.35)
        self.vel = Vector2(
            math.sin(launch_angle) * self.speed,
            -math.cos(launch_angle) * self.speed,
        )
        self.trail: List[Vector2] = []

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.pos.x - self.radius),
            int(self.pos.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )

    def update(self, dt: float, synth: RetroSynth) -> bool:
        """Mengembalikan True jika bola jatuh melewati batas bawah."""
        self.trail.append(Vector2(self.pos))
        if len(self.trail) > 10:
            self.trail.pop(0)

        self.pos += self.vel * dt

        # Pantulan Dinding Kiri & Kanan
        if self.pos.x - self.radius <= 0:
            self.pos.x = self.radius
            self.vel.x = abs(self.vel.x)
            synth.play("wall")
        elif self.pos.x + self.radius >= self.cfg.WIDTH:
            self.pos.x = self.cfg.WIDTH - self.radius
            self.vel.x = -abs(self.vel.x)
            synth.play("wall")

        # Pantulan Atap (Bawah HUD)
        if self.pos.y - self.radius <= self.cfg.HUD_HEIGHT:
            self.pos.y = self.cfg.HUD_HEIGHT + self.radius
            self.vel.y = abs(self.vel.y)
            synth.play("wall")

        return self.pos.y - self.radius > self.cfg.HEIGHT

    def bounce_paddle(self, paddle: Paddle) -> None:
        self.pos.y = paddle.pos.y - paddle.height / 2 - self.radius
        hit_offset = (self.pos.x - paddle.pos.x) / (paddle.width / 2)
        hit_offset = max(-1.0, min(1.0, hit_offset))

        angle = hit_offset * self.cfg.MAX_BOUNCE_ANGLE
        self.speed = min(self.cfg.BALL_MAX_SPEED, self.speed + self.cfg.BALL_ACCEL)
        self.vel.x = self.speed * math.sin(angle)
        self.vel.y = -self.speed * math.cos(angle)

    def draw(self, surface: pygame.Surface, offset: Vector2) -> None:
        base_color = (249, 115, 22) if self.piercing else self.cfg.BALL_COLOR

        # Render Alpha Motion Trail
        for idx, t_pos in enumerate(self.trail):
            alpha = int(110 * ((idx + 1) / len(self.trail)))
            t_rad = max(2, int(self.radius * ((idx + 1) / len(self.trail))))
            trail_surf = pygame.Surface((t_rad * 2, t_rad * 2), pygame.SRCALPHA)
            pygame.draw.circle(trail_surf, (*base_color, alpha), (t_rad, t_rad), t_rad)
            surface.blit(
                trail_surf,
                (int(t_pos.x - t_rad + offset.x), int(t_pos.y - t_rad + offset.y)),
            )

        center = (int(self.pos.x + offset.x), int(self.pos.y + offset.y))
        pygame.draw.circle(surface, base_color, center, self.radius)
        pygame.draw.circle(surface, (255, 255, 255), center, self.radius, 2)


class Brick:
    def __init__(self, rect: pygame.Rect, hp: int) -> None:
        self.rect = rect
        self.hp = hp
        self.score_val = BRICK_TIERS[hp][2]

    @property
    def color(self) -> Tuple[int, int, int]:
        return BRICK_TIERS[self.hp][0]

    @property
    def border_color(self) -> Tuple[int, int, int]:
        return BRICK_TIERS[self.hp][1]

    def hit(self) -> Tuple[bool, Tuple[int, int, int]]:
        old_color = self.color
        self.hp -= 1
        return self.hp <= 0, old_color

    def draw(self, surface: pygame.Surface, offset: Vector2) -> None:
        r = self.rect.move(int(offset.x), int(offset.y))
        pygame.draw.rect(surface, self.color, r, border_radius=4)
        pygame.draw.rect(surface, self.border_color, r, width=2, border_radius=4)


class PowerUp:
    def __init__(self, x: float, y: float, p_type: PowerUpType) -> None:
        self.pos = Vector2(x, y)
        self.p_type = p_type
        self.vel_y = 190.0
        self.width = 58
        self.height = 22

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.pos.x - self.width / 2),
            int(self.pos.y - self.height / 2),
            self.width,
            self.height,
        )

    def update(self, dt: float) -> None:
        self.pos.y += self.vel_y * dt

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, offset: Vector2) -> None:
        r = self.rect.move(int(offset.x), int(offset.y))
        pygame.draw.rect(surface, self.p_type.color, r, border_radius=5)
        pygame.draw.rect(surface, (255, 255, 255), r, width=1, border_radius=5)
        txt = font.render(self.p_type.label, True, (15, 23, 42))
        surface.blit(txt, txt.get_rect(center=r.center))


class Particle:
    def __init__(self, x: float, y: float, color: Tuple[int, int, int]) -> None:
        self.pos = Vector2(x, y)
        angle = random.uniform(0, math.tau)
        speed = random.uniform(70, 260)
        self.vel = Vector2(math.cos(angle) * speed, math.sin(angle) * speed)
        self.color = color
        self.lifetime = random.uniform(0.25, 0.55)
        self.age = 0.0
        self.size = random.uniform(3.0, 6.0)

    def update(self, dt: float) -> bool:
        self.pos += self.vel * dt
        self.vel.y += 380.0 * dt  # Gravitasi partikel
        self.age += dt
        return self.age < self.lifetime

    def draw(self, surface: pygame.Surface, offset: Vector2) -> None:
        alpha = max(0, int(255 * (1.0 - self.age / self.lifetime)))
        s = int(self.size)
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        surf.fill((*self.color, alpha))
        surface.blit(surf, (int(self.pos.x + offset.x), int(self.pos.y + offset.y)))


# =====================================================================
# MAIN GAME ENGINE
# =====================================================================

class BrickBreakerEngine:
    def __init__(self) -> None:
        pygame.init()
        self.cfg = Config()
        self.screen = pygame.display.set_mode((self.cfg.WIDTH, self.cfg.HEIGHT))
        pygame.display.set_caption("Brick Breaker Pro — Pygame SDL2 Edition")
        self.clock = pygame.time.Clock()
        self.synth = RetroSynth()

        # Typography
        self.font_hud = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_title = pygame.font.SysFont("consolas", 42, bold=True)
        self.font_sub = pygame.font.SysFont("consolas", 18)
        self.font_badge = pygame.font.SysFont("consolas", 11, bold=True)

        # Game State
        self.state = GameState.READY
        self.score = 0
        self.high_score = 0
        self.lives = 3
        self.level = 1
        self.combo = 0

        # Timers Efek Aktif
        self.wide_timer = 0.0
        self.pierce_timer = 0.0
        self.shake_timer = 0.0

        # Koleksi Objek
        self.paddle = Paddle(self.cfg)
        self.balls: List[Ball] = []
        self.bricks: List[Brick] = []
        self.powerups: List[PowerUp] = []
        self.particles: List[Particle] = []

        self.reset_game(full_reset=True)

    # -----------------------------------------------------------------
    # SETUP & STATE MANAGEMENT
    # -----------------------------------------------------------------

    def reset_game(self, full_reset: bool = False) -> None:
        if full_reset:
            self.score = 0
            self.lives = 3
            self.level = 1

        self.combo = 0
        self.wide_timer = 0.0
        self.pierce_timer = 0.0
        self.powerups.clear()
        self.particles.clear()

        self._reset_paddle_and_ball()
        self._build_level_bricks()
        self.state = GameState.READY

    def _reset_paddle_and_ball(self) -> None:
        self.paddle = Paddle(self.cfg)
        bx = self.paddle.pos.x
        by = self.paddle.pos.y - self.paddle.height / 2 - self.cfg.BALL_RADIUS - 2
        self.balls = [Ball(bx, by, self.cfg)]

    def _build_level_bricks(self) -> None:
        self.bricks.clear()
        pad = self.cfg.BRICK_PAD
        total_pad = pad * (self.cfg.BRICK_COLS + 1)
        b_width = (self.cfg.WIDTH - total_pad) // self.cfg.BRICK_COLS

        for row in range(self.cfg.BRICK_ROWS):
            for col in range(self.cfg.BRICK_COLS):
                if self.level > 1 and (row + col) % 6 == 0:
                    continue
                hp = min(4, max(1, (self.cfg.BRICK_ROWS - row + self.level - 1) // 2))
                x = pad + col * (b_width + pad)
                y = self.cfg.BRICK_TOP + row * (self.cfg.BRICK_HEIGHT + pad)
                self.bricks.append(Brick(pygame.Rect(x, y, b_width, self.cfg.BRICK_HEIGHT), hp))

    # -----------------------------------------------------------------
    # COLLISION & GAMEPLAY LOGIC
    # -----------------------------------------------------------------

    def _handle_collisions(self, ball: Ball) -> None:
        b_rect = ball.rect

        # 1. Tumbukan Bola dengan Paddle
        if ball.vel.y > 0 and b_rect.colliderect(self.paddle.rect):
            ball.bounce_paddle(self.paddle)
            self.combo = 0  # Reset combo saat menyentuh paddle
            self.synth.play("paddle")
            return

        # 2. Tumbukan Bola dengan Balok
        for brick in self.bricks[:]:
            if not b_rect.colliderect(brick.rect):
                continue

            if not ball.piercing:
                overlap_left = b_rect.right - brick.rect.left
                overlap_right = brick.rect.right - b_rect.left
                overlap_top = b_rect.bottom - brick.rect.top
                overlap_bottom = brick.rect.bottom - b_rect.top

                if min(overlap_left, overlap_right) < min(overlap_top, overlap_bottom):
                    ball.vel.x = -ball.vel.x
                else:
                    ball.vel.y = -ball.vel.y

            destroyed, color = brick.hit()
            self.combo += 1
            multiplier = min(4, 1 + self.combo // 4)

            cx, cy = brick.rect.center
            for _ in range(14 if destroyed else 5):
                self.particles.append(Particle(cx, cy, color))

            if destroyed:
                self.bricks.remove(brick)
                self.score += brick.score_val * multiplier
                self.shake_timer = 0.09
                self.synth.play("brick_break")
                if random.random() < 0.20:
                    self.powerups.append(PowerUp(cx, cy, random.choice(list(PowerUpType))))
            else:
                self.score += 5 * multiplier
                self.synth.play("brick_hit")

            if self.score > self.high_score:
                self.high_score = self.score
            break

    def _apply_powerup(self, p_type: PowerUpType) -> None:
        self.synth.play("powerup")
        if p_type == PowerUpType.WIDE_PADDLE:
            self.paddle.width = self.cfg.PADDLE_WIDTH * 1.55
            self.wide_timer = 10.0
        elif p_type == PowerUpType.EXTRA_LIFE:
            self.lives = min(5, self.lives + 1)
        elif p_type == PowerUpType.LASER_BALL:
            self.pierce_timer = 7.0
            for b in self.balls:
                b.piercing = True
        elif p_type == PowerUpType.MULTI_BALL and self.balls:
            origin = self.balls[0]
            for offset_angle in (-0.4, 0.4):
                nb = Ball(origin.pos.x, origin.pos.y, self.cfg, angle=offset_angle)
                nb.speed = origin.speed
                nb.piercing = origin.piercing
                self.balls.append(nb)

    # -----------------------------------------------------------------
    # UPDATE & RENDERING
    # -----------------------------------------------------------------

    def update(self, dt: float) -> None:
        if self.shake_timer > 0:
            self.shake_timer = max(0.0, self.shake_timer - dt)

        if self.state not in (GameState.READY, GameState.PLAYING):
            return

        # Polling Input Bebas Bug (Menggunakan get_pressed)
        keys = pygame.key.get_pressed()
        move_dir = 0.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            move_dir -= 1.0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            move_dir += 1.0
        self.paddle.update(dt, move_dir)

        if self.state == GameState.READY and self.balls:
            self.balls[0].pos.x = self.paddle.pos.x
            self.balls[0].pos.y = (
                self.paddle.pos.y - self.paddle.height / 2 - self.cfg.BALL_RADIUS - 2
            )
            return

        # Update Power-up Timers
        if self.wide_timer > 0:
            self.wide_timer -= dt
            if self.wide_timer <= 0:
                self.paddle.width = float(self.cfg.PADDLE_WIDTH)

        if self.pierce_timer > 0:
            self.pierce_timer -= dt
            if self.pierce_timer <= 0:
                for b in self.balls:
                    b.piercing = False

        # Update Bola
        for ball in self.balls[:]:
            if ball.update(dt, self.synth):
                self.balls.remove(ball)
            else:
                self._handle_collisions(ball)

        # Update Item Jatuh
        p_rect = self.paddle.rect
        for p in self.powerups[:]:
            p.update(dt)
            if p.rect.colliderect(p_rect):
                self._apply_powerup(p.p_type)
                self.powerups.remove(p)
            elif p.pos.y > self.cfg.HEIGHT + 30:
                self.powerups.remove(p)

        # Update Partikel
        self.particles = [pt for pt in self.particles if pt.update(dt)]

        # Cek Kondisi Level Selesai / Kehilangan Nyawa
        if not self.bricks:
            self.state = GameState.LEVEL_CLEAR
        elif not self.balls:
            self.lives -= 1
            self.synth.play("lose_life")
            if self.lives <= 0:
                self.state = GameState.GAME_OVER
            else:
                self._reset_paddle_and_ball()
                self.state = GameState.READY

    def draw(self) -> None:
        self.screen.fill(self.cfg.BG_COLOR)

        # Hitung Offset Getaran Layar (Screen Shake)
        offset = Vector2(0, 0)
        if self.shake_timer > 0:
            offset.x = random.uniform(-4.5, 4.5)
            offset.y = random.uniform(-4.5, 4.5)

        # Background Subtle Grid
        for gx in range(0, self.cfg.WIDTH, 50):
            pygame.draw.line(
                self.screen, self.cfg.GRID_LINE, (gx, self.cfg.HUD_HEIGHT), (gx, self.cfg.HEIGHT)
            )
        for gy in range(self.cfg.HUD_HEIGHT, self.cfg.HEIGHT, 50):
            pygame.draw.line(
                self.screen, self.cfg.GRID_LINE, (0, gy), (self.cfg.WIDTH, gy)
            )

        # Render Objek Game
        for brick in self.bricks:
            brick.draw(self.screen, offset)
        for p in self.powerups:
            p.draw(self.screen, self.font_badge, offset)
        for pt in self.particles:
            pt.draw(self.screen, offset)

        self.paddle.draw(self.screen, offset)
        for ball in self.balls:
            ball.draw(self.screen, offset)

        self._draw_hud()
        self._draw_overlays()
        pygame.display.flip()

    def _draw_hud(self) -> None:
        pygame.draw.rect(
            self.screen, self.cfg.HUD_BG, (0, 0, self.cfg.WIDTH, self.cfg.HUD_HEIGHT)
        )
        pygame.draw.line(
            self.screen, (51, 65, 85), (0, self.cfg.HUD_HEIGHT), (self.cfg.WIDTH, self.cfg.HUD_HEIGHT), 2
        )

        score_surf = self.font_hud.render(f"SCORE: {self.score}", True, self.cfg.TEXT_MAIN)
        best_surf = self.font_hud.render(f"BEST: {self.high_score}", True, self.cfg.TEXT_MUTED)
        lvl_surf = self.font_hud.render(f"LVL: {self.level}", True, (56, 189, 248))
        mult = min(4, 1 + self.combo // 4)
        combo_surf = self.font_hud.render(f"COMBO: x{mult}", True, (250, 204, 21))
        lives_surf = self.font_hud.render(f"LIVES: {'♥' * self.lives}", True, (251, 113, 133))

        self.screen.blit(score_surf, (20, 18))
        self.screen.blit(best_surf, (210, 18))
        self.screen.blit(lvl_surf, (400, 18))
        self.screen.blit(combo_surf, (530, 18))
        self.screen.blit(lives_surf, (self.cfg.WIDTH - lives_surf.get_width() - 20, 18))

    def _draw_overlays(self) -> None:
        messages = {
            GameState.READY: (
                f"LEVEL {self.level} READY",
                "Tekan [SPACE] untuk Meluncurkan Bola  |  [A/D] atau [Panah] untuk Bergerak",
            ),
            GameState.PAUSED: ("GAME PAUSED", "Tekan [P] untuk Melanjutkan Permainan"),
            GameState.LEVEL_CLEAR: (
                f"STAGE {self.level} CLEARED!",
                "Tekan [SPACE] untuk Lanjut ke Level Berikutnya",
            ),
            GameState.GAME_OVER: (
                "GAME OVER",
                f"Skor Akhir: {self.score}  |  Tekan [SPACE] untuk Main Lagi",
            ),
        }
        if self.state not in messages:
            return

        title_txt, sub_txt = messages[self.state]
        t_surf = self.font_title.render(title_txt, True, self.cfg.TEXT_MAIN)
        s_surf = self.font_sub.render(sub_txt, True, self.cfg.TEXT_MUTED)

        cx, cy = self.cfg.WIDTH // 2, self.cfg.HEIGHT // 2 + 30
        self.screen.blit(t_surf, t_surf.get_rect(center=(cx, cy - 22)))
        self.screen.blit(s_surf, s_surf.get_rect(center=(cx, cy + 24)))

    # -----------------------------------------------------------------
    # MAIN LOOP
    # -----------------------------------------------------------------

    def run(self) -> None:
        running = True
        while running:
            # Delta time (dalam detik), dibatasi maks 0.05s agar tidak tembus tembok saat window digeser
            dt = min(0.05, self.clock.tick(self.cfg.FPS) / 1000.0)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        if self.state == GameState.READY:
                            self.state = GameState.PLAYING
                        elif self.state == GameState.LEVEL_CLEAR:
                            self.level += 1
                            self.reset_game(full_reset=False)
                        elif self.state == GameState.GAME_OVER:
                            self.reset_game(full_reset=True)
                    elif event.key == pygame.K_p:
                        if self.state == GameState.PLAYING:
                            self.state = GameState.PAUSED
                        elif self.state == GameState.PAUSED:
                            self.state = GameState.PLAYING
                    elif event.key == pygame.K_r:
                        self.reset_game(full_reset=True)

            self.update(dt)
            self.draw()

        pygame.quit()


if __name__ == "__main__":
    BrickBreakerEngine().run()