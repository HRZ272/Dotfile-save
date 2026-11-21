#!/bin/bash
# Статус-строка для объединённого модуля custom/volume в Waybar.
# Показывает: иконка+громкость система, и отдельно иконку Chromium если он шумит.

# ── Системная громкость ──
SINK_VOL=$(pactl get-sink-volume @DEFAULT_SINK@ | grep -oP '\d+(?=%)' | head -n1)
SINK_MUTE=$(pactl get-sink-mute @DEFAULT_SINK@ | awk '{print $2}')

if [ "$SINK_MUTE" == "yes" ]; then
    SYS_ICON="󰝟"
else
    if   [ "$SINK_VOL" -ge 70 ]; then SYS_ICON="󰕾"
    elif [ "$SINK_VOL" -ge 30 ]; then SYS_ICON="󰖀"
    else SYS_ICON="󰕿"
    fi
fi

# ── Chromium ──
CHROMIUM_IDS=$(pactl list sink-inputs | grep -B 20 'application.name = "Chromium"' | grep "Sink Input #" | awk '{print $3}' | sed 's/#//')

CHROMIUM_PART=""
TOOLTIP="Система: ${SINK_VOL}%"

if [ -n "$CHROMIUM_IDS" ]; then
    FIRST_ID=$(echo "$CHROMIUM_IDS" | head -n1)
    C_VOL=$(pactl list sink-inputs | grep -A 15 "Sink Input #$FIRST_ID" | grep "Volume:" | head -n1 | grep -oP '\d+(?=%)' | head -n1)
    C_MUTE=$(pactl list sink-inputs | grep -A 15 "Sink Input #$FIRST_ID" | grep "Mute:" | awk '{print $2}')
    C_ICON="󰗧"
    [ "$C_MUTE" == "yes" ] && C_ICON="󰖁"
    CHROMIUM_PART=" ${C_ICON} ${C_VOL}%"
    TOOLTIP="${TOOLTIP}\nChromium: ${C_VOL}%"
fi

echo "{\"text\": \"${SYS_ICON} ${SINK_VOL}%${CHROMIUM_PART}\", \"tooltip\": \"${TOOLTIP}\", \"class\": \"active\"}"
