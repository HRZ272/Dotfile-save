#!/bin/bash
# amnezia-toggle.sh
# Переключает состояние выдвижной панели (открыто / закрыто)

STATE_FILE="/tmp/waybar-amnezia-open"
SIGNAL=8   # RTMIN+8 — сигнал для обновления всех модулей amnezia

if [ -f "$STATE_FILE" ]; then
    rm -f "$STATE_FILE"
else
    touch "$STATE_FILE"
fi

# Отправляем сигнал Waybar — обновить все модули amnezia
pkill -RTMIN+$SIGNAL waybar
