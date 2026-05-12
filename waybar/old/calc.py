#!/usr/bin/env python3
"""
╭──────────────────────────────────────────────────╮
│  waybar-calc  │  Catppuccin Mocha + Lavender      │
│  Engineering mode · Numpad · Memory               │
╰──────────────────────────────────────────────────╯
"""

import tkinter as tk
from tkinter import font as tkfont
import math, re, sys

# ─── Catppuccin Mocha palette ────────────────────────────────────
C = {
    'base':      '#1e1e2e',
    'mantle':    '#181825',
    'crust':     '#11111b',
    'text':      '#cdd6f4',
    'subtext0':  '#a6adc8',
    'subtext1':  '#bac2de',
    'surface0':  '#313244',
    'surface1':  '#45475a',
    'surface2':  '#585b70',
    'overlay0':  '#6c7086',
    'overlay1':  '#7f849c',
    'lavender':  '#b4befe',
    'blue':      '#89b4fa',
    'sapphire':  '#74c7ec',
    'sky':       '#89dceb',
    'teal':      '#94e2d5',
    'green':     '#a6e3a1',
    'yellow':    '#f9e2af',
    'peach':     '#fab387',
    'maroon':    '#eba0ac',
    'red':       '#f38ba8',
    'mauve':     '#cba6f7',
    'pink':      '#f5c2e7',
    'flamingo':  '#f2cdcd',
    'rosewater': '#f5e0dc',
}

MONO_CANDIDATES = [
    'JetBrainsMono Nerd Font', 'JetBrains Mono',
    'Iosevka Nerd Font', 'Iosevka',
    'FiraCode Nerd Font', 'Fira Code',
    'Hack Nerd Font', 'Hack',
    'DejaVu Sans Mono', 'Liberation Mono', 'Courier New',
]

_font_cache: dict = {}

def _available_fonts():
    tmp = tk.Tk(); tmp.withdraw()
    fams = set(tkfont.families())
    tmp.destroy()
    return fams

def resolve_font(size, weight='normal'):
    key = (size, weight)
    if key in _font_cache:
        return _font_cache[key]
    avail = _available_fonts()
    for f in MONO_CANDIDATES:
        if f in avail:
            _font_cache[key] = (f, size, weight)
            return _font_cache[key]
    _font_cache[key] = ('TkFixedFont', size, weight)
    return _font_cache[key]

def hex_brighten(color, amt=22):
    r = min(255, int(color[1:3], 16) + amt)
    g = min(255, int(color[3:5], 16) + amt)
    b = min(255, int(color[5:7], 16) + amt)
    return f'#{r:02x}{g:02x}{b:02x}'


# ─── Rounded button (Canvas-based) ───────────────────────────────
class RndBtn(tk.Canvas):
    """Rounded-rectangle button drawn on a Canvas."""

    def __init__(self, parent, text, cmd,
                 fg=C['text'], bg=C['surface0'],
                 radius=10, font=None, **kw):
        super().__init__(parent, bg=parent.cget('bg'),
                         highlightthickness=0, bd=0, **kw)
        self._text  = text
        self._cmd   = cmd
        self._fg    = fg
        self._bg    = bg
        self._bg_h  = hex_brighten(bg, 22)
        self._r     = radius
        self._font  = font or resolve_font(13)
        self._hov   = False

        self.bind('<Configure>', lambda e: self._draw())
        self.bind('<Button-1>',  lambda e: cmd())
        self.bind('<Enter>',     lambda e: self._hover(True))
        self.bind('<Leave>',     lambda e: self._hover(False))

    def _hover(self, state):
        self._hov = state
        self._draw()

    def _draw(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        r  = min(self._r, w // 2, h // 2)
        bg = self._bg_h if self._hov else self._bg

        self.create_arc(0,     0,     2*r,   2*r,   start=90,  extent=90, fill=bg, outline=bg)
        self.create_arc(w-2*r, 0,     w,     2*r,   start=0,   extent=90, fill=bg, outline=bg)
        self.create_arc(0,     h-2*r, 2*r,   h,     start=180, extent=90, fill=bg, outline=bg)
        self.create_arc(w-2*r, h-2*r, w,     h,     start=270, extent=90, fill=bg, outline=bg)
        self.create_rectangle(r, 0,   w-r, h,   fill=bg, outline=bg)
        self.create_rectangle(0, r,   w,   h-r, fill=bg, outline=bg)

        self.create_text(w // 2, h // 2, text=self._text,
                         fill=self._fg, font=self._font)


# ─── Main window ─────────────────────────────────────────────────
class Calc(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('calc')
        self.resizable(False, False)
        self.configure(bg=C['base'])

        # State
        self.expr     = ''
        self.after_eq = False
        self.memory   = 0.0
        self.mem_set  = False
        self.eng      = False
        self.deg_mode = True

        # Fonts
        self.f_big  = resolve_font(22, 'bold')
        self.f_med  = resolve_font(11)
        self.f_sml  = resolve_font(9)
        self.f_expr = resolve_font(9)
        self.f_fn   = resolve_font(10)

        self._build()
        self._keybinds()
        self._center()

    # ── Layout ───────────────────────────────────────────────────

    def _build(self):
        border = tk.Frame(self, bg=C['crust'])
        border.pack(fill='both', expand=True)

        self._inner = tk.Frame(border, bg=C['base'])
        self._inner.pack(fill='both', expand=True)

        self._build_display()
        self.grid_frame = None
        self._build_grid()

    def _build_display(self):
        disp = tk.Frame(self._inner, bg=C['mantle'])
        disp.pack(fill='x')

        tk.Frame(disp, bg=C['lavender'], height=2).pack(fill='x')

        pad = tk.Frame(disp, bg=C['mantle'], padx=10, pady=6)
        pad.pack(fill='x')

        top = tk.Frame(pad, bg=C['mantle'])
        top.pack(fill='x')

        self.v_angle = tk.StringVar(value='DEG')
        tk.Label(top, textvariable=self.v_angle,
                 font=self.f_sml, bg=C['surface0'], fg=C['teal'],
                 padx=6, pady=2).pack(side='left')

        self.v_mem = tk.StringVar(value='')
        tk.Label(top, textvariable=self.v_mem,
                 font=self.f_sml, bg=C['mantle'], fg=C['mauve']
                 ).pack(side='left', padx=(8, 0))

        self.v_expr = tk.StringVar(value='')
        tk.Label(top, textvariable=self.v_expr,
                 font=self.f_expr, bg=C['mantle'], fg=C['overlay1'],
                 anchor='e').pack(side='right')

        self.v_main = tk.StringVar(value='0')
        tk.Label(pad, textvariable=self.v_main,
                 font=self.f_big, bg=C['mantle'], fg=C['text'],
                 anchor='e').pack(fill='x', pady=(6, 2))

    def _build_grid(self):
        if self.grid_frame is not None:
            self.grid_frame.destroy()
        self.grid_frame = tk.Frame(self._inner, bg=C['base'], padx=4, pady=4)
        self.grid_frame.pack(fill='both')

        if self.eng:
            self._grid_eng()
        else:
            self._grid_std()

    # ── Button helpers ───────────────────────────────────────────

    def _b(self, parent, text, cmd, fg, bg, row, col, cspan=1, rspan=1, font=None):
        btn = RndBtn(parent, text, cmd, fg=fg, bg=bg, radius=8,
                     font=font or self.f_med,
                     width=52, height=36)
        btn.grid(row=row, column=col, columnspan=cspan, rowspan=rspan,
                 padx=2, pady=2, sticky='nsew')
        return btn

    # ── Standard layout ──────────────────────────────────────────

    def _grid_std(self):
        g, B = self.grid_frame, self._b

        layout = [
            ('ENG', self._toggle_eng, C['base'],    C['mauve']),
            ('AC',  self._ac,         C['base'],    C['red']),
            ('⌫',  self._back,       C['text'],    C['surface1']),
            ('÷',  lambda: self._op('/'), C['base'],C['lavender']),
            ('7',  lambda: self._d('7'), C['text'], C['surface0']),
            ('8',  lambda: self._d('8'), C['text'], C['surface0']),
            ('9',  lambda: self._d('9'), C['text'], C['surface0']),
            ('×',  lambda: self._op('*'), C['base'],C['lavender']),
            ('4',  lambda: self._d('4'), C['text'], C['surface0']),
            ('5',  lambda: self._d('5'), C['text'], C['surface0']),
            ('6',  lambda: self._d('6'), C['text'], C['surface0']),
            ('−',  lambda: self._op('-'), C['base'],C['lavender']),
            ('1',  lambda: self._d('1'), C['text'], C['surface0']),
            ('2',  lambda: self._d('2'), C['text'], C['surface0']),
            ('3',  lambda: self._d('3'), C['text'], C['surface0']),
            ('+',  lambda: self._op('+'), C['base'],C['lavender']),
            ('±',  self._negate,     C['text'],    C['surface1']),
            ('0',  lambda: self._d('0'), C['text'], C['surface0']),
            ('.',  self._dot,         C['text'],    C['surface0']),
            ('=',  self._eq,          C['base'],    C['pink']),
        ]

        cols = 4
        for idx, (txt, cmd, fg, bg) in enumerate(layout):
            r, c = divmod(idx, cols)
            B(g, txt, cmd, fg, bg, r, c)

        for i in range(5): g.rowconfigure(i, weight=0, minsize=46)
        for i in range(4): g.columnconfigure(i, weight=0, minsize=54)

    # ── Engineering layout ───────────────────────────────────────

    def _grid_eng(self):
        g, B = self.grid_frame, self._b

        # Row 0 – meta
        B(g, 'STD',  self._toggle_eng,          C['base'],    C['mauve'],    0, 0)
        B(g, 'AC',   self._ac,                   C['base'],    C['red'],      0, 1)
        B(g, '⌫',   self._back,                 C['text'],    C['surface1'], 0, 2)
        B(g, '()',   self._paren,                C['subtext0'],C['surface0'], 0, 3)
        B(g, '°/r',  self._toggle_deg,           C['base'],    C['teal'],     0, 4)

        # Row 1 – trig
        B(g,'sin',  lambda: self._fn('sin'),     C['base'],    C['teal'],     1, 0, font=self.f_fn)
        B(g,'cos',  lambda: self._fn('cos'),     C['base'],    C['teal'],     1, 1, font=self.f_fn)
        B(g,'tan',  lambda: self._fn('tan'),     C['base'],    C['teal'],     1, 2, font=self.f_fn)
        B(g, '√',   lambda: self._fn('sqrt'),    C['base'],    C['sapphire'], 1, 3)
        B(g, 'x²',  lambda: self._fn('sq'),      C['base'],    C['sapphire'], 1, 4)

        # Row 2 – inverse trig
        B(g,'asin', lambda: self._fn('asin'),    C['base'],    C['sky'],      2, 0, font=self.f_fn)
        B(g,'acos', lambda: self._fn('acos'),    C['base'],    C['sky'],      2, 1, font=self.f_fn)
        B(g,'atan', lambda: self._fn('atan'),    C['base'],    C['sky'],      2, 2, font=self.f_fn)
        B(g, 'xʸ',  lambda: self._op('**'),      C['base'],    C['yellow'],   2, 3)
        B(g, '1/x', lambda: self._fn('inv'),     C['base'],    C['sapphire'], 2, 4)

        # Row 3 – logs + constants
        B(g,'log',  lambda: self._fn('log'),     C['base'],    C['peach'],    3, 0, font=self.f_fn)
        B(g,'ln',   lambda: self._fn('ln'),      C['base'],    C['peach'],    3, 1, font=self.f_fn)
        B(g,'eˣ',   lambda: self._fn('exp'),     C['base'],    C['peach'],    3, 2, font=self.f_fn)
        B(g, 'π',   lambda: self._const(math.pi,'π'), C['base'], C['green'], 3, 3)
        B(g, 'e',   lambda: self._const(math.e,'e'),  C['base'], C['green'], 3, 4)

        # Rows 4-6 – digits block
        for ri, (ds, op_s, op_c, mr_lbl, mr_fn) in enumerate([
            (('7','8','9'), '÷', '/', 'MR', self._mem_r),
            (('4','5','6'), '×', '*', 'MS', self._mem_s),
            (('1','2','3'), '−', '-', 'MC', self._mem_c),
        ], start=4):
            for ci, d in enumerate(ds):
                B(g, d, lambda x=d: self._d(x), C['text'], C['surface0'], ri, ci)
            mr_color = C['maroon'] if mr_lbl == 'MC' else C['lavender']
            B(g, mr_lbl, mr_fn,                 mr_color, C['surface1'], ri, 3)
            B(g, op_s,  lambda o=op_c: self._op(o), C['base'], C['lavender'], ri, 4)

        # Row 7 – ± 0 . % +
        B(g, '±',  self._negate,           C['text'], C['surface1'], 7, 0)
        B(g, '0',  lambda: self._d('0'),   C['text'], C['surface0'], 7, 1)
        B(g, '.',  self._dot,              C['text'], C['surface0'], 7, 2)
        B(g, '%',  self._pct,              C['text'], C['surface1'], 7, 3)
        B(g, '+',  lambda: self._op('+'),  C['base'], C['lavender'], 7, 4)
        B(g, '=',  self._eq,               C['base'], C['pink'],     8, 4)
        
        # фикс высоты всех строк
        for i in range(9):
            g.rowconfigure(i, weight=0, minsize=42)

        # фикс колонок
        for i in range(5):
            g.columnconfigure(i, weight=0, minsize=52)

    # ── Keyboard ─────────────────────────────────────────────────

    def _keybinds(self):
        for k, d in [('KP_0','0'),('KP_1','1'),('KP_2','2'),('KP_3','3'),
                     ('KP_4','4'),('KP_5','5'),('KP_6','6'),('KP_7','7'),
                     ('KP_8','8'),('KP_9','9')]:
            self.bind(f'<{k}>', lambda e, c=d: self._d(c))
        self.bind('<KP_Add>',      lambda e: self._op('+'))
        self.bind('<KP_Subtract>', lambda e: self._op('-'))
        self.bind('<KP_Multiply>', lambda e: self._op('*'))
        self.bind('<KP_Divide>',   lambda e: self._op('/'))
        self.bind('<KP_Enter>',    lambda e: self._eq())
        self.bind('<KP_Decimal>',  lambda e: self._dot())
        self.bind('<Return>',      lambda e: self._eq())
        self.bind('<BackSpace>',   lambda e: self._back())
        self.bind('<Escape>',      lambda e: self._ac())
        self.bind('<Delete>',      lambda e: self._ac())
        self.bind('<Key>',         self._on_key)

    def _on_key(self, ev):
        k = ev.char
        if   k in '0123456789': self._d(k)
        elif k == '.':  self._dot()
        elif k == '+':  self._op('+')
        elif k == '-':  self._op('-')
        elif k == '*':  self._op('*')
        elif k == '/':  self._op('/')
        elif k == '%':  self._pct()
        elif k == '(':  self._d('(')
        elif k == ')':  self._d(')')

    # ── Calc logic ───────────────────────────────────────────────

    def _show(self, value, expr=''):
        s = str(value)
        if len(s) > 15:
            try:    s = f'{float(s):.10g}'
            except: s = s[:15] + '…'
        self.v_main.set(s)
        self.v_expr.set(expr)

    def _fmt(self, v):
        if isinstance(v, float):
            if v == int(v) and abs(v) < 1e14:
                return str(int(v))
            return f'{v:.10g}'
        return str(v)

    def _d(self, ch):
        if self.after_eq and ch not in '()':
            self.expr = ''; self.after_eq = False
        self.expr += ch
        self._show(self.expr)

    def _dot(self):
        segs = re.split(r'[\+\-\*\/\(\^]', self.expr)
        last = segs[-1] if segs else ''
        if '.' not in last:
            if not last: self.expr += '0'
            self.expr += '.'
            self._show(self.expr)

    def _op(self, op):
        self.after_eq = False
        if self.expr and self.expr[-1] in '+-*/^':
            self.expr = self.expr[:-1]
        if self.expr:
            self.expr += op
        self._show(self.expr or '0')

    def _paren(self):
        ch = '(' if self.expr.count('(') == self.expr.count(')') else ')'
        self._d(ch)

    def _fn(self, name):
        self.after_eq = False
        try: val = float(self.v_main.get())
        except: val = None

        def apply(v):
            if name == 'sqrt':
                if v < 0: raise ValueError('√neg')
                return math.sqrt(v), f'√({self._fmt(v)})'
            if name == 'sq':  return v**2, f'({self._fmt(v)})²'
            if name == 'inv':
                if v == 0: raise ZeroDivisionError
                return 1/v, f'1/({self._fmt(v)})'
            if name in ('sin','cos','tan'):
                a = math.radians(v) if self.deg_mode else v
                return getattr(math, name)(a), f'{name}({self._fmt(v)}{"°" if self.deg_mode else "r"})'
            if name in ('asin','acos','atan'):
                r2 = getattr(math, name)(v)
                return (math.degrees(r2) if self.deg_mode else r2), f'{name}({self._fmt(v)})'
            if name == 'log':
                if v <= 0: raise ValueError('log(≤0)')
                return math.log10(v), f'log({self._fmt(v)})'
            if name == 'ln':
                if v <= 0: raise ValueError('ln(≤0)')
                return math.log(v), f'ln({self._fmt(v)})'
            if name == 'exp':
                return math.exp(v), f'e^({self._fmt(v)})'

        if val is not None and self.after_eq:
            try:
                result, lbl = apply(val)
                self.expr = str(result)
                self._show(self._fmt(result), lbl); self.after_eq = True
            except Exception as ex:
                self._show('Error', str(ex)); self.expr = ''
            return

        pfx = {'sqrt':'sqrt(','sq':'sq(','inv':'1/(','sin':'sin(','cos':'cos(',
               'tan':'tan(','asin':'asin(','acos':'acos(','atan':'atan(',
               'log':'log(','ln':'ln(','exp':'exp('}
        self.expr += pfx.get(name, name + '(')
        self._show(self.expr)

    def _const(self, val, sym):
        if self.after_eq: self.expr = ''; self.after_eq = False
        self.expr += str(val)
        self._show(sym)

    def _eq(self):
        if not self.expr: return
        raw = self.expr
        try:
            safe = {
                '__builtins__': {},
                'sin':  (lambda x: math.sin(math.radians(x))) if self.deg_mode else math.sin,
                'cos':  (lambda x: math.cos(math.radians(x))) if self.deg_mode else math.cos,
                'tan':  (lambda x: math.tan(math.radians(x))) if self.deg_mode else math.tan,
                'asin': (lambda x: math.degrees(math.asin(x))) if self.deg_mode else math.asin,
                'acos': (lambda x: math.degrees(math.acos(x))) if self.deg_mode else math.acos,
                'atan': (lambda x: math.degrees(math.atan(x))) if self.deg_mode else math.atan,
                'sqrt': math.sqrt, 'sq': lambda x: x**2, 'inv': lambda x: 1/x,
                'log': math.log10, 'ln': math.log, 'exp': math.exp,
                'abs': abs, 'pi': math.pi, 'e': math.e,
            }
            result = eval(raw.replace('×','*').replace('÷','/').replace('^','**'), safe)
            self._show(self._fmt(result), raw + ' =')
            self.expr = str(result); self.after_eq = True
        except ZeroDivisionError:
            self._show('∞', raw); self.expr = ''
        except Exception as ex:
            self._show('Error', str(ex)[:24]); self.expr = ''

    def _ac(self):
        self.expr = ''; self.after_eq = False
        self._show('0'); self.v_expr.set('')

    def _back(self):
        if self.after_eq: self._ac(); return
        self.expr = self.expr[:-1]
        self._show(self.expr or '0')

    def _negate(self):
        try:
            v = -float(self.v_main.get())
            self.expr = str(v); self._show(self._fmt(v))
        except Exception: pass

    def _pct(self):
        try:
            v = float(self.v_main.get()) / 100
            self.expr = str(v); self._show(self._fmt(v))
        except Exception: pass

    def _mem_s(self):
        try:
            self.memory = float(self.v_main.get())
            self.mem_set = True
            self.v_mem.set(f'M={self._fmt(self.memory)}')
        except Exception: pass

    def _mem_r(self):
        if self.mem_set:
            self.expr = str(self.memory)
            self._show(self._fmt(self.memory))

    def _mem_c(self):
        self.memory = 0.0; self.mem_set = False; self.v_mem.set('')

    def _toggle_eng(self):
        self.eng = not self.eng
        self._build_grid()

        self.update_idletasks()
 
    # фикс размера под новый layout
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()

        self.geometry(f"{w}x{h}")
        self._center()
    
    def _toggle_deg(self):
        self.deg_mode = not self.deg_mode
        self.v_angle.set('DEG' if self.deg_mode else 'RAD')

    def _center(self):
        self.update_idletasks()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f'{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}')


# ─── Entry point ─────────────────────────────────────────────────
if __name__ == '__main__':
    app = Calc()
    if '--eng' in sys.argv:
        app._toggle_eng()
    app.mainloop()
