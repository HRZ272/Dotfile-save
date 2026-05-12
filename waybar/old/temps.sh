#!/bin/bash
CPU=$(sensors 2>/dev/null | grep "Tctl" | awk '{print $2}' | tr -d '+°C' | cut -d'.' -f1)
GPU=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits)

TEXT="<span color='#94e2d5'>${CPU}°󰔏</span><span color='#45475a'> | </span><span color='#cba6f7'>${GPU}°󰾲</span>"
TOOLTIP="󰔏 CPU: ${CPU}°C\n󰾲 GPU: ${GPU}°C"

echo "{\"text\": \"$TEXT\", \"tooltip\": \"$TOOLTIP\"}"
