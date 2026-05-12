#!/usr/bin/env python3
"""
Waybar Clock Popup — Таймер + Секундомер
Запуск: python3 waybar-clock.py
Повторный запуск закрывает окно (toggle).
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo
import math
import time
import subprocess
import sys
import os
import signal

PID_FILE = "/tmp/waybar-clock.pid"

# ── toggle: если уже запущен — убиваем ──────────────────────────────────────
if os.path.exists(PID_FILE):
    try:
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        os.kill(old_pid, signal.SIGTERM)
        os.remove(PID_FILE)
        sys.exit(0)
    except (ProcessLookupError, ValueError):
        os.remove(PID_FILE)

with open(PID_FILE, "w") as f:
    f.write(str(os.getpid()))

# ── цвета (Catppuccin Mocha) ─────────────────────────────────────────────────
BG        = (0.118, 0.118, 0.180)   # #1e1e2e
SURFACE   = (0.192, 0.200, 0.302)   # #313244
OVERLAY   = (0.271, 0.278, 0.388)   # #45475a
TEXT      = (0.804, 0.839, 0.957)   # #cdd6f4
SUBTEXT   = (0.549, 0.573, 0.706)   # #8c8fa1
PURPLE    = (0.498, 0.322, 1.000)   # #7f52ff  (accent)
GREEN     = (0.196, 0.800, 0.502)   # #32cc80
AMBER     = (0.941, 0.616, 0.110)   # #f09d1c
RED       = (0.886, 0.290, 0.290)   # #e24a4a
TRACK     = (0.200, 0.200, 0.280)


def rgb(*c):
    return c


class ClockApp(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_title("Таймер / Секундомер")
        self.set_default_size(320, 420)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        # ── состояние ────────────────────────────────────────────────────────
        self.mode = "stopwatch"   # "stopwatch" | "timer"
        self.running = False
        self.elapsed = 0.0        # секунды (секундомер ↑, таймер ↓)
        self.timer_total = 300.0  # секунд в таймере (по умолчанию 5 мин)
        self.start_ts = None      # time.monotonic() при старте
        self.base = 0.0           # накопленное время до паузы
        self.done = False

        self._apply_css()
        self._build_ui()

        GLib.timeout_add(33, self._tick)   # ~30 fps
        self.connect("destroy", self._on_destroy)
        self.show_all()
        self._update_input_visibility()

    # ── CSS ──────────────────────────────────────────────────────────────────
    def _apply_css(self):
        css = b"""
        window {
            background-color: #1e1e2e;
        }
        .pill {
            background: #313244;
            border-radius: 999px;
            padding: 0;
            border: none;
        }
        .tab {
            background: transparent;
            border: none;
            border-radius: 999px;
            padding: 6px 22px;
            transition: background 0.15s;
        }
        .tab label {
            color: #e0e4f8;
            font-size: 13px;
            font-weight: 600;
        }
        .tab:hover { background: #45475a; }
        .tab:hover label { color: #ffffff; }
        .tab.active { background: #7f52ff; }
        .tab.active label { color: #ffffff; }
        .ctrl {
            background: #45475a;
            border: none;
            border-radius: 10px;
            padding: 9px 28px;
            transition: background 0.12s;
        }
        .ctrl label {
            color: #ffffff;
            font-size: 14px;
            font-weight: 700;
        }
        .ctrl:hover  { background: #585b70; }
        .ctrl:active { background: #6c6f85; }
        .ctrl.primary { background: #7f52ff; }
        .ctrl.primary label { color: #ffffff; font-weight: 700; }
        .ctrl.primary:hover { background: #9370ff; }
        .time-input {
            background: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 18px;
            font-family: monospace;
            font-weight: bold;
        }
        label { color: #8c8fa1; font-size: 13px; }
        """
        p = Gtk.CssProvider()
        p.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), p,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)
        self.add(root)

        # Переключатель режима
        pill = Gtk.Box(spacing=0)
        pill.get_style_context().add_class("pill")
        pill.set_halign(Gtk.Align.CENTER)

        self.sw_tab = Gtk.Button(label="⏱  Секундомер")
        self.sw_tab.get_style_context().add_class("tab")
        self.sw_tab.connect("clicked", lambda _: self._set_mode("stopwatch"))

        self.tm_tab = Gtk.Button(label="⏲  Таймер")
        self.tm_tab.get_style_context().add_class("tab")
        self.tm_tab.connect("clicked", lambda _: self._set_mode("timer"))

        pill.pack_start(self.sw_tab, False, False, 0)
        pill.pack_start(self.tm_tab, False, False, 0)
        root.pack_start(pill, False, False, 0)

        # Круглые часики
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(280, 280)
        self.canvas.connect("draw", self._draw)
        root.pack_start(self.canvas, False, False, 0)

        # Ввод времени (только для таймера)
        self.input_row = Gtk.Box(spacing=10)
        self.input_row.set_halign(Gtk.Align.CENTER)

        lbl = Gtk.Label(label="Установить время:")
        self.time_entry = Gtk.Entry()
        self.time_entry.set_text("05:00")
        self.time_entry.set_width_chars(6)
        self.time_entry.set_max_length(5)
        self.time_entry.get_style_context().add_class("time-input")
        self.time_entry.set_placeholder_text("мм:сс")

        hint = Gtk.Label(label="(мм:сс)")

        self.input_row.pack_start(lbl, False, False, 0)
        self.input_row.pack_start(self.time_entry, False, False, 0)
        self.input_row.pack_start(hint, False, False, 0)
        root.pack_start(self.input_row, False, False, 0)

        # Кнопки управления
        btns = Gtk.Box(spacing=10)
        btns.set_halign(Gtk.Align.CENTER)

        self.start_btn = Gtk.Button(label="▶  Старт")
        self.start_btn.get_style_context().add_class("ctrl")
        self.start_btn.get_style_context().add_class("primary")
        self.start_btn.connect("clicked", self._toggle_start)

        self.reset_btn = Gtk.Button(label="↺  Сброс")
        self.reset_btn.get_style_context().add_class("ctrl")
        self.reset_btn.connect("clicked", self._reset)

        btns.pack_start(self.start_btn, False, False, 0)
        btns.pack_start(self.reset_btn, False, False, 0)
        root.pack_start(btns, False, False, 0)

    # ── логика режимов ───────────────────────────────────────────────────────
    def _set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        self._reset(None)
        self._update_tabs()
        self._update_input_visibility()

    def _update_tabs(self):
        if self.mode == "stopwatch":
            self.sw_tab.get_style_context().add_class("active")
            self.tm_tab.get_style_context().remove_class("active")
        else:
            self.tm_tab.get_style_context().add_class("active")
            self.sw_tab.get_style_context().remove_class("active")

    def _update_input_visibility(self):
        if self.mode == "timer" and not self.running and self.base == 0:
            self.input_row.set_visible(True)
        else:
            self.input_row.set_visible(False)

    # ── старт / пауза ────────────────────────────────────────────────────────
    def _toggle_start(self, _):
        if self.done:
            self._reset(None)
            return

        if not self.running:
            if self.mode == "timer" and self.base == 0:
                self.timer_total = self._parse_time(self.time_entry.get_text())
                self.base = self.timer_total
            self.start_ts = time.monotonic()
            self.running = True
            self.start_btn.set_label("⏸  Пауза")
            self.start_btn.get_style_context().remove_class("primary")
            self.start_btn.get_style_context().add_class("ctrl")
            self._update_input_visibility()
        else:
            self.base = self.elapsed
            self.running = False
            self.start_btn.set_label("▶  Продолжить")
            self.start_btn.get_style_context().add_class("primary")

    def _reset(self, _):
        self.running = False
        self.elapsed = 0.0
        self.base = 0.0
        self.start_ts = None
        self.done = False
        self.start_btn.set_label("▶  Старт")
        self.start_btn.get_style_context().add_class("primary")
        self._update_input_visibility()
        self.canvas.queue_draw()

    def _parse_time(self, text):
        try:
            parts = text.strip().split(":")
            if len(parts) == 2:
                return float(int(parts[0]) * 60 + int(parts[1]))
            return float(int(parts[0]))
        except Exception:
            return 300.0

    # ── тик ──────────────────────────────────────────────────────────────────
    def _tick(self):
        if self.running:
            delta = time.monotonic() - self.start_ts
            if self.mode == "stopwatch":
                self.elapsed = self.base + delta
            else:
                self.elapsed = self.base - delta
                if self.elapsed <= 0:
                    self.elapsed = 0.0
                    self.running = False
                    self.done = True
                    self.start_btn.set_label("↺  Готово!")
                    self._on_timer_done()

            self.canvas.queue_draw()
        return True

    def _on_timer_done(self):
        subprocess.Popen(
            ["notify-send", "-u", "critical", "-i", "alarm-clock",
             "⏰ Таймер завершён", "Время вышло!"],
            stderr=subprocess.DEVNULL,
        )
        # пробуем разные звуковые движки по порядку
        sounds = [
            "/usr/share/sounds/freedesktop/stereo/complete.oga",
            "/usr/share/sounds/freedesktop/stereo/bell.oga",
            "/usr/share/sounds/alsa/Front_Center.wav",
        ]
        players = ["paplay", "pw-play", "aplay"]
        for player in players:
            for snd in sounds:
                if os.path.exists(snd):
                    try:
                        subprocess.Popen(
                            [player, snd],
                            stderr=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                        )
                        return
                    except FileNotFoundError:
                        break

    # ── отрисовка ────────────────────────────────────────────────────────────
    def _draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 14   # радиус внешней окружности

        self._draw_face(cr, cx, cy, R)
        self._draw_track(cr, cx, cy, R)
        self._draw_progress(cr, cx, cy, R)
        self._draw_ticks(cr, cx, cy, R)
        self._draw_time_text(cr, cx, cy)

    def _draw_face(self, cr, cx, cy, R):
        cr.set_source_rgb(*SURFACE)
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.fill()

        # тонкая окантовка
        cr.set_source_rgba(*OVERLAY, 0.6)
        cr.set_line_width(1.5)
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.stroke()

    def _draw_track(self, cr, cx, cy, R):
        track_r = R - 14
        cr.set_source_rgba(*TRACK, 1.0)
        cr.set_line_width(10)
        cr.arc(cx, cy, track_r, 0, 2 * math.pi)
        cr.stroke()

    def _draw_progress(self, cr, cx, cy, R):
        track_r = R - 14
        progress = self._get_progress()

        if progress <= 0:
            return

        # цвет дуги
        if self.mode == "stopwatch":
            color = PURPLE
        else:
            if progress > 0.5:
                color = GREEN
            elif progress > 0.2:
                color = AMBER
            else:
                color = RED

        cr.set_source_rgb(*color)
        cr.set_line_width(10)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        start_a = -math.pi / 2
        end_a = start_a + 2 * math.pi * progress
        cr.arc(cx, cy, track_r, start_a, end_a)
        cr.stroke()

        # светящаяся точка на конце дуги
        dot_x = cx + track_r * math.cos(end_a)
        dot_y = cy + track_r * math.sin(end_a)
        cr.set_source_rgb(*color)
        cr.arc(dot_x, dot_y, 6, 0, 2 * math.pi)
        cr.fill()

    def _get_progress(self):
        if self.mode == "stopwatch":
            cycle = 60.0
            return (self.elapsed % cycle) / cycle
        else:
            if self.timer_total == 0:
                return 0
            return self.elapsed / self.timer_total

    def _draw_ticks(self, cr, cx, cy, R):
        for i in range(60):
            angle = -math.pi / 2 + 2 * math.pi * i / 60
            big = (i % 5 == 0)
            r_out = R - 4
            r_in  = R - (12 if big else 7)
            lw    = 2.0 if big else 1.0
            alpha = 0.5 if big else 0.2

            cr.set_source_rgba(*TEXT, alpha)
            cr.set_line_width(lw)
            cr.move_to(cx + r_out * math.cos(angle), cy + r_out * math.sin(angle))
            cr.line_to(cx + r_in  * math.cos(angle), cy + r_in  * math.sin(angle))
            cr.stroke()

    def _draw_time_text(self, cr, cx, cy):
        secs_total = int(self.elapsed)
        mins  = secs_total // 60
        secs  = secs_total % 60
        frac  = int((self.elapsed - secs_total) * 10)
        hours = mins // 60
        mins_d = mins % 60

        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)

        if self.mode == "stopwatch":
            if hours > 0:
                main_str = f"{hours}:{mins_d:02d}:{secs:02d}"
                sub_str  = ""
                font_sz  = 28
            else:
                main_str = f"{mins:02d}:{secs:02d}"
                sub_str  = f".{frac}"
                font_sz  = 38
        else:
            main_str = f"{mins_d:02d}:{secs:02d}"
            sub_str  = ""
            font_sz  = 42

        # основное время
        cr.set_font_size(font_sz)
        ex = cr.text_extents(main_str)
        offset_x = 0

        if sub_str:
            cr.set_font_size(font_sz * 0.55)
            sub_ex = cr.text_extents(sub_str)
            total_w = ex.width + sub_ex.width + 2
            offset_x = -total_w / 2

            cr.set_source_rgb(*TEXT)
            cr.set_font_size(font_sz)
            cr.move_to(cx + offset_x, cy + ex.height / 2 - 4)
            cr.show_text(main_str)

            cr.set_source_rgba(*TEXT, 0.55)
            cr.set_font_size(font_sz * 0.55)
            cr.move_to(cx + offset_x + ex.width + 2, cy + ex.height / 2 - 4)
            cr.show_text(sub_str)
        else:
            cr.set_source_rgb(*TEXT)
            cr.set_font_size(font_sz)
            cr.move_to(cx - ex.width / 2, cy + ex.height / 2 - 4)
            cr.show_text(main_str)

        # подпись режима
        cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11)
        label = "секундомер" if self.mode == "stopwatch" else "таймер"
        if self.done:
            label = "⏰ готово!"
            cr.set_source_rgb(*AMBER)
        else:
            cr.set_source_rgba(*SUBTEXT, 0.8)
        lx = cr.text_extents(label)
        cr.move_to(cx - lx.width / 2, cy + font_sz / 2 + 14)
        cr.show_text(label)

    # ── выход ────────────────────────────────────────────────────────────────
    def _on_destroy(self, _):
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        Gtk.main_quit()


if __name__ == "__main__":
    app = ClockApp()
    # выставляем активный таб при старте
    app.sw_tab.get_style_context().add_class("active")
    Gtk.main()
