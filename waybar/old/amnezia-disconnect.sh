#!/bin/bash
# amnezia-disconnect.sh
# Отключает VPN, останавливая сервис AmneziaVPN

CONFIG="$HOME/.config/AmneziaVPN.ORG/AmneziaVPN.conf"
STATE_FILE="/tmp/waybar-amnezia-open"
SIGNAL=8

# Отключаем autoConnect чтобы после остановки не переподключился
sed -i 's/autoConnect=.*/autoConnect=false/' "$CONFIG"

# Останавливаем сервис
sudo pkill -f "AmneziaVPN-service" 2>/dev/null

# Чистим туннельный интерфейс если остался
sudo ip link delete tun2 2>/dev/null

# Перезапускаем только GUI (без сервиса — значит без VPN)
pkill -f "/opt/AmneziaVPN/client/bin/AmneziaVPN" 2>/dev/null
sleep 0.3
/usr/local/bin/AmneziaVPN &

rm -f "$STATE_FILE"
pkill -RTMIN+$SIGNAL waybar
