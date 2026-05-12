#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weather_popup.py — 3-day forecast popup for Waybar
Edit LAT/LON and WAYBAR_HEIGHT below.
Deps: python3-tkinter, python3-requests
"""

import tkinter as tk
import requests
import threading
import locale
import os

os.environ.setdefault("LANG", "ru_RU.UTF-8")
os.environ.setdefault("LC_ALL", "ru_RU.UTF-8")
try:
    locale.setlocale(locale.LC_ALL, "ru_RU.UTF-8")
except locale.Error:
    pass

LAT           = "55.697726"
LON           = "37.321721"
LANG          = "ru"
WAYBAR_HEIGHT = 34    # высота Waybar в пикселях — подправьте под себя
WIN_W         = 740
WIN_H         = 460

WEATHER_CODES = {
    "113": "☀",  "116": "⛅", "119": "☁",  "122": "☁",
    "143": "≡",  "176": "🌦", "179": "🌨", "182": "🌧",
    "185": "🌧", "200": "⛈", "227": "❄",  "230": "❄",
    "248": "≡",  "260": "≡",  "263": "🌦", "266": "🌧",
    "281": "🌧", "284": "🌧", "293": "🌦", "296": "🌦",
    "299": "🌧", "302": "🌧", "305": "🌧", "308": "🌧",
    "311": "🌧", "314": "🌧", "317": "🌨", "320": "🌨",
    "323": "🌨", "326": "🌨", "329": "❄",  "332": "❄",
    "335": "❄",  "338": "❄",  "350": "🌧", "353": "🌦",
    "356": "🌧", "359": "🌧", "362": "🌨", "365": "🌨",
    "368": "🌨", "371": "❄",  "374": "🌨", "377": "🌨",
    "386": "⛈", "389": "⛈", "392": "⛈", "395": "❄",
}

MONTHS_RU = ["", "янв", "фев", "мар", "апр", "май", "июн",
             "июл", "авг", "сен", "окт", "ноя", "дек"]

BG     = "#1e1e2e"
BG2    = "#313244"
BG3    = "#45475a"
ACCENT = "#89b4fa"
TEXT   = "#cdd6f4"
SUB    = "#a6adc8"
RED    = "#f38ba8"
BLUE   = "#89dceb"

FSANS = "JetBrains Mono Nerd Font"
FMONO = "JetBrains Mono Nerd Font"


def wind_dir(deg):
    dirs = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    return dirs[round(int(deg) / 45) % 8]


def fmt_date(date_str):
    _, m, d = date_str.split("-")
    return f"{int(d)} {MONTHS_RU[int(m)]}"


def moon_phase(s):
    return {
        "New Moon": "🌑", "Waxing Crescent": "🌒", "First Quarter": "🌓",
        "Waxing Gibbous": "🌔", "Full Moon": "🌕", "Waning Gibbous": "🌖",
        "Last Quarter": "🌗", "Waning Crescent": "🌘",
    }.get(s, "🌙")


def get_weather():
    url = f"https://wttr.in/{LAT},{LON}?format=j1&lang={LANG}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    import json
    return json.loads(r.content.decode("utf-8"))


class WeatherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Прогноз погоды")
        self.configure(bg=BG)
        self.resizable(False, False)

        # Позиция: сразу под Waybar, по центру
        sw = self.winfo_screenwidth()
        x  = (sw - WIN_W) // 2
        y  = WAYBAR_HEIGHT + 4
        self.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        # Закрывать ТОЛЬКО по Escape
        self.bind("<Escape>", lambda _e: self.destroy())
        # НЕ закрываем при потере фокуса

        self._loading_frame = tk.Frame(self, bg=BG)
        self._loading_frame.pack(expand=True, fill="both")
        tk.Label(
            self._loading_frame, text="Загрузка прогноза...",
            bg=BG, fg=SUB, font=(FSANS, 13),
        ).place(relx=0.5, rely=0.5, anchor="center")

        self.after(60, self._fetch)

    # ── helpers ───────────────────────────────────────────────────

    def _lbl(self, parent, text, fg=TEXT, font=None, **kw):
        f = font or (FSANS, 10)
        return tk.Label(parent, text=text, bg=parent["bg"], fg=fg, font=f, **kw)

    def _sep(self, parent, pady=4):
        tk.Frame(parent, bg=BG3, height=1).pack(fill="x", pady=pady)

    # ── data fetch ────────────────────────────────────────────────

    def _fetch(self):
        def task():
            try:
                data = get_weather()
                self.after(0, lambda: self._render(data))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._show_error(msg))
        threading.Thread(target=task, daemon=True).start()

    def _show_error(self, msg):
        self._loading_frame.destroy()
        tk.Label(self, text=f"Ошибка:\n{msg}",
                 bg=BG, fg=RED, font=(FSANS, 11), wraplength=660).pack(expand=True)

    # ── render ────────────────────────────────────────────────────

    def _render(self, data):
        self._loading_frame.destroy()

        cur     = data["current_condition"][0]
        weather = data["weather"][:3]

        # ── Шапка: текущие условия ────────────────────────────────
        hdr = tk.Frame(self, bg=BG2, padx=14, pady=10)
        hdr.pack(fill="x")

        code  = cur.get("weatherCode", "113")
        icon  = WEATHER_CODES.get(code, "?")
        temp  = cur["temp_C"]
        feels = cur["FeelsLikeC"]
        desc  = (cur["lang_ru"][0]["value"]
                 if cur.get("lang_ru") else cur["weatherDesc"][0]["value"])
        humid = cur["humidity"]
        wspd  = cur["windspeedKmph"]
        wdir  = wind_dir(cur.get("winddirDegree", 0))
        vis   = cur["visibility"]
        pres  = cur["pressure"]

        self._lbl(hdr, icon, font=(FSANS, 26)).pack(side="left", padx=(0, 12))

        info = tk.Frame(hdr, bg=BG2)
        info.pack(side="left")
        self._lbl(info, f"{temp}°C  {desc}",
                  fg=TEXT, font=(FSANS, 15, "bold")).pack(anchor="w")
        self._lbl(info,
                  f"Ощущается {feels}°C  •  Влажность {humid}%  •  "
                  f"Ветер {wdir} {wspd} км/ч  •  Вид. {vis} км  •  {pres} гПа",
                  fg=SUB, font=(FSANS, 9)).pack(anchor="w")

        tk.Button(
            hdr, text="✕", bg=BG2, fg=SUB,
            activebackground=BG2, activeforeground=RED,
            bd=0, font=(FSANS, 13), cursor="hand2",
            command=self.destroy,
        ).pack(side="right")

        # ── 3 дня ─────────────────────────────────────────────────
        row = tk.Frame(self, bg=BG)
        row.pack(fill="both", expand=True, padx=10, pady=8)

        for i, day in enumerate(weather):
            col = tk.Frame(row, bg=BG2, padx=10, pady=8)
            col.pack(side="left", fill="both", expand=True,
                     padx=(0 if i == 0 else 6, 0))

            astro   = day["astronomy"][0]
            midday  = day["hourly"][4]         # ~12:00
            d_code  = midday.get("weatherCode", "113")
            d_icon  = WEATHER_CODES.get(d_code, "?")
            d_desc  = (midday["lang_ru"][0]["value"]
                       if midday.get("lang_ru")
                       else midday["weatherDesc"][0]["value"])

            # Заголовок
            self._lbl(col, fmt_date(day["date"]),
                      fg=ACCENT, font=(FSANS, 11, "bold")).pack()
            # Иконка дня
            self._lbl(col, d_icon, font=(FSANS, 24)).pack(pady=(2, 1))
            # Описание
            self._lbl(col, d_desc, fg=TEXT,
                      font=(FSANS, 9), wraplength=190).pack()
            # Макс/мин
            tr = tk.Frame(col, bg=BG2)
            tr.pack(pady=3)
            self._lbl(tr, f"▲ {day['maxtempC']}°",
                      fg=RED, font=(FSANS, 12, "bold")).pack(side="left", padx=4)
            self._lbl(tr, f"▼ {day['mintempC']}°",
                      fg=BLUE, font=(FSANS, 12, "bold")).pack(side="left", padx=4)

            self._sep(col)

            # Почасовой прогноз
            for h in day["hourly"]:
                t_hour = int(h["time"]) // 100
                ht_val = int(h["tempC"])          # строку → int
                rain   = float(h.get("precipMM", "0") or "0")
                snow   = float(h.get("snowDepth_cm", "0") or "0")

                if snow > 0:
                    precip = f"❄{snow:.0f}см"
                elif rain > 0:
                    precip = f"🌧{rain:.1f}мм"
                else:
                    precip = "—"

                sign   = "+" if ht_val >= 0 else ""
                hrow   = tk.Frame(col, bg=BG2)
                hrow.pack(fill="x")
                self._lbl(hrow, f"{t_hour:02d}:00",
                          fg=SUB,  font=(FMONO, 8), width=5,
                          anchor="w").pack(side="left")
                self._lbl(hrow, f"{sign}{ht_val}°C",
                          fg=TEXT, font=(FMONO, 8), width=5,
                          anchor="e").pack(side="left", padx=(4, 0))
                self._lbl(hrow, f"  {precip}",
                          fg=(BLUE if precip != "—" else SUB),
                          font=(FMONO, 8)).pack(side="left")

            self._sep(col)

            # Астрономия
            self._lbl(col,
                      f"🌅{astro['sunrise']}  🌇{astro['sunset']}"
                      f"  {moon_phase(astro['moon_phase'])}  ☀UV{day['uvIndex']}",
                      fg=SUB, font=(FSANS, 8)).pack()


if __name__ == "__main__":
    app = WeatherApp()
    app.mainloop()
