#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Объединённый виджет громкости для Waybar: система + отдельно Chromium.
# sudo pacman -S python-gtk-layer-shell python-gobject

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, Gdk, GLib
import subprocess, re, sys

# ─────────────────────────────────────────────
#  Позиция (подгони под своё расположение модуля в баре)
# ─────────────────────────────────────────────
X_OFFSET     = 280      # отступ от края
TOP_TARGET   = 42     # отступ сверху (под баром)
ANCHOR_RIGHT = True    # True — прижать к правому краю, False — к левому
POPUP_W      = 300

# ─────────────────────────────────────────────
#  CSS — тот же катппучин-мокка стиль, что и в widgetM.py
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
.section-title {
    color: #cdd6f4;
    font-family: "JetBrainsMono Nerd Font";
    font-size: 13px;
    font-weight: bold;
}
.section-icon {
    color: #b4befe;
    font-family: "JetBrainsMono Nerd Font";
    font-size: 16px;
}
.pct-label {
    color: #6c7086;
    font-family: "JetBrainsMono Nerd Font";
    font-size: 11px;
    min-width: 34px;
}
.inactive-label {
    color: #585b70;
    font-family: "JetBrainsMono Nerd Font";
    font-size: 12px;
    font-style: italic;
}
.mute-btn {
    background: rgba(49, 50, 68, 0.9);
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 10px;
    padding: 4px 8px;
    font-size: 14px;
    min-width: 30px;
    min-height: 28px;
}
.mute-btn:hover {
    background: rgba(180, 190, 254, 0.18);
    border-color: #b4befe;
    color: #b4befe;
}
.mute-btn.muted {
    background: rgba(243, 139, 168, 0.18);
    border-color: #f38ba8;
    color: #f38ba8;
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
    margin: 6px 0;
}
"""


# ─────────────────────────────────────────────
#  Хелперы pactl
# ─────────────────────────────────────────────
def run(*args):
    try:
        return subprocess.check_output(list(args), stderr=subprocess.DEVNULL).decode()
    except Exception:
        return ''


def get_sink_volume():
    out = run('pactl', 'get-sink-volume', '@DEFAULT_SINK@')
    m = re.search(r'(\d+)%', out)
    return int(m.group(1)) if m else 0


def get_sink_mute():
    out = run('pactl', 'get-sink-mute', '@DEFAULT_SINK@')
    return 'yes' in out


def set_sink_volume(pct):
    subprocess.Popen(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{int(pct)}%'],
                      stderr=subprocess.DEVNULL)


def toggle_sink_mute():
    subprocess.Popen(['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle'],
                      stderr=subprocess.DEVNULL)


def get_chromium_ids():
    out = run('pactl', 'list', 'sink-inputs')
    ids = []
    blocks = out.split('Sink Input #')[1:]
    for b in blocks:
        if 'application.name = "Chromium"' in b:
            ids.append(b.split('\n', 1)[0].strip())
    return ids


def get_chromium_volume(ids):
    if not ids:
        return 0, False
    out = run('pactl', 'list', 'sink-inputs')
    block = out.split(f'Sink Input #{ids[0]}')[1].split('Sink Input #')[0]
    vm = re.search(r'Volume:.*?(\d+)%', block)
    mm = re.search(r'Mute:\s*(\w+)', block)
    vol = int(vm.group(1)) if vm else 0
    muted = mm.group(1) == 'yes' if mm else False
    return vol, muted


def set_chromium_volume(ids, pct):
    for i in ids:
        subprocess.Popen(['pactl', 'set-sink-input-volume', i, f'{int(pct)}%'],
                          stderr=subprocess.DEVNULL)


def toggle_chromium_mute(ids):
    for i in ids:
        subprocess.Popen(['pactl', 'set-sink-input-mute', i, 'toggle'],
                          stderr=subprocess.DEVNULL)


def load_app_icon(names, size):
    """Пытается найти иконку приложения в системной icon theme по списку имён."""
    theme = Gtk.IconTheme.get_default()
    for name in names:
        if theme.has_icon(name):
            try:
                return theme.load_icon(name, size, 0)
            except Exception:
                continue
    return None


# ─────────────────────────────────────────────
#  Окно
# ─────────────────────────────────────────────
class VolumePopup(Gtk.Window):

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
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        if ANCHOR_RIGHT:
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, X_OFFSET)
        else:
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.LEFT, X_OFFSET)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, TOP_TARGET)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._sys_dragging = False
        self._chr_dragging = False
        self._chromium_ids = []

        self._build_ui()
        self._refresh()

        self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect('key-press-event', self._on_key)
        self.connect('leave-notify-event', self._on_leave)
        self.connect('enter-notify-event', self._on_enter)

        self._leave_timer = None

        GLib.timeout_add(700, self._tick)

    # ── UI ────────────────────────────────────

    def _build_ui(self):
        outer = Gtk.Box()
        self.add(outer)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.get_style_context().add_class('card')
        outer.pack_start(card, True, True, 0)

        # ── Системный звук ──
        sys_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.pack_start(sys_row, False, False, 0)

        sys_icon = Gtk.Label(label='󰕾')
        sys_icon.get_style_context().add_class('section-icon')
        sys_row.pack_start(sys_icon, False, False, 0)

        sys_title = Gtk.Label(label='Система')
        sys_title.get_style_context().add_class('section-title')
        sys_row.pack_start(sys_title, False, False, 0)

        self.btn_sys_mute = Gtk.Button(label='󰖁')
        self.btn_sys_mute.get_style_context().add_class('mute-btn')
        self.btn_sys_mute.connect('clicked', self._on_sys_mute)
        sys_row.pack_end(self.btn_sys_mute, False, False, 0)

        self.lbl_sys_pct = Gtk.Label(label='0%')
        self.lbl_sys_pct.get_style_context().add_class('pct-label')
        sys_row.pack_end(self.lbl_sys_pct, False, False, 0)

        self.scale_sys = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        self.scale_sys.set_draw_value(False)
        self.scale_sys.set_hexpand(True)
        self.scale_sys.connect('button-press-event', lambda *_: self._set_dragging('sys', True))
        self.scale_sys.connect('button-release-event', self._on_sys_release)
        self.scale_sys.connect('value-changed', self._on_sys_changed)
        card.pack_start(self.scale_sys, False, False, 0)

        card.pack_start(Gtk.Separator(), False, False, 0)

        # ── Chromium ──
        chr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.pack_start(chr_row, False, False, 0)

        chr_pixbuf = load_app_icon(
            ['chromium', 'chromium-browser', 'google-chrome'], 18
        )
        if chr_pixbuf is not None:
            chr_icon = Gtk.Image.new_from_pixbuf(chr_pixbuf)
        else:
            chr_icon = Gtk.Label(label='󰗧')
            chr_icon.get_style_context().add_class('section-icon')
        chr_row.pack_start(chr_icon, False, False, 0)

        chr_title = Gtk.Label(label='Chromium')
        chr_title.get_style_context().add_class('section-title')
        chr_row.pack_start(chr_title, False, False, 0)

        self.btn_chr_mute = Gtk.Button(label='󰖁')
        self.btn_chr_mute.get_style_context().add_class('mute-btn')
        self.btn_chr_mute.connect('clicked', self._on_chr_mute)
        chr_row.pack_end(self.btn_chr_mute, False, False, 0)

        self.lbl_chr_pct = Gtk.Label(label='0%')
        self.lbl_chr_pct.get_style_context().add_class('pct-label')
        chr_row.pack_end(self.lbl_chr_pct, False, False, 0)

        self.scale_chr = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        self.scale_chr.set_draw_value(False)
        self.scale_chr.set_hexpand(True)
        self.scale_chr.connect('button-press-event', lambda *_: self._set_dragging('chr', True))
        self.scale_chr.connect('button-release-event', self._on_chr_release)
        self.scale_chr.connect('value-changed', self._on_chr_changed)
        card.pack_start(self.scale_chr, False, False, 0)

        self.lbl_chr_inactive = Gtk.Label(label='Вкладок со звуком нет')
        self.lbl_chr_inactive.get_style_context().add_class('inactive-label')
        card.pack_start(self.lbl_chr_inactive, False, False, 0)

    # ── Состояние ─────────────────────────────

    def _set_dragging(self, which, val):
        if which == 'sys':
            self._sys_dragging = val
        else:
            self._chr_dragging = val

    def _on_sys_release(self, *_):
        self._set_dragging('sys', False)

    def _on_chr_release(self, *_):
        self._set_dragging('chr', False)

    def _on_sys_changed(self, scale):
        v = scale.get_value()
        self.lbl_sys_pct.set_text(f'{int(v)}%')
        if self._sys_dragging:
            set_sink_volume(v)

    def _on_chr_changed(self, scale):
        v = scale.get_value()
        self.lbl_chr_pct.set_text(f'{int(v)}%')
        if self._chr_dragging:
            set_chromium_volume(self._chromium_ids, v)

    def _on_sys_mute(self, *_):
        toggle_sink_mute()
        GLib.timeout_add(80, self._refresh)

    def _on_chr_mute(self, *_):
        toggle_chromium_mute(self._chromium_ids)
        GLib.timeout_add(80, self._refresh)

    # ── Обновление из pactl ───────────────────

    def _tick(self):
        self._refresh()
        return True

    def _refresh(self):
        if not self._sys_dragging:
            vol = get_sink_volume()
            muted = get_sink_mute()
            self.scale_sys.set_value(vol)
            self.lbl_sys_pct.set_text(f'{vol}%')
            ctx = self.btn_sys_mute.get_style_context()
            if muted:
                ctx.add_class('muted')
            else:
                ctx.remove_class('muted')

        self._chromium_ids = get_chromium_ids()

        if self._chromium_ids:
            self.scale_chr.set_visible(True)
            self.lbl_chr_pct.set_visible(True)
            self.btn_chr_mute.set_visible(True)
            self.lbl_chr_inactive.set_visible(False)

            if not self._chr_dragging:
                vol, muted = get_chromium_volume(self._chromium_ids)
                self.scale_chr.set_value(vol)
                self.lbl_chr_pct.set_text(f'{vol}%')
                ctx = self.btn_chr_mute.get_style_context()
                if muted:
                    ctx.add_class('muted')
                else:
                    ctx.remove_class('muted')
        else:
            self.scale_chr.set_visible(False)
            self.lbl_chr_pct.set_visible(False)
            self.btn_chr_mute.set_visible(False)
            self.lbl_chr_inactive.set_visible(True)

        return False

    def _on_key(self, _w, event):
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()

    def _on_leave(self, widget, event):
        # event.detail == NOTIFY_INFERIOR значит курсор перешёл на дочерний виджет
        # внутри того же окна (например со слайдера на кнопку) — это не настоящий уход
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        if self._leave_timer is not None:
            GLib.source_remove(self._leave_timer)
        self._leave_timer = GLib.timeout_add(250, self._close_after_leave)

    def _on_enter(self, widget, event):
        if self._leave_timer is not None:
            GLib.source_remove(self._leave_timer)
            self._leave_timer = None

    def _close_after_leave(self):
        Gtk.main_quit()
        return False


# ─────────────────────────────────────────────

if __name__ == '__main__':
    win = VolumePopup()
    win.connect('destroy', Gtk.main_quit)
    win.show_all()
    Gtk.main()
