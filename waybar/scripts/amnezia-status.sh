#!/bin/bash
# amnezia-status.sh

STATE_FILE="/tmp/waybar-amnezia-open"
CONFIG="$HOME/.config/AmneziaVPN.ORG/AmneziaVPN.conf"

# Сервер 1 (AWG) поднимает awg0, Сервер 2 (xray) поднимает tun2
AWG_UP=$(ip link show 2>/dev/null | grep -cE "^[0-9]+: awg[0-9]+:.*state (UP|UNKNOWN)")
TUN_UP=$(ip link show tun2 2>/dev/null | grep -cE "state (UP|UNKNOWN)")

if [ "$AWG_UP" -gt 0 ] || [ "$TUN_UP" -gt 0 ]; then
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
