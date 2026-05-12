#!/bin/bash

CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print 100 - $8}' | cut -d'.' -f1)
GPU=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits)

TEXT="<span color='#94e2d5'>${CPU}% 󰍛</span><span color='#45475a'> | </span><span color='#cba6f7'>${GPU}% 󰾲</span>"
TOOLTIP="󰍛 CPU: ${CPU}%\n󰾲 GPU: ${GPU}%"

echo "{\"text\": \"$TEXT\", \"tooltip\": \"$TOOLTIP\"}"
