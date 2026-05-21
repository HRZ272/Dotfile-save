#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# sudo pacman -S python-gtk-layer-shell python-gobject python-cairo playerctl

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk, GtkLayerShell, Gdk, GdkPixbuf, GLib, Pango
import subprocess, urllib.request, os, tempfile, threading, sys, math
import cairo

def cairo_linear(cr, x0, y0, x1, y1):
    return cairo.LinearGradient(x0, y0, x1, y1)


# ─────────────────────────────────────────────
#  Позиция
# ─────────────────────────────────────────────
X_OFFSET    = 80
TOP_TARGET  = 42

ART_SIZE    = 90
POPUP_W     = 330

ANIM_FPS    = 60
ANIM_MS     = int(1000 / ANIM_FPS)
ANIM_DUR    = 0.45
ANIM_FRAMES = int(ANIM_DUR * ANIM_FPS)

MARQUEE_MAX  = 22          # символов — после этого включается прокрутка
MARQUEE_GAP  = '   ·   '  # разделитель между повторениями
MARQUEE_MS   = 190         # мс на один шаг (скорость прокрутки)
MARQUEE_HOLD = 12          # шагов «держать» перед началом прокрутки


# ─────────────────────────────────────────────
#  Easing
# ─────────────────────────────────────────────
def ease_out_back(t, s=1.8):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


# ─────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────
CSS = b"""
window { background-color: rgba(0,0,0,0); }

.card {
    background: rgba(30, 30, 46, 0.97);
    border: 2px solid #b4befe;
    border-radius: 18px;
    padding: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.75);
}
.title {
    color: #cdd6f4;
    font-family: "JetBrainsMono Nerd Font";
    font-size: 14px;
    font-weight: bold;
}
.artist {
    color: #b4befe;
    font-family: "JetBrainsMono Nerd Font";
    font-size: 12px;
}
.time-label {
    margin-top: 4px;
    color: #6c7086;
    font-family: "JetBrainsMono Nerd Font";
    font-size: 11px;
    min-width: 36px;
}
.ctrl {
    background: rgba(49, 50, 68, 0.9);
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 10px;
    padding: 6px 16px;
    font-size: 17px;
    min-width: 44px;
    min-height: 36px;
}
.ctrl:hover {
    background: rgba(180, 190, 254, 0.18);
    border-color: #b4befe;
    color: #b4befe;
}
.ctrl-play {
    background: linear-gradient(135deg, #b4befe 0%, #cba6f7 100%);
    color: #1e1e2e;
    border: none;
    border-radius: 10px;
    padding: 6px 20px;
    font-size: 18px;
    min-width: 52px;
    min-height: 36px;
    font-weight: bold;
}
.ctrl-play:hover {
    background: linear-gradient(135deg, #cba6f7 0%, #b4befe 100%);
    box-shadow: 0 0 16px rgba(180, 190, 254, 0.5);
}
scale trough {
    background: #313244;
    border-radius: 4px;
    min-height: 4px;
    border: none;
}
scale highlight {
    background: linear-gradient(to right, #b4befe, #cba6f7);
    border-radius: 4px;
    border: none;
}
scale slider {
    background: #b4befe;
    border-radius: 50%;
    min-width: 12px;
    min-height: 12px;
    margin: -4px 0;
    border: none;
    box-shadow: 0 0 6px rgba(180, 190, 254, 0.6);
}
scale slider:hover { background: #cba6f7; }
separator {
    background: #313244;
    min-height: 1px;
    margin: 4px 0;
}
"""


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def run(*args):
    try:
        return subprocess.check_output(list(args), stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ''

def fmt_time(seconds):
    """Форматирует секунды в mm:ss"""
    seconds = max(0, int(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'

def get_position():
    """Текущая позиция в секундах"""
    try:
        return float(run('playerctl', 'position'))
    except Exception:
        return 0.0

def get_duration():
    """Длина трека в секундах (mpris даёт микросекунды)"""
    try:
        raw = run('playerctl', 'metadata', 'mpris:length')
        return float(raw) / 1_000_000 if raw else 0.0
    except Exception:
        return 0.0

def seek_to(seconds):
    subprocess.Popen(
        ['playerctl', 'position', str(float(seconds))],
        stderr=subprocess.DEVNULL
    )


# ─────────────────────────────────────────────
#  Окно
# ─────────────────────────────────────────────
class MusicPopup(Gtk.Window):

    def __init__(self):
        super().__init__()
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_default_size(POPUP_W, 1)

        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP,  True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, X_OFFSET)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, -220)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._seek_dragging  = False
        self._duration       = 0.0
        self._wave_phase     = 0.0   # фаза волны

        self._marquee_text   = ''    # полная строка + разделитель
        self._marquee_offset = 0     # текущий символ
        self._marquee_hold   = 0     # счётчик паузы в начале
        self._marquee_timer  = None

        self._build_ui()
        self._load_track()
        self.connect('key-press-event', self._on_key)

        self._anim_frame = 0
        self._anim_start = -220
        self.connect('map', lambda _: GLib.timeout_add(ANIM_MS, self._animate))

        GLib.timeout_add(1000, self._tick)
        GLib.timeout_add(33,   self._wave_tick)   # ~30fps волны

    # ── Анимация ──────────────────────────────

    def _animate(self):
        self._anim_frame += 1
        t = min(self._anim_frame / ANIM_FRAMES, 1.0)
        eased   = ease_out_back(t)
        current = self._anim_start + (TOP_TARGET - self._anim_start) * eased
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, int(current))
        if t < 1.0:
            return True
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, TOP_TARGET)
        return False

    # ── UI ────────────────────────────────────

    def _build_ui(self):
        outer = Gtk.Box()
        self.add(outer)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.get_style_context().add_class('card')
        outer.pack_start(card, True, True, 0)

        # ── Обложка + инфо ──
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        card.pack_start(top, False, False, 0)

        self.art_img = Gtk.Image()
        self._placeholder_art()
        top.pack_start(self.art_img, False, False, 0)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info.set_valign(Gtk.Align.CENTER)
        top.pack_start(info, True, True, 0)

        self.lbl_title = Gtk.Label(label='Загружаем...')
        self.lbl_title.get_style_context().add_class('title')
        self.lbl_title.set_halign(Gtk.Align.START)
        info.pack_start(self.lbl_title, False, False, 0)

        self.lbl_artist = Gtk.Label(label='')
        self.lbl_artist.get_style_context().add_class('artist')
        self.lbl_artist.set_halign(Gtk.Align.START)
        info.pack_start(self.lbl_artist, False, False, 0)


        # ── Кнопки ──
        ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ctrl.set_halign(Gtk.Align.CENTER)
        card.pack_start(ctrl, False, False, 0)

        btn_prev = Gtk.Button(label='⏮')
        btn_prev.get_style_context().add_class('ctrl')
        btn_prev.connect('clicked', lambda _: self._cmd('previous'))
        ctrl.pack_start(btn_prev, False, False, 0)

        self.btn_play = Gtk.Button(label='⏸')
        self.btn_play.get_style_context().add_class('ctrl-play')
        self.btn_play.connect('clicked', lambda _: self._cmd('play-pause'))
        ctrl.pack_start(self.btn_play, False, False, 0)

        btn_next = Gtk.Button(label='⏭')
        btn_next.get_style_context().add_class('ctrl')
        btn_next.connect('clicked', lambda _: self._cmd('next'))
        ctrl.pack_start(btn_next, False, False, 0)


        # ── Прогресс трека (ФИКС) ──
        seek_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.pack_start(seek_col, False, False, 0)

        overlay = Gtk.Overlay()
        overlay.set_size_request(-1, 36)
        seek_col.pack_start(overlay, False, False, 0)

        # Волны (фон)
        self.wave_area = Gtk.DrawingArea()
        self.wave_area.set_hexpand(True)
        self.wave_area.set_vexpand(True)
        self.wave_area.connect('draw', self._draw_waves)
        overlay.add(self.wave_area)

        # Ползунок (поверх волн)
        self.seek_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.seek_scale.set_draw_value(False)
        self.seek_scale.set_hexpand(True)
        self.seek_scale.set_valign(Gtk.Align.CENTER)

        self.seek_scale.connect('button-press-event', self._seek_start)
        self.seek_scale.connect('button-release-event', self._seek_end)
        self.seek_scale.connect('value-changed', self._seek_moving)

        overlay.add_overlay(self.seek_scale)

        # Время
        time_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        seek_col.pack_start(time_row, False, False, 0)

        self.lbl_pos = Gtk.Label(label='0:00')
        self.lbl_pos.get_style_context().add_class('time-label')
        self.lbl_pos.set_halign(Gtk.Align.START)
        time_row.pack_start(self.lbl_pos, False, False, 0)

        self.lbl_dur = Gtk.Label(label='0:00')
        self.lbl_dur.get_style_context().add_class('time-label')
        self.lbl_dur.set_halign(Gtk.Align.END)
        time_row.pack_end(self.lbl_dur, False, False, 0)
    
    # ── Бегущая строка (marquee) ──────────────

    def _set_title(self, text):
        """Устанавливает заголовок: если длинный — запускает прокрутку."""
        # останавливаем старый таймер
        if self._marquee_timer is not None:
            GLib.source_remove(self._marquee_timer)
            self._marquee_timer = None

        if len(text) <= MARQUEE_MAX:
            self.lbl_title.set_text(text)
            return

        # готовим бесконечную циклическую строку
        self._marquee_text   = text + MARQUEE_GAP
        self._marquee_offset = 0
        self._marquee_hold   = MARQUEE_HOLD
        # показываем начало сразу
        self.lbl_title.set_text(self._marquee_text[:MARQUEE_MAX])
        self._marquee_timer  = GLib.timeout_add(MARQUEE_MS, self._marquee_tick)

    def _marquee_tick(self):
        # пауза в начале (как у настоящего табло)
        if self._marquee_hold > 0:
            self._marquee_hold -= 1
            return True

        full = self._marquee_text
        n    = len(full)
        i    = self._marquee_offset
        # берём MARQUEE_MAX символов циклически
        chunk = (full + full)[i : i + MARQUEE_MAX]
        self.lbl_title.set_text(chunk)

        self._marquee_offset = (i + 1) % n
        # когда сделали полный круг — снова держим паузу
        if self._marquee_offset == 0:
            self._marquee_hold = MARQUEE_HOLD
        return True

    # ── Волна ─────────────────────────────────

    def _wave_tick(self):
        self._wave_phase += 0.04
        if self.wave_area.get_window():
            self.wave_area.queue_draw()
        return True

    def _draw_waves(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()

        # Скругляем края волн как у карточки — clip по rounded rect
        r = 16
        cr.new_sub_path()
        cr.arc(r,     r,     r, math.pi,       3*math.pi/2)
        cr.arc(w-r,   r,     r, 3*math.pi/2,   0)
        cr.arc(w-r,   h-r,   r, 0,             math.pi/2)
        cr.arc(r,     h-r,   r, math.pi/2,     math.pi)
        cr.close_path()
        cr.clip()

        # Тёмный фон под волнами
        cr.set_source_rgba(0.12, 0.12, 0.18, 1.0)
        cr.paint()

        layers = [
            ((0.40, 0.33, 0.68), 14, 1.3, 1.0, 0.55),
            ((0.62, 0.52, 0.87), 9,  2.0, 1.6, 0.45),
            ((0.71, 0.75, 1.00), 6,  2.8, 2.4, 0.30),
        ]

        for (r2, g, b), amp, freq, speed, alpha in layers:
            ph = self._wave_phase * speed
            cr.move_to(0, h)
            for x in range(w + 1):
                y = h * 0.5 \
                    + amp * math.sin(freq * math.pi * x / w + ph) \
                    + amp * 0.5 * math.sin(freq * 1.8 * math.pi * x / w - ph * 0.7)
                cr.line_to(x, y)
            cr.line_to(w, h)
            cr.close_path()
            grad = cairo.LinearGradient(0, 0, 0, h)
            grad.add_color_stop_rgba(0,   r2, g, b, alpha)
            grad.add_color_stop_rgba(1.0, r2*0.6, g*0.6, b*0.8, alpha * 1.5)
            cr.set_source(grad)
            cr.fill()

    # ── Прогресс трека ────────────────────────

    def _tick(self):
        """Вызывается каждую секунду — обновляет трек и ползунок"""
        title = run('playerctl', 'metadata', 'title')
        if title != getattr(self, '_last_title', ''):
            self._last_title = title
            self._load_track()
        if not self._seek_dragging:
            pos = get_position()
            if self._duration > 0:
                GLib.idle_add(self._update_seek_ui, pos)
        return True  # повторять

    def _update_seek_ui(self, pos):
        if self._seek_dragging:
            return
        self.seek_scale.set_value(pos)
        self.lbl_pos.set_text(fmt_time(pos))

    def _seek_start(self, *_):
        self._seek_dragging = True

    def _seek_end(self, *_):
        pos = self.seek_scale.get_value()
        seek_to(pos)
        self._seek_dragging = False

    def _seek_moving(self, scale):
        """Обновляем только лейбл времени пока тащим"""
        if self._seek_dragging:
            self.lbl_pos.set_text(fmt_time(scale.get_value()))

    # ── Данные трека ──────────────────────────

    def _load_track(self):
        status  = run('playerctl', 'status')
        title   = run('playerctl', 'metadata', 'title')
        artist  = run('playerctl', 'metadata', 'artist')
        art_url = run('playerctl', 'metadata', 'mpris:artUrl')

        self._duration = get_duration()
        pos            = get_position()

        self._set_title(title or 'Неизвестный трек')
        self.lbl_artist.set_text(artist or 'Неизвестный исполнитель')
        self.btn_play.set_label('⏸' if status == 'Playing' else '▶')

        # Настраиваем диапазон ползунка под длину трека
        if self._duration > 0:
            self.seek_scale.set_range(0, self._duration)
            self.seek_scale.set_increments(5, 30)
            self.seek_scale.set_value(pos)
            self.lbl_pos.set_text(fmt_time(pos))
            self.lbl_dur.set_text(fmt_time(self._duration))

        if art_url:
            threading.Thread(target=self._fetch_art, args=(art_url,), daemon=True).start()

    def _fetch_art(self, url):
        try:
            if url.startswith('file://'):
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(url[7:], ART_SIZE, ART_SIZE, True)
            elif url.startswith('http'):
                with urllib.request.urlopen(url, timeout=4) as r:
                    data = r.read()
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                tmp.write(data); tmp.close()
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(tmp.name, ART_SIZE, ART_SIZE, True)
                os.unlink(tmp.name)
            else:
                return
            pb = self._round(pb, 12)
            GLib.idle_add(self.art_img.set_from_pixbuf, pb)
        except Exception as e:
            print(f'[widgetM] art: {e}', file=sys.stderr)

    @staticmethod
    def _round(pb, r):
        try:
            import cairo
            w, h = pb.get_width(), pb.get_height()
            s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            c = cairo.Context(s)
            c.set_source_rgba(0,0,0,0); c.paint()
            c.arc(r,r,r,math.pi,3*math.pi/2)
            c.arc(w-r,r,r,3*math.pi/2,0)
            c.arc(w-r,h-r,r,0,math.pi/2)
            c.arc(r,h-r,r,math.pi/2,math.pi)
            c.close_path(); c.clip()
            Gdk.cairo_set_source_pixbuf(c, pb, 0, 0); c.paint()
            return Gdk.pixbuf_get_from_surface(s, 0, 0, w, h)
        except Exception:
            return pb

    def _placeholder_art(self):
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, ART_SIZE, ART_SIZE)
        pb.fill(0x313244FF)
        self.art_img.set_from_pixbuf(self._round(pb, 12))

    def _cmd(self, cmd):
        subprocess.Popen(['playerctl', cmd], stderr=subprocess.DEVNULL)
        GLib.timeout_add(350, self._load_track)

    def _on_key(self, _w, event):
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()


# ─────────────────────────────────────────────

if __name__ == '__main__':
    if not run('playerctl', 'status'):
        subprocess.Popen(['notify-send', 'Яндекс Музыка', 'Плеер не запущен', '-i', 'dialog-information'])
        sys.exit(1)

    win = MusicPopup()
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()
