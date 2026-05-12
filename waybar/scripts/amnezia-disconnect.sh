#!/bin/bash
# amnezia-disconnect.sh

CONFIG="$HOME/.config/AmneziaVPN.ORG/AmneziaVPN.conf"
STATE_FILE="/tmp/waybar-amnezia-open"
SIGNAL=8

# Отключаем autoConnect — GUI при старте не будет реконнектиться
sed -i 's/autoConnect=.*/autoConnect=false/' "$CONFIG"

# Перезапускаем ТОЛЬКО GUI — он отправит disconnect демону и не реконнектится
# Сервис-демон НЕ трогаем — он сам чисто уберёт туннель
pkill -f "/opt/AmneziaVPN/client/bin/AmneziaVPN" 2>/dev/null
sleep 1
/usr/local/bin/AmneziaVPN &

rm -f "$STATE_FILE"
sleep 2
pkill -RTMIN+$SIGNAL waybar
