#!/bin/bash
# amnezia-btn.sh
# Отображает кнопку только когда панель открыта
# Аргументы: $1 = иконка/текст, $2 = CSS-класс

STATE_FILE="/tmp/waybar-amnezia-open"
TEXT="$1"
CLASS="$2"

if [ -f "$STATE_FILE" ]; then
    printf '{"text":"%s","class":"%s"}\n' "$TEXT" "$CLASS"
else
    # Пустой вывод → CSS схлопывает элемент через max-width: 0
    printf '{"text":"","class":"hidden"}\n'
fi
