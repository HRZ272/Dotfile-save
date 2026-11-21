#!/bin/bash
# Открывает/закрывает GTK-попап громкости (volume_popup.py)

PID=$(pgrep -f "python3 .*volume_popup\.py")

if [ -n "$PID" ]; then
    kill "$PID"
else
    python3 ~/.config/waybar/scripts/volume_popup.py &
    disown
fi
