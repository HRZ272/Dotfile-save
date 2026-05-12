#!/usr/bin/env python3
"""
calendaR.py — Waybar calendar popup (tkinter, Catppuccin Mocha)
Position/geometry mirrored from weather_popup.py.
Closes on Escape.
"""

import tkinter as tk
import datetime
import calendar as cal_mod

# ── same as weather_popup.py ──────────────────────────────────────
WAYBAR_HEIGHT = 34
WIN_W         = 340
WIN_H         = 310

DAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

BG     = "#1e1e2e"
ACCENT = "#b4befe"
TEXT   = "#cdd6f4"
MUTED  = "#585b70"
SUB    = "#45475a"
PEACH  = "#fab387"
GREEN  = "#a6e3a1"
BLUE   = "#89b4fa"
RED    = "#f38ba8"

FONT = "JetBrains Mono"
RADIUS = 14


# ── rounded rect helper ───────────────────────────────────────────
def _rrect(cv, x1, y1, x2, y2, r, **kw):
    """Draw a rounded rectangle using a smooth polygon."""
    pts = [
        x1+r, y1,   x1+r, y1,
        x2-r, y1,   x2-r, y1,
        x2,   y1,
        x2,   y1+r, x2,   y1+r,
        x2,   y2-r, x2,   y2-r,
        x2,   y2,
        x2-r, y2,   x2-r, y2,
        x1+r, y2,   x1+r, y2,
        x1,   y2,
        x1,   y2-r, x1,   y2-r,
        x1,   y1+r, x1,   y1+r,
        x1,   y1,
    ]
    return cv.create_polygon(pts, smooth=True, **kw)


def _arrow(parent, text, cmd):
    b = tk.Label(parent, text=text, bg=BG, fg=BLUE,
                 font=(FONT, 16), cursor="hand2", padx=8)
    b.bind("<Button-1>", lambda _: cmd())
    b.bind("<Enter>",    lambda _: b.config(fg=ACCENT))
    b.bind("<Leave>",    lambda _: b.config(fg=BLUE))
    return b


class CalApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=BG)
        self.resizable(False, False)

        self.today     = datetime.date.today()
        self.cur_month = self.today.month
        self.cur_year  = self.today.year

        # ── position: identical formula to weather_popup ──────────
        sw = self.winfo_screenwidth()
        x  = (sw - WIN_W) // 2
        y  = WAYBAR_HEIGHT + 4
        self.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        self._build()
        self._fill()

        # identical to weather_popup.py
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Button-4>", lambda _e: self._shift(-1))
        self.bind("<Button-5>", lambda _e: self._shift(1))
        self.bind("<FocusOut>", self._on_focus_out)
        self.after(150, lambda: (self.lift(), self.focus_force()))

    # ── build UI ─────────────────────────────────────────────────
    def _build(self):
        PAD = 14

        # Root canvas — draws the rounded border + fill
        cv = tk.Canvas(self, width=WIN_W, height=WIN_H,
                       bg=BG, highlightthickness=0)
        cv.place(x=0, y=0)
        self._cv = cv

        # Border (accent colour, 2 px thick)
        _rrect(cv, 1, 1, WIN_W-1, WIN_H-1, RADIUS,
               fill=ACCENT, outline="")
        # Inner fill
        _rrect(cv, 3, 3, WIN_W-3, WIN_H-3, RADIUS-2,
               fill=BG, outline="")

        # Content frame on top of canvas
        frame = tk.Frame(cv, bg=BG)
        cv.create_window(WIN_W//2, WIN_H//2, window=frame)

        # ── header ───────────────────────────────────────────────
        hdr = tk.Frame(frame, bg=BG, pady=8)
        hdr.pack(fill="x", padx=PAD)
        _arrow(hdr, "‹", lambda: self._shift(-1)).pack(side="left")
        self.lbl_month = tk.Label(hdr, text="", bg=BG, fg=ACCENT,
                                  font=(FONT, 14, "bold"))
        self.lbl_month.pack(side="left", expand=True)
        _arrow(hdr, "›", lambda: self._shift(1)).pack(side="right")

        # ── grid ─────────────────────────────────────────────────
        g = tk.Frame(frame, bg=BG)
        g.pack(padx=PAD, pady=(0, 8))

        # week-num spacer
        tk.Label(g, text="", bg=BG, width=3).grid(row=0, column=0)

        # day name headers
        for c, d in enumerate(DAYS):
            fg = RED if d in ("Sa", "Su") else PEACH
            tk.Label(g, text=d, bg=BG, fg=fg,
                     font=(FONT, 10, "bold"), width=4,
                     anchor="center").grid(row=0, column=c+1, pady=(0, 4))

        # 6 week rows — each day cell is a Canvas for circle drawing
        self.week_lbls = []
        self.day_cells = []
        for r in range(6):
            wl = tk.Label(g, text="", bg=BG, fg=GREEN,
                          font=(FONT, 9), width=3, anchor="e")
            wl.grid(row=r+1, column=0, padx=(0, 4))
            self.week_lbls.append(wl)

            row_cells = []
            for c in range(7):
                cell = tk.Canvas(g, width=28, height=28, bg=BG,
                                 highlightthickness=0)
                cell.grid(row=r+1, column=c+1, padx=1, pady=1)
                row_cells.append(cell)
            self.day_cells.append(row_cells)

    # ── fill calendar ─────────────────────────────────────────────
    def _fill(self):
        self.lbl_month.config(
            text=datetime.date(self.cur_year, self.cur_month, 1).strftime("%B %Y"))

        weeks = cal_mod.Calendar(firstweekday=0).monthdatescalendar(
            self.cur_year, self.cur_month)
        while len(weeks) < 6:
            weeks.append([d + datetime.timedelta(days=7) for d in weeks[-1]])

        for r, week in enumerate(weeks[:6]):
            self.week_lbls[r].config(text=str(week[0].isocalendar()[1]))
            for c, day in enumerate(week):
                cell = self.day_cells[r][c]
                cell.delete("all")
                W, H = 28, 28

                if day == self.today:
                    m = 2
                    cell.create_oval(m, m, W-m, H-m,
                                     fill=ACCENT, outline="")
                    cell.create_text(W//2, H//2, text=str(day.day),
                                     fill=BG, font=(FONT, 11, "bold"))
                else:
                    if day.month != self.cur_month:
                        fg = MUTED
                    elif c >= 5:
                        fg = RED
                    else:
                        fg = TEXT
                    cell.create_text(W//2, H//2, text=str(day.day),
                                     fill=fg, font=(FONT, 11))

    # ── navigation ────────────────────────────────────────────────
    def _shift(self, delta):
        m = self.cur_month - 1 + delta
        self.cur_year  += m // 12
        self.cur_month  = m % 12 + 1
        self._fill()

    def _on_focus_out(self, event):
        self.after(50, lambda: self.destroy() if not self.focus_displayof() else None)


if __name__ == "__main__":
    CalApp().mainloop()
