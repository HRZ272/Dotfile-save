#!/bin/bash

HEADPHONES_ID=45
SPEAKERS_ID=57

CURRENT=$(wpctl status | grep -A 999 "Sinks:" | grep "^\s*\*" | grep -oP '\d+' | head -1)

# Показываем текущее активное устройство
if [ "$CURRENT" = "$HEADPHONES_ID" ]; then
    echo "󰋋"  # Наушники активны
else
    echo "󰓃"  # Колонки активны
fi
