"""Animated on-screen approximation of the mouse's lighting effects."""

import colorsys
import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

SPEED_RATE = {1: 0.5, 2: 1.0, 3: 1.8}
BRIGHTNESS_SCALE = {1: 0.35, 2: 0.65, 3: 0.85, 4: 1.0}
LED_COUNT = 36


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hue(h):
    return colorsys.hsv_to_rgb(h % 1.0, 1, 1)


def scale(c, k):
    return tuple(v * k for v in c)


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def led_color(light, pos, ypos, t):
    """Colour of one LED. pos: 0..1 along the strip, ypos: 0 top .. 1 bottom."""
    mode = light.get("mode", "off")
    rate = SPEED_RATE.get(light.get("speed", 2), 1.0) * t
    colors = [hex_rgb(c) for c in light.get("colors") or []] or [(1, 1, 1)]
    if mode == "static":
        return colors[0]
    if mode in ("breathing", "spectrum-breathing"):
        phase = rate * 0.4
        level = 0.5 - 0.5 * math.cos(2 * math.pi * phase)
        return scale(colors[int(phase) % len(colors)], level)
    if mode == "rainbow":
        sign = -1 if light.get("direction") == "up" else 1
        return hue(ypos * 0.8 - sign * rate * 0.25)
    if mode == "spectrum-cycle":
        return hue(rate * 0.1)
    if mode == "wave":
        return hue(pos - rate * 0.3)
    if mode == "multicolor":
        x = rate * 0.5
        i = int(x)
        return mix(colors[i % len(colors)], colors[(i + 1) % len(colors)], x - i)
    if mode == "tail":
        head = (rate * 0.6) % 1.0
        dist = (head - pos) % 1.0
        return scale(hue(rate * 0.05), math.exp(-dist * 9))
    if mode == "rave":
        return colors[int(rate * 3) % len(colors)]
    if mode == "epilepsy":
        rnd = random.Random(int(rate * 12))
        return hue(rnd.random()) if rnd.random() < 0.5 else (0, 0, 0)
    return (0, 0, 0)


def qcolor(c, alpha=1.0):
    return QColor.fromRgbF(min(c[0], 1), min(c[1], 1), min(c[2], 1), alpha)


class Preview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.light = {"mode": "off"}
        self.dpi_flash = None  # (rgb, until) shown on the logo after a DPI change
        self.timer = QTimer(self, interval=33, timeout=self.update)
        self.timer.start()

    def set_lighting(self, light):
        self.light = dict(light)

    def flash_dpi(self, hexc):
        self.dpi_flash = (hex_rgb(hexc), time.monotonic() + 1.2)

    @staticmethod
    def body_path(cx, cy, w, h):
        # Top view of a symmetric mouse, narrower at the front.
        top, bot = cy - h / 2, cy + h / 2
        p = QPainterPath(QPointF(cx, top))
        p.cubicTo(cx + w * 0.42, top, cx + w * 0.46, cy - h * 0.15, cx + w * 0.5, cy + h * 0.12)
        p.cubicTo(cx + w * 0.54, cy + h * 0.4, cx + w * 0.3, bot, cx, bot)
        p.cubicTo(cx - w * 0.3, bot, cx - w * 0.54, cy + h * 0.4, cx - w * 0.5, cy + h * 0.12)
        p.cubicTo(cx - w * 0.46, cy - h * 0.15, cx - w * 0.42, top, cx, top)
        p.closeSubpath()
        return p

    def glow(self, painter, x, y, radius, c, alpha):
        g = QRadialGradient(QPointF(x, y), radius)
        g.setColorAt(0, qcolor(c, alpha))
        g.setColorAt(1, qcolor(c, 0))
        painter.setBrush(g)
        painter.drawEllipse(QPointF(x, y), radius, radius)

    def paintEvent(self, _event):
        t = time.monotonic()
        bright = BRIGHTNESS_SCALE.get(self.light.get("brightness", 4), 1.0)
        width, height = self.width(), self.height()

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(18, 18, 23))
        p.drawRoundedRect(QRectF(0, 0, width, height), 12, 12)

        h = height * 0.84
        w = h * 0.56
        cx, cy = width / 2, height / 2

        # LED strip: a U around the rear half of the shell.
        leds = []
        for i in range(LED_COUNT):
            pos = i / (LED_COUNT - 1)
            a = math.pi * pos  # 0 = right side, pi/2 = rear, pi = left side
            x = cx + math.cos(a) * w * 0.52
            y = cy + h * 0.12 + math.sin(a) * h * 0.38
            c = scale(led_color(self.light, pos, (y - (cy - h / 2)) / h, t), bright)
            leds.append((x, y, c))

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for x, y, c in leds:
            self.glow(p, x, y, w * 0.16, c, 0.55)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Shell.
        p.setBrush(QColor(31, 31, 36))
        p.setPen(QPen(QColor(71, 71, 82), 1.5))
        p.drawPath(self.body_path(cx, cy, w, h))

        # Button split and scroll wheel.
        p.drawLine(QPointF(cx, cy - h / 2), QPointF(cx, cy - h * 0.12))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(51, 51, 59))
        ww, wh = w * 0.09, h * 0.13
        p.drawRoundedRect(QRectF(cx - ww / 2, cy - h * 0.38, ww, wh), 3, 3)

        # LED cores on top of the shell edge.
        for x, y, c in leds:
            p.setBrush(qcolor(mix((0.18, 0.18, 0.2), c, 0.9)))
            r = max(w * 0.022, 1.5)
            p.drawEllipse(QPointF(x, y), r, r)

        # Logo, lit like the middle of the strip (or the DPI colour briefly).
        c = scale(led_color(self.light, 0.5, 0.7, t), bright)
        if self.dpi_flash and t < self.dpi_flash[1]:
            c = self.dpi_flash[0]
        self.glow(p, cx, cy + h * 0.2, w * 0.2, c, 0.9)
        p.end()
