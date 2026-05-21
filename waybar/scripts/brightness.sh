#!/bin/bash
STATE_FILE="/tmp/brightness_state"

[ -f "$STATE_FILE" ] && STATE=$(cat "$STATE_FILE") || STATE="max"

case $1 in
    toggle)
        if [ "$STATE" = "max" ]; then
            ddcutil setvcp 10 10 --bus 3 --noverify
            echo "min" > "$STATE_FILE"
        else
            ddcutil setvcp 10 100 --bus 3 --noverify
            echo "max" > "$STATE_FILE"
        fi
        pkill -RTMIN+9 waybar
        ;;
    *)
        if [ "$STATE" = "min" ]; then
            echo '{"text": "󰖔"}'
        else
            echo '{"text": "󰖙"}'
        fi
        ;;
esac
