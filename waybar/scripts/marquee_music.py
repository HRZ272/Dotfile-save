#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Marquee-тикер для waybar custom модуля.
# Помести куда-нибудь, например: ~/.config/waybar/scripts/marquee_music.py
# Сделай исполняемым: chmod +x marquee_music.py

import subprocess, time, sys, json

# ── настройки ──────────────────────────────────
WINDOW    = 20      # сколько символов показывать в баре
SPEED     = 0.35    # секунд между шагами прокрутки
PAUSE     = 2.5     # пауза на старте (сек) перед началом прокрутки
ICON      = "󰎈 "   # nerd font иконка перед текстом (можно убрать)
# ───────────────────────────────────────────────

def run(*args):
    try:
        return subprocess.check_output(list(args), stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ''

def output(text, tooltip='', css_class=''):
    print(json.dumps({'text': text, 'tooltip': tooltip, 'class': css_class}),
          flush=True)

def make_ticker(text):
    """Генератор: отдаёт куски текста со сдвигом, как бегущая строка."""
    if len(text) <= WINDOW:
        # текст влезает — просто отдаём как есть бесконечно
        while True:
            yield text
    else:
        padded      = text + '   '
        total       = len(padded)
        pause_steps = int(PAUSE / SPEED)
        while True:
            for _ in range(pause_steps):
                yield text[:WINDOW]
            for offset in range(total):
                yield (padded + padded)[offset: offset + WINDOW]

def main():
    last_title  = None
    last_artist = None
    ticker      = None

    while True:
        status = run('playerctl', 'status')

        if status not in ('Playing', 'Paused'):
            output('󰎈 ничего не играет')
            time.sleep(2)
            continue

        title  = run('playerctl', 'metadata', 'title')  or 'Неизвестный трек'
        artist = run('playerctl', 'metadata', 'artist') or ''
        full   = f'{title} — {artist}' if artist else title

        # новый трек — перезапускаем тикер
        if title != last_title or artist != last_artist:
            last_title  = title
            last_artist = artist
            ticker      = make_ticker(full)

        icon   = ICON
        chunk  = next(ticker)

        output(
            text    = f'{icon}{chunk}',
            tooltip = f'{title}\n{artist}',
            css_class = 'playing' if status == 'Playing' else 'paused',
        )

        time.sleep(SPEED)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
