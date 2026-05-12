#!/bin/bash

SPEAKERS_ID=$(wpctl status | grep "Starship" | grep "Аналоговый" | grep -oP '\d+' | head -1)
CURRENT=$(wpctl status | grep "^\s*\*" | grep -oP '\d+' | head -1)

if [ "$CURRENT" = "$SPEAKERS_ID" ]; then
    echo '{"text":"󰓃","class":"active"}'
else
    echo '{"text":"󰓃","class":""}'
fi
