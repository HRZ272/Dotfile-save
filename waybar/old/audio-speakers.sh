#!/bin/bash

# Простой поиск ID колонок
SPEAKERS_ID=$(wpctl status | grep "Starship" | grep "Аналоговый" | grep -oP '\d+' | head -1)

if [ -z "$SPEAKERS_ID" ]; then
    notify-send "⚠ Ошибка" "Колонки не найдены" -i dialog-error
    exit 1
fi

wpctl set-default "$SPEAKERS_ID"
notify-send "🔊 Аудио" "Колонки" -i audio-speakers
