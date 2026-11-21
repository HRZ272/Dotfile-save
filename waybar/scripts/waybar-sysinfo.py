#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
waybar-sysinfo — выдвигающийся системный монитор для waybar (Wayland / gtk-layer-shell)
Тот же стиль, что у widgetL / widgetM: один Cairo-холст, Catppuccin Mocha, aurora-фон, градиентная рамка.

  sudo pacman -S python-gtk-layer-shell python-gobject python-cairo python-psutil
  GPU: NVIDIA — через nvidia-smi, AMD — через /sys (gpu_busy_percent)

Что внутри
  • карточка выезжает сверху с пружинным «перелётом», блоки появляются каскадом
  • CPU и GPU — кольца с засечками, свечением и плавным «доезжанием» значений, температура справа
  • ПАМЯТЬ (RAM + SWAP), ЯДРА (по столбику на поток), ДИСКИ, СЕТЬ (↑/↓ + живой график)
  • hover на блоке — подсветка цветом блока и «оживающие» иконки
  • повторный запуск = закрыть (toggle), Esc / q / ПКМ — закрыть с анимацией

Клавиши: Esc / q — закрыть
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GtkLayerShell, GLib, Pango, PangoCairo

import cairo
import glob
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

try:
    import psutil
except ImportError:
    _msg = 'нужен python-psutil:  sudo pacman -S python-psutil'
    print(_msg, file=sys.stderr)
    try:
        subprocess.Popen(['notify-send', 'waybar-sysinfo', _msg])
    except OSError:
        pass
    sys.exit(1)


# ═════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ═════════════════════════════════════════════════════════════
ANCHOR       = 'right'       # 'left' | 'right' — с какой стороны экрана выезжает окно
X_OFFSET     = 80            # отступ от этого края (подгони под положение иконки в waybar)
TOP_TARGET   = 42            # отступ сверху (под waybar)
NAMESPACE    = 'waybar-sysinfo'   # для layerrule в Hyprland (blur / ignore_alpha)

CARD_W       = 400
CARD_RADIUS  = 24
CARD_OPACITY = 0.96          # < 1 -> сквозь карточку видно blur композитора
PAD          = 16
M            = 22            # запас вокруг карточки под тень/свечение

FONT         = 'JetBrainsMono Nerd Font'

ANIM_FPS     = 60
OPEN_DUR     = 0.55
CLOSE_DUR    = 0.26
IDLE_FPS     = 20            # частота перерисовки в покое (aurora-фон)

TOGGLE       = True          # повторный запуск закрывает окно

# ── какие блоки показывать ──
SHOW_CORES   = True
SHOW_DISKS   = True
SHOW_NET     = True
MAX_DISKS    = 4
NET_HIST     = 60            # сколько секунд истории на графике сети

# ── какие разделы не показывать в «ДИСКИ» ──
DISK_SKIP_PREFIX = ('/boot', '/efi', '/snap', '/var/lib/docker', '/var/lib/containers',
                    '/var/lib/flatpak', '/run')
DISK_SKIP_FS     = {'squashfs', 'overlay', 'tmpfs', 'devtmpfs', 'iso9660', 'efivarfs'}

# Catppuccin Mocha
LAVENDER = (0.706, 0.745, 0.996)   # #b4befe
MAUVE    = (0.796, 0.651, 0.969)   # #cba6f7
BLUE     = (0.537, 0.706, 0.980)   # #89b4fa
SKY      = (0.537, 0.863, 0.922)   # #89dceb
TEAL     = (0.580, 0.886, 0.835)   # #94e2d5
GREEN    = (0.651, 0.890, 0.631)   # #a6e3a1
YELLOW   = (0.976, 0.886, 0.686)   # #f9e2af
PEACH    = (0.980, 0.702, 0.529)   # #fab387
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


def soft_shadow(cr, x, y, w, h, r, rgb, alpha, spread, steps=9):
    """Мягкая тень/свечение из набора расходящихся скруглённых прямоугольников."""
    a = alpha / steps
    for i in range(steps, 0, -1):
        e = spread * i / steps
        rrect(cr, x - e, y - e, w + 2 * e, h + 2 * e, r + e)
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


def text_w(cr, text, size, bold=False, spacing=0.0):
    return make_layout(cr, text, size, bold, spacing).get_pixel_size()[0]


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


# ── цвета по нагрузке / температуре ──
def load_color(p):
    p = clamp(p, 0.0, 100.0)
    if p < 50:
        return mix(GREEN, YELLOW, p / 50)
    if p < 80:
        return mix(YELLOW, PEACH, (p - 50) / 30)
    return mix(PEACH, RED, (p - 80) / 20)


def temp_color(t):
    if t < 60:
        return GREEN
    if t < 80:
        return PEACH
    return RED


# ── форматирование ──
def fmt_bytes(b):
    for unit, div in (('TB', 1024 ** 4), ('GB', 1024 ** 3), ('MB', 1024 ** 2), ('KB', 1024)):
        if b >= div:
            v = b / div
            return f'{v:.1f} {unit}' if v < 100 else f'{v:.0f} {unit}'
    return f'{b:.0f} B'


def fmt_speed(bps):
    if bps < 1024:
        return f'{bps:.0f} B/s'
    if bps < 1024 ** 2:
        return f'{bps / 1024:.0f} KB/s'
    return f'{bps / 1024 ** 2:.1f} MB/s'


def fmt_uptime(sec):
    d, rem = divmod(int(sec), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f'{d} д {h} ч'
    if h:
        return f'{h} ч {m} мин'
    return f'{m} мин'


def plural_threads(n):
    if n % 10 == 1 and n % 100 != 11:
        return f'{n} поток'
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f'{n} потока'
    return f'{n} потоков'


def short_mount(m, limit=20):
    return m if len(m) <= limit else '…' + m[-(limit - 1):]


# ═════════════════════════════════════════════════════════════
#  СИСТЕМА: сбор данных в фоне
# ═════════════════════════════════════════════════════════════
def read_num(path):
    try:
        with open(path) as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return None


def read_cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        return 0.0
    for name in ('coretemp', 'k10temp', 'zenpower', 'cpu_thermal', 'acpitz'):
        ents = temps.get(name)
        if not ents:
            continue
        for e in ents:
            lab = (e.label or '').lower()
            if any(k in lab for k in ('package', 'tctl', 'tdie')):
                return e.current
        return ents[0].current
    return 0.0


class Stats:
    """Живые данные: CPU / RAM / GPU / диски / сеть. Поля обновляются из фонового потока."""

    def __init__(self):
        self.cpu = 0.0
        self.cores = []
        self.freq = 0.0                 # МГц
        self.cpu_temp = 0.0
        self.ram_used = self.ram_total = 0
        self.ram_pct = 0.0
        self.swap_used = self.swap_total = 0
        self.swap_pct = 0.0
        self.gpu_pct = -1.0             # < 0 — данных нет
        self.gpu_mem_used = self.gpu_mem_total = -1   # байты
        self.gpu_temp = -1.0
        self.disks = []
        self.net_up = self.net_dn = 0.0
        self.net_hist = []              # [(up, dn), ...] — список заменяется целиком
        self.uptime = 0

        self._gpu_be = None
        self._net_prev = None
        self._boot = psutil.boot_time()
        self._stop = threading.Event()

        # прогрев + первичные данные (нужны, чтобы рассчитать высоту карточки)
        psutil.cpu_percent(None)
        self.cores = [0.0] * len(psutil.cpu_percent(None, percpu=True))
        self._read_ram()
        self._read_disks()
        self._read_time()
        threading.Thread(target=self._loop, daemon=True).start()

    # ── CPU / RAM / время ──
    def _read_cpu(self):
        self.cpu = psutil.cpu_percent(None)
        self.cores = psutil.cpu_percent(None, percpu=True)
        f = psutil.cpu_freq()
        self.freq = f.current if f else 0.0
        self.cpu_temp = read_cpu_temp()

    def _read_ram(self):
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        self.ram_used, self.ram_total, self.ram_pct = vm.used, vm.total, vm.percent
        self.swap_used, self.swap_total, self.swap_pct = sw.used, sw.total, sw.percent

    def _read_time(self):
        self.uptime = int(time.time() - self._boot)

    # ── GPU ──
    def _detect_gpu(self):
        if shutil.which('nvidia-smi'):
            try:
                r = subprocess.run(['nvidia-smi', '-L'], capture_output=True, timeout=3)
                if r.returncode == 0:
                    return 'nvidia'
            except Exception:
                pass
        for p in sorted(glob.glob('/sys/class/drm/card[0-9]*/device/gpu_busy_percent')):
            return os.path.dirname(p)         # AMD: путь к device/
        return 'none'

    def _read_gpu(self):
        if self._gpu_be is None:
            self._gpu_be = self._detect_gpu()
        be = self._gpu_be
        if be == 'nvidia':
            try:
                r = subprocess.run(
                    ['nvidia-smi',
                     '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                     '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=2)
                a = [x.strip() for x in r.stdout.strip().splitlines()[0].split(',')]
                self.gpu_pct = float(a[0])
                self.gpu_mem_used = int(float(a[1])) * 1024 ** 2
                self.gpu_mem_total = int(float(a[2])) * 1024 ** 2
                self.gpu_temp = float(a[3])
            except Exception:
                self.gpu_pct = -1.0
        elif be != 'none':
            busy = read_num(be + '/gpu_busy_percent')
            if busy is None:
                self.gpu_pct = -1.0
                return
            self.gpu_pct = busy
            vu, vt = read_num(be + '/mem_info_vram_used'), read_num(be + '/mem_info_vram_total')
            if vu is not None and vt:
                self.gpu_mem_used, self.gpu_mem_total = int(vu), int(vt)
            for p in glob.glob(be + '/hwmon/hwmon*/temp1_input'):
                v = read_num(p)
                if v is not None:
                    self.gpu_temp = v / 1000.0
                    break

    # ── диски ──
    def _read_disks(self):
        seen = {}
        for p in psutil.disk_partitions(all=False):
            if p.fstype in DISK_SKIP_FS or p.mountpoint.startswith(DISK_SKIP_PREFIX):
                continue
            old = seen.get(p.device)
            if old is None or len(p.mountpoint) < len(old.mountpoint):   # btrfs-сабвольюмы → один раз
                seen[p.device] = p
        out = []
        for p in seen.values():
            try:
                u = psutil.disk_usage(p.mountpoint)
            except OSError:
                continue
            if u.total > 0:
                out.append({'mount': p.mountpoint, 'used': u.used, 'total': u.total, 'pct': u.percent})
        out.sort(key=lambda d: (d['mount'] != '/', -d['total']))
        self.disks = out[:MAX_DISKS]

    # ── сеть ──
    def _read_net(self):
        rx = tx = 0
        for name, c in psutil.net_io_counters(pernic=True).items():
            if name == 'lo' or name.startswith(('veth', 'docker', 'br-', 'virbr')):
                continue
            rx += c.bytes_recv
            tx += c.bytes_sent
        now = time.monotonic()
        if self._net_prev:
            t0, rx0, tx0 = self._net_prev
            dt = now - t0
            if dt > 0:
                self.net_dn = max(0.0, (rx - rx0) / dt)
                self.net_up = max(0.0, (tx - tx0) / dt)
                self.net_hist = (self.net_hist + [(self.net_up, self.net_dn)])[-NET_HIST:]
        self._net_prev = (now, rx, tx)

    def _loop(self):
        steps = [self._read_cpu, self._read_ram, self._read_gpu, self._read_net, self._read_time]
        i, first = 0, True
        while not self._stop.wait(0.4 if first else 1.0):
            first = False
            for fn in steps:
                try:
                    fn()
                except Exception:
                    pass
            if i % 5 == 0:
                try:
                    self._read_disks()
                except Exception:
                    pass
            i += 1

    def stop(self):
        self._stop.set()


# ═════════════════════════════════════════════════════════════
#  ИКОНКИ (рисуются вокруг (0, 0), «размер» ≈ 24 px)
# ═════════════════════════════════════════════════════════════
def icon_chip(cr, rgb, alpha, hover, t):
    """Процессор: корпус, кристалл, ножки. Кристалл на hover «дышит»."""
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(1.8)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    rrect(cr, -6.5, -6.5, 13, 13, 2.8)
    cr.stroke()
    s = 2.7 * (1.0 + 0.18 * clamp(hover) * (0.5 + 0.5 * math.sin(t * 5.0)))
    rrect(cr, -s, -s, 2 * s, 2 * s, 1.0)
    cr.fill()
    for d in (-3.5, 3.5):
        for sg in (-1, 1):
            cr.move_to(d, sg * 7.0)
            cr.line_to(d, sg * 10.4)
            cr.move_to(sg * 7.0, d)
            cr.line_to(sg * 10.4, d)
    cr.stroke()


def icon_gpu(cr, rgb, alpha, hover, t):
    """Видеокарта: плата, кулер (крутится быстрее на hover), планка."""
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(1.8)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    rrect(cr, -10.5, -7, 21, 13, 3.2)
    cr.stroke()
    cx, cy = 3.2, -0.5
    cr.set_line_width(1.5)
    cr.new_sub_path()
    cr.arc(cx, cy, 4.2, 0, 2 * math.pi)
    cr.stroke()
    spin = t * (1.6 + 5.0 * clamp(hover))
    for k in range(3):
        a = spin + k * 2 * math.pi / 3
        cr.move_to(cx, cy)
        cr.line_to(cx + math.cos(a) * 3.4, cy + math.sin(a) * 3.4)
    cr.stroke()
    rrect(cr, -8.2, -3.2, 4.2, 5.4, 1.0)
    cr.fill()
    cr.set_line_width(1.8)
    cr.move_to(-8, 9.2)
    cr.line_to(-1.5, 9.2)
    cr.stroke()


def icon_ram(cr, rgb, alpha, hover, t):
    """Планка памяти: чипы мигают по очереди."""
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(1.8)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    rrect(cr, -10.5, -6, 21, 11, 2.4)
    cr.stroke()
    for i in range(4):
        a = alpha * (0.62 + 0.38 * (0.5 + 0.5 * math.sin(t * 3.0 + i * 1.3)) * (0.4 + 0.6 * clamp(hover)))
        cr.set_source_rgba(*rgb, a)
        rrect(cr, -7.8 + i * 4.7, -3.1, 3.2, 5.2, 0.9)
        cr.fill()
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(1.6)
    for i in range(5):
        cr.move_to(-8.4 + i * 4.2, 5.6)
        cr.line_to(-8.4 + i * 4.2, 8.8)
    cr.stroke()


def icon_cores(cr, rgb, alpha, hover, t):
    """Сетка ядер 3×2 с бегущей подсветкой."""
    for r in range(2):
        for c in range(3):
            i = r * 3 + c
            wave = 0.5 + 0.5 * math.sin(t * 2.4 + i * 1.1)
            a = alpha * (0.55 + 0.45 * wave * (0.35 + 0.65 * clamp(hover)))
            cr.set_source_rgba(*rgb, a)
            rrect(cr, -10 + c * 7.0, -7.2 + r * 7.2, 6, 6, 1.6)
            cr.fill()


def icon_disk(cr, rgb, alpha, hover, t):
    """Накопитель: корпус, разделитель, светодиод (мигает на hover)."""
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(1.8)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    rrect(cr, -10.5, -7.5, 21, 15, 3.6)
    cr.stroke()
    cr.set_line_width(1.4)
    cr.move_to(-10.5, 2.0)
    cr.line_to(10.5, 2.0)
    cr.stroke()
    led = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * 7.0)) * clamp(hover)
    cr.set_source_rgba(*rgb, alpha * led)
    cr.new_sub_path()
    cr.arc(6.4, 5.4, 1.25, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(1.6)
    cr.move_to(-7, 5.4)
    cr.line_to(-2.5, 5.4)
    cr.stroke()


def icon_net(cr, rgb, alpha, hover, t):
    """Две стрелки ↑↓, на hover плавно «ездят»."""
    off = 1.6 * math.sin(t * 2.6) * (0.35 + 0.65 * clamp(hover))
    cr.set_source_rgba(*rgb, alpha)
    cr.set_line_width(1.9)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.save()
    cr.translate(0, -off)
    cr.move_to(-4.6, 6.4)
    cr.line_to(-4.6, -6.4)
    cr.move_to(-8.2, -2.8)
    cr.line_to(-4.6, -6.4)
    cr.line_to(-1.0, -2.8)
    cr.stroke()
    cr.restore()
    cr.save()
    cr.translate(0, off)
    cr.move_to(4.6, -6.4)
    cr.line_to(4.6, 6.4)
    cr.move_to(1.0, 2.8)
    cr.line_to(4.6, 6.4)
    cr.line_to(8.2, 2.8)
    cr.stroke()
    cr.restore()


ICONS = {'chip': icon_chip, 'gpu': icon_gpu, 'ram': icon_ram,
         'cores': icon_cores, 'disk': icon_disk, 'net': icon_net}


# ═════════════════════════════════════════════════════════════
#  РАСКЛАДКА
# ═════════════════════════════════════════════════════════════
HEAD_H    = 68
GAP       = 9
FULL_W    = CARD_W - 2 * PAD
TILE_HEAD = 36                 # высота шапки блока (иконка + заголовок)
RING_H    = 154
BAR_ROW   = 36                 # строка «подпись + полоска»
CORES_BH  = 44                 # высота столбиков ядер
CORES_H   = TILE_HEAD + CORES_BH + 22
NET_GH    = 34                 # высота графика сети
NET_H     = TILE_HEAD + 24 + NET_GH + 10


class Tile:
    def __init__(self, tid, kind, x, y, w, h, acc, icon, title):
        self.id, self.kind = tid, kind
        self.x, self.y, self.w, self.h = x, y, w, h
        self.acc, self.icon, self.title = acc, icon, title
        self.hover = Spring(0.0, 230.0, 22.0)
        self.enter = 0.0                       # каскадное появление 0..1


def build_layout(st):
    tiles = []
    y = HEAD_H
    half = (FULL_W - GAP) / 2
    tiles.append(Tile('cpu', 'ring', PAD, y, half, RING_H, LAVENDER, 'chip', 'CPU'))
    tiles.append(Tile('gpu', 'ring', PAD + half + GAP, y, half, RING_H, MAUVE, 'gpu', 'GPU'))
    y += RING_H + GAP

    rows = 2 if st.swap_total > 0 else 1
    h = TILE_HEAD + rows * BAR_ROW + 2
    tiles.append(Tile('ram', 'ram', PAD, y, FULL_W, h, TEAL, 'ram', 'ПАМЯТЬ'))
    y += h + GAP

    if SHOW_CORES and st.cores:
        tiles.append(Tile('cores', 'cores', PAD, y, FULL_W, CORES_H, BLUE, 'cores', 'ЯДРА'))
        y += CORES_H + GAP

    if SHOW_DISKS and st.disks:
        h = TILE_HEAD + len(st.disks) * BAR_ROW + 2
        tiles.append(Tile('disks', 'disks', PAD, y, FULL_W, h, PEACH, 'disk', 'ДИСКИ'))
        y += h + GAP

    if SHOW_NET:
        tiles.append(Tile('net', 'net', PAD, y, FULL_W, NET_H, SKY, 'net', 'СЕТЬ'))
        y += NET_H + GAP

    return tiles, int(y - GAP + PAD)


# ═════════════════════════════════════════════════════════════
#  КАРТОЧКА (вся отрисовка + логика наведения)
# ═════════════════════════════════════════════════════════════
class Card:
    def __init__(self, stats):
        self.st = stats
        self.t0 = time.monotonic()
        self.t_open = None
        self.tiles, self.H = build_layout(stats)
        self.by_id = {t.id: t for t in self.tiles}
        self.hov = None

        # сглаженные значения (доезжают плавно)
        self.cpu_s = self.gpu_s = self.ram_s = self.swap_s = 0.0
        self.cores_s = [0.0] * len(stats.cores)
        nd = len(stats.disks) if 'disks' in self.by_id else 0
        self.disk_s = [0.0] * nd
        self.net_scale = 100 * 1024.0
        self.moving = False

    # ── логика ──
    def start_open(self, now):
        self.t_open = now

    def update(self, dt, now):
        st = self.st
        k = min(1.0, dt * 7.0)
        mv = False

        def ease(cur, tgt):
            nonlocal mv
            if abs(tgt - cur) > 0.15:
                mv = True
            return cur + (tgt - cur) * k

        self.cpu_s = ease(self.cpu_s, st.cpu)
        self.gpu_s = ease(self.gpu_s, max(st.gpu_pct, 0.0))
        self.ram_s = ease(self.ram_s, st.ram_pct)
        self.swap_s = ease(self.swap_s, st.swap_pct)
        cores = st.cores
        for i in range(len(self.cores_s)):
            self.cores_s[i] = ease(self.cores_s[i], cores[i] if i < len(cores) else 0.0)
        disks = st.disks
        for i in range(len(self.disk_s)):
            self.disk_s[i] = ease(self.disk_s[i], disks[i]['pct'] if i < len(disks) else 0.0)
        hist = st.net_hist
        if hist:
            want = max(max(u, d) for u, d in hist) * 1.15
            self.net_scale += (max(want, 100 * 1024.0) - self.net_scale) * min(1.0, dt * 4)
        self.moving = mv

        el = (now - self.t_open) if self.t_open is not None else -1.0
        for i, tl in enumerate(self.tiles):
            tl.enter = clamp((el - 0.10 - i * 0.055) / 0.38)
            tl.hover.t = 1.0 if tl is self.hov else 0.0
            tl.hover.update(dt)

    def busy(self, now):
        if self.moving:
            return True
        for tl in self.tiles:
            if tl.enter < 1.0 or not tl.hover.settled:
                return True
        return False

    def on_motion(self, x, y):
        self.hov = None
        for tl in self.tiles:
            if tl.x <= x <= tl.x + tl.w and tl.y <= y <= tl.y + tl.h:
                self.hov = tl
                break

    def on_leave(self):
        self.hov = None

    # ── отрисовка ──
    def draw(self, cr, now):
        t = now - self.t0
        W, H = CARD_W, self.H
        soft_shadow(cr, 0, 5, W, H, CARD_RADIUS, (0, 0, 0), 0.50, 15, 9)
        soft_shadow(cr, 0, 0, W, H, CARD_RADIUS, LAVENDER, 0.15, 13, 8)

        cr.save()
        rrect(cr, 0, 0, W, H, CARD_RADIUS)
        cr.clip()
        self._draw_bg(cr, t)
        self._draw_header(cr, t)
        for tl in self.tiles:
            self._draw_tile(cr, tl, now, t)
        cr.restore()
        self._draw_border(cr)

    def _draw_bg(self, cr, t):
        W, H = CARD_W, self.H
        c0 = mix((0.105, 0.105, 0.155), TINT, 0.42)
        c1 = mix((0.040, 0.040, 0.070), TINT, 0.26)
        g = cairo.LinearGradient(0, 0, W, H)
        g.add_color_stop_rgba(0, *c0, CARD_OPACITY)
        g.add_color_stop_rgba(1, *c1, CARD_OPACITY)
        cr.set_source(g)
        cr.paint()

        sg = cairo.LinearGradient(0, 0, 0, H)
        sg.add_color_stop_rgba(0, 0, 0, 0, 0.10)
        sg.add_color_stop_rgba(1, 0, 0, 0, 0.40)
        cr.set_source(sg)
        cr.paint()

        blobs = (
            (W * (0.14 + 0.14 * math.sin(t * 0.31)),       H * (0.16 + 0.12 * math.cos(t * 0.23)),       250, LAVENDER, 0.22),
            (W * (0.90 + 0.10 * math.cos(t * 0.27 + 1.0)), H * (0.90 + 0.07 * math.sin(t * 0.19)),       280, MAUVE,    0.19),
            (W * (0.60 + 0.20 * math.sin(t * 0.17 + 2.0)), H * (0.50 + 0.30 * math.cos(t * 0.21 + 0.5)), 180, mix(LAVENDER, WHITE, 0.45), 0.06),
            (W * (0.85 + 0.08 * math.sin(t * 0.22)),       H * (0.45 + 0.12 * math.cos(t * 0.26)),       150, PEACH,    0.05),
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
        # плитка-логотип (чип)
        s = 34
        x0, y0 = PAD, 14
        g = cairo.LinearGradient(x0, y0, x0 + s, y0 + s)
        g.add_color_stop_rgba(0, *mix(LAVENDER, WHITE, 0.25), 1)
        g.add_color_stop_rgba(1, *MAUVE, 1)
        rrect(cr, x0, y0, s, s, 11)
        cr.set_source(g)
        cr.fill()
        cx, cy = x0 + s / 2, y0 + s / 2
        cr.set_source_rgba(0.10, 0.10, 0.18, 0.88)
        rrect(cr, cx - 6.5, cy - 6.5, 13, 13, 3.2)
        cr.fill()
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for d in (-3.5, 3.5):
            for sg in (-1, 1):
                cr.move_to(cx + d, cy + sg * 8.2)
                cr.line_to(cx + d, cy + sg * 10.6)
                cr.move_to(cx + sg * 8.2, cy + d)
                cr.line_to(cx + sg * 10.6, cy + d)
        cr.stroke()
        cr.set_source_rgba(*mix(LAVENDER, WHITE, 0.2), 0.95)
        rrect(cr, cx - 2.7, cy - 2.7, 5.4, 5.4, 1.3)
        cr.fill()

        put_text(cr, 'Система', x0 + s + 11, 13, 15, TEXT, 0.97, bold=True)
        put_text(cr, f'waybar · аптайм {fmt_uptime(self.st.uptime)}', x0 + s + 11, 33, 10, SUBTEXT, 0.55)

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

    # ── блок ──
    def _draw_tile(self, cr, tl, now, t):
        e = ease_out_cubic(tl.enter)
        if e <= 0.002:
            return
        h = clamp(tl.hover.x, 0.0, 1.2)
        grouped = e < 0.999
        if grouped:
            cr.push_group()
        cr.save()
        cr.translate(tl.x, tl.y + (1 - e) * 14)

        self._frame(cr, tl, h)
        self._head(cr, tl, h, t)
        getattr(self, '_body_' + tl.kind)(cr, tl, h, now, t)

        cr.restore()
        if grouped:
            cr.pop_group_to_source()
            cr.paint_with_alpha(e)

    def _frame(self, cr, tl, h):
        acc, w, hh = tl.acc, tl.w, tl.h
        if h > 0.02:
            soft_shadow(cr, 0, 0, w, hh, 16, acc, 0.16 * h, 9, 6)
        rrect(cr, 0, 0, w, hh, 16)
        cr.set_source_rgba(0, 0, 0, 0.22)
        cr.fill()
        g = cairo.LinearGradient(0, 0, w, 0)
        g.add_color_stop_rgba(0.0, *acc, 0.08 + 0.10 * h)
        g.add_color_stop_rgba(0.6, 1, 1, 1, 0.035 + 0.030 * h)
        g.add_color_stop_rgba(1.0, 1, 1, 1, 0.025 + 0.020 * h)
        rrect(cr, 0, 0, w, hh, 16)
        cr.set_source(g)
        cr.fill()
        rrect(cr, 0.5, 0.5, w - 1, hh - 1, 15.5)
        cr.set_source_rgba(*mix(acc, WHITE, 0.25), 0.10 + 0.45 * h)
        cr.set_line_width(1.0)
        cr.stroke()

    def _head_right(self, tl):
        st = self.st
        if tl.id == 'cpu' and st.cpu_temp > 0:
            return f'{st.cpu_temp:.0f}°C', temp_color(st.cpu_temp)
        if tl.id == 'gpu' and st.gpu_temp >= 0:
            return f'{st.gpu_temp:.0f}°C', temp_color(st.gpu_temp)
        if tl.id == 'cores':
            return plural_threads(len(st.cores)), SUBTEXT
        return None

    def _head(self, cr, tl, h, t):
        acc = tl.acc
        bs, bx, by = 22, 10, 8
        ig = cairo.LinearGradient(bx, by, bx, by + bs)
        ig.add_color_stop_rgba(0, *acc, 0.34 + 0.18 * h)
        ig.add_color_stop_rgba(1, *acc, 0.12 + 0.10 * h)
        rrect(cr, bx, by, bs, bs, 8)
        cr.set_source(ig)
        cr.fill_preserve()
        cr.set_source_rgba(*acc, 0.30 + 0.35 * h)
        cr.set_line_width(1)
        cr.stroke()
        cr.save()
        cr.translate(bx + bs / 2, by + bs / 2)
        cr.scale(0.72, 0.72)
        ICONS[tl.icon](cr, mix(acc, WHITE, 0.30), 0.95, h, t)
        cr.restore()

        put_text(cr, tl.title, bx + bs + 9, 12, 10.5, TEXT, 0.92, bold=True, spacing=1.2)
        r = self._head_right(tl)
        if r:
            put_text(cr, r[0], tl.w - 12, 11, 11, r[1], 0.95, bold=True, align='r')
        elif tl.id == 'net':
            put_text(cr, 'сек', tl.w - 12, 12, 9.5, SUBTEXT, 0.40, align='r')

    # ── CPU / GPU: кольцо ──
    def _body_ring(self, cr, tl, h, now, t):
        st = self.st
        cx, cy, R, lw = tl.w / 2, 94, 42, 9
        if tl.id == 'cpu':
            ok, pct = True, self.cpu_s
            sub = f'{st.freq / 1000:.2f} GHz' if st.freq else ''
        else:
            ok, pct = st.gpu_pct >= 0, self.gpu_s
            sub = ''
            if ok and st.gpu_mem_total > 0:
                sub = f'{st.gpu_mem_used / 1024 ** 3:.1f}/{st.gpu_mem_total / 1024 ** 3:.0f} GB'
        col = load_color(pct) if ok else mix(SUBTEXT, TINT, 0.4)

        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        # риски
        N = 40
        r0 = R + lw / 2 + 4
        for i in range(N):
            a = -math.pi / 2 + 2 * math.pi * i / N
            major = (i % 5 == 0)
            r1 = r0 + (5 if major else 3)
            if ok and (i + 0.5) / N <= pct / 100:
                cr.set_source_rgba(*col, 0.60)
            else:
                cr.set_source_rgba(1, 1, 1, 0.09)
            cr.set_line_width(1.4 if major else 1.0)
            cr.move_to(cx + math.cos(a) * r0, cy + math.sin(a) * r0)
            cr.line_to(cx + math.cos(a) * r1, cy + math.sin(a) * r1)
            cr.stroke()

        # дорожка
        cr.set_line_width(lw)
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.new_sub_path()
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.stroke()

        # дуга: свечение → основа → блик → точка на конце
        p = clamp(pct / 100.0) if ok else 0.0
        if p > 0.004:
            a0 = -math.pi / 2
            a1 = a0 + 2 * math.pi * p
            for extra, al in ((9, 0.08), (4, 0.12)):
                cr.set_source_rgba(*col, al)
                cr.set_line_width(lw + extra)
                cr.new_sub_path()
                cr.arc(cx, cy, R, a0, a1)
                cr.stroke()
            cr.set_source_rgba(*col, 0.95)
            cr.set_line_width(lw)
            cr.new_sub_path()
            cr.arc(cx, cy, R, a0, a1)
            cr.stroke()
            cr.set_source_rgba(*mix(col, WHITE, 0.55), 0.35)
            cr.set_line_width(lw * 0.32)
            cr.new_sub_path()
            cr.arc(cx, cy, R - lw * 0.17, a0, a1)
            cr.stroke()
            cr.set_source_rgba(1, 1, 1, 0.92)
            cr.new_sub_path()
            cr.arc(cx + R * math.cos(a1), cy + R * math.sin(a1), lw * 0.20, 0, 2 * math.pi)
            cr.fill()

        # значение в центре
        if ok:
            num = f'{pct:.0f}'
            w1 = text_w(cr, num, 26, True)
            w2 = text_w(cr, '%', 12, True)
            x0 = cx - (w1 + w2 + 2) / 2
            put_text(cr, num, x0, cy - 22, 26, TEXT, 0.98, bold=True)
            put_text(cr, '%', x0 + w1 + 2, cy - 13, 12, SUBTEXT, 0.80, bold=True)
            if sub:
                put_text(cr, sub, cx, cy + 12, 9.5, SUBTEXT, 0.70, align='c')
        else:
            put_text(cr, '—', cx, cy - 20, 24, SUBTEXT, 0.50, bold=True, align='c')
            put_text(cr, 'нет данных', cx, cy + 8, 9.5, SUBTEXT, 0.50, align='c')

    # ── полоски ──
    def _bar(self, cr, x, y, w, h, frac, col):
        rrect(cr, x, y, w, h, h / 2)
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.fill()
        fw = max(h, w * clamp(frac)) if frac > 0.004 else 0.0
        if fw > 0:
            soft_shadow(cr, x, y, fw, h, h / 2, col, 0.30, 5, 5)
            g = cairo.LinearGradient(x, 0, x + fw, 0)
            g.add_color_stop_rgba(0, *col, 0.80)
            g.add_color_stop_rgba(1, *mix(col, WHITE, 0.35), 0.98)
            rrect(cr, x, y, fw, h, h / 2)
            cr.set_source(g)
            cr.fill()

    def _bar_row(self, cr, w, y, name, mid, info, pct, col):
        wn = put_text(cr, name, 12, y, 10.5, TEXT, 0.92, bold=True)
        if mid:
            put_text(cr, mid, 12 + wn + 8, y + 0.5, 10, SUBTEXT, 0.65)
        wp = put_text(cr, f'{pct:.0f}%', w - 12, y, 10.5, col, 0.95, bold=True, align='r')
        if info:
            put_text(cr, info, w - 12 - wp - 8, y + 0.5, 10, SUBTEXT, 0.60, align='r')
        self._bar(cr, 12, y + 19, w - 24, 7, pct / 100.0, col)

    def _body_ram(self, cr, tl, h, now, t):
        st = self.st
        y = TILE_HEAD
        self._bar_row(cr, tl.w, y, 'RAM', fmt_bytes(st.ram_used), fmt_bytes(st.ram_total),
                      self.ram_s, load_color(self.ram_s))
        if st.swap_total > 0:
            self._bar_row(cr, tl.w, y + BAR_ROW, 'SWAP', fmt_bytes(st.swap_used),
                          fmt_bytes(st.swap_total), self.swap_s, TEAL)

    def _body_disks(self, cr, tl, h, now, t):
        disks = self.st.disks
        for i in range(min(len(self.disk_s), len(disks))):
            d = disks[i]
            self._bar_row(cr, tl.w, TILE_HEAD + i * BAR_ROW, short_mount(d['mount']), '',
                          f"{fmt_bytes(d['used'])} / {fmt_bytes(d['total'])}",
                          self.disk_s[i], load_color(self.disk_s[i]))

    # ── ядра ──
    def _body_cores(self, cr, tl, h, now, t):
        vals = self.cores_s
        n = len(vals)
        if not n:
            return
        x0, avail = 12, tl.w - 24
        gap = 3 if n <= 24 else 2
        bw = (avail - gap * (n - 1)) / n
        top, BH = TILE_HEAD, CORES_BH
        r = min(bw / 2, 3.5)
        for i, v in enumerate(vals):
            x = x0 + i * (bw + gap)
            rrect(cr, x, top, bw, BH, r)
            cr.set_source_rgba(1, 1, 1, 0.07)
            cr.fill()
            fh = BH * clamp(v / 100.0)
            if fh > 0.5:
                fh = max(fh, 3.0)
                col = load_color(v)
                g = cairo.LinearGradient(0, top + BH - fh, 0, top + BH)
                g.add_color_stop_rgba(0, *mix(col, WHITE, 0.30), 0.98)
                g.add_color_stop_rgba(1, *col, 0.85)
                rrect(cr, x, top + BH - fh, bw, fh, r)
                cr.set_source(g)
                cr.fill()
            if bw >= 11:
                put_text(cr, str(i), x + bw / 2, top + BH + 4, 8, SUBTEXT, 0.55, align='c')

    # ── сеть ──
    def _body_net(self, cr, tl, h, now, t):
        st = self.st
        put_text(cr, '↑ ' + fmt_speed(st.net_up), 12, TILE_HEAD, 12.5, MAUVE, 0.97, bold=True)
        put_text(cr, '↓ ' + fmt_speed(st.net_dn), tl.w - 12, TILE_HEAD, 12.5, TEAL, 0.97,
                 bold=True, align='r')

        gx, gy, gw, gh = 12, TILE_HEAD + 24, tl.w - 24, NET_GH
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.rectangle(gx, gy + gh, gw, 1)
        cr.fill()

        hist = st.net_hist
        n = len(hist)
        if n < 2:
            return
        step = gw / (NET_HIST - 1)
        xf = gx + gw - (n - 1) * step          # свежие значения справа

        def series(idx, col):
            pts = [(xf + i * step, gy + gh - clamp(hist[i][idx] / self.net_scale) * gh)
                   for i in range(n)]
            cr.move_to(pts[0][0], gy + gh)
            for px, py in pts:
                cr.line_to(px, py)
            cr.line_to(pts[-1][0], gy + gh)
            cr.close_path()
            g = cairo.LinearGradient(0, gy, 0, gy + gh)
            g.add_color_stop_rgba(0, *col, 0.28)
            g.add_color_stop_rgba(1, *col, 0.0)
            cr.set_source(g)
            cr.fill()
            cr.move_to(*pts[0])
            for p in pts[1:]:
                cr.line_to(*p)
            cr.set_source_rgba(*col, 0.95)
            cr.set_line_width(1.5)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.stroke()

        series(1, TEAL)
        series(0, MAUVE)

    def _draw_border(self, cr):
        W, H = CARD_W, self.H
        rrect(cr, 0.75, 0.75, W - 1.5, H - 1.5, CARD_RADIUS - 0.75)
        g = cairo.LinearGradient(0, 0, W, H)
        g.add_color_stop_rgba(0.0, *mix(LAVENDER, WHITE, 0.35), 0.95)
        g.add_color_stop_rgba(0.5, *MAUVE, 0.26)
        g.add_color_stop_rgba(1.0, *LAVENDER, 0.72)
        cr.set_source(g)
        cr.set_line_width(1.5)
        cr.stroke()
        rrect(cr, 2.3, 2.3, W - 4.6, H - 4.6, CARD_RADIUS - 2.3)
        cr.set_source_rgba(1, 1, 1, 0.05)
        cr.set_line_width(1.0)
        cr.stroke()


# ═════════════════════════════════════════════════════════════
#  ОКНО
# ═════════════════════════════════════════════════════════════
CSS = b'window { background-color: rgba(0,0,0,0); }'


class SysinfoPopup(Gtk.Window):

    def __init__(self):
        super().__init__(title='waybar-sysinfo')
        self.stats = Stats()
        self.card = Card(self.stats)
        W, H = CARD_W + 2 * M, self.card.H + 2 * M
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
        GtkLayerShell.set_namespace(self, NAMESPACE)
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

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(W, H)
        self.canvas.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK |
                               Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.canvas.connect('draw', self._on_draw)
        self.canvas.connect('motion-notify-event', self._on_motion)
        self.canvas.connect('button-press-event', self._on_press)
        self.canvas.connect('leave-notify-event', self._on_leave)
        self.add(self.canvas)

        self.connect('key-press-event', self._on_key)
        self.connect('realize', self._on_realize)

        self._open_a = 0.0
        self._t_open = None
        self._t_close = None
        self._last = time.monotonic()
        self._last_draw = 0.0
        self._done = False

        GLib.timeout_add(int(1000 / ANIM_FPS), self._tick)
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self.close_animated)

    # ── служебное ──
    def _on_realize(self, *_):
        try:   # клики только по самой карточке, а не по прозрачной тени
            rg = cairo.Region(cairo.RectangleInt(M, M, CARD_W, self.card.H))
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
    def _on_motion(self, _w, e):
        self.card.on_motion(e.x - M, e.y - M)
        return True

    def _on_leave(self, *_):
        self.card.on_leave()
        return True

    def _on_press(self, _w, e):
        if e.button == 3:
            self.close_animated()
        return True

    def _on_key(self, _w, e):
        if e.keyval in (Gdk.KEY_Escape, Gdk.KEY_q):
            self.close_animated()
        return True


# ═════════════════════════════════════════════════════════════
#  ЗАПУСК
# ═════════════════════════════════════════════════════════════
def _pidfile():
    return os.path.join(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir()), 'waybar-sysinfo.pid')


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

    win = SysinfoPopup()
    win.connect('destroy', lambda *_: Gtk.main_quit())
    win.show_all()
    try:
        Gtk.main()
    finally:
        cleanup_pidfile()
