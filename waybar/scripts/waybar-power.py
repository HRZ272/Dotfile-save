#!/usr/bin/env python3
"""
Waybar Power Menu — компактный попап
Toggle: повторный запуск закрывает окно.
Команды под себя меняй в ACTIONS ниже.
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo, math, os, sys, signal, subprocess

PID_FILE = "/tmp/waybar-power.pid"

# ── toggle ───────────────────────────────────────────────────────────────────
if os.path.exists(PID_FILE):
    try:
        with open(PID_FILE) as f:
            old = int(f.read().strip())
        os.kill(old, signal.SIGTERM)
        os.remove(PID_FILE)
        sys.exit(0)
    except (ProcessLookupError, ValueError):
        os.remove(PID_FILE)

with open(PID_FILE, "w") as f:
    f.write(str(os.getpid()))

# ── действия — меняй команды под себя ────────────────────────────────────────
ACTIONS = [
    {
        "label": "Заблокировать",
        "sub":   "hyprlock",
        "cmd":   ["hyprlock"],
        "color": (0.388, 0.647, 1.000),   # blue
        "icon":  "lock",
        "confirm": False,
    },
    {
        "label": "Сон",
        "sub":   "systemctl suspend",
        "cmd":   ["systemctl", "suspend"],
        "color": (0.149, 0.780, 0.749),   # teal
        "icon":  "sleep",
        "confirm": False,
    },
    {
        "label": "Выйти",
        "sub":   "hyprctl dispatch exit",
        "cmd":   ["hyprctl", "dispatch", "exit", ""],
        "color": (0.941, 0.616, 0.110),   # amber
        "icon":  "logout",
        "confirm": True,
    },
    {
        "label": "Перезагрузить",
        "sub":   "systemctl reboot",
        "cmd":   ["systemctl", "reboot"],
        "color": (0.886, 0.290, 0.290),   # red
        "icon":  "reboot",
        "confirm": True,
    },
    {
        "label": "Выключить",
        "sub":   "systemctl poweroff",
        "cmd":   ["systemctl", "poweroff"],
        "color": (0.800, 0.180, 0.180),   # deep red
        "icon":  "power",
        "confirm": True,
    },
]

# ── цвета Catppuccin Mocha ────────────────────────────────────────────────────
BG      = (0.098, 0.098, 0.149)
SURF    = (0.149, 0.153, 0.220)
OVERLAY = (0.220, 0.227, 0.318)
TEXT    = (0.820, 0.855, 0.965)
SUB     = (0.494, 0.518, 0.655)


# ── SVG-иконки через Cairo ───────────────────────────────────────────────────
def draw_icon(cr, name, cx, cy, size, color):
    cr.set_source_rgb(*color)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    s = size / 24   # scale factor (иконки в координатах 24x24)

    def T(x, y):
        return cx + (x - 12) * s, cy + (y - 12) * s

    cr.set_line_width(2.0)

    if name == "lock":
        # дужка замка
        cr.new_path()
        cr.arc(*T(12, 11), 4 * s, math.pi, 0)
        cr.stroke()
        # корпус
        x0, y0 = T(7, 11)
        cr.rectangle(x0, y0, 10 * s, 8 * s)
        cr.fill()
        # замочная скважина
        cr.set_source_rgb(*BG)
        cr.arc(*T(12, 15.5), 1.5 * s, 0, 2 * math.pi)
        cr.fill()

    elif name == "sleep":
        # луна
        cr.new_path()
        cr.arc(*T(13, 12), 6 * s, math.radians(135), math.radians(315))
        cr.arc_negative(*T(10, 9), 5 * s, math.radians(315), math.radians(135))
        cr.close_path()
        cr.fill()

    elif name == "logout":
        # стрелка вправо из двери
        cr.new_path()
        x0, y0 = T(9, 6)
        cr.move_to(x0, y0)
        cr.line_to(*T(4, 6))
        cr.line_to(*T(4, 18))
        cr.line_to(*T(9, 18))
        cr.set_line_width(2.0)
        cr.stroke()
        # стрелка
        cr.new_path()
        cr.move_to(*T(12, 12))
        cr.line_to(*T(20, 12))
        cr.stroke()
        cr.new_path()
        cr.move_to(*T(17, 9))
        cr.line_to(*T(20, 12))
        cr.line_to(*T(17, 15))
        cr.stroke()

    elif name == "reboot":
        # круговая стрелка
        cr.new_path()
        cr.arc(*T(12, 12), 6 * s, math.radians(-30), math.radians(270))
        cr.stroke()
        # наконечник
        tip = T(15.2, 6.5)
        cr.move_to(*tip)
        cr.line_to(*T(18, 8))
        cr.line_to(*T(16, 10.5))
        cr.stroke()

    elif name == "power":
        # кнопка питания
        cr.new_path()
        cr.arc(*T(12, 12), 6.5 * s, math.radians(-60), math.radians(240))
        cr.stroke()
        # вертикальная черта
        cr.new_path()
        cr.move_to(*T(12, 5.5))
        cr.line_to(*T(12, 12.5))
        cr.set_line_width(2.2)
        cr.stroke()


# ── окно ─────────────────────────────────────────────────────────────────────
class PowerMenu(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_title("Power Menu")
        self.set_default_size(300, 1)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self._confirm_action = None

        self._apply_css()
        self._build()
        self.connect("destroy", self._on_destroy)
        self.connect("key-press-event", self._on_key)
        self.show_all()

    def _apply_css(self):
        css = b"""
        window { background: #191927; }
        .btn {
            background: #262638;
            border: 1px solid #2e2e46;
            border-radius: 12px;
            padding: 0;
            transition: background 0.12s, border-color 0.12s;
        }
        .btn:hover {
            background: #2e2e48;
            border-color: #45475a;
        }
        .btn:active { background: #38384e; }
        .btn label { color: #ffffff; font-weight: 600; }
        .btn:hover label { color: #ffffff; }

        .confirm-bar {
            background: #1e1e30;
            border-radius: 10px;
            padding: 2px;
        }
        .yes {
            background: #c0392b;
            border: none;
            border-radius: 8px;
            padding: 6px 20px;
        }
        .yes label { color: #ffffff; font-weight: 500; font-size: 13px; }
        .yes:hover { background: #e74c3c; }
        .no {
            background: #313244;
            border: none;
            border-radius: 8px;
            padding: 6px 20px;
        }
        .no label { color: #cdd6f4; font-size: 13px; }
        .no:hover { background: #45475a; }
        """
        p = Gtk.CssProvider()
        p.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), p,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(14); root.set_margin_bottom(14)
        root.set_margin_start(14); root.set_margin_end(14)
        self.add(root)

        # заголовок
        hdr = Gtk.Label(label="ПИТАНИЕ")
        hdr.set_halign(Gtk.Align.START)
        sc = hdr.get_style_context()
        root.pack_start(hdr, False, False, 0)

        # кнопки
        for action in ACTIONS:
            btn = self._make_button(action)
            root.pack_start(btn, False, False, 0)

        # панель подтверждения (скрытая)
        self.confirm_box = Gtk.Box(spacing=8)
        self.confirm_box.get_style_context().add_class("confirm-bar")
        self.confirm_box.set_halign(Gtk.Align.CENTER)
        self.confirm_box.set_margin_top(4)

        self.confirm_label = Gtk.Label(label="")
        self.confirm_label.set_halign(Gtk.Align.CENTER)

        yes_btn = Gtk.Button(label="Да, выполнить")
        yes_btn.get_style_context().add_class("yes")
        yes_btn.connect("clicked", self._do_confirm)

        no_btn = Gtk.Button(label="Отмена")
        no_btn.get_style_context().add_class("no")
        no_btn.connect("clicked", self._cancel_confirm)

        self.confirm_box.pack_start(no_btn, False, False, 0)
        self.confirm_box.pack_start(yes_btn, False, False, 0)

        root.pack_start(self.confirm_label, False, False, 0)
        root.pack_start(self.confirm_box, False, False, 0)

        self.confirm_label.set_visible(False)
        self.confirm_box.set_visible(False)

    def _make_button(self, action):
        btn = Gtk.Button()
        btn.get_style_context().add_class("btn")
        btn.set_size_request(-1, 62)

        inner = Gtk.Box(spacing=14)
        inner.set_margin_start(14); inner.set_margin_end(14)
        inner.set_valign(Gtk.Align.CENTER)

        # иконка через DrawingArea
        icon_da = Gtk.DrawingArea()
        icon_da.set_size_request(32, 32)
        color = action["color"]
        icon_name = action["icon"]
        icon_da.connect("draw", lambda w, cr, c=color, n=icon_name:
                        self._draw_icon_da(w, cr, n, c))

        # текстовая часть
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        txt.set_valign(Gtk.Align.CENTER)

        lbl = Gtk.Label(label=action["label"])
        lbl.set_halign(Gtk.Align.START)
        lbl.set_markup(f'<span font_weight="bold" font_size="13000">{action["label"]}</span>')

        sub = Gtk.Label(label=action["sub"])
        sub.set_halign(Gtk.Align.START)
        sub.set_markup(f'<span foreground="#6c6f85" font_size="10000">{action["sub"]}</span>')

        txt.pack_start(lbl, False, False, 0)
        txt.pack_start(sub, False, False, 0)

        inner.pack_start(icon_da, False, False, 0)
        inner.pack_start(txt, True, True, 0)
        btn.add(inner)

        btn.connect("clicked", self._on_action, action)
        return btn

    def _draw_icon_da(self, widget, cr, name, color):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        draw_icon(cr, name, w / 2, h / 2, 26, color)

    def _on_action(self, btn, action):
        if action["confirm"]:
            self._confirm_action = action
            self.confirm_label.set_markup(
                f'<span foreground="#cdd6f4" font_size="12000">'
                f'Выполнить: <b>{action["label"]}</b>?</span>'
            )
            self.confirm_label.set_visible(True)
            self.confirm_box.set_visible(True)
            self.resize(300, 1)
        else:
            self._run(action)

    def _do_confirm(self, _):
        if self._confirm_action:
            self._run(self._confirm_action)

    def _cancel_confirm(self, _):
        self._confirm_action = None
        self.confirm_label.set_visible(False)
        self.confirm_box.set_visible(False)
        self.resize(300, 1)

    def _run(self, action):
        subprocess.Popen(action["cmd"], stderr=subprocess.DEVNULL)
        self.destroy()

    def _on_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            if self._confirm_action:
                self._cancel_confirm(None)
            else:
                self.destroy()

    def _on_destroy(self, _):
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        Gtk.main_quit()


if __name__ == "__main__":
    app = PowerMenu()
    Gtk.main()
