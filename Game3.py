# NEON BREAKER - upgraded standalone Pygame edition
# Install: python -m pip install pygame-ce
# Run:     python Neon_Breaker.py
# Mouse / A,D / arrows: move | Space: launch | P: pause | M: mute | V: shake
# B: toggle original procedural 140 BPM breakbeat music (M toggles SFX only).
# High scores are stored per difficulty in your user profile / NeonBreaker.

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
    WIDTH: int = 1000
    HEIGHT: int = 760
    HUD_HEIGHT: int = 110
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
    PADDLE_Y: int = 680

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

import json
import os
from pathlib import Path

CYAN = (88, 235, 230)
PINK = (255, 106, 160)
INK = (9, 13, 27)
WHITE = (235, 244, 255)
MUTED = (127, 148, 178)


class BreakbeatMusic:
    """Original 140 BPM loop: syncopated drums, sub bass and minor-key synth.

    Generated once in memory; no audio files or additional dependencies.
    A reserved mixer channel keeps gameplay effects from stopping the music.
    """
    def __init__(self):
        self.available = False
        self.enabled = True
        self.channel = None
        self.loop = None
        self.volume = .20
        if not pygame.mixer.get_init():
            return
        try:
            pygame.mixer.set_num_channels(24)
            pygame.mixer.set_reserved(1)
            self.channel = pygame.mixer.Channel(0)
            self.loop = self._compose()
            self.channel.set_volume(self.volume)
            self.channel.play(self.loop, loops=-1)
            self.available = True
        except (pygame.error, ValueError):
            self.available = False

    def _compose(self):
        rate, _, channels = pygame.mixer.get_init()
        beat = 60 / 140
        step = beat / 4
        frames = round(32 * beat * rate)  # Eight seamless bars.
        mix = array.array('f', [0.0]) * frames
        rng = random.Random(140)  # Music does not affect gameplay randomness.

        def add(start, duration, voice, freq=55, gain=1):
            first = round(start * rate)
            count = round(duration * rate)
            phase = 0.0
            prev_noise = 0.0
            for i in range(count):
                t = i / rate
                u = i / count
                if voice == 'kick':
                    phase += math.tau * (48 + 125 * math.exp(-t * 40)) / rate
                    sample = math.sin(phase) * math.exp(-t * 16)
                elif voice == 'snare':
                    noise = rng.uniform(-1, 1)
                    sample = (.72 * noise + .28 * math.sin(math.tau * 180 * t)) * math.exp(-t * 25)
                elif voice == 'hat':
                    noise = rng.uniform(-1, 1)
                    sample = (noise - prev_noise) * .5 * math.exp(-t * 65)
                    prev_noise = noise
                elif voice == 'bass':
                    env = min(1, t * 180) * min(1, (duration-t) * 70)
                    sample = (math.sin(math.tau*freq*t) + .24*math.sin(math.tau*freq*2*t)) * env
                else:
                    env = min(1, t * 120) * (1-u)**2
                    sample = (math.sin(math.tau*freq*t) + .25*math.sin(math.tau*freq*3*t)) * env
                mix[(first+i) % frames] += sample * gain

        roots = [41.2034, 41.2034, 49.0, 36.7081, 41.2034, 41.2034, 55.0, 36.7081]
        for bar, root in enumerate(roots):
            start = bar * 4 * beat
            for tick in (0, 6, 10, 14) if bar % 2 else (0, 7, 10):
                add(start+tick*step, .24, 'kick', gain=.66)
            for tick in (4, 12):
                add(start+tick*step, .17, 'snare', gain=.39)
            for tick in (3, 11, 15):
                add(start+tick*step, .08, 'snare', gain=.075)
            for tick in range(16):
                add(start+tick*step, .055, 'hat', gain=.11 if tick % 2 == 0 else .055)
            if bar in (3, 7):
                for tick in (14, 14.5, 15, 15.5):
                    add(start+tick*step, .08, 'snare', gain=.12)
            for tick, semitone in ((0,0),(3,0),(6,12),(8,0),(11,7),(14,0)):
                add(start+tick*step, step*1.6, 'bass', root*2**(semitone/12), .23)
            for tick, semitone in ((2,0),(5,7),(9,12),(13,15)):
                frequency = root * 8 * 2**(semitone/12)
                add(start+tick*step, .25, 'synth', frequency, .095)
                add(start+tick*step+beat*.75, .22, 'synth', frequency, .035)
        peak = max(1.0, max(abs(x) for x in mix))
        pcm = array.array('h')
        for sample in mix:
            value = int(sample / peak * 28500)
            for _ in range(channels):
                pcm.append(value)
        return pygame.mixer.Sound(buffer=pcm)

    def toggle(self):
        if not self.available:
            return
        self.enabled = not self.enabled
        if self.enabled:
            self.channel.unpause()
        else:
            self.channel.pause()

    def update(self, state, dt):
        if not self.available:
            return
        target = .07 if state == 'paused' else (.13 if state in ('menu', 'over') else .22)
        self.volume += (target-self.volume) * min(1, dt*4)
        self.channel.set_volume(self.volume)


class NeonBreaker:
    """Standalone arcade game. Physics runs at fixed 240 Hz, rendering up to 120 Hz."""
    MODES = [('SANTAI', 340, 5), ('ARCADE', 420, 3), ('EXPERT', 500, 3)]
    NAMES = ['FIRST CONTACT', 'DIAMOND FIELD', 'PULSE WAVE', 'TWIN TOWERS', 'THE PORTAL']

    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        self.cfg = Config()
        self.screen = pygame.display.set_mode((1000, 760), pygame.RESIZABLE)
        pygame.display.set_caption('NEON BREAKER | Arcade Edition')
        self.canvas = pygame.Surface((1000, 760))
        self.clock = pygame.time.Clock()
        self.synth = RetroSynth()
        self.music = BreakbeatMusic()
        self.fonts = {n: pygame.font.SysFont('dejavusans', n, bold=n >= 26) for n in (12, 14, 18, 22, 26, 36, 58)}
        self.mode = 1
        self.muted = False
        self.motion = True
        self.control = 'mouse'
        self.mouse_x = 500
        self.time = 0
        self.accumulator = 0
        self.buttons = []
        self.stars = [(random.randrange(1000), random.randrange(110, 720), random.uniform(.4, 1)) for _ in range(75)]
        self.save_path = Path(os.environ.get('APPDATA', str(Path.home()))) / 'NeonBreaker' / 'scores.json'
        try:
            raw = json.loads(self.save_path.read_text())
            self.records = {k: max(0, int(raw.get(k, 0))) for k, _, _ in self.MODES}
        except (OSError, ValueError, TypeError, AttributeError):
            self.records = {}
        self.reset()
        self.state = 'menu'

    def sound(self, name):
        if not self.muted:
            self.synth.play(name)

    def save(self):
        key = self.MODES[self.mode][0]
        self.records[key] = max(self.records.get(key, 0), self.score)
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.save_path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.records))
            temp.replace(self.save_path)
        except OSError:
            pass  # Game tetap dapat dimainkan jika folder skor tidak bisa ditulis.

    def reset(self):
        self.level = 1
        self.score = 0
        self.lives = self.MODES[self.mode][2]
        self.setup_level()

    def setup_level(self):
        self.bricks = []
        pattern = (self.level - 1) % 5
        for row in range(6):
            for col in range(10):
                if pattern == 1 and abs(col - 4.5) + abs(row - 2.5) > 5: continue
                if pattern == 2 and (col + row) % 4 == 0: continue
                if pattern == 3 and col in (4, 5): continue
                if pattern == 4 and row in (2, 3) and col in (3, 4, 5, 6): continue
                hp = min(4, 1 + (5-row)//3 + (self.level-1)//3)
                self.bricks.append(Brick(pygame.Rect(35+col*94, 155+row*37, 85, 27), hp))
        self.initial_bricks = len(self.bricks)
        self.particles = []
        self.floaters = []
        self.shake = 0
        self.serve()

    def serve(self):
        self.paddle = Paddle(self.cfg)
        self.powerups = []
        self.wide = self.pierce = 0
        self.combo = 0
        self.combo_time = 0
        self.balls = [self.new_ball(500, 654)]
        self.state = 'ready'

    def new_ball(self, x, y):
        b = Ball(x, y, self.cfg, .2)
        b.speed = min(690, self.MODES[self.mode][1]+(self.level-1)*18)
        b.vel.scale_to_length(b.speed)
        b.contacts = set()
        return b

    def burst(self, x, y, color, count=12):
        for _ in range(count):
            self.particles.append(Particle(x, y, color))
        self.particles = self.particles[-500:]

    def popup(self, text, x, y, color=CYAN):
        self.floaters.append([text, x, y, 1., color])

    def power(self, kind):
        self.sound('powerup')
        self.popup(kind.label, self.paddle.pos.x, 630, kind.color)
        if kind == PowerUpType.WIDE_PADDLE:
            self.wide = 12
        elif kind == PowerUpType.LASER_BALL:
            self.pierce = 8
        elif kind == PowerUpType.EXTRA_LIFE:
            if self.lives < 5: self.lives += 1
            else: self.score += 250
        elif kind == PowerUpType.MULTI_BALL and self.balls:
            origin = self.balls[0]
            for angle in (-24, 24):
                if len(self.balls) >= 5: break
                b = self.new_ball(origin.pos.x, origin.pos.y)
                b.speed = origin.speed
                b.vel = origin.vel.rotate(angle)
                if abs(b.vel.y) < b.speed*.3:
                    b.vel.y = -b.speed*.4
                    b.vel.scale_to_length(b.speed)
                self.balls.append(b)

    def collision(self, b):
        if b.vel.y > 0 and b.rect.colliderect(self.paddle.rect):
            b.bounce_paddle(self.paddle)
            self.sound('paddle')
            self.burst(b.pos.x, b.pos.y+8, CYAN, 4)
        touching = {id(brick) for brick in self.bricks if b.rect.colliderect(brick.rect)}
        for brick in self.bricks[:]:
            if id(brick) not in touching or id(brick) in b.contacts: continue
            if not b.piercing:
                r = brick.rect
                overlaps = [b.pos.x+b.radius-r.left, r.right-b.pos.x+b.radius,
                            b.pos.y+b.radius-r.top, r.bottom-b.pos.y+b.radius]
                side = overlaps.index(min(overlaps))
                if side == 0: b.pos.x = r.left-b.radius-.1; b.vel.x = -abs(b.vel.x)
                elif side == 1: b.pos.x = r.right+b.radius+.1; b.vel.x = abs(b.vel.x)
                elif side == 2: b.pos.y = r.top-b.radius-.1; b.vel.y = -abs(b.vel.y)
                else: b.pos.y = r.bottom+b.radius+.1; b.vel.y = abs(b.vel.y)
            dead, color = brick.hit()
            self.combo += 1
            self.combo_time = 3.5
            mult = min(5, 1+self.combo//5)
            points = (brick.score_val if dead else 5)*mult
            self.score += points
            self.burst(*brick.rect.center, color, 16 if dead else 4)
            self.sound('brick_break' if dead else 'brick_hit')
            if dead:
                self.bricks.remove(brick)
                self.popup('+'+str(points), *brick.rect.center, color)
                self.shake = .09
                if random.random() < .22:
                    kind = random.choices(list(PowerUpType), [4, 3, 1, 3])[0]
                    self.powerups.append(PowerUp(*brick.rect.center, kind))
            if not b.piercing: break
        b.contacts = touching

    def step(self, dt, direction):
        if self.state not in ('ready', 'playing'): return
        target_width = self.cfg.PADDLE_WIDTH*(1.55 if self.wide > 0 else 1)
        self.paddle.width += (target_width-self.paddle.width)*min(1, dt*16)
        if self.control == 'keyboard': self.paddle.update(dt, direction)
        else:
            dx = self.mouse_x-self.paddle.pos.x
            self.paddle.pos.x += max(-1000*dt, min(1000*dt, dx))
            self.paddle.update(0, 0)
        if self.state == 'ready':
            self.balls[0].pos.update(self.paddle.pos.x, 654)
            return
        self.wide = max(0, self.wide-dt)
        self.pierce = max(0, self.pierce-dt)
        self.combo_time = max(0, self.combo_time-dt)
        if self.combo_time == 0: self.combo = 0
        for b in self.balls[:]:
            b.piercing = self.pierce > 0
            b.pos += b.vel*dt
            if b.pos.x < b.radius:
                b.pos.x = b.radius; b.vel.x = abs(b.vel.x)
            if b.pos.x > 1000-b.radius:
                b.pos.x = 1000-b.radius; b.vel.x = -abs(b.vel.x)
            if b.pos.y < 112+b.radius:
                b.pos.y = 112+b.radius; b.vel.y = abs(b.vel.y)
            self.collision(b)
            if b.pos.y > 740: self.balls.remove(b)
        for p in self.powerups[:]:
            p.update(dt)
            if p.rect.colliderect(self.paddle.rect):
                self.power(p.p_type); self.powerups.remove(p)
            elif p.pos.y > 740: self.powerups.remove(p)
        if not self.bricks:
            bonus = 250*self.level
            self.score += bonus
            self.save()
            self.state = 'clear'
            self.sound('powerup')
        elif not self.balls:
            self.lives -= 1
            self.sound('lose_life')
            self.save()
            if self.lives <= 0: self.state = 'over'
            else: self.serve()

    def text(self, text, pos, size=18, color=WHITE, center=False):
        img = self.fonts[size].render(str(text), True, color)
        self.canvas.blit(img, img.get_rect(center=pos) if center else pos)

    def panel(self, rect, color=(17, 25, 44), border=(37, 54, 77)):
        pygame.draw.rect(self.canvas, color, rect, border_radius=15)
        pygame.draw.rect(self.canvas, border, rect, 1, border_radius=15)

    def button(self, label, rect, action, active=False):
        r = pygame.Rect(rect)
        hover = r.collidepoint(self.pointer())
        self.panel(r, CYAN if active or hover else (24, 36, 56), CYAN if hover or active else (48, 68, 91))
        self.text(label, r.center, 18, INK if active or hover else WHITE, True)
        self.buttons.append((r, action))

    def pointer(self):
        w, h = self.screen.get_size()
        scale = min(w/1000, h/760)
        mx, my = pygame.mouse.get_pos()
        return ((mx-(w-1000*scale)/2)/scale, (my-(h-760*scale)/2)/scale)

    def draw(self):
        self.canvas.fill(INK)
        self.buttons = []
        for x, y, brightness in self.stars:
            v = int(40+35*brightness*(1+math.sin(self.time*.7+x))/2)
            pygame.draw.circle(self.canvas, (v//2, v, v+20), (x,y), 1)
        for x in range(30, 1000, 47):
            pygame.draw.line(self.canvas, (14, 23, 39), (x,114), (x,720))
        for y in range(130, 720, 47):
            pygame.draw.line(self.canvas, (14, 23, 39), (0,y), (1000,y))
        offset = Vector2(random.uniform(-3,3), random.uniform(-3,3)) if self.shake > 0 and self.motion else Vector2()
        for brick in self.bricks:
            r = brick.rect.move(round(offset.x), round(offset.y))
            c = brick.color
            pygame.draw.rect(self.canvas, tuple(int(v*.22) for v in c), r.move(0,4), border_radius=7)
            pygame.draw.rect(self.canvas, tuple(int(v*.65) for v in c), r, border_radius=6)
            pygame.draw.rect(self.canvas, c, r, 1, border_radius=6)
            pygame.draw.line(self.canvas, tuple(min(255,int(v*.7+75)) for v in c), (r.x+9,r.y+4), (r.right-9,r.y+4), 2)
            for i in range(brick.hp):
                pygame.draw.circle(self.canvas, WHITE, (r.centerx+(i*7)-(brick.hp-1)*3, r.centery+3), 1)
        for p in self.powerups: p.draw(self.canvas, self.fonts[12], offset)
        for p in self.particles: p.draw(self.canvas, offset)
        self.paddle.draw(self.canvas, Vector2())
        for b in self.balls: b.draw(self.canvas, Vector2())
        for text, x, y, age, color in self.floaters:
            self.text(text, (x,y), 14, tuple(int(v*min(1,age*2)) for v in color), True)
        if self.state == 'ready':
            b = self.balls[0]
            for i in range(1,10):
                pos = b.pos + b.vel.normalize()*i*13
                pygame.draw.circle(self.canvas, (53, 91, 103), (int(pos.x),int(pos.y)), 2)
        music_label = 'B / MUSIC ' + ('ON' if self.music.enabled else 'OFF') if self.music.available else 'NO AUDIO'
        self.button(music_label, (810, 620, 155, 36), 'music')
        pygame.draw.line(self.canvas, (61, 33, 57), (25,718), (975,718), 1)
        self.panel((20,15,960,83))
        self.text('NEON / BREAKER', (40,27), 22, CYAN)
        self.text(self.MODES[self.mode][0]+'  /  '+self.NAMES[(self.level-1)%5], (40,61), 12, MUTED)
        for label, value, x in [('SCORE',f'{self.score:06}',355),('BEST',f'{max(self.score,self.records.get(self.MODES[self.mode][0],0)):06}',505),('LEVEL',f'{self.level:02}',655),('LIVES',str(self.lives),760)]:
            self.text(label, (x,29), 12, MUTED)
            self.text(value, (x,48), 26, PINK if label=='LIVES' else WHITE)
        self.button('II', (874,31,42,48), 'pause')
        self.button('S' if not self.muted else '-', (925,31,38,48), 'mute')
        progress = 1-len(self.bricks)/self.initial_bricks
        pygame.draw.rect(self.canvas,(25,40,58),(35,122,930,3),border_radius=1)
        if progress: pygame.draw.rect(self.canvas,CYAN,(35,122,int(930*progress),3))
        if self.combo >= 5:
            self.text(f'x{min(5,1+self.combo//5)} COMBO', (500,393), 26, CYAN, True)
            pygame.draw.rect(self.canvas,(27,68,73),(450,416,int(100*self.combo_time/3.5),3))
        for i, (label, remaining, total, color) in enumerate([('WIDE',self.wide,12,CYAN),('PIERCE',self.pierce,8,(255,161,88))]):
            if remaining > 0:
                x = 35+i*165
                self.text(f'{label}  {remaining:.1f}s',(x,620),12,color)
                pygame.draw.rect(self.canvas,color,(x,642,int(130*remaining/total),3))
        self.text('MOUSE / A D : GERAK     SPACE : LUNCUR     P : JEDA     M : SFX     B : MUSIK     V : EFEK', (500,741),12,MUTED,True)
        if self.state == 'ready':
            self.text('SIAP MELUNCUR?', (500,460),36,WHITE,True)
            self.text('Arah pantulan mengikuti titik bola mengenai paddle.', (500,500),14,MUTED,True)
            self.button('KLIK / SPACE UNTUK MULAI', (335,530,330,48), 'start',True)
        elif self.state in ('menu','paused','clear','over'):
            self.buttons = []
            shade = pygame.Surface((1000,760),pygame.SRCALPHA); shade.fill((3,7,17,205)); self.canvas.blit(shade,(0,0))
            self.panel((180,175,640,420),(15,23,41),(51,74,100))
            if self.state == 'menu':
                self.text('THE ARCADE / REIMAGINED', (500,215),12,CYAN,True)
                self.text('NEON BREAKER', (500,272),58,WHITE,True)
                self.text('Pecahkan balok. Rangkai combo. Kuasai arena.',(500,325),18,MUTED,True)
                for i,(name,_,_) in enumerate(self.MODES):
                    self.button(name,(240+i*178,365,164,45),'mode'+str(i),i==self.mode)
                self.button('MULAI BERMAIN', (330,438,340,56),'new',True)
                self.text('Tangkap WIDE, MULTI, PIERCE, dan ekstra nyawa.',(500,528),14,MUTED,True)
                self.text('Pilih Santai untuk kecepatan lebih rendah dan 5 nyawa.',(500,554),14,MUTED,True)
            else:
                title = {'paused':'AMBIL NAPAS.','clear':'STAGE COMPLETE!','over':'NICE RUN.'}[self.state]
                self.text(title,(500,255),36,WHITE,True)
                caption = f'Skor {self.score:,}  /  Level {self.level}'
                if self.state == 'clear': caption += f'  /  Bonus +{250*self.level}'
                self.text(caption,(500,320),18,MUTED,True)
                label = {'paused':'LANJUTKAN','clear':'LEVEL BERIKUTNYA','over':'MAIN LAGI'}[self.state]
                self.button(label,(330,382,340,56),'start',True)
                self.button('MENU UTAMA',(330,454,340,48),'menu')
                self.text('SPACE untuk lanjut  /  ESC untuk menu',(500,550),14,MUTED,True)
        w,h = self.screen.get_size()
        scale = min(w/1000,h/760)
        size = (max(1,int(1000*scale)), max(1,int(760*scale)))
        self.screen.fill((3,5,11))
        self.screen.blit(pygame.transform.smoothscale(self.canvas,size),((w-size[0])//2,(h-size[1])//2))
        pygame.display.flip()

    def action(self, action):
        if action == 'music': self.music.toggle()
        elif action == 'mute': self.muted = not self.muted
        elif action.startswith('mode'):
            self.mode = int(action[-1]); self.reset(); self.state = 'menu'
        elif action == 'new': self.reset()
        elif action == 'menu': self.save(); self.state = 'menu'
        elif action == 'pause':
            if self.state in ('ready','playing'):
                self.previous = self.state; self.state = 'paused'
            elif self.state == 'paused': self.state = self.previous
        elif action == 'start':
            if self.state == 'menu': self.reset()
            elif self.state == 'ready': self.state = 'playing'
            elif self.state == 'paused': self.state = self.previous
            elif self.state == 'clear': self.level += 1; self.setup_level()
            elif self.state == 'over': self.reset()

    def run(self):
        running = True
        while running:
            dt = min(.05,self.clock.tick(120)/1000)
            self.time += dt
            for e in pygame.event.get():
                if e.type == pygame.QUIT: running = False
                elif e.type == pygame.WINDOWFOCUSLOST and self.state in ('playing','ready'):
                    self.action('pause')
                elif e.type == pygame.MOUSEMOTION:
                    self.control = 'mouse'; self.mouse_x = self.pointer()[0]
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    hit = next((a for r,a in self.buttons if r.collidepoint(self.pointer())),None)
                    if hit: self.action(hit)
                    elif self.state == 'ready': self.action('start')
                elif e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_a,pygame.K_d,pygame.K_LEFT,pygame.K_RIGHT): self.control = 'keyboard'
                    elif e.key in (pygame.K_SPACE,pygame.K_RETURN): self.action('start')
                    elif e.key == pygame.K_p: self.action('pause')
                    elif e.key == pygame.K_m: self.action('mute')
                    elif e.key == pygame.K_b: self.action('music')
                    elif e.key == pygame.K_v: self.motion = not self.motion
                    elif e.key == pygame.K_ESCAPE:
                        self.action('pause' if self.state in ('playing','ready') else 'menu')
            keys = pygame.key.get_pressed()
            direction = int(keys[pygame.K_d] or keys[pygame.K_RIGHT])-int(keys[pygame.K_a] or keys[pygame.K_LEFT])
            self.accumulator += dt
            while self.accumulator >= 1/240:
                self.step(1/240,direction)
                self.accumulator -= 1/240
            if self.state in ('playing','ready','clear'):
                self.shake = max(0,self.shake-dt)
                self.particles = [p for p in self.particles if p.update(dt)]
                for f in self.floaters: f[2] -= 35*dt; f[3] -= dt
                self.floaters = [f for f in self.floaters if f[3]>0]
                for b in self.balls:
                    b.trail.append(Vector2(b.pos)); b.trail = b.trail[-10:]
            self.music.update(self.state, dt)
            self.draw()
        self.save()
        pygame.quit()


if __name__ == '__main__':
    NeonBreaker().run()
