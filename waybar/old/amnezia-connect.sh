#!/bin/bash
# amnezia-connect.sh
# $1 = индекс сервера: 0 = Сервер 1 (AWG/WARP), 1 = Сервер 2 (xray)

INDEX=$1
CONFIG="$HOME/.config/AmneziaVPN.ORG/AmneziaVPN.conf"
STATE_FILE="/tmp/waybar-amnezia-open"
SIGNAL=8

# Меняем активный сервер в конфиге
sed -i "s/defaultServerIndex=.*/defaultServerIndex=$INDEX/" "$CONFIG"
# Убеждаемся что autoConnect включён
sed -i 's/autoConnect=.*/autoConnect=true/' "$CONFIG"

# Перезапускаем сервис — он сам подключится к нужному серверу
sudo pkill -f "AmneziaVPN-service" 2>/dev/null
sleep 0.5
sudo /opt/AmneziaVPN/service/bin/AmneziaVPN-service &

# Перезапускаем GUI-клиент (startMinimized=true — в трей)
pkill -f "/opt/AmneziaVPN/client/bin/AmneziaVPN" 2>/dev/null
sleep 1
/usr/local/bin/AmneziaVPN &

# Закрываем панель, обновляем Waybar
rm -f "$STATE_FILE"
sleep 2  # ждём пока поднимется тоннель
pkill -RTMIN+$SIGNAL waybar
