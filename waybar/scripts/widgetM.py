#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
widgetM v2 — музыкальный попап для waybar (Wayland / gtk-layer-shell)

  sudo pacman -S python-gtk-layer-shell python-gobject python-cairo playerctl
  (опционально, для НАСТОЯЩЕГО спектра)   sudo pacman -S cava

Что внутри
  • вся карточка рисуется одним Cairo-холстом -> 60 fps, никаких дёрганий GTK
  • палитра берётся из обложки (акцент, градиенты, свечение) и плавно перетекает
  • размытый «ambient»-фон из обложки + живые aurora-блобы
  • обложка с пружинным «дыханием» (пауза -> уменьшается), кросс-фейд при смене
  • волнистый прогресс-бар (волна гаснет на паузе), перемотка кликом/драгом + тултип
  • векторные иконки, play<->pause морфинг, hover/press-пружины на всех кнопках
  • shuffle / repeat (None -> Playlist -> Track), громкость (клик/драг/колесо)
  • плавная бегущая строка по пикселям с затуханием по краям
  • спектр внизу карточки: cava со ВСЕГО системного звука (монитор вывода), иначе процедурная анимация
  • громкость — потоки Chromium/Yandex через pactl (логика chromium_vol.sh)
  • повторный запуск = закрыть (toggle), Esc / ПКМ — закрыть с анимацией

Клавиши: Esc/q закрыть · Space пауза · ←/→ ±5с · ↑/↓ громкость · n/p трек
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GtkLayerShell, GdkPixbuf, GLib, Pango, PangoCairo

import cairo
import colorsys
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from urllib.parse import unquote, urlparse


# ═════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ═════════════════════════════════════════════════════════════
X_OFFSET     = 80            # отступ слева (как раньше)
TOP_TARGET   = 42            # отступ сверху (под waybar)

CARD_W       = 380
CARD_H       = 240
CARD_RADIUS  = 24
CARD_OPACITY = 0.96          # < 1 -> сквозь карточку видно blur композитора
ART          = 108           # размер обложки
PAD          = 18
M            = 22            # запас вокруг карточки под тень/свечение

FONT         = 'JetBrainsMono Nerd Font'
PLAYER       = ''            # '' = любой; или имя плеера, напр. 'YandexMusic'

ANIM_FPS     = 60
OPEN_DUR     = 0.60
CLOSE_DUR    = 0.28
POLL_S       = 0.6           # как часто опрашивать playerctl

BARS         = 34            # столбиков в спектре
USE_CAVA     = True          # реальный спектр, если установлен cava
SPECTRUM_ALL = True          # спектр со ВСЕГО системного звука (монитор выходного устройства)
SPECTRUM_SENS  = 1000         # фиксированное усиление cava, % (волны низкие -> больше, упираются в потолок -> меньше)
SPECTRUM_CURVE = 0.45        # меньше = сильнее поднимает тихие звуки (1.0 = линейно)
SPECTRUM_MAX_SINKS = 4       # сколько выходных устройств слушать одновременно
PA_VOLUME    = True          # громкость через pactl (как chromium_vol.sh), а не через MPRIS
VOLUME_APPS  = ('chromium', 'yandex')   # потоки каких приложений крутит ползунок громкости
TOGGLE       = True          # повторный запуск закрывает окно
EXIT_IF_NO_PLAYER = True     # как в оригинале: нет плеера -> уведомление и выход

# Catppuccin Mocha — базовая палитра (если у трека нет обложки)
DEFAULT_THEME = {
    'acc':  (0.706, 0.745, 0.996),   # lavender  #b4befe
    'acc2': (0.796, 0.651, 0.969),   # mauve     #cba6f7
    'tint': (0.130, 0.130, 0.250),
}
WHITE = (1.0, 1.0, 1.0)

PA = ['--player', PLAYER] if PLAYER else []


# ═════════════════════════════════════════════════════════════
#  МАТЕМАТИКА / ПРИМИТИВЫ
# ═════════════════════════════════════════════════════════════
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x

def lerp(a, b, t):
    return a + (b - a) * t

def mix(c1, c2, t):
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))

def smoothstep(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)

def ease_out_cubic(t):
    return 1 - (1 - t) ** 3

def ease_in_cubic(t):
    return t ** 3

def ease_out_back(t, s=1.5):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


class Spring:
    """Пружина: даёт живой отклик с лёгким перелётом."""
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


def put_text(cr, text, x, y, size, rgb, alpha=1.0, bold=False, spacing=0.0, align='l'):
    """Рисует строку; align: l / r / c относительно x. Возвращает ширину."""
    lay = make_layout(cr, text, size, bold, spacing)
    w, h = lay.get_pixel_size()
    if align == 'r':
        x -= w
    elif align == 'c':
        x -= w / 2
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, lay)
    return w


def fmt_time(sec):
    sec = max(0, int(sec))
    return f'{sec // 60}:{sec % 60:02d}'


def _run(args, timeout=2.0):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ''
    except Exception:
        return ''


HAVE_PACTL = shutil.which('pactl') is not None


def pa_streams():
    """Потоки звука нужных приложений: [(id, громкость 0..1, mute)].
    None — pactl недоступен/не ответил, [] — подходящих потоков сейчас нет."""
    if not (PA_VOLUME and HAVE_PACTL):
        return None
    out = _run(['pactl', '--format=json', 'list', 'sink-inputs'], timeout=2.5)
    if not out:
        return None
    try:
        items = json.loads(out)
    except ValueError:
        return None
    res = []
    for it in items:
        pr = it.get('properties') or {}
        hay = ' '.join(str(pr.get(k, '')) for k in
                       ('application.name', 'application.process.binary')).lower()
        if not any(a in hay for a in VOLUME_APPS):
            continue
        vols = [c.get('value', 0) for c in (it.get('volume') or {}).values()
                if isinstance(c, dict)]
        if not vols:
            continue
        res.append((it.get('index'), clamp(max(vols) / 65536.0), bool(it.get('mute'))))
    return res


def pa_apply(v, streams):
    """Выставляет громкость v (0..1) всем найденным потокам."""
    pct = '%d%%' % round(clamp(v) * 100)
    for sid, _vol, muted in streams:
        _run(['pactl', 'set-sink-input-volume', str(sid), pct])
        if muted and v > 0.001:
            _run(['pactl', 'set-sink-input-mute', str(sid), '0'])


def default_monitor():
    """Монитор текущего выходного устройства — сюда приходит звук ото всех приложений."""
    if not HAVE_PACTL:
        return ''
    sink = _run(['pactl', 'get-default-sink']).strip()
    return sink + '.monitor' if sink else ''


def all_monitors():
    """Мониторы ВСЕХ выходных устройств: звук любого приложения попадает хотя бы в один из них."""
    if not HAVE_PACTL:
        return []
    out = _run(['pactl', 'list', 'short', 'sinks'])
    mons = []
    for ln in out.splitlines():
        p = ln.split('\t')
        if len(p) >= 2 and p[1]:
            mons.append(p[1] + '.monitor')
    d = default_monitor()
    if d in mons:                                   # устройство по умолчанию — первым
        mons.remove(d)
        mons.insert(0, d)
    return mons


# ═════════════════════════════════════════════════════════════
#  ПАЛИТРА ИЗ ОБЛОЖКИ
# ═════════════════════════════════════════════════════════════
def extract_palette(pb):
    """Берёт самый «сочный» оттенок обложки и строит из него тему."""
    w, h, ch, rs = pb.get_width(), pb.get_height(), pb.get_n_channels(), pb.get_rowstride()
    px = pb.get_pixels()
    bins = [[0.0, 0.0, 0.0, 0.0] for _ in range(12)]    # вес, r, g, b
    for y in range(h):
        for x in range(w):
            i = y * rs + x * ch
            r, g, b = px[i] / 255.0, px[i + 1] / 255.0, px[i + 2] / 255.0
            hh, s, v = colorsys.rgb_to_hsv(r, g, b)
            if v < 0.14:
                continue
            wt = (s ** 1.4) * (0.25 + v)
            if s < 0.14:
                wt *= 0.15
            k = int(hh * 12) % 12
            bins[k][0] += wt
            bins[k][1] += r * wt
            bins[k][2] += g * wt
            bins[k][3] += b * wt
    best = max(bins, key=lambda b: b[0])
    if best[0] < 0.6:                       # почти ч/б обложка
        return dict(DEFAULT_THEME)
    r, g, b = best[1] / best[0], best[2] / best[0], best[3] / best[0]
    hh, s, v = colorsys.rgb_to_hsv(r, g, b)
    acc  = colorsys.hsv_to_rgb(hh, clamp(s, 0.42, 0.88), max(v, 0.90))
    acc2 = colorsys.hsv_to_rgb((hh + 0.085) % 1.0, clamp(s * 0.85, 0.34, 0.80), 1.0)
    tint = colorsys.hsv_to_rgb(hh, 0.62, 0.20)
    return {'acc': acc, 'acc2': acc2, 'tint': tint}


def pixbuf_to_surface(pb):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, pb.get_width(), pb.get_height())
    c = cairo.Context(surf)
    Gdk.cairo_set_source_pixbuf(c, pb, 0, 0)
    c.paint()
    return surf


# ═════════════════════════════════════════════════════════════
#  БЕГУЩАЯ СТРОКА (плавная, по пикселям)
# ═════════════════════════════════════════════════════════════
class TextLine:
    HOLD, SPEED, GAP = 2.2, 38.0, 46.0

    def __init__(self, size, bold=False):
        self.size, self.bold = size, bold
        self.cur = self.prev = ''
        self.t = 1.0
        self.t0 = time.monotonic()

    def set(self, text):
        if text == self.cur:
            return
        self.prev, self.cur = self.cur, text
        self.t = 0.0
        self.t0 = time.monotonic() + 0.4

    def update(self, dt):
        if self.t < 1.0:
            self.t = min(1.0, self.t + dt / 0.42)

    @property
    def moving(self):
        return self.t < 1.0

    def draw(self, cr, x, y, w, rgb, alpha, now):
        """Возвращает True, если строка сейчас прокручивается (нужна анимация)."""
        e = ease_out_cubic(self.t)
        scrolling = False
        cr.save()
        cr.rectangle(x - 3, y - 12, w + 6, self.size * 1.4 + 24)
        cr.clip()
        if self.prev and self.t < 1.0:
            self._paint(cr, self.prev, x, y - 9 * e, w, rgb, alpha * (1 - e), False, now)
        if self.cur:
            scrolling = self._paint(cr, self.cur, x, y + 9 * (1 - e), w, rgb, alpha * e, True, now)
        cr.restore()
        return scrolling or self.t < 1.0

    def _paint(self, cr, text, x, y, w, rgb, alpha, scroll, now):
        lay = make_layout(cr, text, self.size, self.bold)
        tw, _ = lay.get_pixel_size()
        if tw <= w:
            cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)
            cr.move_to(x, y)
            PangoCairo.show_layout(cr, lay)
            return False

        L = tw + self.GAP
        off = 0.0
        if scroll:
            cycle = self.HOLD + L / self.SPEED
            ph = (now - self.t0) % cycle
            if ph > self.HOLD:
                off = (ph - self.HOLD) * self.SPEED
        cr.push_group()
        cr.set_source_rgb(*rgb)
        for dx in (0.0, L):
            cr.move_to(x - off + dx, y)
            PangoCairo.show_layout(cr, lay)
        cr.pop_group_to_source()
        fade = 16.0 / w
        mask = cairo.LinearGradient(x, 0, x + w, 0)
        mask.add_color_stop_rgba(0.0,        0, 0, 0, alpha * min(1.0, off / 10.0))
        mask.add_color_stop_rgba(fade,       0, 0, 0, alpha)
        mask.add_color_stop_rgba(1.0 - fade, 0, 0, 0, alpha)
        mask.add_color_stop_rgba(1.0,        0, 0, 0, 0.0)
        cr.mask(mask)
        return scroll


# ═════════════════════════════════════════════════════════════
#  СПЕКТР (cava или процедурный)
# ═════════════════════════════════════════════════════════════
class Spectrum:
    """Спектр системного звука: по одному cava на каждый выход, столбики = максимум по выходам.
    Усиление фиксированное, без «памяти»: громкое приложение не делает остальные тише."""

    def __init__(self, n):
        self.n = n
        self.live = False
        self.data = [0.0] * n
        self._last = 0.0
        self._fr = {}                        # монитор -> (время, кадр)
        self._procs = {}                     # монитор -> (Popen, время старта, cfg)
        self._bad = {}                       # монитор -> до какого времени не пытаться снова
        self._cnt = 0
        self._lock = threading.Lock()
        self._stop_ev = threading.Event()
        if USE_CAVA and shutil.which('cava'):
            threading.Thread(target=self._manage, daemon=True).start()

    def _config(self, source):
        inp = ('[input]\nmethod = pulse\nsource = %s\n' % source) if source else ''
        return (
            '[general]\nbars = %d\nframerate = 60\nautosens = 0\nsensitivity = %d\n'
            '%s'
            '[smoothing]\nnoise_reduction = 55\n'
            '[output]\nmethod = raw\nraw_target = /dev/stdout\n'
            'data_format = ascii\nascii_max_range = 1000\n'
            'bar_delimiter = 59\nframe_delimiter = 10\n' % (self.n, SPECTRUM_SENS, inp)
        )

    def _wanted(self):
        now = time.monotonic()
        mons = all_monitors()[:SPECTRUM_MAX_SINKS] if SPECTRUM_ALL else []
        alive = [m for m in mons if self._bad.get(m, 0) < now]
        return alive if alive else ['']             # '' = автоопределение источника самой cava

    def _start(self, mon):
        self._cnt += 1
        cfg = os.path.join(tempfile.gettempdir(), 'widgetM-cava-%d-%d.conf' % (os.getpid(), self._cnt))
        try:
            with open(cfg, 'w') as f:
                f.write(self._config(mon))
            proc = subprocess.Popen(['cava', '-p', cfg], stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, bufsize=1)
        except Exception as e:
            print(f'[widgetM] cava: {e}', file=sys.stderr)
            self._bad[mon] = time.monotonic() + 30
            return
        self._procs[mon] = (proc, time.monotonic(), cfg)
        threading.Thread(target=self._reader, args=(mon, proc, cfg), daemon=True).start()

    def _reader(self, mon, proc, cfg):
        t0 = time.monotonic()
        try:
            for line in proc.stdout:
                vals = [int(p) for p in line.strip().split(';') if p.strip().isdigit()]
                if len(vals) >= self.n:
                    self._fr[mon] = (time.monotonic(), vals[:self.n])
                    self._publish()
        except Exception:
            pass
        finally:
            self._fr.pop(mon, None)
            cur = self._procs.get(mon)
            if cur and cur[0] is proc:
                self._procs.pop(mon, None)
            if time.monotonic() - t0 < 3.0 and not self._stop_ev.is_set():
                self._bad[mon] = time.monotonic() + 30      # сразу упала — не молотим в цикле
            try:
                os.unlink(cfg)
            except OSError:
                pass
            self._publish()

    def _publish(self):
        now = time.monotonic()
        with self._lock:
            fr = [v for t, v in list(self._fr.values()) if now - t < 0.6]
            if fr:
                k = SPECTRUM_CURVE
                self.data = [min(1.0, max(col) / 1000.0) ** k for col in zip(*fr)]
                self.live, self._last = True, now
            else:
                self.live = False

    def _manage(self):
        """Держит по одному cava на каждый выход: подхватывает новые устройства, чистит пропавшие."""
        while not self._stop_ev.is_set():
            want = self._wanted()
            for mon in list(self._procs):
                if mon not in want:
                    self._procs[mon][0].terminate()
            now = time.monotonic()
            for mon, (proc, t0, _cfg) in list(self._procs.items()):
                last = self._fr.get(mon, (0,))[0]
                if now - max(t0, last) > 6.0:        # завис без данных — перезапуск
                    proc.terminate()
            for mon in want:
                if mon not in self._procs:
                    self._start(mon)
            self._stop_ev.wait(2.5)

    def target(self, t, playing):
        if self.live and time.monotonic() - self._last < 0.8:
            return self.data              # реальный звук со всех выходов, независимо от плеера
        if not playing:
            return [0.0] * self.n
        out = []
        beat = 0.5 + 0.5 * max(0.0, math.sin(t * math.tau * 1.9)) ** 2
        for i in range(self.n):
            x = i / (self.n - 1)
            env = 0.50 + 0.50 * math.sin(math.pi * (0.10 + 0.78 * x))
            a = math.sin(t * 3.1 + i * 0.90) * 0.5 + 0.5
            b = math.sin(t * 5.3 + i * 1.70 + 1.3) * 0.5 + 0.5
            c = math.sin(t * 1.7 - i * 0.35) * 0.5 + 0.5
            out.append((0.40 * a + 0.35 * b + 0.25 * c) * env * beat)
        return out

    def stop(self):
        self._stop_ev.set()
        for proc, _t0, cfg in list(self._procs.values()):
            try:
                proc.terminate()
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════
#  БЭКЕНД (playerctl)
# ═════════════════════════════════════════════════════════════
class State:
    def __init__(self):
        self.alive = False
        self.status = 'Stopped'
        self.title = self.artist = self.album = self.art_url = self.player = ''
        self.length = 0.0
        self.pos = 0.0
        self.pos_t = time.monotonic()
        self.volume = None          # 0..1 или None, если плеер не умеет
        self.shuffle = None         # True/False/None
        self.loop = None            # 'None' / 'Track' / 'Playlist' / None

    @property
    def playing(self):
        return self.alive and self.status == 'Playing'

    def position(self, now):
        p = self.pos + (now - self.pos_t) if self.playing else self.pos
        return clamp(p, 0.0, self.length) if self.length > 0 else max(0.0, p)


class Backend:
    SEP = '<|>'
    FMT = SEP.join(['{{status}}', '{{title}}', '{{artist}}', '{{album}}', '{{mpris:artUrl}}',
                    '{{mpris:length}}', '{{position}}', '{{volume}}', '{{playerName}}'])

    def __init__(self):
        self.s = State()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._hold_status = self._hold_pos = self._hold_vol = self._hold_misc = 0.0
        # громкость (pactl)
        self._vol_pending = None
        self._vol_timer = False
        self._vol_busy = False
        self._pending_vol = None      # применим, когда у приложения появится поток звука
        self._last_pa_vol = None
        # shuffle / repeat
        self._loc_loop = None         # локальный режим повтора, если плеер игнорирует запись
        self._no_playlist = False     # плеер не умеет режим Playlist
        self._shuffle_dead = False    # плеер не принимает shuffle через MPRIS
        self._notified = False
        self._key = None
        self._skip_until = 0.0        # до этого момента смену трека считаем «ручной»
        self._rep_block = 0.0
        threading.Thread(target=self._loop, daemon=True).start()
        GLib.timeout_add(100, self._repeat_watch)

    # ── опрос ──
    def _loop(self):
        n = 0
        while not self._stop.is_set():
            out = _run(['playerctl', *PA, 'metadata', '--format', self.FMT])
            d = {'alive': False}
            f = out.rstrip('\n').split(self.SEP) if out else []
            if len(f) >= 9:
                def num(x, k=1.0):
                    try:
                        return float(x) / k
                    except ValueError:
                        return None
                d = {
                    'alive': True, 'status': f[0], 'title': f[1], 'artist': f[2], 'album': f[3],
                    'art_url': f[4], 'length': num(f[5], 1e6) or 0.0, 'pos': num(f[6], 1e6) or 0.0,
                    'volume': num(f[7]), 'player': f[8],
                }
                if n % 3 == 0:
                    sh = _run(['playerctl', *PA, 'shuffle']).strip()
                    lp = _run(['playerctl', *PA, 'loop']).strip()
                    d['shuffle'] = {'On': True, 'Off': False}.get(sh)
                    d['loop'] = lp if lp in ('None', 'Track', 'Playlist') else None
                    d['has_misc'] = True
                st = pa_streams()
                d['pa'] = st
                if st and self._pending_vol is not None:      # громкость, выставленную до старта потока
                    v, self._pending_vol = self._pending_vol, None
                    pa_apply(v, st)
            n += 1
            GLib.idle_add(self._apply, d)
            self._wake.wait(POLL_S)
            self._wake.clear()

    def _apply(self, d):
        now = time.monotonic()
        s = self.s
        if not d['alive']:
            s.alive, s.status = False, 'Stopped'
            return False
        s.alive = True
        if now >= self._hold_status:
            s.status = d['status']

        # трек сменился сам (не по кнопке) при «повторе трека» -> возвращаемся назад
        key = (d['title'], d['artist'])
        if (self._key is not None and key != self._key and self._loc_loop == 'Track'
                and s.loop == 'Track' and s.length > 5 and now > self._skip_until
                and now > self._rep_block and s.length - s.position(now) < 4.0):
            self._rep_block = self._skip_until = now + 4.0
            self._cmd('previous')
        self._key = key

        s.title, s.artist, s.album = d['title'], d['artist'], d['album']
        s.art_url, s.length = d['art_url'], d['length']
        name = (d['player'] or '').split('.')[0]
        s.player = name[:1].upper() + name[1:] if name else ''
        if now >= self._hold_pos:
            cur, new = s.position(now), d['pos']
            if s.playing and abs(new - cur) < 0.6:
                new = cur + (new - cur) * 0.35     # мягкая подстройка без рывков
            s.pos, s.pos_t = new, now
        if now >= self._hold_vol:
            pa = d.get('pa')
            if pa:                                  # реальные потоки приложения (pactl)
                s.volume = 0.0 if all(m for _, _, m in pa) else max(v for _, v, _ in pa)
                self._last_pa_vol = s.volume
            elif pa is not None:                    # pactl работает, но потока пока нет (пауза)
                s.volume = self._last_pa_vol if self._last_pa_vol is not None else \
                    (clamp(d['volume']) if d['volume'] is not None else 1.0)
            else:                                   # pactl нет -> громкость плеера по MPRIS
                s.volume = clamp(d['volume']) if d['volume'] is not None else None
        if d.get('has_misc') and now >= self._hold_misc:
            s.shuffle = None if self._shuffle_dead else d['shuffle']
            s.loop = self._loc_loop if self._loc_loop is not None else d['loop']
        return False

    # ── команды ──
    def _cmd(self, *args):
        try:
            subprocess.Popen(['playerctl', *PA, *args], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError:
            pass
        GLib.timeout_add(260, self._kick)

    def _kick(self):
        self._wake.set()
        return False

    def toggle_play(self):
        now = time.monotonic()
        s = self.s
        s.pos, s.pos_t = s.position(now), now
        s.status = 'Paused' if s.playing else 'Playing'
        self._hold_status = now + 0.7
        self._cmd('play-pause')

    def next(self):
        self._skip_until = time.monotonic() + 3.0
        self._cmd('next')

    def prev(self):
        self._skip_until = time.monotonic() + 3.0
        self._cmd('previous')

    def seek(self, sec):
        now = time.monotonic()
        self.s.pos, self.s.pos_t = sec, now
        self._hold_pos = now + 1.0
        self._cmd('position', '%.2f' % sec)

    # ── громкость: потоки приложения через pactl (как chromium_vol.sh) ──
    def set_volume(self, v):
        v = clamp(v)
        self.s.volume = v
        self._last_pa_vol = v
        self._hold_vol = time.monotonic() + 1.2
        self._vol_pending = v
        self._arm_volume()

    def _arm_volume(self):
        if not self._vol_timer:
            self._vol_timer = True
            GLib.timeout_add(70, self._flush_volume)

    def _flush_volume(self):
        self._vol_timer = False
        if self._vol_pending is None:
            return False
        if self._vol_busy:                      # предыдущий вызов ещё идёт — подождём
            self._arm_volume()
            return False
        v, self._vol_pending = self._vol_pending, None
        self._vol_busy = True
        threading.Thread(target=self._vol_worker, args=(v,), daemon=True).start()
        return False

    def _vol_worker(self, v):
        try:
            st = pa_streams()
            if st is None:                      # pactl нет -> громкость плеера по MPRIS
                _run(['playerctl', *PA, 'volume', '%.3f' % v])
            elif not st:                        # потока пока нет -> применим, когда появится
                self._pending_vol = v
            else:
                pa_apply(v, st)
        finally:
            GLib.idle_add(self._vol_done)

    def _vol_done(self):
        self._vol_busy = False
        if self._vol_pending is not None:
            self._arm_volume()
        return False

    # ── shuffle / repeat ──
    def _set_prop(self, prop, want):
        """Ставит свойство плеера, ждёт и проверяет, принял ли он значение."""
        def work():
            _run(['playerctl', *PA, prop, want])
            time.sleep(0.9)
            got = _run(['playerctl', *PA, prop]).strip()
            GLib.idle_add(self._prop_checked, prop, want, got)
        threading.Thread(target=work, daemon=True).start()

    def _prop_checked(self, prop, want, got):
        ok = (got == want)
        if prop == 'loop':
            if ok:
                self._loc_loop = None                      # плеер умеет сам
            elif want == 'Playlist':
                self._no_playlist = True                   # этот режим плеер не принимает
                self._loop_to('Track')
                return False
            else:
                self._loc_loop = want                      # плеер игнорирует -> эмулируем повтор трека
        else:
            if ok:
                self._shuffle_dead = False
            else:
                self._shuffle_dead = True
                self.s.shuffle = None
                if not self._notified:
                    self._notified = True
                    try:
                        subprocess.Popen(['notify-send', 'widgetM',
                                          'Плеер не принимает shuffle через MPRIS — кнопка отключена',
                                          '-i', 'dialog-information'])
                    except OSError:
                        pass
        self._hold_misc = 0.0
        self._wake.set()
        return False

    def toggle_shuffle(self):
        if self._shuffle_dead:
            return
        want = not bool(self.s.shuffle)            # None (не прочитали) -> считаем «выкл»
        self.s.shuffle = want
        self._hold_misc = time.monotonic() + 4.0
        self._set_prop('shuffle', 'On' if want else 'Off')

    def _loop_to(self, nxt):
        self.s.loop = nxt
        self._hold_misc = time.monotonic() + 4.0
        self._set_prop('loop', nxt)

    def cycle_loop(self):
        cur = self.s.loop or 'None'
        emul = self.s.loop is None or self._loc_loop is not None or self._no_playlist
        order = ['None', 'Track'] if emul else ['None', 'Playlist', 'Track']
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else 'Track'
        self._loop_to(nxt)

    def _repeat_watch(self):
        """Эмуляция «повтор трека»: если плеер её игнорирует — перематываем в начало перед концом."""
        s = self.s
        if self._loc_loop == 'Track' and s.loop == 'Track' and s.playing and s.length > 3:
            now = time.monotonic()
            if s.length - s.position(now) < 0.7 and now > self._rep_block:
                self._rep_block = now + 3.0
                s.pos, s.pos_t = 0.0, now
                self._hold_pos = now + 1.2
                self._cmd('position', '0')
        return not self._stop.is_set()

    def stop(self):
        self._stop.set()
        self._wake.set()


# ═════════════════════════════════════════════════════════════
#  СЦЕНА — вся отрисовка и анимации
# ═════════════════════════════════════════════════════════════
TX, TW      = PAD + ART + 18, CARD_W - (PAD + ART + 18) - PAD     # колонка текста
SEEK_X0     = PAD
SEEK_X1     = CARD_W - PAD
SEEK_Y      = 152
CTRL_Y      = 198
VOL_Y       = 116
VOL_X0      = TX + 26
VOL_X1      = CARD_W - PAD - 40

BUTTONS = {                       # имя: (центр x, центр y, радиус)
    'play':    (CARD_W / 2,       CTRL_Y, 25),
    'prev':    (CARD_W / 2 - 62,  CTRL_Y, 20),
    'next':    (CARD_W / 2 + 62,  CTRL_Y, 20),
    'shuffle': (CARD_W / 2 - 116, CTRL_Y, 15),
    'loop':    (CARD_W / 2 + 116, CTRL_Y, 15),
}
INTERACTIVE = ('play', 'prev', 'next', 'shuffle', 'loop', 'seek', 'vol', 'mute', 'dur')


class Scene:
    def __init__(self, backend):
        self.b = backend
        self.th = {k: tuple(v) for k, v in DEFAULT_THEME.items()}
        self.th_tgt = {k: tuple(v) for k, v in DEFAULT_THEME.items()}
        self._th_moving = False

        self.art = self.art_old = None
        self.blur = self.blur_old = None
        self.art_t = 1.0
        self._art_req = None
        self._last_meta = None

        self.l_title  = TextLine(18, True)
        self.l_artist = TextLine(13.5)
        self.l_album  = TextLine(11)

        self.t = 0.0
        self.speed = Spring(0.0, 40, 12)
        self.phase = 0.0
        self.spec = Spectrum(BARS)
        self.bars = [0.0] * BARS
        self.eq = [0.3] * 4

        names = ('play', 'prev', 'next', 'shuffle', 'loop', 'seek', 'vol', 'mute', 'dur')
        self.hv = {n: Spring(0.0, 240, 22) for n in names}
        self.pr = {n: Spring(0.0, 300, 24) for n in names}
        self.bump = {'prev': Spring(0.0, 220, 12), 'next': Spring(0.0, 220, 12)}
        self.sp_art   = Spring(0.9, 150, 14)
        self.sp_wave  = Spring(0.0, 60, 13)
        self.sp_morph = Spring(0.0, 260, 24)
        self.sp_vis   = Spring(0.0, 120, 18)

        self.mx = self.my = None
        self.hover = None
        self.pressed = None
        self.drag = None
        self.drag_pos = 0.0
        self.show_remaining = False
        self._vol_prev = 0.6
        self._need_anim = False

    # ── данные ──────────────────────────────────────────────
    def _on_meta(self, s):
        if not s.alive:
            self.l_title.set('Плеер не запущен')
            self.l_artist.set('')
            self.l_album.set('')
        else:
            self.l_title.set(s.title or 'Неизвестный трек')
            self.l_artist.set(s.artist or 'Неизвестный исполнитель')
            self.l_album.set(s.album)
        if s.art_url != self._art_req:
            self._art_req = s.art_url
            if s.art_url:
                threading.Thread(target=self._fetch_art, args=(s.art_url,), daemon=True).start()
            else:
                self._swap_art(None, None, dict(DEFAULT_THEME))

    def _fetch_art(self, url):
        try:
            if url.startswith('file://'):
                pb = GdkPixbuf.Pixbuf.new_from_file(unquote(urlparse(url).path))
            elif url.startswith(('http://', 'https://')):
                req = urllib.request.Request(url, headers={'User-Agent': 'widgetM/2'})
                with urllib.request.urlopen(req, timeout=5) as r:
                    data = r.read()
                ld = GdkPixbuf.PixbufLoader()
                ld.write(data)
                ld.close()
                pb = ld.get_pixbuf()
            else:
                return
            self.load_art_pixbuf(pb, url)
        except Exception as e:
            print(f'[widgetM] art: {e}', file=sys.stderr)

    def load_art_pixbuf(self, pb, url=None):
        """Готовит обложку, размытый фон и палитру (можно звать из потока)."""
        w, h = pb.get_width(), pb.get_height()
        side = min(w, h)
        pb = pb.new_subpixbuf((w - side) // 2, (h - side) // 2, side, side)
        big = pb.scale_simple(ART * 2, ART * 2, GdkPixbuf.InterpType.BILINEAR)
        pal = extract_palette(pb.scale_simple(24, 24, GdkPixbuf.InterpType.BILINEAR))
        blur = (pb.scale_simple(14, 14, GdkPixbuf.InterpType.HYPER)
                  .scale_simple(84, 53, GdkPixbuf.InterpType.BILINEAR))
        GLib.idle_add(self._set_art, url, big, blur, pal)

    def _set_art(self, url, big, blur, pal):
        if url is not None and url != self._art_req:
            return False                                   # трек уже сменился
        self._swap_art(pixbuf_to_surface(big), pixbuf_to_surface(blur), pal)
        return False

    def _swap_art(self, art, blur, pal):
        self.art_old, self.blur_old = self.art, self.blur
        self.art, self.blur = art, blur
        self.art_t = 0.0
        self.th_tgt = {k: tuple(v) for k, v in pal.items()}

    # ── обновление ──────────────────────────────────────────
    def update(self, dt, now):
        s = self.b.s
        meta = (s.alive, s.title, s.artist, s.album, s.art_url)
        if meta != self._last_meta:
            self._last_meta = meta
            self._on_meta(s)

        playing = s.playing
        for sp in self._springs():
            sp.update(dt)
        self.sp_art.t   = 1.0 if playing else 0.88
        self.sp_wave.t  = 1.0 if playing else 0.0
        self.sp_morph.t = 1.0 if playing else 0.0
        self.sp_vis.t   = 1.0 if playing else 0.0
        self.speed.t    = 1.0 if playing else 0.18
        for n in self.hv:
            self.hv[n].t = 1.0 if (self.hover == n and self.pressed in (None, n)) else 0.0
            self.pr[n].t = 1.0 if self.pressed == n and self.hover == n else 0.0

        self.t += dt * max(0.05, self.speed.x)
        self.phase += dt * 2.6 * self.sp_wave.x
        for tl in (self.l_title, self.l_artist, self.l_album):
            tl.update(dt)
        if self.art_t < 1.0:
            self.art_t = min(1.0, self.art_t + dt / 0.55)

        k = 1 - math.exp(-dt * 5.0)
        dist = 0.0
        for key in self.th:
            self.th[key] = mix(self.th[key], self.th_tgt[key], k)
            dist += sum(abs(a - b) for a, b in zip(self.th[key], self.th_tgt[key]))
        self._th_moving = dist > 0.004

        # спектр
        tgt = self.spec.target(now, playing)
        for i in range(BARS):
            rate = 24.0 if tgt[i] > self.bars[i] else 7.0
            self.bars[i] += (tgt[i] - self.bars[i]) * (1 - math.exp(-dt * rate))
        # мини-эквалайзер в шапке
        for i in range(4):
            target = 0.15 + 0.85 * (0.5 + 0.5 * math.sin(now * (4.2 + i * 1.7) + i * 2.1)) if playing else 0.0
            self.eq[i] += (target - self.eq[i]) * (1 - math.exp(-dt * 12))

    def _springs(self):
        yield from self.hv.values()
        yield from self.pr.values()
        yield from self.bump.values()
        yield self.sp_art
        yield self.sp_wave
        yield self.sp_morph
        yield self.sp_vis
        yield self.speed

    def busy(self):
        s = self.b.s
        if s.playing or self.art_t < 1.0 or self._th_moving or self._need_anim or self.drag:
            return True
        if any(tl.moving for tl in (self.l_title, self.l_artist, self.l_album)):
            return True
        if any(b > 0.004 for b in self.bars):
            return True
        return any(not sp.settled for sp in self._springs())

    def shown_pos(self, now):
        if self.drag == 'seek':
            return self.drag_pos
        return self.b.s.position(now)

    # ── hit-test и ввод (координаты — внутри карточки) ──────
    def hit(self, x, y):
        for name, (cx, cy, r) in BUTTONS.items():
            if (x - cx) ** 2 + (y - cy) ** 2 <= (r + 5) ** 2:
                return name
        if SEEK_X0 - 8 <= x <= SEEK_X1 + 8 and abs(y - SEEK_Y) <= 15:
            return 'seek'
        if VOL_X0 - 8 <= x <= VOL_X1 + 8 and abs(y - VOL_Y) <= 11:
            return 'vol'
        if TX - 4 <= x <= TX + 20 and abs(y - VOL_Y) <= 11:
            return 'mute'
        if x >= CARD_W - PAD - 44 and abs(y - CTRL_Y) <= 12 and x > BUTTONS['loop'][0] + 22:
            return 'dur'
        return None

    def on_motion(self, x, y):
        self.mx, self.my = x, y
        if self.drag:
            self._drag_to(x)
        self.hover = self.hit(x, y)
        if self.hover == 'vol' and self.b.s.volume is None:
            self.hover = None
        return self.hover

    def on_leave(self):
        self.mx = self.my = None
        self.hover = None

    def on_press(self, x, y):
        name = self.hit(x, y)
        if name is None or (name == 'vol' and self.b.s.volume is None):
            return False
        self.pressed = name
        if name in ('seek', 'vol'):
            self.drag = name
            self._drag_to(x)
        return True

    def on_release(self, x, y):
        name, self.pressed = self.pressed, None
        if self.drag == 'seek':
            self.b.seek(self.drag_pos)
        self.drag = None
        if name and name == self.hit(x, y) and name not in ('seek', 'vol'):
            self._activate(name)
        self.hover = self.hit(x, y)

    def _drag_to(self, x):
        p = clamp((x - (SEEK_X0 if self.drag == 'seek' else VOL_X0)) /
                  ((SEEK_X1 - SEEK_X0) if self.drag == 'seek' else (VOL_X1 - VOL_X0)))
        if self.drag == 'seek':
            self.drag_pos = p * self.b.s.length
        else:
            self.b.set_volume(p)

    def _activate(self, name):
        b = self.b
        if name == 'play':
            b.toggle_play()
        elif name in ('prev', 'next'):
            self.bump[name].x = 1.0
            self.bump[name].v = 0.0
            (b.prev if name == 'prev' else b.next)()
        elif name == 'shuffle':
            b.toggle_shuffle()
        elif name == 'loop':
            b.cycle_loop()
        elif name == 'dur':
            self.show_remaining = not self.show_remaining
        elif name == 'mute':
            v = b.s.volume
            if v is not None:
                if v > 0.01:
                    self._vol_prev = v
                    b.set_volume(0.0)
                else:
                    b.set_volume(self._vol_prev)

    def on_scroll(self, steps):
        v = self.b.s.volume
        if v is not None:
            self.b.set_volume(v - steps * 0.04)

    # ═══ ОТРИСОВКА ═══════════════════════════════════════════
    def draw(self, cr, now):
        self._need_anim = False
        acc, acc2, tint = self.th['acc'], self.th['acc2'], self.th['tint']

        glow = 0.35 + 0.65 * clamp(self.sp_vis.x)
        soft_shadow(cr, 0, 5, CARD_W, CARD_H, CARD_RADIUS, (0, 0, 0), 0.50, 15, 9)
        soft_shadow(cr, 0, 0, CARD_W, CARD_H, CARD_RADIUS, acc, 0.17 * glow, 13, 8)

        cr.save()
        rrect(cr, 0, 0, CARD_W, CARD_H, CARD_RADIUS)
        cr.clip()
        self._draw_bg(cr, acc, acc2, tint)
        self._draw_spectrum(cr, acc, acc2)
        self._draw_cover(cr, acc, acc2)
        self._draw_header_and_text(cr, acc, now)
        self._draw_volume(cr, acc, acc2)
        self._draw_seek(cr, now, acc, acc2)
        self._draw_controls(cr, now, acc, acc2)
        cr.restore()
        self._draw_border(cr, acc, acc2)

    # ── фон ──
    def _paint_blur(self, cr, surf, alpha):
        cr.save()
        cr.scale(CARD_W / surf.get_width(), CARD_H / surf.get_height())
        cr.set_source_surface(surf, 0, 0)
        p = cr.get_source()
        p.set_filter(cairo.FILTER_BILINEAR)
        p.set_extend(cairo.EXTEND_PAD)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _draw_bg(self, cr, acc, acc2, tint):
        c0 = mix((0.105, 0.105, 0.155), tint, 0.42)
        c1 = mix((0.040, 0.040, 0.070), tint, 0.26)
        g = cairo.LinearGradient(0, 0, CARD_W, CARD_H)
        g.add_color_stop_rgba(0, *c0, CARD_OPACITY)
        g.add_color_stop_rgba(1, *c1, CARD_OPACITY)
        cr.set_source(g)
        cr.paint()

        e = ease_out_cubic(self.art_t)
        if self.blur_old is not None and e < 1.0:
            self._paint_blur(cr, self.blur_old, 0.42)
        if self.blur is not None:
            self._paint_blur(cr, self.blur, 0.42 * e)

        sg = cairo.LinearGradient(0, 0, 0, CARD_H)
        sg.add_color_stop_rgba(0, 0, 0, 0, 0.14)
        sg.add_color_stop_rgba(1, 0, 0, 0, 0.46)
        cr.set_source(sg)
        cr.paint()

        t = self.t
        blobs = (
            (CARD_W * (0.16 + 0.14 * math.sin(t * 0.31)),       CARD_H * (0.28 + 0.22 * math.cos(t * 0.23)),       220, acc,  0.22),
            (CARD_W * (0.88 + 0.10 * math.cos(t * 0.27 + 1.0)), CARD_H * (0.82 + 0.14 * math.sin(t * 0.19)),       240, acc2, 0.19),
            (CARD_W * (0.55 + 0.20 * math.sin(t * 0.17 + 2.0)), CARD_H * (0.50 + 0.30 * math.cos(t * 0.21 + 0.5)), 150, mix(acc, WHITE, 0.45), 0.07),
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

    def _draw_spectrum(self, cr, acc, acc2):
        n, gap, H = BARS, 3.0, 78.0
        bw = (CARD_W - 20 - gap * (n - 1)) / n
        g = cairo.LinearGradient(0, CARD_H - H, 0, CARD_H)
        g.add_color_stop_rgba(0, *acc2, 0.10)
        g.add_color_stop_rgba(1, *acc, 0.36)
        for i, v in enumerate(self.bars):
            if v < 0.02:
                continue
            h = 2.0 + v * (H - 8)
            rrect(cr, 10 + i * (bw + gap), CARD_H - h, bw, h + 8, bw / 2)
        cr.set_source(g)
        cr.fill()

    # ── обложка ──
    def _draw_cover(self, cr, acc, acc2):
        sc = self.sp_art.x
        cr.save()
        cr.translate(PAD + ART / 2, PAD + ART / 2)
        cr.scale(sc, sc)
        cr.translate(-ART / 2, -ART / 2)

        soft_shadow(cr, 4, 10, ART - 8, ART - 8, 18, acc, 0.40 * clamp(sc * sc), 15, 8)
        soft_shadow(cr, 0, 6, ART, ART, 20, (0, 0, 0), 0.38, 9, 6)

        cr.save()
        rrect(cr, 0, 0, ART, ART, 20)
        cr.clip()
        e = ease_out_cubic(self.art_t)
        painted = False
        if self.art_old is not None and e < 1.0:
            self._paint_art(cr, self.art_old, 1.0)
            painted = True
        if self.art is not None:
            self._paint_art(cr, self.art, e if painted else 1.0)
            painted = True
        if not painted or (self.art is None and e >= 1.0):
            self._draw_placeholder(cr, acc, acc2)
        gl = cairo.LinearGradient(0, 0, ART, ART)
        gl.add_color_stop_rgba(0.0, 1, 1, 1, 0.20)
        gl.add_color_stop_rgba(0.45, 1, 1, 1, 0.0)
        gl.add_color_stop_rgba(1.0, 0, 0, 0, 0.18)
        cr.set_source(gl)
        cr.paint()
        cr.restore()

        rrect(cr, 0.5, 0.5, ART - 1, ART - 1, 19.5)
        cr.set_source_rgba(1, 1, 1, 0.16)
        cr.set_line_width(1.0)
        cr.stroke()
        cr.restore()

    def _paint_art(self, cr, surf, alpha):
        cr.save()
        k = ART / surf.get_width()
        cr.scale(k, k)
        cr.set_source_surface(surf, 0, 0)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _draw_placeholder(self, cr, acc, acc2):
        g = cairo.LinearGradient(0, 0, ART, ART)
        g.add_color_stop_rgb(0, *mix(acc, (0, 0, 0), 0.35))
        g.add_color_stop_rgb(1, *mix(acc2, (0, 0, 0), 0.55))
        cr.set_source(g)
        cr.paint()
        cr.save()
        cr.translate(ART / 2, ART / 2)
        cr.set_source_rgba(1, 1, 1, 0.88)
        cr.save()
        cr.translate(-6, 15)
        cr.scale(1.0, 0.78)
        cr.arc(0, 0, 9.5, 0, math.tau)
        cr.restore()
        cr.fill()
        cr.set_line_width(4.2)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(2.5, 14)
        cr.line_to(2.5, -22)
        cr.curve_to(2.5, -22, 18, -17, 17, -3)
        cr.stroke()
        cr.restore()

    # ── шапка и текст ──
    def _draw_header_and_text(self, cr, acc, now):
        s = self.b.s
        # мини-эквалайзер + подпись
        base = PAD + 12
        for i, h in enumerate(self.eq):
            bh = 2.5 + h * 9.5
            rrect(cr, TX + i * 4.6, base - bh, 2.8, bh, 1.4)
        cr.set_source_rgba(*acc, 0.95)
        cr.fill()
        lab = 'СЕЙЧАС ИГРАЕТ' if s.playing else ('ПАУЗА' if s.alive else 'НЕТ ПЛЕЕРА')
        lw = put_text(cr, lab, TX + 23, PAD - 1, 9.5, acc, 0.95, True, 1.5)
        if s.player:
            pw = make_layout(cr, s.player[:16], 9.5).get_pixel_size()[0]
            if TX + 23 + lw + 14 + pw < CARD_W - PAD:
                put_text(cr, s.player[:16], CARD_W - PAD, PAD - 1, 9.5, WHITE, 0.32, False, 0, 'r')

        sub = mix(acc, WHITE, 0.48)
        mv = False
        mv |= self.l_title.draw(cr, TX, PAD + 17, TW, (0.97, 0.97, 1.0), 1.0, now)
        mv |= self.l_artist.draw(cr, TX, PAD + 47, TW, sub, 0.96, now)
        mv |= self.l_album.draw(cr, TX, PAD + 70, TW, WHITE, 0.42, now)
        if mv:
            self._need_anim = True

    # ── громкость ──
    def _draw_speaker(self, cr, cx, cy, vol, rgb, alpha):
        cr.save()
        cr.translate(cx, cy)
        cr.set_source_rgba(*rgb, alpha)
        cr.move_to(-7, -2.7); cr.line_to(-3.8, -2.7); cr.line_to(0.2, -6.2)
        cr.line_to(0.2, 6.2); cr.line_to(-3.8, 2.7); cr.line_to(-7, 2.7)
        cr.close_path()
        cr.fill()
        cr.set_line_width(1.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if vol < 0.01:
            cr.move_to(3.2, -3.2); cr.line_to(8.2, 3.2)
            cr.move_to(8.2, -3.2); cr.line_to(3.2, 3.2)
            cr.stroke()
        else:
            cr.arc(0.6, 0, 4.0, -0.85, 0.85)
            cr.stroke()
            cr.set_source_rgba(*rgb, alpha * clamp((vol - 0.25) * 4))
            cr.arc(0.6, 0, 7.4, -0.85, 0.85)
            cr.stroke()
        cr.restore()

    def _draw_volume(self, cr, acc, acc2):
        v = self.b.s.volume
        ok = v is not None
        vv = v if ok else 0.0
        hv, hm = self.hv['vol'].x, self.hv['mute'].x
        a = 0.55 + 0.45 * hm if ok else 0.22
        self._draw_speaker(cr, TX + 8, VOL_Y, vv, WHITE, a)

        h = 3.6 + 1.8 * hv
        wtot = VOL_X1 - VOL_X0
        rrect(cr, VOL_X0, VOL_Y - h / 2, wtot, h, h / 2)
        cr.set_source_rgba(1, 1, 1, 0.14 if ok else 0.07)
        cr.fill()
        if ok and vv > 0.003:
            fw = max(h, wtot * vv)
            g = cairo.LinearGradient(VOL_X0, 0, VOL_X1, 0)
            g.add_color_stop_rgb(0, *acc)
            g.add_color_stop_rgb(1, *acc2)
            rrect(cr, VOL_X0, VOL_Y - h / 2, fw, h, h / 2)
            cr.set_source(g)
            cr.fill()
            if hv > 0.02:
                kx = VOL_X0 + wtot * vv
                cr.arc(kx, VOL_Y, 5.2 * hv, 0, math.tau)
                cr.set_source_rgba(1, 1, 1, 0.98)
                cr.fill()
        txt = '%d%%' % round(vv * 100) if ok else '—'
        put_text(cr, txt, CARD_W - PAD, VOL_Y - 7, 10.5, WHITE, 0.55 + 0.25 * hv if ok else 0.25, False, 0, 'r')

    # ── прогресс-бар-волна ──
    def _draw_seek(self, cr, now, acc, acc2):
        s = self.b.s
        x0, x1, cy = SEEK_X0, SEEK_X1, SEEK_Y
        dur = s.length
        pos = self.shown_pos(now)
        p = clamp(pos / dur) if dur > 0 else 0.0
        xp = x0 + (x1 - x0) * p
        hv, pr = self.hv['seek'].x, self.pr['seek'].x
        lw = 4.0 + 1.2 * hv
        gap = 10.0

        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        if x1 > xp + gap:
            cr.set_line_width(lw)
            cr.set_source_rgba(1, 1, 1, 0.17)
            cr.move_to(xp + gap, cy)
            cr.line_to(x1, cy)
            cr.stroke()

        xe = xp - gap * 0.6
        if xe > x0 + 0.5:
            amp = 3.6 * self.sp_wave.x
            k = math.tau / 24.0
            x = x0
            first = True
            while True:
                env = smoothstep((x - x0) / 14.0) * smoothstep((xe - x) / 20.0)
                y = cy + amp * env * math.sin(k * x - self.phase)
                if first:
                    cr.move_to(x, y)
                    first = False
                else:
                    cr.line_to(x, y)
                if x >= xe:
                    break
                x = min(x + 2.0, xe)
            gl = cairo.LinearGradient(x0, 0, x1, 0)
            gl.add_color_stop_rgba(0, *acc, 0.26)
            gl.add_color_stop_rgba(1, *acc2, 0.26)
            cr.set_line_width(lw + 7)
            cr.set_source(gl)
            cr.stroke_preserve()
            g = cairo.LinearGradient(x0, 0, x1, 0)
            g.add_color_stop_rgb(0, *acc)
            g.add_color_stop_rgb(1, *acc2)
            cr.set_line_width(lw)
            cr.set_source(g)
            cr.stroke()

        # ручка-«пилюля»
        kw = 5.0 + 1.6 * hv + 1.0 * pr
        kh = 20.0 + 5.0 * hv
        rg = cairo.RadialGradient(xp, cy, 0, xp, cy, 22)
        rg.add_color_stop_rgba(0, *mix(acc, acc2, p), 0.55)
        rg.add_color_stop_rgba(1, *mix(acc, acc2, p), 0.0)
        cr.set_source(rg)
        cr.arc(xp, cy, 22, 0, math.tau)
        cr.fill()
        rrect(cr, xp - kw / 2, cy - kh / 2, kw, kh, kw / 2)
        cr.set_source_rgb(0.98, 0.98, 1.0)
        cr.fill()

        # тултип со временем под курсором
        if (self.hover == 'seek' or self.drag == 'seek') and self.mx is not None and dur > 0:
            mx = clamp(self.mx, x0, x1)
            tsec = (mx - x0) / (x1 - x0) * dur
            txt = fmt_time(tsec)
            tw = make_layout(cr, txt, 11, True).get_pixel_size()[0]
            bw, bh = tw + 18, 22
            bx = clamp(mx - bw / 2, PAD, CARD_W - PAD - bw)
            by = cy - 40
            soft_shadow(cr, bx, by + 3, bw, bh, 11, (0, 0, 0), 0.35, 6, 4)
            rrect(cr, bx, by, bw, bh, 11)
            cr.set_source_rgba(0.06, 0.06, 0.10, 0.94)
            cr.fill_preserve()
            cr.set_source_rgba(*acc, 0.65)
            cr.set_line_width(1.0)
            cr.stroke()
            put_text(cr, txt, bx + bw / 2, by + 3.5, 11, WHITE, 0.98, True, 0, 'c')
            cr.set_source_rgba(1, 1, 1, 0.30)
            cr.set_line_width(1.2)
            cr.move_to(mx, cy - 9)
            cr.line_to(mx, cy + 9)
            cr.stroke()

    # ── кнопки ──
    def _draw_controls(self, cr, now, acc, acc2):
        s = self.b.s
        pos = self.shown_pos(now)
        # время
        put_text(cr, fmt_time(pos), PAD, CTRL_Y - 8, 12.5, WHITE, 0.82, False)
        if s.length > 0:
            if self.show_remaining:
                right = '-' + fmt_time(max(0.0, s.length - pos))
            else:
                right = fmt_time(s.length)
        else:
            right = '--:--'
        put_text(cr, right, CARD_W - PAD, CTRL_Y - 8, 12.5, WHITE, 0.46 + 0.4 * self.hv['dur'].x, False, 0, 'r')

        ink = (0.075, 0.075, 0.115)

        # prev / next
        for name, direction in (('prev', -1), ('next', 1)):
            cx, cy, r = BUTTONS[name]
            hv, pr = self.hv[name].x, self.pr[name].x
            rr = r * (1 + 0.05 * hv - 0.10 * pr)
            if hv > 0.01:
                cr.arc(cx, cy, rr, 0, math.tau)
                cr.set_source_rgba(1, 1, 1, 0.10 * hv)
                cr.fill()
            self._draw_skip(cr, cx + direction * 5.0 * self.bump[name].x, cy, direction,
                            1.0 + 0.06 * hv - 0.12 * pr, WHITE, 0.78 + 0.22 * hv)

        # shuffle / loop
        for name in ('shuffle', 'loop'):
            cx, cy, r = BUTTONS[name]
            hv, pr = self.hv[name].x, self.pr[name].x
            val = s.shuffle if name == 'shuffle' else s.loop
            supported = val is not None
            active = bool(val) if name == 'shuffle' else (val in ('Track', 'Playlist'))
            col = acc if active else WHITE
            alpha = (0.95 if active else 0.42 + 0.30 * hv) if supported else 0.15
            if hv > 0.01 and supported:
                cr.arc(cx, cy, r * (1 + 0.1 * hv), 0, math.tau)
                cr.set_source_rgba(1, 1, 1, 0.08 * hv)
                cr.fill()
            sc = 1.0 + 0.08 * hv - 0.14 * pr
            if name == 'shuffle':
                self._draw_shuffle(cr, cx, cy, col, alpha, sc)
            else:
                self._draw_loop(cr, cx, cy, val, col, alpha, sc)
            if active:
                cr.arc(cx, cy + 14.5, 1.7, 0, math.tau)
                cr.set_source_rgba(*acc, 0.95)
                cr.fill()

        # play / pause
        cx, cy, r = BUTTONS['play']
        hv, pr = self.hv['play'].x, self.pr['play'].x
        rr = r * (1 + 0.07 * hv - 0.09 * pr)
        gl = cairo.RadialGradient(cx, cy, rr * 0.6, cx, cy, rr * 2.3)
        gl.add_color_stop_rgba(0, *acc, 0.36 + 0.22 * hv + 0.2 * self.sp_vis.x)
        gl.add_color_stop_rgba(1, *acc, 0.0)
        cr.set_source(gl)
        cr.arc(cx, cy, rr * 2.3, 0, math.tau)
        cr.fill()
        g = cairo.LinearGradient(cx - rr, cy - rr, cx + rr, cy + rr)
        g.add_color_stop_rgb(0, *mix(acc, WHITE, 0.18))
        g.add_color_stop_rgb(1, *acc2)
        cr.arc(cx, cy, rr, 0, math.tau)
        cr.set_source(g)
        cr.fill()
        hl = cairo.LinearGradient(0, cy - rr, 0, cy + rr)
        hl.add_color_stop_rgba(0, 1, 1, 1, 0.28)
        hl.add_color_stop_rgba(0.5, 1, 1, 1, 0.0)
        cr.arc(cx, cy, rr, 0, math.tau)
        cr.set_source(hl)
        cr.fill()
        self._draw_playpause(cr, cx, cy, clamp(self.sp_morph.x, -0.05, 1.05), rr / 25.0, ink)

    def _draw_playpause(self, cr, cx, cy, t, scale, rgb):
        L0 = [(-7, -10), (1.5, -5.5), (1.5, 5.5), (-7, 10)]
        L1 = [(-8, -10), (-3, -10), (-3, 10), (-8, 10)]
        R0 = [(1.5, -5.5), (11, 0), (11, 0), (1.5, 5.5)]
        R1 = [(3, -10), (8, -10), (8, 10), (3, 10)]
        cr.save()
        cr.translate(cx - 2.0 * (1 - t) * scale, cy)
        cr.scale(scale, scale)
        cr.set_source_rgb(*rgb)
        for A, B in ((L0, L1), (R0, R1)):
            pts = [(lerp(a[0], b[0], t), lerp(a[1], b[1], t)) for a, b in zip(A, B)]
            cr.move_to(*pts[0])
            for p in pts[1:]:
                cr.line_to(*p)
            cr.close_path()
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_width(2.6)
        cr.fill_preserve()
        cr.stroke()
        cr.restore()

    def _draw_skip(self, cr, cx, cy, direction, scale, rgb, alpha):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(direction * scale, scale)
        cr.set_source_rgba(*rgb, alpha)
        cr.move_to(-8.5, -8)
        cr.line_to(5, 0)
        cr.line_to(-8.5, 8)
        cr.close_path()
        rrect(cr, 6.5, -8, 3, 16, 1.2)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_width(1.8)
        cr.fill_preserve()
        cr.stroke()
        cr.restore()

    def _draw_shuffle(self, cr, cx, cy, rgb, alpha, scale):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(scale, scale)
        cr.set_source_rgba(*rgb, alpha)
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(-8, 4); cr.line_to(-4, 4)
        cr.curve_to(-1, 4, 0, -4, 3, -4); cr.line_to(5, -4)
        cr.stroke()
        cr.move_to(-8, -4); cr.line_to(-4, -4)
        cr.curve_to(-1, -4, 0, 4, 3, 4); cr.line_to(5, 4)
        cr.stroke()
        for sy in (-4, 4):
            cr.move_to(4, sy - 3); cr.line_to(8.2, sy); cr.line_to(4, sy + 3)
            cr.close_path()
            cr.fill()
        cr.restore()

    def _draw_loop(self, cr, cx, cy, mode, rgb, alpha, scale):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(scale, scale)
        cr.set_source_rgba(*rgb, alpha)
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(-7, 1); cr.line_to(-7, -1)
        cr.arc(-4, -1, 3, math.pi, 1.5 * math.pi)
        cr.line_to(3, -4)
        cr.stroke()
        cr.move_to(7, -1); cr.line_to(7, 1)
        cr.arc(4, 1, 3, 0, 0.5 * math.pi)
        cr.line_to(-3, 4)
        cr.stroke()
        cr.move_to(2.6, -7); cr.line_to(7, -4); cr.line_to(2.6, -1); cr.close_path()
        cr.move_to(-2.6, 1); cr.line_to(-7, 4); cr.line_to(-2.6, 7); cr.close_path()
        cr.fill()
        if mode == 'Track':
            lay = make_layout(cr, '1', 7.5, True)
            w, h = lay.get_pixel_size()
            cr.move_to(-w / 2, -h / 2)
            PangoCairo.show_layout(cr, lay)
        cr.restore()

    # ── рамка ──
    def _draw_border(self, cr, acc, acc2):
        rrect(cr, 0.75, 0.75, CARD_W - 1.5, CARD_H - 1.5, CARD_RADIUS - 0.75)
        g = cairo.LinearGradient(0, 0, CARD_W, CARD_H)
        g.add_color_stop_rgba(0.0, *mix(acc, WHITE, 0.35), 0.95)
        g.add_color_stop_rgba(0.5, *acc2, 0.26)
        g.add_color_stop_rgba(1.0, *acc, 0.72)
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


class MusicPopup(Gtk.Window):

    def __init__(self):
        super().__init__(title='widgetM')
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

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'widgetM')
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, X_OFFSET - M)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, self._y_start)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        self._margin = self._y_start

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.backend = Backend()
        self.scene = Scene(self.backend)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(W, H)
        self.canvas.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK |
                               Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK |
                               Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.canvas.connect('draw', self._on_draw)
        self.canvas.connect('motion-notify-event', self._on_motion)
        self.canvas.connect('button-press-event', self._on_press)
        self.canvas.connect('button-release-event', self._on_release)
        self.canvas.connect('leave-notify-event', self._on_leave)
        self.canvas.connect('scroll-event', self._on_scroll)
        self.add(self.canvas)

        self.connect('key-press-event', self._on_key)
        self.connect('realize', self._on_realize)

        self._open_a = 0.0
        self._pop = 0.0
        self._t_open = None
        self._t_close = None
        self._last = time.monotonic()
        self._last_draw = 0.0
        self._cursor = None
        self._scroll_acc = 0.0
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
        self.backend.stop()
        self.scene.spec.stop()
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
        else:
            p = clamp((now - self._t_open) / OPEN_DUR)
            y = lerp(self._y_start, self._y_end, ease_out_back(p))
            self._open_a = clamp(p * 3.0)
            busy_win = p < 1.0
        iy = int(round(y))
        if iy != self._margin:
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, iy)
            self._margin = iy

        self.scene.update(dt, now)
        if busy_win or self.scene.busy() or now - self._last_draw > 0.12:
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
        self.scene.draw(cr, time.monotonic())
        cr.restore()
        if grouped:
            cr.pop_group_to_source()
            cr.paint_with_alpha(a)
        return False

    # ── ввод ──
    def _local(self, e):
        return e.x - M, e.y - M

    def _set_cursor(self, name):
        want = 'pointer' if name in INTERACTIVE else None
        if want == self._cursor:
            return
        self._cursor = want
        win = self.canvas.get_window()
        if win:
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), want) if want else None)

    def _on_motion(self, _w, e):
        self._set_cursor(self.scene.on_motion(*self._local(e)))
        return True

    def _on_leave(self, *_):
        self.scene.on_leave()
        self._set_cursor(None)
        return True

    def _on_press(self, _w, e):
        if e.button == 3:
            self.close_animated()
            return True
        if e.button == 1:
            self.scene.on_press(*self._local(e))
        return True

    def _on_release(self, _w, e):
        if e.button == 1:
            self.scene.on_release(*self._local(e))
        return True

    def _on_scroll(self, _w, e):
        if e.direction == Gdk.ScrollDirection.UP:
            self.scene.on_scroll(-1)
        elif e.direction == Gdk.ScrollDirection.DOWN:
            self.scene.on_scroll(1)
        elif e.direction == Gdk.ScrollDirection.SMOOTH:
            self._scroll_acc += e.delta_y
            if abs(self._scroll_acc) >= 0.5:
                steps = int(self._scroll_acc / 0.5)
                self._scroll_acc -= steps * 0.5
                self.scene.on_scroll(steps)
        return True

    def _on_key(self, _w, e):
        k, b, s = e.keyval, self.backend, self.backend.s
        now = time.monotonic()
        if k in (Gdk.KEY_Escape, Gdk.KEY_q):
            self.close_animated()
        elif k == Gdk.KEY_space:
            b.toggle_play()
        elif k in (Gdk.KEY_Left, Gdk.KEY_Right) and s.length > 0:
            d = -5 if k == Gdk.KEY_Left else 5
            b.seek(clamp(s.position(now) + d, 0, s.length))
        elif k in (Gdk.KEY_Up, Gdk.KEY_Down) and s.volume is not None:
            b.set_volume(s.volume + (0.05 if k == Gdk.KEY_Up else -0.05))
        elif k == Gdk.KEY_n:
            self.scene._activate('next')
        elif k == Gdk.KEY_p:
            self.scene._activate('prev')
        return True


# ═════════════════════════════════════════════════════════════
#  ЗАПУСК
# ═════════════════════════════════════════════════════════════
def _pidfile():
    return os.path.join(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir()), 'widgetM.pid')


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

    if not _run(['playerctl', *PA, 'status']).strip():
        if EXIT_IF_NO_PLAYER:
            subprocess.Popen(['notify-send', 'Яндекс Музыка', 'Плеер не запущен',
                              '-i', 'dialog-information'])
            cleanup_pidfile()
            sys.exit(1)

    win = MusicPopup()
    win.connect('destroy', lambda *_: Gtk.main_quit())
    win.show_all()
    try:
        Gtk.main()
    finally:
        cleanup_pidfile()
