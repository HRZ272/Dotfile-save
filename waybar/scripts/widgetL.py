#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
widgetL — выдвигающееся меню быстрого запуска для waybar (Wayland / gtk-layer-shell)
Тот же стиль, что у widgetM: один Cairo-холст, Catppuccin Mocha, aurora-фон, градиентная рамка.

  sudo pacman -S python-gtk-layer-shell python-gobject python-cairo

Кнопки
  1  War Thunder   ->  cd /mnt/games/WarThunder && ./launcher
  2  btop          ->  kitty btop -u 1000          (интервал обновления 1000 мс)
  3  aces | 4  Discord   (двойная кнопка)  ->  pkill -9 aces  /  pkill -9 Discord

Что внутри
  • карточка выезжает сверху с пружинным «перелётом», кнопки появляются каскадом
  • hover / press-пружины, свечение цветом кнопки, векторные иконки
  • живые данные: CPU/RAM на кнопке btop, статус «запущено» у War Thunder и Discord
  • у кнопок kill — отклик после нажатия («завершён ✓» / «не запущен»)
  • повторный запуск = закрыть (toggle), Esc / ПКМ — закрыть с анимацией

Клавиши: Esc/q закрыть · 1-4 запуск кнопки · ↑/↓/←/→/Tab выбор · Enter/Space нажать
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GtkLayerShell, GLib, Pango, PangoCairo

import cairo
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time


# ═════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ═════════════════════════════════════════════════════════════
ANCHOR       = 'left'        # 'left' | 'right' — с какой стороны экрана выезжает меню
X_OFFSET     = 80            # отступ от этого края (подгони под положение иконки в waybar)
TOP_TARGET   = 42            # отступ сверху (под waybar)

CARD_W       = 320
CARD_H       = 288
CARD_RADIUS  = 24
CARD_OPACITY = 0.96          # < 1 -> сквозь карточку видно blur композитора
PAD          = 16
M            = 22            # запас вокруг карточки под тень/свечение

FONT         = 'JetBrainsMono Nerd Font'

ANIM_FPS     = 60
OPEN_DUR     = 0.55
CLOSE_DUR    = 0.26
IDLE_FPS     = 20            # частота перерисовки в покое (aurora-фон + CPU/RAM)

TOGGLE           = True      # повторный запуск закрывает окно
CLOSE_AFTER_KILL = False     # закрывать меню после kill (False — можно убить оба подряд)

# ── что запускаем ──
WT_DIR       = '/mnt/games/WarThunder'
WT_CMD       = ['./launcher']                      # запускается из WT_DIR
BTOP_CMD     = ['kitty', 'btop', '-u', '1000']     # -u = интервал обновления, мс

# ── что убиваем (имена процессов; -x = точное совпадение, чтобы не задеть лишнее) ──
PROC_WT      = 'aces'
PROC_DISCORD = 'Discord'

# Catppuccin Mocha
LAVENDER = (0.706, 0.745, 0.996)   # #b4befe
MAUVE    = (0.796, 0.651, 0.969)   # #cba6f7
PEACH    = (0.980, 0.702, 0.529)   # #fab387
GREEN    = (0.651, 0.890, 0.631)   # #a6e3a1
RED      = (0.953, 0.545, 0.659)   # #f38ba8
TEXT     = (0.804, 0.839, 0.957)   # #cdd6f4
SUBTEXT  = (0.651, 0.678, 0.784)   # #a6adc8
TINT     = (0.130, 0.130, 0.250)
WHITE    = (1.0, 1.0, 1.0)


# ═════════════════════════════════════════════════════════════
#  МАТЕМАТИКА / ПРИМИТИВЫ
# ═════════════════════════════════════════════════════════════
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x

def lerp(a, b, t):
    return a + (b - a) * t

def mix(c1, c2, t):
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def ease_in_cubic(t):
    return t ** 3

def ease_out_back(t, s=1.5):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


class Spring:
    """Пружина: живой отклик с лёгким перелётом."""
    def __init__(self, value=0.0, k=170.0, d=19.0):
        self.x, self.v, self.t, self.k, self.d = value, 0.0, value, k, d

    def update(self, dt):
        dt = min(dt, 0.033)
        a = self.k * (self.t - self.x) - self.d * self.v
        self.v += a * dt
        self.x += self.v * dt

    @property
    def settled(self):
        return abs(self.t - self.x) < 1e-3 and abs(self.v) < 1e-3


def rrect(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r,     r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0,            math.pi / 2)
    cr.arc(x + r,     y + h - r, r, math.pi / 2,  math.pi)
    cr.arc(x + r,     y + r,     r, math.pi,      1.5 * math.pi)
    cr.close_path()


def rrect_c(cr, x, y, w, h, tl, tr, br, bl):
    """Скруглённый прямоугольник с разными радиусами углов (для двойной кнопки)."""
    m = min(w, h) / 2
    tl, tr, br, bl = (max(0.0, min(r, m)) for r in (tl, tr, br, bl))
    cr.new_sub_path()
    cr.arc(x + w - tr, y + tr,     tr, -math.pi / 2, 0)
    cr.arc(x + w - br, y + h - br, br, 0,            math.pi / 2)
    cr.arc(x + bl,     y + h - bl, bl, math.pi / 2,  math.pi)
    cr.arc(x + tl,     y + tl,     tl, math.pi,      1.5 * math.pi)
    cr.close_path()


def soft_shadow(cr, x, y, w, h, r, rgb, alpha, spread, steps=9):
    """Мягкая тень/свечение из набора расходящихся скруглённых прямоугольников."""
    a = alpha / steps
    for i in range(steps, 0, -1):
        e = spread * i / steps
        rrect(cr, x - e, y - e, w + 2 * e, h + 2 * e, r + e)
        cr.set_source_rgba(rgb[0], rgb[1], rgb[2], a)
        cr.fill()


def soft_glow_c(cr, x, y, w, h, radii, rgb, alpha, spread, steps=6):
    a = alpha / steps
    for i in range(steps, 0, -1):
        e = spread * i / steps
        rrect_c(cr, x - e, y - e, w + 2 * e, h + 2 * e, *[r + e for r in radii])
        cr.set_source_rgba(rgb[0], rgb[1], rgb[2], a)
        cr.fill()


def make_layout(cr, text, size, bold=False, spacing=0.0):
    lay = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription()
    fd.set_family(FONT)
    fd.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    fd.set_absolute_size(size * Pango.SCALE)
    lay.set_font_description(fd)
    if spacing:
        al = Pango.AttrList()
        al.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
        lay.set_attributes(al)
    lay.set_text(text, -1)
    return lay


def put_text(cr, text, x, y, size, rgb, alpha=1.0, bold=False, spacing=0.0, align='l'):
    """Рисует строку; align: l / r / c относительно x. Возвращает ширину."""
    lay = make_layout(cr, text, size, bold, spacing)
    w, _h = lay.get_pixel_size()
    if align == 'r':
        x -= w
    elif align == 'c':
        x -= w / 2
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, lay)
    return w


# ═════════════════════════════════════════════════════════════
#  СИСТЕМА: процессы, CPU/RAM, запуск
# ═════════════════════════════════════════════════════════════
def proc_alive(name):
    try:
        return subprocess.run(['pgrep', '-x', name], capture_output=True,
                              timeout=1.5).returncode == 0
    except Exception:
        return False


def notify(msg):
    try:
        subprocess.Popen(['notify-send', 'widgetL', msg, '-i', 'dialog-information'])
    except OSError:
        pass


def spawn(cmd, cwd=None):
    """Запускает программу отдельно от меню (переживёт закрытие виджета)."""
    try:
        subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as e:
        notify(f'Не удалось запустить {cmd[0]}: {e}')
        return False


class Stats:
    """Живые данные для меню: загрузка CPU/RAM и запущены ли aces / Discord."""

    def __init__(self, live=True):
        self.cpu = 0.0
        self.ram = 0.0
        self.wt = False
        self.discord = False
        self._stop = threading.Event()
        if live:
            threading.Thread(target=self._loop, daemon=True).start()

    @staticmethod
    def _cpu_times():
        with open('/proc/stat') as f:
            v = [int(x) for x in f.readline().split()[1:]]
        return v[3] + v[4], sum(v[:8])

    @staticmethod
    def _ram():
        info = {}
        with open('/proc/meminfo') as f:
            for ln in f:
                k, _, rest = ln.partition(':')
                if k in ('MemTotal', 'MemAvailable'):
                    info[k] = int(rest.split()[0])
                    if len(info) == 2:
                        break
        return 100.0 * (1 - info['MemAvailable'] / info['MemTotal'])

    def _loop(self):
        prev, first = None, True
        while not self._stop.is_set():
            try:
                idle, total = self._cpu_times()
                if prev and total > prev[1]:
                    self.cpu = clamp(1 - (idle - prev[0]) / (total - prev[1])) * 100
                prev = (idle, total)
                self.ram = self._ram()
            except (OSError, KeyError, ValueError, IndexError, ZeroDivisionError):
                pass
            self.wt = proc_alive(PROC_WT)
            self.discord = proc_alive(PROC_DISCORD)
            self._stop.wait(0.4 if first else 1.0)
            first = False

    def stop(self):
        self._stop.set()


# ═════════════════════════════════════════════════════════════
#  ИКОНКИ (рисуются вокруг (0, 0), «размер» ≈ 24 px)
# ═════════════════════════════════════════════════════════════
def icon_target(cr, rgb, alpha, hover, t):
    """Прицел — War Thunder. На hover медленно довернётся."""
    spin = hover * math.pi / 4
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(1.8)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.new_sub_path()
    cr.arc(0, 0, 6.2, 0, 2 * math.pi)
    cr.stroke()
    for k in range(4):
        a = k * math.pi / 2 + spin
        cr.move_to(math.cos(a) * 8.4, math.sin(a) * 8.4)
        cr.line_to(math.cos(a) * 11.4, math.sin(a) * 11.4)
        cr.stroke()
    cr.new_sub_path()
    cr.arc(0, 0, 1.8, 0, 2 * math.pi)
    cr.fill()


def icon_chart(cr, rgb, alpha, hover, t):
    """Столбики — btop. Чуть «дышат», на hover сильнее."""
    cr.set_source_rgba(*rgb, alpha)
    amp = 0.10 + 0.25 * clamp(hover)
    for i, hh in enumerate((8.0, 15.0, 11.0)):
        k = 1.0 - amp * (0.5 + 0.5 * math.sin(t * 3.2 + i * 1.9))
        h = hh * k
        rrect(cr, -9.5 + i * 6.5, 7.5 - h, 4.2, h, 1.7)
        cr.fill()


def icon_x(cr, rgb, alpha, hover, t):
    """Крестик — kill. На hover слегка увеличивается."""
    s = 1.0 + 0.14 * clamp(hover)
    cr.scale(s, s)
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(2.3)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for a, b in (((-5.2, -5.2), (5.2, 5.2)), ((-5.2, 5.2), (5.2, -5.2))):
        cr.move_to(*a)
        cr.line_to(*b)
        cr.stroke()


ICONS = {'target': icon_target, 'chart': icon_chart, 'x': icon_x}


# ═════════════════════════════════════════════════════════════
#  КНОПКА
# ═════════════════════════════════════════════════════════════
ROW_H   = 54
Y1      = 66
Y2      = Y1 + ROW_H + 9
Y3      = Y2 + ROW_H + 9 + 28        # + место под подпись секции
FULL_W  = CARD_W - 2 * PAD
HALF_W  = (FULL_W - 3) / 2           # двойная кнопка: две половинки, зазор 3px
R_OUT, R_IN = 16, 6


class Btn:
    def __init__(self, bid, kind, x, y, w, acc, icon, title, key, tag='', kill=False):
        self.id, self.kind = bid, kind                 # kind: full | left | right
        self.x, self.y, self.w, self.h = x, y, w, ROW_H
        self.acc, self.icon, self.title, self.key, self.tag = acc, icon, title, key, tag
        self.kill = kill
        self.hover = Spring(0.0, 230.0, 22.0)
        self.press = Spring(0.0, 320.0, 26.0)
        self.enter = 0.0                                # каскадное появление 0..1
        self.dim = 1.0                                  # 0.5, если kill-цели нет в системе
        self.flash = None                               # (до какого времени, текст, цвет)

    @property
    def radii(self):                                    # tl, tr, br, bl
        if self.kind == 'left':
            return (R_OUT, R_IN, R_IN, R_OUT)
        if self.kind == 'right':
            return (R_IN, R_OUT, R_OUT, R_IN)
        return (R_OUT, R_OUT, R_OUT, R_OUT)


# ═════════════════════════════════════════════════════════════
#  КАРТОЧКА (вся отрисовка + логика наведения)
# ═════════════════════════════════════════════════════════════
class Card:
    def __init__(self, stats):
        self.st = stats
        self.t0 = time.monotonic()
        self.t_open = None
        self.btns = [
            Btn('wt',           'full',  PAD,                  Y1, FULL_W, PEACH, 'target', 'War Thunder', '1'),
            Btn('btop',         'full',  PAD,                  Y2, FULL_W, GREEN, 'chart',  'btop',        '2', tag='-u 1000'),
            Btn('kill_aces',    'left',  PAD,                  Y3, HALF_W, RED,   'x',      PROC_WT,       '3', kill=True),
            Btn('kill_discord', 'right', PAD + HALF_W + 3,     Y3, HALF_W, RED,   'x',      PROC_DISCORD,  '4', kill=True),
        ]
        self.by_id = {b.id: b for b in self.btns}
        self.hov = None
        self.foc = None
        self.pressed = None
        self.cpu_s = 0.0
        self.ram_s = 0.0

    # ── логика ──
    def start_open(self, now):
        self.t_open = now

    def alive(self, b):
        if b.id in ('wt', 'kill_aces'):
            return self.st.wt
        if b.id == 'kill_discord':
            return self.st.discord
        return None

    def update(self, dt, now):
        self.cpu_s += (self.st.cpu - self.cpu_s) * min(1.0, dt * 6)
        self.ram_s += (self.st.ram - self.ram_s) * min(1.0, dt * 6)
        el = (now - self.t_open) if self.t_open is not None else -1.0
        focused = self.btns[self.foc] if self.foc is not None else None
        for i, b in enumerate(self.btns):
            b.enter = clamp((el - 0.10 - i * 0.055) / 0.38)
            b.hover.t = 1.0 if (b is self.hov or b is focused) else 0.0
            b.hover.update(dt)
            b.press.update(dt)
            want = 1.0 if (not b.kill or self.alive(b)) else 0.5
            b.dim += (want - b.dim) * min(1.0, dt * 8)
            if b.flash and now >= b.flash[0]:
                b.flash = None

    def busy(self, now):
        for b in self.btns:
            if b.enter < 1.0 or not b.hover.settled or not b.press.settled or b.flash:
                return True
        return False

    def flash(self, bid, text, rgb, secs=1.4):
        self.by_id[bid].flash = (time.monotonic() + secs, text, rgb)

    def hit(self, x, y):
        for b in self.btns:
            if b.x <= x <= b.x + b.w and b.y <= y <= b.y + b.h:
                return b
        return None

    def on_motion(self, x, y):
        b = self.hit(x, y)
        self.hov = b
        if b is not None:
            self.foc = None               # мышь перехватывает выбор у клавиатуры
        return b.id if b else None

    def on_leave(self):
        self.hov = None
        if self.pressed:
            self.pressed.press.t = 0.0
            self.pressed = None

    def on_press(self, x, y):
        b = self.hit(x, y)
        if b:
            self.pressed = b
            b.press.t = 1.0

    def on_release(self, x, y):
        b, p = self.hit(x, y), self.pressed
        self.pressed = None
        if p:
            p.press.t = 0.0
            if b is p:
                return p.id
        return None

    def focus_move(self, d):
        n = len(self.btns)
        self.foc = (0 if d > 0 else n - 1) if self.foc is None else (self.foc + d) % n

    def focus_id(self):
        return self.btns[self.foc].id if self.foc is not None else None

    def pulse(self, bid):
        b = self.by_id[bid]
        b.press.x = 0.9                   # короткий «клик» пружиной
        b.press.t = 0.0

    # ── отрисовка ──
    def draw(self, cr, now):
        t = now - self.t0
        soft_shadow(cr, 0, 5, CARD_W, CARD_H, CARD_RADIUS, (0, 0, 0), 0.50, 15, 9)
        soft_shadow(cr, 0, 0, CARD_W, CARD_H, CARD_RADIUS, LAVENDER, 0.15, 13, 8)

        cr.save()
        rrect(cr, 0, 0, CARD_W, CARD_H, CARD_RADIUS)
        cr.clip()
        self._draw_bg(cr, t)
        self._draw_header(cr, t)
        for b in self.btns[:2]:
            self._draw_btn(cr, b, now, t)
        self._draw_section(cr)
        for b in self.btns[2:]:
            self._draw_btn(cr, b, now, t)
        cr.restore()
        self._draw_border(cr)

    def _draw_bg(self, cr, t):
        c0 = mix((0.105, 0.105, 0.155), TINT, 0.42)
        c1 = mix((0.040, 0.040, 0.070), TINT, 0.26)
        g = cairo.LinearGradient(0, 0, CARD_W, CARD_H)
        g.add_color_stop_rgba(0, *c0, CARD_OPACITY)
        g.add_color_stop_rgba(1, *c1, CARD_OPACITY)
        cr.set_source(g)
        cr.paint()

        sg = cairo.LinearGradient(0, 0, 0, CARD_H)
        sg.add_color_stop_rgba(0, 0, 0, 0, 0.10)
        sg.add_color_stop_rgba(1, 0, 0, 0, 0.40)
        cr.set_source(sg)
        cr.paint()

        blobs = (
            (CARD_W * (0.14 + 0.14 * math.sin(t * 0.31)),       CARD_H * (0.22 + 0.18 * math.cos(t * 0.23)),       230, LAVENDER, 0.22),
            (CARD_W * (0.90 + 0.10 * math.cos(t * 0.27 + 1.0)), CARD_H * (0.88 + 0.10 * math.sin(t * 0.19)),       250, MAUVE,    0.19),
            (CARD_W * (0.60 + 0.20 * math.sin(t * 0.17 + 2.0)), CARD_H * (0.50 + 0.30 * math.cos(t * 0.21 + 0.5)), 160, mix(LAVENDER, WHITE, 0.45), 0.06),
            (CARD_W * (0.85 + 0.08 * math.sin(t * 0.22)),       CARD_H * (0.45 + 0.12 * math.cos(t * 0.26)),       140, PEACH,    0.05),
        )
        for cx, cy, r, col, a in blobs:
            rg = cairo.RadialGradient(cx, cy, 0, cx, cy, r)
            rg.add_color_stop_rgba(0, *col, a)
            rg.add_color_stop_rgba(1, *col, 0.0)
            cr.set_source(rg)
            cr.paint()

        sh = cairo.RadialGradient(70, -20, 0, 70, -20, 300)
        sh.add_color_stop_rgba(0, 1, 1, 1, 0.085)
        sh.add_color_stop_rgba(1, 1, 1, 1, 0.0)
        cr.set_source(sh)
        cr.paint()

    def _draw_header(self, cr, t):
        # плитка-логотип 2×2
        s = 34
        x0, y0 = PAD, 14
        g = cairo.LinearGradient(x0, y0, x0 + s, y0 + s)
        g.add_color_stop_rgba(0, *mix(LAVENDER, WHITE, 0.25), 1)
        g.add_color_stop_rgba(1, *MAUVE, 1)
        rrect(cr, x0, y0, s, s, 11)
        cr.set_source(g)
        cr.fill()
        cr.set_source_rgba(0.10, 0.10, 0.18, 0.88)
        for i in range(2):
            for j in range(2):
                rrect(cr, x0 + 7.5 + i * 10.5, y0 + 7.5 + j * 10.5, 8, 8, 2.6)
                cr.fill()

        put_text(cr, 'Быстрый запуск', x0 + s + 11, 13, 15, TEXT, 0.97, bold=True)
        put_text(cr, 'waybar · launcher', x0 + s + 11, 33, 10, SUBTEXT, 0.55)

        # подсказка Esc
        px, py, pw, ph = CARD_W - PAD - 36, 22, 36, 19
        rrect(cr, px, py, pw, ph, 7)
        cr.set_source_rgba(1, 1, 1, 0.06)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.09)
        cr.set_line_width(1)
        cr.stroke()
        put_text(cr, 'esc', px + pw / 2, py + 3, 10, SUBTEXT, 0.65, align='c')

        # разделитель
        dg = cairo.LinearGradient(PAD, 0, CARD_W - PAD, 0)
        dg.add_color_stop_rgba(0.0, 1, 1, 1, 0.0)
        dg.add_color_stop_rgba(0.5, 1, 1, 1, 0.12)
        dg.add_color_stop_rgba(1.0, 1, 1, 1, 0.0)
        cr.set_source(dg)
        cr.rectangle(PAD, 56, CARD_W - 2 * PAD, 1)
        cr.fill()

    def _draw_section(self, cr):
        e = ease_out_cubic(self.by_id['kill_aces'].enter)
        if e <= 0.01:
            return
        y = Y3 - 22
        put_text(cr, 'ЗАВЕРШИТЬ ПРОЦЕСС', PAD + 4, y, 9.5, SUBTEXT, 0.50 * e, bold=True, spacing=1.6)
        put_text(cr, 'kill -9', CARD_W - PAD - 4, y, 9.5, RED, 0.70 * e, bold=True, align='r')

    # ── кнопка ──
    def _sub(self, b, now):
        """Вторая строка кнопки: (текст, цвет, прозрачность)."""
        if b.flash:
            until, text, rgb = b.flash
            return text, rgb, clamp((until - now) / 0.3)
        if b.id == 'wt':
            if self.st.wt:
                return '● запущено', GREEN, 0.75 + 0.25 * math.sin(now * 3.0)
            return 'запустить лаунчер', SUBTEXT, 0.62
        if b.id == 'btop':
            return f'CPU {self.cpu_s:>3.0f}%  RAM {self.ram_s:>3.0f}%', SUBTEXT, 0.70
        if self.alive(b):
            return '● работает', GREEN, 0.75 + 0.25 * math.sin(now * 3.0)
        return 'не запущен', SUBTEXT, 0.50

    def _draw_btn(self, cr, b, now, t):
        e = ease_out_cubic(b.enter)
        if e <= 0.002:
            return
        h, p, dim, acc = clamp(b.hover.x, 0.0, 1.2), b.press.x, b.dim, b.acc
        full = b.kind == 'full'
        rd = b.radii
        cx, cy = b.x + b.w / 2, b.y + b.h / 2
        focused = (self.foc is not None and self.btns[self.foc] is b)

        grouped = e < 0.999
        if grouped:
            cr.push_group()
        cr.save()
        sc = 1 + 0.010 * h - 0.030 * p
        cr.translate(cx, cy + (1 - e) * 14)
        cr.scale(sc, sc)
        cr.translate(-cx, -cy)

        # свечение + тёмная подложка + градиент цветом кнопки
        if h > 0.02:
            soft_glow_c(cr, b.x, b.y, b.w, b.h, rd, acc, 0.20 * h * dim, 10)
        rrect_c(cr, b.x, b.y, b.w, b.h, *rd)
        cr.set_source_rgba(0, 0, 0, 0.22)
        cr.fill()
        g = cairo.LinearGradient(b.x, 0, b.x + b.w, 0)
        g.add_color_stop_rgba(0.0, *acc, (0.10 + 0.16 * h) * dim)
        g.add_color_stop_rgba(0.6, 1, 1, 1, 0.040 + 0.030 * h)
        g.add_color_stop_rgba(1.0, 1, 1, 1, 0.030 + 0.025 * h)
        rrect_c(cr, b.x, b.y, b.w, b.h, *rd)
        cr.set_source(g)
        cr.fill()

        # рамка (+ кольцо фокуса с клавиатуры)
        rrect_c(cr, b.x + 0.5, b.y + 0.5, b.w - 1, b.h - 1, *[max(r - 0.5, 0) for r in rd])
        bc = mix(acc, WHITE, 0.25)
        cr.set_source_rgba(*bc, min(1.0, (0.10 + 0.55 * h + (0.30 if focused else 0.0)) * (0.5 + 0.5 * dim)))
        cr.set_line_width(1.6 if focused else 1.0)
        cr.stroke()

        # плитка иконки
        bs = 34 if full else 30
        bx = b.x + (10 if full else 9)
        by = cy - bs / 2
        ig = cairo.LinearGradient(bx, by, bx, by + bs)
        ig.add_color_stop_rgba(0, *acc, (0.34 + 0.18 * h) * dim)
        ig.add_color_stop_rgba(1, *acc, (0.12 + 0.10 * h) * dim)
        rrect(cr, bx, by, bs, bs, 11 if full else 10)
        cr.set_source(ig)
        cr.fill_preserve()
        cr.set_source_rgba(*acc, (0.30 + 0.35 * h) * dim)
        cr.set_line_width(1)
        cr.stroke()
        cr.save()
        cr.translate(bx + bs / 2, cy)
        s = 1.0 if full else 0.88
        cr.scale(s, s)
        ICONS[b.icon](cr, mix(acc, WHITE, 0.30), (0.95 * dim), h, t)
        cr.restore()

        # текст
        tx = bx + bs + (12 if full else 10)
        size = 14 if full else 13
        ty = cy - (18 if full else 16)
        w = put_text(cr, b.title, tx, ty, size, TEXT, 0.97 * (0.55 + 0.45 * dim), bold=True)
        if b.tag:
            put_text(cr, b.tag, tx + w + 8, ty + 3.5, 10, SUBTEXT, 0.45)
        text, rgb, a = self._sub(b, now)
        put_text(cr, text, tx, cy + (3 if full else 2), 10.5 if full else 10, rgb, a * (0.6 + 0.4 * dim))

        # клавиша-подсказка
        if full:
            kx, ky = b.x + b.w - 30, cy - 10
            rrect(cr, kx, ky, 20, 20, 7)
            cr.set_source_rgba(1, 1, 1, 0.05 + 0.06 * h)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.08)
            cr.set_line_width(1)
            cr.stroke()
            put_text(cr, b.key, kx + 10, ky + 3.5, 10.5, SUBTEXT, 0.55 + 0.30 * h, align='c')
        else:
            put_text(cr, b.key, b.x + b.w - 11, b.y + 7, 9.5, SUBTEXT, 0.30 + 0.30 * h, align='r')

        cr.restore()
        if grouped:
            cr.pop_group_to_source()
            cr.paint_with_alpha(e)

    def _draw_border(self, cr):
        rrect(cr, 0.75, 0.75, CARD_W - 1.5, CARD_H - 1.5, CARD_RADIUS - 0.75)
        g = cairo.LinearGradient(0, 0, CARD_W, CARD_H)
        g.add_color_stop_rgba(0.0, *mix(LAVENDER, WHITE, 0.35), 0.95)
        g.add_color_stop_rgba(0.5, *MAUVE, 0.26)
        g.add_color_stop_rgba(1.0, *LAVENDER, 0.72)
        cr.set_source(g)
        cr.set_line_width(1.5)
        cr.stroke()
        rrect(cr, 2.3, 2.3, CARD_W - 4.6, CARD_H - 4.6, CARD_RADIUS - 2.3)
        cr.set_source_rgba(1, 1, 1, 0.05)
        cr.set_line_width(1.0)
        cr.stroke()


# ═════════════════════════════════════════════════════════════
#  ОКНО
# ═════════════════════════════════════════════════════════════
CSS = b'window { background-color: rgba(0,0,0,0); }'


class LauncherPopup(Gtk.Window):

    def __init__(self):
        super().__init__(title='widgetL')
        W, H = CARD_W + 2 * M, CARD_H + 2 * M
        self._y_start = -(H + 26)
        self._y_end = TOP_TARGET - M

        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_resizable(False)
        self.set_default_size(W, H)
        vis = self.get_screen().get_rgba_visual()
        if vis:
            self.set_visual(vis)

        side = GtkLayerShell.Edge.RIGHT if ANCHOR == 'right' else GtkLayerShell.Edge.LEFT
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'widgetL')
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, side, True)
        GtkLayerShell.set_margin(self, side, X_OFFSET - M)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, self._y_start)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        self._margin = self._y_start

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.stats = Stats()
        self.card = Card(self.stats)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(W, H)
        self.canvas.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK |
                               Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.canvas.connect('draw', self._on_draw)
        self.canvas.connect('motion-notify-event', self._on_motion)
        self.canvas.connect('button-press-event', self._on_press)
        self.canvas.connect('button-release-event', self._on_release)
        self.canvas.connect('leave-notify-event', self._on_leave)
        self.add(self.canvas)

        self.connect('key-press-event', self._on_key)
        self.connect('realize', self._on_realize)

        self._open_a = 0.0
        self._t_open = None
        self._t_close = None
        self._last = time.monotonic()
        self._last_draw = 0.0
        self._cursor = None
        self._done = False

        GLib.timeout_add(int(1000 / ANIM_FPS), self._tick)
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self.close_animated)

    # ── служебное ──
    def _on_realize(self, *_):
        try:   # клики только по самой карточке, а не по прозрачной тени
            rg = cairo.Region(cairo.RectangleInt(M, M, CARD_W, CARD_H))
            self.input_shape_combine_region(rg)
        except Exception:
            pass

    def close_animated(self, *_):
        if self._t_close is None:
            self._t_close = time.monotonic()
        return False

    def _shutdown(self):
        if self._done:
            return
        self._done = True
        self.stats.stop()
        Gtk.main_quit()

    # ── действия кнопок ──
    def activate(self, bid):
        c = self.card
        c.pulse(bid)
        if bid == 'wt':
            ok = spawn(WT_CMD, cwd=WT_DIR)
            c.flash(bid, 'запускаю…' if ok else 'не удалось', GREEN if ok else RED)
            if ok:
                GLib.timeout_add(260, self.close_animated)
        elif bid == 'btop':
            ok = spawn(BTOP_CMD)
            c.flash(bid, 'открываю…' if ok else 'не удалось', GREEN if ok else RED)
            if ok:
                GLib.timeout_add(260, self.close_animated)
        elif bid == 'kill_aces':
            self._kill(bid, PROC_WT)
        elif bid == 'kill_discord':
            self._kill(bid, PROC_DISCORD)

    def _kill(self, bid, name):
        def work():
            try:
                rc = subprocess.run(['pkill', '-9', '-x', name], timeout=3).returncode
            except Exception:
                rc = 2
            GLib.idle_add(self._after_kill, bid, rc)
        threading.Thread(target=work, daemon=True).start()

    def _after_kill(self, bid, rc):
        if rc == 0:
            self.card.flash(bid, 'завершён ✓', GREEN)
            self.stats.wt = self.stats.wt and bid != 'kill_aces'
            self.stats.discord = self.stats.discord and bid != 'kill_discord'
            if CLOSE_AFTER_KILL:
                GLib.timeout_add(700, self.close_animated)
        elif rc == 1:
            self.card.flash(bid, 'не запущен', SUBTEXT)
        else:
            self.card.flash(bid, 'ошибка pkill', RED)
        return False

    # ── кадр ──
    def _tick(self):
        now = time.monotonic()
        dt = min(now - self._last, 0.05)
        self._last = now

        busy_win = True
        if self._t_close is not None:
            q = clamp((now - self._t_close) / CLOSE_DUR)
            y = lerp(self._y_end, self._y_start, ease_in_cubic(q))
            self._open_a = 1.0 - q
            if q >= 1.0:
                self._shutdown()
                return False
        elif self._t_open is None:
            y = self._y_start
            self._open_a = 0.0
            if self.get_mapped():
                self._t_open = now
                self.card.start_open(now)
        else:
            p = clamp((now - self._t_open) / OPEN_DUR)
            y = lerp(self._y_start, self._y_end, ease_out_back(p))
            self._open_a = clamp(p * 3.0)
            busy_win = p < 1.0
        iy = int(round(y))
        if iy != self._margin:
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, iy)
            self._margin = iy

        self.card.update(dt, now)
        if busy_win or self.card.busy(now) or now - self._last_draw > 1.0 / IDLE_FPS:
            self._last_draw = now
            self.canvas.queue_draw()
        return True

    def _on_draw(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        a = self._open_a
        if a <= 0.001:
            return False
        grouped = a < 0.999
        if grouped:
            cr.push_group()
        cr.save()
        cr.translate(M, M)
        self.card.draw(cr, time.monotonic())
        cr.restore()
        if grouped:
            cr.pop_group_to_source()
            cr.paint_with_alpha(a)
        return False

    # ── ввод ──
    def _local(self, e):
        return e.x - M, e.y - M

    def _set_cursor(self, over):
        want = 'pointer' if over else None
        if want == self._cursor:
            return
        self._cursor = want
        win = self.canvas.get_window()
        if win:
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), want) if want else None)

    def _on_motion(self, _w, e):
        self._set_cursor(self.card.on_motion(*self._local(e)))
        return True

    def _on_leave(self, *_):
        self.card.on_leave()
        self._set_cursor(None)
        return True

    def _on_press(self, _w, e):
        if e.button == 3:
            self.close_animated()
            return True
        if e.button == 1:
            self.card.on_press(*self._local(e))
        return True

    def _on_release(self, _w, e):
        if e.button == 1:
            bid = self.card.on_release(*self._local(e))
            if bid:
                self.activate(bid)
        return True

    def _on_key(self, _w, e):
        k = e.keyval
        if k in (Gdk.KEY_Escape, Gdk.KEY_q):
            self.close_animated()
        elif k in (Gdk.KEY_1, Gdk.KEY_2, Gdk.KEY_3, Gdk.KEY_4):
            self.activate(self.card.btns[k - Gdk.KEY_1].id)
        elif k in (Gdk.KEY_Down, Gdk.KEY_Right, Gdk.KEY_Tab):
            self.card.focus_move(1)
        elif k in (Gdk.KEY_Up, Gdk.KEY_Left, Gdk.KEY_ISO_Left_Tab):
            self.card.focus_move(-1)
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            bid = self.card.focus_id()
            if bid:
                self.activate(bid)
        return True


# ═════════════════════════════════════════════════════════════
#  ЗАПУСК
# ═════════════════════════════════════════════════════════════
def _pidfile():
    return os.path.join(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir()), 'widgetL.pid')


def toggle_existing():
    """Если окно уже открыто — закрываем его и выходим (удобно для on-click в waybar)."""
    try:
        with open(_pidfile()) as f:
            pid = int(f.read().strip())
        if pid != os.getpid():
            with open(f'/proc/{pid}/cmdline', 'rb') as f:
                cmd = f.read()
            if os.path.basename(__file__).encode() in cmd:
                os.kill(pid, signal.SIGTERM)
                return True
    except (OSError, ValueError):
        pass
    try:
        with open(_pidfile(), 'w') as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    return False


def cleanup_pidfile():
    try:
        with open(_pidfile()) as f:
            if int(f.read().strip()) == os.getpid():
                os.unlink(_pidfile())
    except (OSError, ValueError):
        pass


if __name__ == '__main__':
    if TOGGLE and toggle_existing():
        sys.exit(0)

    win = LauncherPopup()
    win.connect('destroy', lambda *_: Gtk.main_quit())
    win.show_all()
    try:
        Gtk.main()
    finally:
        cleanup_pidfile()
