#!/bin/bash

HEADPHONES_ID=$(wpctl status | grep "HyperX" | grep "Аналоговый" | grep -oP '\d+' | head -1)
CURRENT=$(wpctl status | grep "^\s*\*" | grep -oP '\d+' | head -1)

if [ "$CURRENT" = "$HEADPHONES_ID" ]; then
    echo '{"text":"󰋋","class":"active"}'
else
    echo '{"text":"󰋋","class":""}'
fi
