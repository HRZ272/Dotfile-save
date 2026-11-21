#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
waybar-power — меню питания для waybar (Wayland / gtk-layer-shell)
Тот же стиль, что у widgetL и widgetM: один Cairo-холст, Catppuccin Mocha, aurora-фон, градиентная рамка.

  sudo pacman -S python-gtk-layer-shell python-gobject python-cairo

Кнопки
  1  Заблокировать  ->  hyprlock
  2  Сон            ->  systemctl suspend
  3  Выйти          ->  hyprctl dispatch exit        (с подтверждением)
  4  Рестарт        ->  systemctl reboot             (с подтверждением)
  5  Выключить      ->  systemctl poweroff           (с подтверждением)

Что внутри
  • карточка выезжает сверху с пружинным «перелётом», кнопки появляются каскадом
  • hover / press-пружины, свечение цветом кнопки, анимированные векторные иконки
  • свечение и рамка карточки плавно перекрашиваются в цвет наведённой кнопки
  • подтверждение прямо внутри карточки: панель выезжает поверх опасных кнопок,
    полоска-таймер сама отменяет действие через CONFIRM_TIMEOUT секунд,
    первые 0.35 с кнопки панели не нажимаются (защита от случайного двойного клика)
  • в шапке: user@host и аптайм
  • повторный запуск = закрыть (toggle), Esc / ПКМ — закрыть с анимацией

Клавиши: Esc/q закрыть (в подтверждении — отмена) · 1-5 выбрать · ↑/↓/←/→/Tab фокус
         Enter/Space нажать · в подтверждении: Enter/y выполнить, n отмена
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GtkLayerShell, GLib, Pango, PangoCairo

import cairo
import getpass
import math
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time


# ═════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ═════════════════════════════════════════════════════════════
ANCHOR       = 'right'       # 'left' | 'right' — с какой стороны экрана выезжает меню
X_OFFSET     = 12            # отступ от этого края (подгони под положение кнопки питания в waybar)
TOP_TARGET   = 42            # отступ сверху (под waybar)

CARD_W       = 330
CARD_RADIUS  = 24
CARD_OPACITY = 0.96          # < 1 -> сквозь карточку видно blur композитора
PAD          = 16
M            = 22            # запас вокруг карточки под тень/свечение

FONT         = 'JetBrainsMono Nerd Font'

ANIM_FPS     = 60
OPEN_DUR     = 0.55
CLOSE_DUR    = 0.26
IDLE_FPS     = 20            # частота перерисовки в покое (aurora-фон)

TOGGLE          = True       # повторный запуск закрывает окно
CONFIRM_TIMEOUT = 6.0        # через сколько секунд подтверждение отменяется само
CONFIRM_READY   = 0.35       # сколько секунд кнопки подтверждения «спят» после появления

# Catppuccin Mocha
LAVENDER = (0.706, 0.745, 0.996)   # #b4befe
MAUVE    = (0.796, 0.651, 0.969)   # #cba6f7
BLUE     = (0.537, 0.706, 0.980)   # #89b4fa
TEAL     = (0.580, 0.886, 0.835)   # #94e2d5
PEACH    = (0.980, 0.702, 0.529)   # #fab387
GREEN    = (0.651, 0.890, 0.631)   # #a6e3a1
RED      = (0.953, 0.545, 0.659)   # #f38ba8
TEXT     = (0.804, 0.839, 0.957)   # #cdd6f4
SUBTEXT  = (0.651, 0.678, 0.784)   # #a6adc8
TINT     = (0.130, 0.130, 0.250)
WHITE    = (1.0, 1.0, 1.0)

# ── что делает каждая кнопка (команды меняй здесь) ──
ACTIONS = [
    dict(id='lock', kind='full', icon='lock', acc=BLUE, key='1',
         title='Заблокировать', tag='hyprlock', sub='защитить сеанс паролем',
         cmd=['hyprlock'], now=True, flash='блокирую…', confirm=None),

    dict(id='sleep', kind='full', icon='moon', acc=TEAL, key='2',
         title='Сон', tag='suspend', sub='быстрое пробуждение',
         cmd=['systemctl', 'suspend'], now=False, flash='засыпаю…', confirm=None),

    dict(id='logout', kind='left', icon='logout', acc=PEACH, key='3',
         title='Выйти', tag='', sub='завершить сеанс',
         cmd=['hyprctl', 'dispatch', 'exit', ''], now=False, flash='выхожу…',
         confirm=dict(title='Выйти из сеанса?', sub='Все приложения сеанса закроются',
                      yes='Выйти', busy='Выходим…')),

    dict(id='reboot', kind='right', icon='reboot', acc=MAUVE, key='4',
         title='Рестарт', tag='', sub='перезагрузка',
         cmd=['systemctl', 'reboot'], now=False, flash='перезагружаю…',
         confirm=dict(title='Перезагрузить?', sub='Несохранённые данные пропадут',
                      yes='Рестарт', busy='Перезагрузка…')),

    dict(id='poweroff', kind='full', icon='power', acc=RED, key='5',
         title='Выключить', tag='poweroff', sub='завершить работу',
         cmd=['systemctl', 'poweroff'], now=False, flash='выключаю…',
         confirm=dict(title='Выключить?', sub='Несохранённые данные пропадут',
                      yes='Выключить', busy='Выключаю…')),
]


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
#  СИСТЕМА
# ═════════════════════════════════════════════════════════════
def notify(msg):
    try:
        subprocess.Popen(['notify-send', 'waybar-power', msg, '-i', 'dialog-information'])
    except OSError:
        pass


def spawn(cmd, cwd=None):
    """Запускает команду отдельно от меню (переживёт закрытие виджета)."""
    try:
        subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as e:
        notify(f'Не удалось выполнить {cmd[0]}: {e}')
        return False


def read_uptime():
    try:
        with open('/proc/uptime') as f:
            s = int(float(f.read().split()[0]))
    except (OSError, ValueError, IndexError):
        return ''
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f'{d}д {h}ч'
    if h:
        return f'{h}ч {m:02d}м'
    return f'{m}м'


def whoami():
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get('USER', 'user')
    host = socket.gethostname().split('.')[0]
    return f'{user}@{host}'


# ═════════════════════════════════════════════════════════════
#  ИКОНКИ (рисуются вокруг (0, 0), «размер» ≈ 24 px)
# ═════════════════════════════════════════════════════════════
def _stroke_setup(cr, rgb, alpha, width=2.0):
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(width)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)


def icon_lock(cr, rgb, alpha, hover, t):
    """Замок — на hover дужка приподнимается."""
    hv = clamp(hover)
    lift = 2.8 * hv
    cr.translate(0, -0.6)
    _stroke_setup(cr, rgb, alpha, 2.0)
    cr.new_path()
    cr.move_to(-4.2, -0.5)
    cr.line_to(-4.2, -4.6 - lift)
    cr.arc(0, -4.6 - lift, 4.2, math.pi, 2 * math.pi)
    cr.line_to(4.2, -0.5 - lift)
    cr.stroke()
    cr.set_source_rgba(*rgb, alpha)
    rrect(cr, -6.6, -0.4, 13.2, 10.6, 3.0)
    cr.fill()
    cr.set_source_rgba(0.09, 0.09, 0.15, 0.92 * alpha)     # замочная скважина
    cr.new_sub_path()
    cr.arc(0, 4.0, 1.6, 0, 2 * math.pi)
    cr.fill()
    cr.rectangle(-0.75, 4.2, 1.5, 3.2)
    cr.fill()


def icon_moon(cr, rgb, alpha, hover, t):
    """Месяц со звёздочками — на hover чуть поворачивается, звёзды мерцают."""
    hv = clamp(hover)
    cr.save()
    cr.rotate(-0.25 * hv)
    cr.arc(-0.8, 0.8, 8.6, 0, 2 * math.pi)
    cr.clip()
    cr.rectangle(-14, -14, 28, 28)
    cr.new_sub_path()
    cr.arc(3.4, -2.6, 7.0, 0, 2 * math.pi)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.set_source_rgba(*rgb, alpha)
    cr.fill()
    cr.set_fill_rule(cairo.FILL_RULE_WINDING)
    cr.restore()
    for (sx, sy, ph, r) in ((6.0, -6.4, 0.0, 1.15), (9.4, -1.0, 1.7, 0.85)):
        tw = 0.55 + 0.45 * math.sin(t * 2.4 + ph)
        cr.set_source_rgba(*rgb, alpha * (0.45 + 0.55 * tw))
        cr.new_sub_path()
        cr.arc(sx, sy, r * (1.0 + 0.35 * hv * tw), 0, 2 * math.pi)
        cr.fill()


def icon_logout(cr, rgb, alpha, hover, t):
    """Дверь и стрелка — на hover стрелка выезжает вправо."""
    hv = clamp(hover)
    cr.translate(-0.8, 0)
    _stroke_setup(cr, rgb, alpha, 2.0)
    cr.new_path()
    cr.move_to(-0.5, -8)
    cr.line_to(-6.8, -8)
    cr.line_to(-6.8, 8)
    cr.line_to(-0.5, 8)
    cr.stroke()
    nx = 2.0 * hv
    cr.move_to(-2.8 + nx, 0)
    cr.line_to(8.2 + nx, 0)
    cr.stroke()
    cr.move_to(4.8 + nx, -3.6)
    cr.line_to(8.2 + nx, 0)
    cr.line_to(4.8 + nx, 3.6)
    cr.stroke()


def icon_reboot(cr, rgb, alpha, hover, t):
    """Круговая стрелка — на hover прокручивается."""
    cr.rotate(hover * 0.9)
    _stroke_setup(cr, rgb, alpha, 2.1)
    a0, a1 = math.radians(-35), math.radians(255)
    r = 7.2
    cr.new_path()
    cr.arc(0, 0, r, a0, a1)
    cr.stroke()
    ex, ey = r * math.cos(a1), r * math.sin(a1)
    tx, ty = -math.sin(a1), math.cos(a1)          # касательная по часовой
    nx, ny = -ty, tx
    tip = (ex + tx * 2.6, ey + ty * 2.6)
    bk = (ex - tx * 1.6, ey - ty * 1.6)
    cr.move_to(bk[0] + nx * 3.6, bk[1] + ny * 3.6)
    cr.line_to(*tip)
    cr.line_to(bk[0] - nx * 3.6, bk[1] - ny * 3.6)
    cr.stroke()


def icon_power(cr, rgb, alpha, hover, t):
    """Кнопка питания — на hover слегка «набухает» и подсвечивается."""
    hv = clamp(hover)
    s = 1.0 + 0.10 * hv
    cr.scale(s, s)
    if hv > 0.02:
        rg = cairo.RadialGradient(0, 0, 3, 0, 0, 12)
        rg.add_color_stop_rgba(0, *rgb, 0.0)
        rg.add_color_stop_rgba(0.7, *rgb, 0.16 * hv * alpha)
        rg.add_color_stop_rgba(1, *rgb, 0.0)
        cr.set_source(rg)
        cr.new_sub_path()
        cr.arc(0, 0, 12, 0, 2 * math.pi)
        cr.fill()
    _stroke_setup(cr, rgb, alpha, 2.1)
    cr.new_path()
    cr.arc(0, 0, 7.4, math.radians(-50), math.radians(230))
    cr.stroke()
    cr.move_to(0, -9.2)
    cr.line_to(0, -1.4)
    cr.stroke()


ICONS = {'lock': icon_lock, 'moon': icon_moon, 'logout': icon_logout,
         'reboot': icon_reboot, 'power': icon_power}


# ═════════════════════════════════════════════════════════════
#  РАСКЛАДКА
# ═════════════════════════════════════════════════════════════
ROW_H   = 52
GAP     = 8
Y1      = 66
Y2      = Y1 + ROW_H + GAP
Y3      = Y2 + ROW_H + GAP + 26          # + место под подпись секции
Y4      = Y3 + ROW_H + GAP
CARD_H  = Y4 + ROW_H + PAD
FULL_W  = CARD_W - 2 * PAD
HALF_W  = (FULL_W - 3) / 2               # двойная кнопка: две половинки, зазор 3px
R_OUT, R_IN = 16, 6

# панель подтверждения закрывает секцию «опасных» кнопок
PX, PY, PW = PAD, Y3 - 26, FULL_W
PH = (Y4 + ROW_H) - PY
CB_H = 44
CB_W = (PW - 28 - 6) / 2
CB_Y = PY + PH - 14 - CB_H

POS = {
    'lock':     (PAD,                 Y1, FULL_W),
    'sleep':    (PAD,                 Y2, FULL_W),
    'logout':   (PAD,                 Y3, HALF_W),
    'reboot':   (PAD + HALF_W + 3,    Y3, HALF_W),
    'poweroff': (PAD,                 Y4, FULL_W),
}


class Btn:
    def __init__(self, bid, kind, x, y, w, h, acc, icon='', title='', key='', tag='', sub='', act=None):
        self.id, self.kind = bid, kind          # kind: full | left | right | cl | cr
        self.x, self.y, self.w, self.h = x, y, w, h
        self.acc, self.icon, self.title, self.key, self.tag, self.sub = acc, icon, title, key, tag, sub
        self.act = act
        self.hover = Spring(0.0, 230.0, 22.0)
        self.press = Spring(0.0, 320.0, 26.0)
        self.enter = 0.0                        # каскадное появление 0..1
        self.flash = None                       # (до какого времени, текст, цвет)

    @property
    def radii(self):                            # tl, tr, br, bl
        return {
            'left':  (R_OUT, R_IN, R_IN, R_OUT),
            'right': (R_IN, R_OUT, R_OUT, R_IN),
            'cl':    (14, 6, 6, 14),
            'cr':    (6, 14, 14, 6),
        }.get(self.kind, (R_OUT, R_OUT, R_OUT, R_OUT))


# ═════════════════════════════════════════════════════════════
#  КАРТОЧКА (вся отрисовка + логика наведения)
# ═════════════════════════════════════════════════════════════
class Card:
    def __init__(self):
        self.t0 = time.monotonic()
        self.t_open = None
        self.btns = []
        for a in ACTIONS:
            x, y, w = POS[a['id']]
            self.btns.append(Btn(a['id'], a['kind'], x, y, w, ROW_H, a['acc'], a['icon'],
                                 a['title'], a['key'], a['tag'], a['sub'], a))
        self.cancel = Btn('cancel', 'cl', PX + 14, CB_Y, CB_W, CB_H, SUBTEXT,
                          title='Отмена', key='esc')
        self.yes = Btn('yes', 'cr', PX + 14 + CB_W + 6, CB_Y, CB_W, CB_H, RED,
                       title='Выполнить', key='enter')
        self.cbtns = [self.cancel, self.yes]
        self.by_id = {b.id: b for b in self.btns + self.cbtns}

        self.hov = None
        self.foc = None                          # id кнопки с клавиатурным фокусом
        self.pressed = None

        self.mode = None                         # id действия в подтверждении
        self.cur = None                          # последнее подтверждаемое (для анимации закрытия)
        self.conf = Spring(0.0, 210.0, 24.0)
        self.conf_t0 = 0.0
        self.conf_ready = 0.0
        self.executing = False

        self.glow = LAVENDER
        self.glow_k = Spring(0.0, 120.0, 17.0)
        self.who = whoami()
        self.uptime = read_uptime()
        self._up_t = 0.0

    # ── логика ──
    def start_open(self, now):
        self.t_open = now

    def interactive(self, now=None):
        now = time.monotonic() if now is None else now
        lst = self.btns[:2]
        if self.executing:
            return lst
        if self.mode:
            if now >= self.conf_ready:
                lst = lst + self.cbtns
        else:
            lst = lst + self.btns[2:]
        return lst

    def open_confirm(self, b, now):
        self.mode = b.id
        self.cur = b
        self.conf_t0 = now
        self.conf_ready = now + CONFIRM_READY
        self.yes.acc = b.acc
        self.yes.title = b.act['confirm']['yes']
        self.foc = None
        self.hov = None

    def close_confirm(self):
        self.mode = None
        self.foc = None
        self.hov = None

    def update(self, dt, now):
        self.conf.t = 1.0 if self.mode else 0.0
        self.conf.update(dt)

        if self.mode and not self.executing and now - self.conf_t0 > CONFIRM_TIMEOUT:
            self.close_confirm()

        focused = self.by_id.get(self.foc) if self.foc else None
        hb = self.hov or focused
        if self.mode and self.cur:
            tgt, kk = self.cur.acc, 1.0
        elif hb is not None:
            tgt, kk = hb.acc, 1.0
        else:
            tgt, kk = LAVENDER, 0.0
        self.glow = mix(self.glow, tgt, min(1.0, dt * 7))
        self.glow_k.t = kk
        self.glow_k.update(dt)

        if now - self._up_t > 1.0:
            self._up_t = now
            self.uptime = read_uptime()

        el = (now - self.t_open) if self.t_open is not None else -1.0
        for i, b in enumerate(self.btns):
            b.enter = clamp((el - 0.10 - i * 0.055) / 0.38)
        for b in self.btns + self.cbtns:
            b.hover.t = 1.0 if (b is self.hov or b is focused) else 0.0
            b.hover.update(dt)
            b.press.update(dt)
            if b.flash and now >= b.flash[0]:
                b.flash = None

    def busy(self, now):
        if self.mode or not self.conf.settled or not self.glow_k.settled:
            return True
        for b in self.btns + self.cbtns:
            if b.enter < 1.0 or not b.hover.settled or not b.press.settled or b.flash:
                return True
        return False

    def flash(self, bid, text, rgb, secs=1.4):
        self.by_id[bid].flash = (time.monotonic() + secs, text, rgb)

    def hit(self, x, y):
        for b in self.interactive():
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
        lst = [b.id for b in self.interactive()]
        if not lst:
            return
        if self.foc in lst:
            self.foc = lst[(lst.index(self.foc) + d) % len(lst)]
        else:
            self.foc = lst[0] if d > 0 else lst[-1]

    def pulse(self, bid):
        b = self.by_id[bid]
        b.press.x = 0.9                   # короткий «клик» пружиной
        b.press.t = 0.0

    # ── отрисовка ──
    def draw(self, cr, now):
        t = now - self.t0
        g = self.glow
        soft_shadow(cr, 0, 5, CARD_W, CARD_H, CARD_RADIUS, (0, 0, 0), 0.50, 15, 9)
        soft_shadow(cr, 0, 0, CARD_W, CARD_H, CARD_RADIUS, g, 0.15 + 0.12 * clamp(self.glow_k.x), 13, 8)

        cr.save()
        rrect(cr, 0, 0, CARD_W, CARD_H, CARD_RADIUS)
        cr.clip()
        self._draw_bg(cr, t)
        self._draw_header(cr, t)

        c = clamp(self.conf.x)
        for b in self.btns[:2]:
            self._draw_btn(cr, b, now, t)
        self._draw_section(cr, 1.0 - c)
        if c < 0.99:
            for b in self.btns[2:]:
                self._draw_btn(cr, b, now, t, fade=1.0 - c)
        self._draw_confirm(cr, now, t)
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
            # блоб цвета наведённой кнопки — фон «подсвечивается» вслед за курсором
            (CARD_W * (0.50 + 0.30 * math.sin(t * 0.20 + 0.7)), CARD_H * (0.72 + 0.10 * math.cos(t * 0.24)),       190, self.glow, 0.05 + 0.13 * clamp(self.glow_k.x)),
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
        # плитка-логотип с иконкой питания
        s = 34
        x0, y0 = PAD, 14
        g = cairo.LinearGradient(x0, y0, x0 + s, y0 + s)
        g.add_color_stop_rgba(0, *mix(LAVENDER, WHITE, 0.25), 1)
        g.add_color_stop_rgba(1, *MAUVE, 1)
        rrect(cr, x0, y0, s, s, 11)
        cr.set_source(g)
        cr.fill()
        cr.save()
        cr.translate(x0 + s / 2, y0 + s / 2)
        cr.scale(0.82, 0.82)
        icon_power(cr, (0.10, 0.10, 0.18), 0.88, 0.0, t)
        cr.restore()

        put_text(cr, 'Питание', x0 + s + 11, 13, 15, TEXT, 0.97, bold=True)
        sub = self.who if not self.uptime else f'{self.who} · up {self.uptime}'
        if len(sub) > 30:
            sub = sub[:29] + '…'
        put_text(cr, sub, x0 + s + 11, 33, 10, SUBTEXT, 0.55)

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

    def _draw_section(self, cr, fade):
        e = ease_out_cubic(self.by_id['logout'].enter) * fade
        if e <= 0.01:
            return
        y = Y3 - 22
        put_text(cr, 'ЗАВЕРШЕНИЕ РАБОТЫ', PAD + 4, y, 9.5, SUBTEXT, 0.50 * e, bold=True, spacing=1.6)
        put_text(cr, 'подтверждение', CARD_W - PAD - 4, y, 9.5, RED, 0.70 * e, bold=True, align='r')

    # ── кнопка ──
    def _sub(self, b, now, h):
        """Вторая строка кнопки: (текст, цвет, прозрачность)."""
        if b.flash:
            until, text, rgb = b.flash
            return text, rgb, clamp((until - now) / 0.3)
        return b.sub, mix(SUBTEXT, b.acc, 0.55 * clamp(h)), 0.62 + 0.18 * clamp(h)

    def _draw_btn(self, cr, b, now, t, fade=1.0):
        e = ease_out_cubic(b.enter)
        k = e * fade
        if k <= 0.002:
            return
        h, p, acc = clamp(b.hover.x, 0.0, 1.2), b.press.x, b.acc
        full = b.kind == 'full'
        rd = b.radii
        cx, cy = b.x + b.w / 2, b.y + b.h / 2
        focused = (self.foc == b.id)

        grouped = k < 0.999
        if grouped:
            cr.push_group()
        cr.save()
        sc = 1 + 0.010 * h - 0.030 * p
        cr.translate(cx, cy + (1 - e) * 14)
        cr.scale(sc, sc)
        cr.translate(-cx, -cy)

        # свечение + тёмная подложка + градиент цветом кнопки
        if h > 0.02:
            soft_glow_c(cr, b.x, b.y, b.w, b.h, rd, acc, 0.20 * h, 10)
        rrect_c(cr, b.x, b.y, b.w, b.h, *rd)
        cr.set_source_rgba(0, 0, 0, 0.22)
        cr.fill()
        g = cairo.LinearGradient(b.x, 0, b.x + b.w, 0)
        g.add_color_stop_rgba(0.0, *acc, 0.10 + 0.16 * h)
        g.add_color_stop_rgba(0.6, 1, 1, 1, 0.040 + 0.030 * h)
        g.add_color_stop_rgba(1.0, 1, 1, 1, 0.030 + 0.025 * h)
        rrect_c(cr, b.x, b.y, b.w, b.h, *rd)
        cr.set_source(g)
        cr.fill()

        # рамка (+ кольцо фокуса с клавиатуры)
        rrect_c(cr, b.x + 0.5, b.y + 0.5, b.w - 1, b.h - 1, *[max(r - 0.5, 0) for r in rd])
        bc = mix(acc, WHITE, 0.25)
        cr.set_source_rgba(*bc, min(1.0, 0.10 + 0.55 * h + (0.30 if focused else 0.0)))
        cr.set_line_width(1.6 if focused else 1.0)
        cr.stroke()

        # плитка иконки
        bs = 34 if full else 30
        bx = b.x + (10 if full else 9)
        by = cy - bs / 2
        ig = cairo.LinearGradient(bx, by, bx, by + bs)
        ig.add_color_stop_rgba(0, *acc, 0.34 + 0.18 * h)
        ig.add_color_stop_rgba(1, *acc, 0.12 + 0.10 * h)
        rrect(cr, bx, by, bs, bs, 11 if full else 10)
        cr.set_source(ig)
        cr.fill_preserve()
        cr.set_source_rgba(*acc, 0.30 + 0.35 * h)
        cr.set_line_width(1)
        cr.stroke()
        cr.save()
        cr.translate(bx + bs / 2, cy)
        s = 1.0 if full else 0.88
        cr.scale(s, s)
        ICONS[b.icon](cr, mix(acc, WHITE, 0.30), 0.95, h, t)
        cr.restore()

        # текст
        tx = bx + bs + (12 if full else 10)
        size = 14 if full else 13
        ty = cy - (18 if full else 16)
        w = put_text(cr, b.title, tx, ty, size, TEXT, 0.97, bold=True)
        if b.tag:
            put_text(cr, b.tag, tx + w + 8, ty + 3.5, 10, SUBTEXT, 0.45)
        text, rgb, a = self._sub(b, now, h)
        put_text(cr, text, tx, cy + (3 if full else 2), 10.5 if full else 10, rgb, a)

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
            cr.paint_with_alpha(k)

    # ── панель подтверждения ──
    def _draw_confirm(self, cr, now, t):
        c = clamp(self.conf.x)
        b = self.cur
        if c <= 0.01 or b is None:
            return
        acc = b.acc
        cf = b.act['confirm']
        ex = self.executing
        x, y, w, h = PX, PY, PW, PH

        cr.push_group()
        cr.save()
        cr.translate(0, (1 - c) * 12)

        soft_shadow(cr, x, y, w, h, 18, acc, 0.14, 9, 6)
        rrect(cr, x, y, w, h, 18)
        cr.set_source_rgba(0, 0, 0, 0.32)
        cr.fill()
        g = cairo.LinearGradient(x, y, x + w, y + h)
        g.add_color_stop_rgba(0.0, *acc, 0.20)
        g.add_color_stop_rgba(0.6, 1, 1, 1, 0.04)
        g.add_color_stop_rgba(1.0, *acc, 0.07)
        rrect(cr, x, y, w, h, 18)
        cr.set_source(g)
        cr.fill()
        rrect(cr, x + 0.5, y + 0.5, w - 1, h - 1, 17.5)
        cr.set_source_rgba(*mix(acc, WHITE, 0.25), 0.55)
        cr.set_line_width(1.2)
        cr.stroke()

        # плитка с иконкой
        bs = 40
        bx, by = x + 14, y + 14
        ig = cairo.LinearGradient(bx, by, bx, by + bs)
        ig.add_color_stop_rgba(0, *acc, 0.42)
        ig.add_color_stop_rgba(1, *acc, 0.16)
        rrect(cr, bx, by, bs, bs, 13)
        cr.set_source(ig)
        cr.fill_preserve()
        cr.set_source_rgba(*acc, 0.55)
        cr.set_line_width(1)
        cr.stroke()
        cr.save()
        cr.translate(bx + bs / 2, by + bs / 2)
        cr.scale(1.15, 1.15)
        ICONS[b.icon](cr, mix(acc, WHITE, 0.30), 0.97, 0.55 + 0.45 * math.sin(t * 2.6), t)
        cr.restore()

        # заголовок / подпись
        tx = bx + bs + 12
        put_text(cr, cf['busy'] if ex else cf['title'], tx, y + 15, 15, TEXT, 0.98, bold=True)
        put_text(cr, 'выполняю команду…' if ex else cf['sub'], tx, y + 38, 10, SUBTEXT, 0.70)

        # полоска-таймер (при выполнении — бегущий блик)
        lx, ly, lw = x + 14, y + 62, w - 28
        rrect(cr, lx, ly, lw, 3, 1.5)
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.fill()
        bar = mix(acc, WHITE, 0.2)
        if ex:
            seg = lw * 0.35
            left = lx + (lw + seg) * ((t * 1.3) % 1.0) - seg
            cr.save()
            rrect(cr, lx, ly, lw, 3, 1.5)
            cr.clip()
            sg = cairo.LinearGradient(left, 0, left + seg, 0)
            sg.add_color_stop_rgba(0.0, *bar, 0.0)
            sg.add_color_stop_rgba(0.5, *bar, 0.95)
            sg.add_color_stop_rgba(1.0, *bar, 0.0)
            cr.set_source(sg)
            cr.rectangle(left, ly, seg, 3)
            cr.fill()
            cr.restore()
        else:
            frac = clamp(1.0 - (now - self.conf_t0) / CONFIRM_TIMEOUT)
            if frac > 0.0:
                rrect(cr, lx, ly, max(3.0, lw * frac), 3, 1.5)
                cr.set_source_rgba(*bar, 0.85)
                cr.fill()

        # кнопки
        sleepy = 0.35 if ex else (0.55 if now < self.conf_ready else 1.0)
        for cb in self.cbtns:
            self._draw_cbtn(cr, cb, now, sleepy)

        cr.restore()
        cr.pop_group_to_source()
        cr.paint_with_alpha(c)

    def _draw_cbtn(self, cr, b, now, k):
        h, p, acc = clamp(b.hover.x, 0.0, 1.2), b.press.x, b.acc
        yes = b.id == 'yes'
        rd = b.radii
        cx, cy = b.x + b.w / 2, b.y + b.h / 2
        focused = (self.foc == b.id)

        cr.save()
        sc = 1 + 0.010 * h - 0.030 * p
        cr.translate(cx, cy)
        cr.scale(sc, sc)
        cr.translate(-cx, -cy)

        if yes and h > 0.02:
            soft_glow_c(cr, b.x, b.y, b.w, b.h, rd, acc, 0.24 * h * k, 10)
        rrect_c(cr, b.x, b.y, b.w, b.h, *rd)
        cr.set_source_rgba(0, 0, 0, 0.22 * k)
        cr.fill()

        g = cairo.LinearGradient(b.x, b.y, b.x, b.y + b.h)
        if yes:
            g.add_color_stop_rgba(0, *acc, (0.34 + 0.18 * h) * k)
            g.add_color_stop_rgba(1, *acc, (0.16 + 0.10 * h) * k)
        else:
            g.add_color_stop_rgba(0, 1, 1, 1, (0.07 + 0.05 * h) * k)
            g.add_color_stop_rgba(1, 1, 1, 1, (0.03 + 0.03 * h) * k)
        rrect_c(cr, b.x, b.y, b.w, b.h, *rd)
        cr.set_source(g)
        cr.fill()

        rrect_c(cr, b.x + 0.5, b.y + 0.5, b.w - 1, b.h - 1, *[max(r - 0.5, 0) for r in rd])
        if yes:
            cr.set_source_rgba(*mix(acc, WHITE, 0.25), min(1.0, (0.45 + 0.50 * h + (0.30 if focused else 0.0)) * k))
        else:
            cr.set_source_rgba(1, 1, 1, min(1.0, (0.10 + 0.18 * h + (0.30 if focused else 0.0)) * k))
        cr.set_line_width(1.6 if focused else 1.0)
        cr.stroke()

        col = mix(acc, WHITE, 0.78) if yes else TEXT
        put_text(cr, b.title, b.x + 14, cy - 8, 12.5, col, 0.97 * k, bold=True)
        put_text(cr, b.key, b.x + b.w - 11, cy - 5, 9.5, SUBTEXT, (0.35 + 0.30 * h) * k, align='r')
        cr.restore()

    def _draw_border(self, cr):
        rrect(cr, 0.75, 0.75, CARD_W - 1.5, CARD_H - 1.5, CARD_RADIUS - 0.75)
        gk = clamp(self.glow_k.x)
        mid = mix(MAUVE, self.glow, gk)
        g = cairo.LinearGradient(0, 0, CARD_W, CARD_H)
        g.add_color_stop_rgba(0.0, *mix(LAVENDER, WHITE, 0.35), 0.95)
        g.add_color_stop_rgba(0.5, *mid, 0.26 + 0.34 * gk)
        g.add_color_stop_rgba(1.0, *mix(LAVENDER, self.glow, gk), 0.72)
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


class PowerPopup(Gtk.Window):

    def __init__(self):
        super().__init__(title='waybar-power')
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
        GtkLayerShell.set_namespace(self, 'waybar-power')
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

        self.card = Card()

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
        self._pending = None          # команда, которую выполним после закрытия анимации

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
        if self._pending:
            spawn(self._pending)
        Gtk.main_quit()

    # ── действия кнопок ──
    def activate(self, bid):
        c = self.card
        if c.executing:
            return
        now = time.monotonic()

        if bid == 'cancel':
            if c.mode:
                c.pulse('cancel')
                c.close_confirm()
            return
        if bid == 'yes':
            if c.mode and now >= c.conf_ready:
                c.pulse('yes')
                self._execute(c.by_id[c.mode], via_confirm=True)
            return

        b = c.by_id.get(bid)
        if b is None or c.mode == bid:        # повторное нажатие на ту же кнопку игнорируем
            return
        c.pulse(bid)
        if b.act['confirm']:
            c.open_confirm(b, now)
        else:
            self._execute(b, via_confirm=False)

    def _execute(self, b, via_confirm):
        act = b.act
        c = self.card
        if via_confirm:
            c.executing = True
        else:
            c.flash(b.id, act['flash'], GREEN)
        if act['now']:
            spawn(act['cmd'])                 # блокировка — сразу
        else:
            self._pending = act['cmd']        # остальное — после закрытия карточки
        GLib.timeout_add(260, self.close_animated)

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
        c = self.card
        k = e.keyval
        if k in (Gdk.KEY_Escape, Gdk.KEY_q):
            if c.mode and not c.executing:
                self.activate('cancel')
            else:
                self.close_animated()
        elif k in (Gdk.KEY_1, Gdk.KEY_2, Gdk.KEY_3, Gdk.KEY_4, Gdk.KEY_5):
            self.activate(c.btns[k - Gdk.KEY_1].id)
        elif k == Gdk.KEY_y and c.mode:
            self.activate('yes')
        elif k == Gdk.KEY_n and c.mode:
            self.activate('cancel')
        elif k in (Gdk.KEY_Down, Gdk.KEY_Right, Gdk.KEY_Tab):
            c.focus_move(1)
        elif k in (Gdk.KEY_Up, Gdk.KEY_Left, Gdk.KEY_ISO_Left_Tab):
            c.focus_move(-1)
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            if c.foc:
                self.activate(c.foc)
            elif c.mode:
                self.activate('yes')
        return True


# ═════════════════════════════════════════════════════════════
#  ЗАПУСК
# ═════════════════════════════════════════════════════════════
def _pidfile():
    return os.path.join(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir()), 'waybar-power.pid')


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

    win = PowerPopup()
    win.connect('destroy', lambda *_: Gtk.main_quit())
    win.show_all()
    try:
        Gtk.main()
    finally:
        cleanup_pidfile()
