#!/usr/bin/env python3
import os, re, signal, subprocess, sys, threading, time
from urllib.request import Request, urlopen

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell

PIDFILE = f"/run/user/{os.getuid()}/speedtest_popup.pid"
CF = "https://speed.cloudflare.com"
HDR = {"User-Agent": "Mozilla/5.0"}
PING_HOST = "1.1.1.1"
DURATION = 8   # секунд на каждую фазу
THREADS = 4

# --- toggle: повторный клик закрывает попап ---
try:
    old = int(open(PIDFILE).read())
    os.kill(old, 0)
    os.kill(old, signal.SIGTERM)
    sys.exit(0)
except (FileNotFoundError, ProcessLookupError, ValueError):
    pass
open(PIDFILE, "w").write(str(os.getpid()))

def default_iface():
    try:
        with open("/proc/net/route") as f:
            next(f)
            for line in f:
                p = line.split()
                if p[1] == "00000000" and int(p[3], 16) & 2:
                    return p[0]
    except Exception:
        pass
    return None

def conn_name(iface):
    if not iface:
        return "Нет подключения"
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"],
            capture_output=True, text=True, timeout=3).stdout
        for l in out.splitlines():
            name, _, dev = l.rpartition(":")
            if dev == iface:
                return name.replace("\\:", ":")
    except Exception:
        pass
    return iface

def do_ping():
    try:
        out = subprocess.run(["ping", "-c", "5", "-i", "0.2", "-q", PING_HOST],
                             capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)", out)
        if m:
            return float(m.group(2)), float(m.group(4))  # avg, jitter
    except Exception:
        pass
    return None

class Body:
    """file-like тело для upload со счётчиком"""
    def __init__(self, size, add, stop):
        self.left, self.add, self.stop = size, add, stop
    def read(self, n=-1):
        if self.left <= 0 or time.time() > self.stop:
            return b""
        n = min(n if n and n > 0 else 65536, self.left)
        self.left -= n
        self.add(n)
        return bytes(n)

def dl_worker(add, stop):
    while time.time() < stop:
        try:
            with urlopen(Request(f"{CF}/__down?bytes=25000000", headers=HDR), timeout=10) as r:
                while time.time() < stop:
                    b = r.read(65536)
                    if not b:
                        break
                    add(len(b))
        except Exception:
            time.sleep(0.2)

def ul_worker(add, stop):
    size = 10_000_000
    while time.time() < stop:
        try:
            req = Request(f"{CF}/__up", data=Body(size, add, stop), method="POST",
                          headers={**HDR, "Content-Length": str(size),
                                   "Content-Type": "application/octet-stream"})
            urlopen(req, timeout=15).read()
        except Exception:
            time.sleep(0.2)

CSS = b"""
window { background: rgba(24,24,32,0.95); border-radius: 14px;
         border: 1px solid rgba(255,255,255,0.12); }
label { color: #e6e6ef; font-family: monospace; }
.title { font-size: 16px; font-weight: bold; }
.sub { font-size: 11px; color: #8a8aa0; }
.key { font-size: 13px; color: #8a8aa0; }
.val { font-size: 22px; font-weight: bold; }
button { background: #2b2b3b; color: #e6e6ef; border-radius: 8px; border: none; padding: 6px 14px; }
button:hover { background: #3a3a50; }
"""

class Popup(Gtk.Window):
    def __init__(self):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, 8)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, 8)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(18)
        self.add(box)

        self.l_name = self.lbl("…", "title")
        self.l_iface = self.lbl("", "sub")
        box.pack_start(self.l_name, False, False, 0)
        box.pack_start(self.l_iface, False, False, 4)

        grid = Gtk.Grid(column_spacing=24, row_spacing=6)
        box.pack_start(grid, False, False, 4)
        self.v_ping = self.lbl("—", "val")
        self.v_jit = self.lbl("", "sub")
        self.v_dl = self.lbl("—", "val")
        self.v_ul = self.lbl("—", "val")
        for i, (k, v) in enumerate([("Пинг", self.v_ping), ("Вход ↓", self.v_dl), ("Исход ↑", self.v_ul)]):
            kl = self.lbl(k, "key")
            kl.set_xalign(0); v.set_xalign(0)
            grid.attach(kl, 0, i, 1, 1)
            grid.attach(v, 1, i, 1, 1)
        grid.attach(self.v_jit, 2, 0, 1, 1)

        self.status = self.lbl("", "sub")
        box.pack_start(self.status, False, False, 0)
        self.btn = Gtk.Button(label="Повторить")
        self.btn.connect("clicked", lambda *_: self.start())
        box.pack_start(self.btn, False, False, 4)

        self.connect("key-press-event",
                     lambda w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else None)
        self.connect("destroy", lambda *_: Gtk.main_quit())
        self.set_default_size(300, -1)
        self.show_all()
        self.start()

    @staticmethod
    def lbl(text, cls):
        l = Gtk.Label(label=text)
        l.get_style_context().add_class(cls)
        l.set_xalign(0)
        return l

    def start(self):
        self.btn.set_sensitive(False)
        for l in (self.v_ping, self.v_dl, self.v_ul):
            l.set_text("—")
        self.v_jit.set_text("")
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        ui = GLib.idle_add
        iface = default_iface()
        ui(self.l_name.set_text, conn_name(iface))
        ui(self.l_iface.set_text, f"интерфейс: {iface or 'нет'}")

        ui(self.status.set_text, "Пинг…")
        p = do_ping()
        if p:
            ui(self.v_ping.set_text, f"{p[0]:.1f} ms")
            ui(self.v_jit.set_text, f"jitter {p[1]:.1f}")
        else:
            ui(self.v_ping.set_text, "fail")

        ui(self.status.set_text, "Скачивание…")
        self.measure(dl_worker, self.v_dl)
        ui(self.status.set_text, "Отдача…")
        self.measure(ul_worker, self.v_ul)

        ui(self.status.set_text, f"Готово · сервер: Cloudflare")
        ui(self.btn.set_sensitive, True)

    def measure(self, worker, label):
        ui = GLib.idle_add
        total = [0]
        lock = threading.Lock()
        def add(n):
            with lock:
                total[0] += n
        start = time.time()
        stop = start + DURATION
        for _ in range(THREADS):
            threading.Thread(target=worker, args=(add, stop), daemon=True).start()
        last, lastt = 0, start
        while time.time() < stop:
            time.sleep(0.25)
            now, cur = time.time(), total[0]
            mbit = (cur - last) * 8 / (now - lastt) / 1e6
            last, lastt = cur, now
            ui(label.set_text, f"{mbit:.1f} Mbit/s")
        avg = total[0] * 8 / (time.time() - start) / 1e6
        ui(label.set_text, f"{avg:.1f} Mbit/s")

def cleanup(*_):
    try: os.remove(PIDFILE)
    except FileNotFoundError: pass
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)
Popup()
try:
    Gtk.main()
finally:
    try: os.remove(PIDFILE)
    except FileNotFoundError: pass
