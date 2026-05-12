#!/bin/bash

# === Устройство ===
MIC="alsa_input.usb-MV-SILICON_fifine_Microphone_20190808-00.mono-fallback"

# Display usage help
print_error() {
    cat <<"EOF"
Usage: ./mic-control.sh <action>
Actions:
    i   -- increase sensitivity [+1%]
    d   -- decrease sensitivity [-1%]
    m   -- toggle mute
EOF
    exit 1
}

# Send notification and switch cursor on mute
notify_mute() {
    mute=$(pactl get-source-mute "$MIC" | awk '{print $2}')

    # Получаем текущую позицию курсора
    pos=$(hyprctl cursorpos)
    cx=$(echo "$pos" | cut -d',' -f1)
    cy=$(echo "$pos" | cut -d',' -f2 | tr -d ' ')

    if [ "${mute}" = "yes" ]; then
        notify-send "Microphone" "Muted" -i microphone-sensitivity-high-symbolic -t 1000 -r 91191
        hyprctl setcursor Bibata-Modern-Amber 20
    else
        notify-send "Microphone" "Unmuted" -i microphone-sensitivity-high-symbolic -t 1000 -r 91191
        hyprctl setcursor Bibata-Modern-Classic 20
    fi

    # Двигаем на месте
    hyprctl dispatch movecursor $((cx + 1)) "$cy"
    hyprctl dispatch movecursor "$cx" "$cy"
}

# Handle sensitivity changes
action_volume() {
    current_vol=$(pactl get-source-volume "$MIC" | grep -m1 'Volume:' | awk '{print $5}' | sed 's/%//')
    case "${1}" in
    i)
        if [ "$current_vol" -lt 100 ]; then
            new_vol=$((current_vol + 1))
            [ "$new_vol" -gt 100 ] && new_vol=100
            pactl set-source-volume "$MIC" "${new_vol}%"
        fi
        ;;
    d)
        new_vol=$((current_vol - 1))
        [ "$new_vol" -lt 0 ] && new_vol=0
        pactl set-source-volume "$MIC" "${new_vol}%"
        ;;
    esac
}

# Main execution
case "${1}" in
i) action_volume i ;;
d) action_volume d ;;
m) pactl set-source-mute "$MIC" toggle && notify_mute ;;
*) print_error ;;
esac
