#!/bin/bash

# Скрипт для одновременного управления всеми потоками Chromium
# Позволяет регулировать громкость, даже если открыто много вкладок со звуком

get_chromium_sink_ids() {
    # Получаем все ID потоков для Chromium
    pactl list sink-inputs | grep -B 20 "application.name = \"Chromium\"" | grep "Sink Input #" | awk '{print $3}' | sed 's/#//'
}

SINK_IDS=$(get_chromium_sink_ids)

if [ -z "$SINK_IDS" ]; then
    if [ "$1" == "status" ]; then
        echo '{"text": "󰗧 󱉟", "class": "inactive", "tooltip": "Chromium не активен"}'
    fi
    exit 0
fi

case $1 in
    up)
        for id in $SINK_IDS; do
            pactl set-sink-input-volume "$id" +5%
        done
        ;;
    down)
        for id in $SINK_IDS; do
            pactl set-sink-input-volume "$id" -5%
        done
        ;;
    mute)
        for id in $SINK_IDS; do
            pactl set-sink-input-mute "$id" toggle
        done
        ;;
    status)
        # Для статуса берем громкость первого потока
        FIRST_ID=$(echo "$SINK_IDS" | head -n 1)
        CURRENT_VOL=$(pactl list sink-inputs | grep -A 15 "Sink Input #$FIRST_ID" | grep "Volume:" | head -n 1 | awk '{print $5}' | sed 's/%//')
        IS_MUTED=$(pactl list sink-inputs | grep -A 15 "Sink Input #$FIRST_ID" | grep "Mute:" | awk '{print $2}')
        
        ICON=""
        if [ "$IS_MUTED" == "yes" ]; then ICON="󰝟"; fi
        
        COUNT=$(echo "$SINK_IDS" | wc -l)
        echo "{\"text\": \"$ICON $CURRENT_VOL%\", \"tooltip\": \"Потоков: $COUNT\nГромкость: $CURRENT_VOL%\", \"class\": \"active\"}"
        ;;
esac
