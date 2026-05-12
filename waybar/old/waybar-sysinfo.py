#!/usr/bin/env python3
"""
Waybar System Dashboard — CPU · GPU · RAM · Temps
Запуск: python3 waybar-sysinfo.py
Повторный запуск — закрывает (toggle).
Зависимости: python3-gi, python3-psutil
  pip install psutil  /  sudo pacman -S python-psutil
GPU (NVIDIA): nvidia-smi   GPU (AMD): читает /sys
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo, math, os, sys, signal, subprocess, time, threading

PID_FILE = "/tmp/waybar-sysinfo.pid"

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

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ── цвета ────────────────────────────────────────────────────────────────────
BG      = (0.098, 0.098, 0.149)
SURF    = (0.149, 0.153, 0.220)
OVERLAY = (0.220, 0.227, 0.318)
TEXT    = (0.820, 0.855, 0.965)
SUB     = (0.494, 0.518, 0.655)
PURPLE  = (0.498, 0.322, 1.000)
BLUE    = (0.388, 0.647, 1.000)
GREEN   = (0.196, 0.800, 0.502)
AMBER   = (0.941, 0.616, 0.110)
RED     = (0.886, 0.290, 0.290)
TEAL    = (0.149, 0.780, 0.749)


def lerp_color(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def load_color(pct):
    if pct < 50:
        return lerp_color(GREEN, AMBER, pct / 50)
    return lerp_color(AMBER, RED, (pct - 50) / 50)


def temp_color(t):
    if t < 55:  return GREEN
    if t < 75:  return AMBER
    return RED


# ── сбор данных ──────────────────────────────────────────────────────────────
class SysData:
    def __init__(self):
        self.cpu_pct   = 0.0
        self.cpu_cores = []
        self.cpu_freq  = 0
        self.cpu_temp  = 0.0
        self.ram_used  = 0
        self.ram_total = 0
        self.ram_pct   = 0.0
        self.swap_used = 0
        self.swap_total= 0
        self.gpu_pct   = -1.0
        self.gpu_mem_used  = -1
        self.gpu_mem_total = -1
        self.gpu_temp  = -1.0
        self.gpu_name  = ""
        self.disks     = []
        self.net_up    = 0.0
        self.net_dn    = 0.0
        self._net_prev = None
        self._net_ts   = None

    def update(self):
        self._update_cpu()
        self._update_ram()
        self._update_gpu()
        self._update_disk()
        self._update_net()

    def _update_cpu(self):
        if not HAS_PSUTIL:
            return
        self.cpu_pct   = psutil.cpu_percent(interval=None)
        self.cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
        freq = psutil.cpu_freq()
        self.cpu_freq  = int(freq.current) if freq else 0
        try:
            for name, entries in psutil.sensors_temperatures().items():
                for e in entries:
                    if any(k in e.label.lower() for k in ("core 0", "cpu", "tdie", "tccd", "package")):
                        self.cpu_temp = e.current
                        return
                # fallback: первое попавшееся
                if entries and self.cpu_temp == 0:
                    self.cpu_temp = entries[0].current
        except Exception:
            pass

    def _update_ram(self):
        if not HAS_PSUTIL:
            return
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        self.ram_used  = vm.used
        self.ram_total = vm.total
        self.ram_pct   = vm.percent
        self.swap_used  = sw.used
        self.swap_total = sw.total

    def _update_gpu(self):
        # NVIDIA
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=1
            ).decode().strip()
            parts = [p.strip() for p in out.split(",")]
            self.gpu_pct       = float(parts[0])
            self.gpu_mem_used  = int(parts[1])
            self.gpu_mem_total = int(parts[2])
            self.gpu_temp      = float(parts[3])
            self.gpu_name      = parts[4] if len(parts) > 4 else "NVIDIA GPU"
            return
        except Exception:
            pass
        # AMD — /sys
        try:
            base = "/sys/class/drm/card0/device"
            busy = open(f"{base}/gpu_busy_percent").read().strip()
            self.gpu_pct = float(busy)
            try:
                self.gpu_temp = float(
                    open(f"{base}/hwmon/hwmon0/temp1_input").read().strip()
                ) / 1000
            except Exception:
                pass
            self.gpu_name = "AMD GPU"
        except Exception:
            pass

    def _update_disk(self):
        if not HAS_PSUTIL:
            return
        self.disks = []
        for part in psutil.disk_partitions():
            if any(x in part.fstype for x in ("tmpfs", "devtmpfs", "squash")):
                continue
            try:
                u = psutil.disk_usage(part.mountpoint)
                self.disks.append({
                    "mount": part.mountpoint,
                    "used":  u.used,
                    "total": u.total,
                    "pct":   u.percent,
                })
            except Exception:
                pass

    def _update_net(self):
        if not HAS_PSUTIL:
            return
        try:
            now   = time.monotonic()
            cnt   = psutil.net_io_counters()
            if self._net_prev and self._net_ts:
                dt = now - self._net_ts
                if dt > 0:
                    self.net_up = (cnt.bytes_sent - self._net_prev.bytes_sent) / dt
                    self.net_dn = (cnt.bytes_recv - self._net_prev.bytes_recv) / dt
            self._net_prev = cnt
            self._net_ts   = now
        except Exception:
            pass


def fmt_bytes(b):
    if b < 1024:          return f"{b:.0f} B"
    if b < 1024**2:       return f"{b/1024:.1f} KB"
    if b < 1024**3:       return f"{b/1024**2:.1f} MB"
    return                       f"{b/1024**3:.2f} GB"


def fmt_speed(bps):
    if bps < 1024:        return f"{bps:.0f} B/s"
    if bps < 1024**2:     return f"{bps/1024:.0f} KB/s"
    return                       f"{bps/1024**2:.1f} MB/s"


# ── главное окно ─────────────────────────────────────────────────────────────
class Dashboard(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.data = SysData()
        self.data.update()          # первый прогрев

        self.set_title("System Dashboard")
        self.set_default_size(400, 560)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        self._apply_css()
        self._build()
        self.connect("destroy", self._on_destroy)

        # обновление каждую секунду в фоне
        self._stop = False
        self._thread = threading.Thread(target=self._bg_update, daemon=True)
        self._thread.start()

        self.show_all()

    # ── CSS ──────────────────────────────────────────────────────────────────
    def _apply_css(self):
        css = b"""
        window { background: #191927; }
        .section {
            background: #262638;
            border-radius: 12px;
            padding: 2px;
            border: 1px solid #2e2e46;
        }
        .section-title {
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.5px;
        }
        .section-title label { color: #7a7a9a; font-size: 10px; }
        .val { font-size: 22px; font-weight: 700; font-family: monospace; }
        .val label { color: #d0d8f8; font-size: 22px; }
        .sub label { color: #7a7a9a; font-size: 11px; }
        """
        p = Gtk.CssProvider()
        p.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # ── build ─────────────────────────────────────────────────────────────────
    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(14); root.set_margin_bottom(14)
        root.set_margin_start(14); root.set_margin_end(14)
        self.add(root)

        # ── заголовок ────────────────────────────────────────────────────────
        hdr = Gtk.Label(label="SYSTEM DASHBOARD")
        hdr.get_style_context().add_class("section-title")
        hdr.set_halign(Gtk.Align.START)
        root.pack_start(hdr, False, False, 0)

        # ── CPU + GPU кружки ─────────────────────────────────────────────────
        top_row = Gtk.Box(spacing=10)
        root.pack_start(top_row, False, False, 0)

        self.cpu_canvas = self._make_ring_canvas()
        self.gpu_canvas = self._make_ring_canvas()

        top_row.pack_start(self._wrap_section(self.cpu_canvas, "CPU"), True, True, 0)
        top_row.pack_start(self._wrap_section(self.gpu_canvas, "GPU"), True, True, 0)

        # ── RAM ──────────────────────────────────────────────────────────────
        self.ram_canvas = Gtk.DrawingArea()
        self.ram_canvas.set_size_request(-1, 70)
        self.ram_canvas.connect("draw", self._draw_ram)
        root.pack_start(self._wrap_section(self.ram_canvas, "RAM / SWAP"), False, False, 0)

        # ── Ядра CPU ─────────────────────────────────────────────────────────
        self.cores_canvas = Gtk.DrawingArea()
        self.cores_canvas.set_size_request(-1, 54)
        self.cores_canvas.connect("draw", self._draw_cores)
        root.pack_start(self._wrap_section(self.cores_canvas, "CPU CORES"), False, False, 0)

        # ── Диски ────────────────────────────────────────────────────────────
        self.disk_canvas = Gtk.DrawingArea()
        self.disk_canvas.set_size_request(-1, 20)
        self.disk_canvas.connect("draw", self._draw_disks)
        root.pack_start(self._wrap_section(self.disk_canvas, "ДИСКИ"), False, False, 0)

        # ── Сеть ─────────────────────────────────────────────────────────────
        self.net_canvas = Gtk.DrawingArea()
        self.net_canvas.set_size_request(-1, 32)
        self.net_canvas.connect("draw", self._draw_net)
        root.pack_start(self._wrap_section(self.net_canvas, "СЕТЬ"), False, False, 0)

        # подключаем отрисовку кружков
        self.cpu_canvas.connect("draw", self._draw_cpu_ring)
        self.gpu_canvas.connect("draw", self._draw_gpu_ring)

    def _make_ring_canvas(self):
        c = Gtk.DrawingArea()
        c.set_size_request(160, 160)
        return c

    def _wrap_section(self, widget, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("section")
        box.set_margin_top(2); box.set_margin_bottom(2)
        box.set_margin_start(2); box.set_margin_end(2)

        lbl_box = Gtk.Box()
        lbl_box.set_margin_start(10); lbl_box.set_margin_top(8)
        lbl = Gtk.Label(label=title)
        lbl.get_style_context().add_class("section-title")
        lbl_box.pack_start(lbl, False, False, 0)
        box.pack_start(lbl_box, False, False, 0)
        box.pack_start(widget, True, True, 0)

        pad = Gtk.Box()
        pad.set_size_request(-1, 8)
        box.pack_start(pad, False, False, 0)
        return box

    # ── отрисовка ─────────────────────────────────────────────────────────────
    def _draw_ring(self, cr, w, h, pct, color, label_top, label_val, label_bot):
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 18

        # фон кольца
        cr.set_source_rgba(*OVERLAY, 0.6)
        cr.set_line_width(12)
        cr.arc(cx, cy, R, 0, 2 * math.pi)
        cr.stroke()

        # дуга прогресса
        p = max(0, min(pct, 100)) / 100
        cr.set_source_rgb(*color)
        cr.set_line_width(12)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        start = -math.pi / 2
        cr.arc(cx, cy, R, start, start + 2 * math.pi * p)
        cr.stroke()

        # точка на конце
        if p > 0.01:
            ea = start + 2 * math.pi * p
            cr.set_source_rgb(*color)
            cr.arc(cx + R * math.cos(ea), cy + R * math.sin(ea), 5, 0, 2 * math.pi)
            cr.fill()

        # текст внутри
        cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(10)
        cr.set_source_rgba(*SUB, 0.9)
        e = cr.text_extents(label_top)
        cr.move_to(cx - e.width / 2, cy - 16)
        cr.show_text(label_top)

        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(24)
        cr.set_source_rgb(*TEXT)
        e = cr.text_extents(label_val)
        cr.move_to(cx - e.width / 2, cy + 9)
        cr.show_text(label_val)

        cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9.5)
        cr.set_source_rgba(*SUB, 0.8)
        e = cr.text_extents(label_bot)
        cr.move_to(cx - e.width / 2, cy + 26)
        cr.show_text(label_bot)

    def _draw_cpu_ring(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        d = self.data
        color = load_color(d.cpu_pct)
        top = f"{d.cpu_temp:.0f}°C" if d.cpu_temp else "—"
        val = f"{d.cpu_pct:.0f}%"
        bot = f"{d.cpu_freq} MHz" if d.cpu_freq else ""
        self._draw_ring(cr, w, h, d.cpu_pct, color, top, val, bot)

    def _draw_gpu_ring(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        d = self.data
        if d.gpu_pct < 0:
            # нет GPU данных
            cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(12)
            cr.set_source_rgba(*SUB, 0.7)
            cr.move_to(w / 2 - 28, h / 2)
            cr.show_text("нет данных")
            return
        color = load_color(d.gpu_pct)
        temp  = f"{d.gpu_temp:.0f}°C" if d.gpu_temp >= 0 else "—"
        val   = f"{d.gpu_pct:.0f}%"
        if d.gpu_mem_total > 0:
            bot = f"{fmt_bytes(d.gpu_mem_used*1024**2)} / {fmt_bytes(d.gpu_mem_total*1024**2)}"
        else:
            bot = ""
        self._draw_ring(cr, w, h, d.gpu_pct, color, temp, val, bot)

    def _draw_ram(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        d = self.data
        pad = 12
        bar_h = 14
        r = 6

        def draw_bar(y, used, total, color, label_l, label_r):
            bw = w - pad * 2
            pct = used / total if total else 0

            # фон
            cr.set_source_rgba(*OVERLAY, 0.5)
            self._rounded_rect(cr, pad, y, bw, bar_h, r)
            cr.fill()

            # заполнение
            fill_w = max(r * 2, bw * pct)
            cr.set_source_rgb(*color)
            self._rounded_rect(cr, pad, y, fill_w, bar_h, r)
            cr.fill()

            # текст
            cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(10)
            cr.set_source_rgb(*TEXT)
            cr.move_to(pad + 6, y + bar_h - 3)
            cr.show_text(label_l)
            e = cr.text_extents(label_r)
            cr.move_to(pad + bw - e.width - 6, y + bar_h - 3)
            cr.show_text(label_r)

        ram_color = load_color(d.ram_pct)
        draw_bar(
            8, d.ram_used, d.ram_total, ram_color,
            f"RAM  {fmt_bytes(d.ram_used)}",
            f"{fmt_bytes(d.ram_total)}  {d.ram_pct:.0f}%",
        )
        if d.swap_total > 0:
            sw_pct = d.swap_used / d.swap_total * 100
            draw_bar(
                32, d.swap_used, d.swap_total, TEAL,
                f"SWAP  {fmt_bytes(d.swap_used)}",
                f"{fmt_bytes(d.swap_total)}  {sw_pct:.0f}%",
            )

    def _draw_cores(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        cores = self.data.cpu_cores or []
        if not cores:
            return
        n = len(cores)
        pad = 12
        gap = 4
        bw = (w - pad * 2 - gap * (n - 1)) / n
        bar_h = h - 20
        r = 3

        for i, pct in enumerate(cores):
            x = pad + i * (bw + gap)
            color = load_color(pct)
            filled = bar_h * pct / 100

            # фон
            cr.set_source_rgba(*OVERLAY, 0.5)
            self._rounded_rect(cr, x, 6, bw, bar_h, r)
            cr.fill()

            # заполнение (снизу вверх)
            if filled > 0:
                cr.set_source_rgb(*color)
                self._rounded_rect(cr, x, 6 + bar_h - filled, bw, filled, r)
                cr.fill()

            # номер ядра
            cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(8)
            cr.set_source_rgba(*SUB, 0.8)
            e = cr.text_extents(str(i))
            cr.move_to(x + bw / 2 - e.width / 2, h - 2)
            cr.show_text(str(i))

    def _draw_disks(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        disks = self.data.disks
        if not disks:
            return

        # динамически расширяем высоту
        needed_h = len(disks) * 36 + 8
        if widget.get_allocated_height() < needed_h:
            widget.set_size_request(-1, needed_h)

        pad = 12; bar_h = 12; r = 4; row_h = 36

        for i, dk in enumerate(disks):
            y = 6 + i * row_h
            bw = w - pad * 2
            pct = dk["pct"]
            color = load_color(pct)

            # фон
            cr.set_source_rgba(*OVERLAY, 0.5)
            self._rounded_rect(cr, pad, y + 12, bw, bar_h, r)
            cr.fill()

            # заполнение
            fill_w = max(r * 2, bw * pct / 100)
            cr.set_source_rgb(*color)
            self._rounded_rect(cr, pad, y + 12, fill_w, bar_h, r)
            cr.fill()

            # метки
            cr.select_font_face("sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(10)
            cr.set_source_rgba(*SUB, 0.9)
            cr.move_to(pad, y + 9)
            cr.show_text(dk["mount"])

            rstr = f"{fmt_bytes(dk['used'])} / {fmt_bytes(dk['total'])}  {pct:.0f}%"
            cr.set_source_rgb(*TEXT)
            e = cr.text_extents(rstr)
            cr.move_to(pad + bw - e.width, y + 9)
            cr.show_text(rstr)

    def _draw_net(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        pad = 12

        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)

        # ↑ upload
        cr.set_source_rgb(*PURPLE)
        cr.move_to(pad, h / 2 + 5)
        cr.show_text(f"↑  {fmt_speed(self.data.net_up)}")

        # ↓ download
        cr.set_source_rgb(*TEAL)
        up_e = cr.text_extents(f"↑  {fmt_speed(self.data.net_up)}")
        cr.move_to(pad + up_e.width + 24, h / 2 + 5)
        cr.show_text(f"↓  {fmt_speed(self.data.net_dn)}")

    # ── helpers ───────────────────────────────────────────────────────────────
    def _rounded_rect(self, cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r,     r, -math.pi/2,  0)
        cr.arc(x + w - r, y + h - r, r,  0,           math.pi/2)
        cr.arc(x + r,     y + h - r, r,  math.pi/2,   math.pi)
        cr.arc(x + r,     y + r,     r,  math.pi,     3*math.pi/2)
        cr.close_path()

    # ── фоновое обновление ───────────────────────────────────────────────────
    def _bg_update(self):
        # первый вызов cpu_percent должен быть с interval=None после прогрева
        if HAS_PSUTIL:
            import psutil as _p
            _p.cpu_percent(interval=1)   # блокирует 1 с, зато даёт точные данные
        while not self._stop:
            self.data.update()
            GLib.idle_add(self._queue_redraw)
            time.sleep(1)

    def _queue_redraw(self):
        for c in [self.cpu_canvas, self.gpu_canvas,
                  self.ram_canvas, self.cores_canvas,
                  self.disk_canvas, self.net_canvas]:
            c.queue_draw()
        return False

    def _on_destroy(self, _):
        self._stop = True
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        Gtk.main_quit()


if __name__ == "__main__":
    if not HAS_PSUTIL:
        print("Установи psutil: pip install psutil  или  sudo pacman -S python-psutil")

    app = Dashboard()
    Gtk.main()
