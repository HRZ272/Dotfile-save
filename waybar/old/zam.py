#!/usr/bin/env python3
import tkinter as tk
from tkinter import font as tkfont
import json, os, sys

SAVE_FILE = os.path.expanduser('~/.local/share/waybar_notes.json')

C = {
    'base':     '#1e1e2e', 'mantle':  '#181825', 'crust':   '#11111b',
    'text':     '#cdd6f4', 'subtext': '#a6adc8',
    'surface0': '#313244', 'surface1':'#45475a',  'overlay': '#6c7086',
    'lavender': '#b4befe', 'mauve':   '#cba6f7',  'teal':    '#94e2d5',
    'red':      '#f38ba8', 'green':   '#a6e3a1',  'pink':    '#f5c2e7',
}

MONO = ['JetBrainsMono Nerd Font','JetBrains Mono','Iosevka Nerd Font',
        'Iosevka','Fira Code','DejaVu Sans Mono','Liberation Mono']

def resolve(size, w='normal'):
    tmp = tk.Tk(); tmp.withdraw()
    avail = set(tkfont.families()); tmp.destroy()
    for f in MONO:
        if f in avail: return (f, size, w)
    return ('TkFixedFont', size, w)

def brighten(c, a=22):
    return '#{:02x}{:02x}{:02x}'.format(
        min(255,int(c[1:3],16)+a), min(255,int(c[3:5],16)+a), min(255,int(c[5:7],16)+a))


# ── Rounded button ───────────────────────────────────────────────
class RndBtn(tk.Canvas):
    def __init__(self, parent, text, cmd, fg=C['text'], bg=C['surface0'],
                 radius=8, font=None, **kw):
        super().__init__(parent, bg=parent.cget('bg'),
                         highlightthickness=0, bd=0, **kw)
        self._t=text; self._cmd=cmd; self._fg=fg; self._bg=bg
        self._bgh=brighten(bg); self._r=radius; self._hov=False
        self._font = font or resolve(10)
        self.bind('<Configure>', lambda e: self._draw())
        self.bind('<Button-1>',  lambda e: cmd())
        self.bind('<Enter>',     lambda e: self._h(True))
        self.bind('<Leave>',     lambda e: self._h(False))

    def _h(self, s): self._hov=s; self._draw()

    def _draw(self):
        self.delete('all')
        w,h = self.winfo_width(), self.winfo_height()
        if w<4 or h<4: return
        r = min(self._r, w//2, h//2)
        bg = self._bgh if self._hov else self._bg
        for x0,y0,x1,y1,start in [(0,0,2*r,2*r,90),(w-2*r,0,w,2*r,0),
                                    (0,h-2*r,2*r,h,180),(w-2*r,h-2*r,w,h,270)]:
            self.create_arc(x0,y0,x1,y1,start=start,extent=90,fill=bg,outline=bg)
        self.create_rectangle(r,0,w-r,h,fill=bg,outline=bg)
        self.create_rectangle(0,r,w,h-r,fill=bg,outline=bg)
        self.create_text(w//2,h//2,text=self._t,fill=self._fg,font=self._font)


# ── Rounded entry wrapper ────────────────────────────────────────
class RndEntry(tk.Canvas):
    """Canvas background + an Entry widget placed inside."""
    def __init__(self, parent, bg=C['surface0'], radius=8, **kw):
        super().__init__(parent, bg=parent.cget('bg'),
                         highlightthickness=0, bd=0, **kw)
        self._bg=bg; self._r=radius
        self.bind('<Configure>', lambda e: self._draw())

    def _draw(self):
        self.delete('all')
        w,h = self.winfo_width(), self.winfo_height()
        if w<4 or h<4: return
        r = min(self._r, w//2, h//2)
        for x0,y0,x1,y1,s in [(0,0,2*r,2*r,90),(w-2*r,0,w,2*r,0),
                                (0,h-2*r,2*r,h,180),(w-2*r,h-2*r,w,h,270)]:
            self.create_arc(x0,y0,x1,y1,start=s,extent=90,fill=self._bg,outline=self._bg)
        self.create_rectangle(r,0,w-r,h,fill=self._bg,outline=self._bg)
        self.create_rectangle(0,r,w,h-r,fill=self._bg,outline=self._bg)


def _rrect(canvas, x0, y0, x1, y1, r, bg):
    """Draw a filled rounded rectangle on a Canvas."""
    r = min(r, (x1-x0)//2, (y1-y0)//2)
    for ax,ay,bx,by,s in [(x0,y0,x0+2*r,y0+2*r,90),(x1-2*r,y0,x1,y0+2*r,0),
                           (x0,y1-2*r,x0+2*r,y1,180),(x1-2*r,y1-2*r,x1,y1,270)]:
        canvas.create_arc(ax,ay,bx,by,start=s,extent=90,fill=bg,outline=bg)
    canvas.create_rectangle(x0+r,y0,x1-r,y1,fill=bg,outline=bg)
    canvas.create_rectangle(x0,y0+r,x1,y1-r,fill=bg,outline=bg)


# ── Waybar mode ──────────────────────────────────────────────────
def waybar_out():
    notes=[]
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE,'r',encoding='utf-8') as f: notes=json.load(f)
        except: pass
    print(json.dumps({"text":f"󰎞 {len(notes)}",
                      "tooltip":f"Заметок: {len(notes)}\nКликни чтобы открыть",
                      "class":"notes"}))
    sys.exit(0)


# ── App ──────────────────────────────────────────────────────────
class NotesApp(tk.Tk):
    def __init__(self):
        super().__init__(className='waybar-notes')
        self.title('Заметки')
        self.configure(bg=C['base'])
        self.resizable(True, True)
        self.notes=[]; self.cur=None
        self._load()
        self.bind('<Control-s>', lambda e: self._save())
        self.bind('<Control-n>', lambda e: self._new())
        self._fonts()
        self._build()
        self._refresh()
        self._center(640, 440)

    def _fonts(self):
        self.fu = resolve(10); self.fb = resolve(11,'bold')
        self.ft = resolve(10); self.fs = resolve(9)

    def _build(self):
        bdr = tk.Frame(self, bg=C['crust'], padx=1, pady=0)
        bdr.pack(fill='both', expand=True)
        root = tk.Frame(bdr, bg=C['base'])
        root.pack(fill='both', expand=True)
        tk.Frame(root, bg=C['lavender'], height=2).pack(fill='x')
        body = tk.Frame(root, bg=C['base'])
        body.pack(fill='both', expand=True, padx=10, pady=10)
        self._left(body)
        self._right(body)

    def _left(self, p):
        f = tk.Frame(p, bg=C['base'], width=190)
        f.pack(side='left', fill='y', padx=(0,8))
        f.pack_propagate(False)

        RndBtn(f, '＋  Новая заметка', self._new,
               fg=C['crust'], bg=C['lavender'], radius=8,
               font=self.fu, width=170, height=32).pack(pady=(0,8))

        wrap = tk.Frame(f, bg=C['mantle'], bd=0)
        wrap.pack(fill='both', expand=True)

        sb = tk.Scrollbar(wrap, orient='vertical', bg=C['surface1'],
                          troughcolor=C['mantle'], relief='flat',
                          bd=0, width=5, highlightthickness=0)
        sb.pack(side='right', fill='y', pady=6)

        self.lb = tk.Listbox(
            wrap, bg=C['mantle'], fg=C['text'],
            selectbackground=C['surface1'], selectforeground=C['lavender'],
            activestyle='none', bd=0, highlightthickness=0,
            font=self.ft, yscrollcommand=sb.set, cursor='hand2',
        )
        self.lb.pack(side='left', fill='both', expand=True, padx=(6,0), pady=6)
        sb.config(command=self.lb.yview)
        self.lb.bind('<<ListboxSelect>>', self._sel)

    def _right(self, p):
        f = tk.Frame(p, bg=C['base'])
        f.pack(side='right', fill='both', expand=True)

        # ── Buttons — СНАЧАЛА bottom ──
        btf = tk.Frame(f, bg=C['base'])
        btf.pack(side='bottom', fill='x', pady=(8,0))

        RndBtn(btf, '󰆓  Сохранить', self._save,
               fg=C['crust'], bg=C['teal'], radius=8,
               font=self.fu, width=140, height=30).pack(side='left', padx=(0,6))

        RndBtn(btf, '✕ Удалить', self._delete,
               fg=C['crust'], bg=C['red'], radius=8,
               font=self.fu, width=110, height=30).pack(side='right')

        # ── Title: Canvas с rounded bg + Entry внутри ──
        tc = tk.Canvas(f, bg=C['base'], highlightthickness=0, bd=0, height=36)
        tc.pack(fill='x', pady=(0,6))

        def _draw_tc(e=None):
            tc.delete('all')
            w, h = tc.winfo_width(), tc.winfo_height()
            if w < 4: return
            _rrect(tc, 0, 0, w, h, 8, C['surface0'])
            tc.coords('tw', w//2, h//2)
            tc.itemconfig('tw', width=w-24)

        self.e_title = tk.Entry(tc, bg=C['surface0'], fg=C['text'],
                                insertbackground=C['lavender'],
                                relief='flat', bd=0, font=self.fb)
        tc.create_window(0, 0, window=self.e_title, anchor='center',
                         width=100, height=24, tags='tw')
        tc.bind('<Configure>', _draw_tc)

        # ── Body: Canvas с rounded bg + Text внутри ──
        bc = tk.Canvas(f, bg=C['base'], highlightthickness=0, bd=0)
        bc.pack(fill='both', expand=True, pady=(0,8))

        def _draw_bc(e=None):
            bc.delete('all')
            w, h = bc.winfo_width(), bc.winfo_height()
            if w < 4: return
            _rrect(bc, 0, 0, w, h, 8, C['surface0'])
            bc.coords('bw', w//2, h//2)
            bc.itemconfig('bw', width=w-12, height=h-12)

        self.txt = tk.Text(bc, bg=C['surface0'], fg=C['text'],
                           insertbackground=C['lavender'],
                           relief='flat', bd=0, font=self.ft,
                           padx=10, pady=8, wrap='word')
        bc.create_window(0, 0, window=self.txt, anchor='center',
                         width=100, height=100, tags='bw')
        bc.bind('<Configure>', _draw_bc)

    def _round_frame(self, widget, bg):
        pass  # не используется

    # ── Data ────────────────────────────────────────────────────
    def _load(self):
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE,'r',encoding='utf-8') as f:
                    self.notes=json.load(f)
            except: pass

    def _save_data(self):
        os.makedirs(os.path.dirname(SAVE_FILE), exist_ok=True)
        with open(SAVE_FILE,'w',encoding='utf-8') as f:
            json.dump(self.notes, f, ensure_ascii=False, indent=4)

    def _refresh(self):
        self.lb.delete(0, tk.END)
        for n in self.notes:
            self.lb.insert(tk.END, f'  {n.get("title","Без названия")}')

    def _new(self):
        self.cur=None
        self.e_title.delete(0,tk.END)
        self.txt.delete('1.0',tk.END)
        self.e_title.insert(0,'Новая заметка')
        self.e_title.focus()

    def _sel(self, _):
        s = self.lb.curselection()
        if not s: return
        self.cur = s[0]
        n = self.notes[self.cur]
        self.e_title.delete(0,tk.END); self.e_title.insert(0,n.get('title',''))
        self.txt.delete('1.0',tk.END); self.txt.insert(tk.END,n.get('content',''))

    def _save(self):
        t = self.e_title.get().strip() or 'Без названия'
        c = self.txt.get('1.0',tk.END).strip()
        if self.cur is None:
            self.notes.append({'title':t,'content':c})
            self.cur = len(self.notes)-1
        else:
            self.notes[self.cur] = {'title':t,'content':c}
        self._save_data(); self._refresh()
        self.lb.selection_clear(0,tk.END); self.lb.selection_set(self.cur)

    def _delete(self):
        if self.cur is not None:
            del self.notes[self.cur]
            self._save_data(); self._refresh(); self._new()

    def _center(self, w, h):
        sw=self.winfo_screenwidth(); sh=self.winfo_screenheight()
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')


if __name__ == '__main__':
    if '--gui' in sys.argv:
        NotesApp().mainloop()
    else:
        waybar_out()
