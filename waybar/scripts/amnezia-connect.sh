#!/bin/bash
# amnezia-connect.sh
# $1 = индекс сервера: 0 = Сервер 1 (AWG), 1 = Сервер 2 (xray)

INDEX=$1
CONFIG="$HOME/.config/AmneziaVPN.ORG/AmneziaVPN.conf"
STATE_FILE="/tmp/waybar-amnezia-open"
SIGNAL=8

# Меняем сервер и включаем автоподключение
sed -i "s/defaultServerIndex=.*/defaultServerIndex=$INDEX/" "$CONFIG"
sed -i 's/autoConnect=.*/autoConnect=true/' "$CONFIG"

# Перезапускаем ТОЛЬКО GUI-клиент (сервис-демон НЕ трогаем — он держит маршруты)
# GUI читает конфиг при старте и сам посылает команду connect демону
pkill -f "/opt/AmneziaVPN/client/bin/AmneziaVPN" 2>/dev/null
sleep 1
/usr/local/bin/AmneziaVPN &

rm -f "$STATE_FILE"
sleep 3
pkill -RTMIN+$SIGNAL waybar
