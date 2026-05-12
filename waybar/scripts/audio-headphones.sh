#!/bin/bash

# Простой поиск ID наушников
HEADPHONES_ID=$(wpctl status | grep "HyperX" | grep "Аналоговый" | grep -oP '\d+' | head -1)

if [ -z "$HEADPHONES_ID" ]; then
    notify-send "⚠ Ошибка" "Наушники не найдены" -i dialog-error
    exit 1
fi

wpctl set-default "$HEADPHONES_ID"
notify-send "🎧 Аудио" "Наушники" -i audio-headphones
