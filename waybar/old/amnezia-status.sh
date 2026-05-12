#!/bin/bash
# amnezia-status.sh

STATE_FILE="/tmp/waybar-amnezia-open"
CONFIG="$HOME/.config/AmneziaVPN.ORG/AmneziaVPN.conf"

# Смотрим активный туннель (AmneziaVPN всегда поднимает tun2)
if ip link show tun2 2>/dev/null | grep -qE "state (UP|UNKNOWN)"; then
    IDX=$(grep 'defaultServerIndex=' "$CONFIG" 2>/dev/null | cut -d= -f2)
    case "$IDX" in
        0) SRV=" S1" ;;
        1) SRV=" S2" ;;
        *) SRV=""    ;;
    esac
    ICON="󰒄"
    CLASS="connected"
    TOOLTIP="AmneziaVPN ● Сервер $((IDX+1))"
else
    ICON="󰒃"
    CLASS="disconnected"
    TOOLTIP="AmneziaVPN ○ отключён"
    SRV=""
fi

[ -f "$STATE_FILE" ] && ARROW=" ‹" || ARROW=""

printf '{"text":"%s%s%s","class":"%s","tooltip":"%s"}\n' \
    "$ICON" "$SRV" "$ARROW" "$CLASS" "$TOOLTIP"
