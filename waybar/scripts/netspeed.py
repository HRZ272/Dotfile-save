#!/usr/bin/env python3
import json, time

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

def read_bytes(iface):
    with open("/proc/net/dev") as f:
        for line in f:
            if line.strip().startswith(iface + ":"):
                d = line.split(":", 1)[1].split()
                return int(d[0]), int(d[8])
    return None

def fmt(b):
    for u in ("B", "K", "M", "G"):
        if b < 1024 or u == "G":
            return f"{b:.0f}{u}"
        b /= 1024

prev = None
prev_iface = None
while True:
    iface = default_iface()
    if not iface:
        print(json.dumps({"text": "󰖪 offline", "class": "offline",
                          "tooltip": "Нет сети"}), flush=True)
        prev = None
        time.sleep(1)
        continue

    cur = read_bytes(iface)
    now = time.time()
    if cur and prev and iface == prev_iface:
        dt = now - prev[2]
        rx = (cur[0] - prev[0]) / dt
        tx = (cur[1] - prev[1]) / dt
        print(json.dumps({
            "text": f"󰇚 {fmt(rx)}",
            "tooltip": f"{iface}\n↓ {fmt(rx)}/s\n↑ {fmt(tx)}/s\nКлик: тест скорости",
            "class": "active" if rx > 10240 else "idle",
        }), flush=True)
    if cur:
        prev = (cur[0], cur[1], now)
        prev_iface = iface
    time.sleep(1)
