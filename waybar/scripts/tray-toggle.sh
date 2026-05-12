#!/usr/bin/env bash
# tray-toggle.sh — показывает/скрывает #tray в Waybar через SIGUSR2 (CSS reload)
#
# Установка:
#   chmod +x ~/.config/waybar/scripts/tray-toggle.sh
#
# Waybar config:
#   "custom/tray-toggle": {
#       "exec": "~/.config/waybar/scripts/tray-toggle.sh --status",
#       "on-click": "~/.config/waybar/scripts/tray-toggle.sh --toggle",
#       "interval": "once",
#       "signal": 8,
#       "tooltip": false
#   }
#
# style.css — добавь в самый конец:
#   @import url("/home/horizon/.config/waybar/tray-state.css");

STATE_FILE="$HOME/.cache/waybar-tray-state"   # open / closed
CSS_FILE="$HOME/.config/waybar/tray-state.css"

ICON_OPEN="󰄬 "    # стрелка вниз  (nerd font md-chevron_down)
ICON_CLOSED="󰄿 "  # стрелка вправо (nerd font md-chevron_right)

# ── Инициализация при первом запуске ───────────────────────────────────────
init() {
    mkdir -p "$(dirname "$CSS_FILE")" "$(dirname "$STATE_FILE")"
    if [[ ! -f "$STATE_FILE" ]]; then
        echo "closed" > "$STATE_FILE"
    fi
    if [[ ! -f "$CSS_FILE" ]]; then
        echo '#tray { min-width: 0; padding: 0; margin: 0; border: none !important; background: transparent !important; box-shadow: none !important; }' > "$CSS_FILE"
        # скрыть содержимое трея — дочерние виджеты
        echo '#tray > * { display: none; }' >> "$CSS_FILE"
    fi
}

# ── Применить состояние → записать CSS → сигнал Waybar ────────────────────
apply() {
    local state
    state=$(cat "$STATE_FILE")

    if [[ "$state" == "open" ]]; then
        # Показываем трей полностью
        cat > "$CSS_FILE" <<'EOF'
#tray > * { display: flex; }
EOF
    else
        # Прячем иконки, оставляем место только для кнопки-тоггла
        cat > "$CSS_FILE" <<'EOF'
#tray { min-width: 0; padding: 0; margin: 0; border: none !important;
        background: transparent !important; box-shadow: none !important; }
#tray > * { display: none; }
EOF
    fi

    # Перезагрузить CSS (без перезапуска Waybar)
    pkill -SIGUSR2 waybar

    # Обновить иконку кнопки (SIGRTMIN+8)
    pkill -SIGRTMIN+8 waybar
}

# ── --status : вывести иконку для Waybar ──────────────────────────────────
cmd_status() {
    init
    local state
    state=$(cat "$STATE_FILE")
    if [[ "$state" == "open" ]]; then
        echo "$ICON_OPEN"
    else
        echo "$ICON_CLOSED"
    fi
}

# ── --toggle : переключить и применить ────────────────────────────────────
cmd_toggle() {
    init
    local state
    state=$(cat "$STATE_FILE")
    if [[ "$state" == "open" ]]; then
        echo "closed" > "$STATE_FILE"
    else
        echo "open" > "$STATE_FILE"
    fi
    apply
}

# ── Точка входа ───────────────────────────────────────────────────────────
case "$1" in
    --toggle) cmd_toggle ;;
    --status) cmd_status ;;
    *)        cmd_status ;;  # дефолт — просто статус
esac
