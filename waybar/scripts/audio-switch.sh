#!/bin/bash

HEADPHONES_ID=45
SPEAKERS_ID=57

CURRENT=$(wpctl status | grep -A 999 "Sinks:" | grep "^\s*\*" | grep -oP '\d+' | head -1)

if [ "$CURRENT" = "$HEADPHONES_ID" ]; then
    wpctl set-default "$SPEAKERS_ID"
    notify-send "🔊 Аудио" "Переключено на колонки" -i audio-speakers
else
    wpctl set-default "$HEADPHONES_ID"
    notify-send "🎧 Аудио" "Переключено на наушники" -i audio-headphones
fi
