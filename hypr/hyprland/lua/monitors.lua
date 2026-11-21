---@module 'hl'

--###############

--## MONITORS ###

--###############

-- https://wiki.hyprland.org/Configuring/Monitors/

hl.monitor({
    output   = "HDMI-A-1",
    mode     = "1920x1080@180",
    position = "0x0",
    scale    = 1,
})

hl.monitor({
    output   = "DP-2",
    mode     = "1920x1080@180",
    position = "1920x0",
    scale    = 1,
})

