---@module 'hl'

--###################

--##   PROGRAMS   ###

--###################

-- https://wiki.hyprland.org/Configuring/Keywords/

local terminal = "kitty"

local fileManager = "nautilus"

local editor = "vscodium"

local browser = "chromium"

local passwordManager = "keepassxc"

--##################

--## KEYBINDINGS ###

--##################

-- https://wiki.hyprland.org/Configuring/Binds/

-- https://wiki.hyprland.org/Configuring/Keywords/

local mainMod = "SUPER"

-- Application shortcuts

hl.bind(mainMod .. " + " .. "W", hl.dsp.exec_cmd("uwsm app -- kitty"))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. "W", hl.dsp.exec_cmd("[float; size 700 400; move (monitor_w*0.6) (monitor_h*0.1)] uwsm app -- kitty"))

hl.bind(mainMod .. " + " .. "T", hl.dsp.exec_cmd("tor-browser"))

hl.bind(mainMod .. " + " .. "X", hl.dsp.exec_cmd("~/.config/waybar/scripts/weather_popup.py"))

hl.bind(mainMod .. " + " .. "E", hl.dsp.exec_cmd("uwsm app -- nautilus"))

hl.bind(mainMod .. " + " .. "C", hl.dsp.exec_cmd("uwsm app -- vscodium"))

hl.bind(mainMod .. " + " .. "B", hl.dsp.exec_cmd("uwsm app -- chromium"))

hl.bind(mainMod .. " + " .. "K", hl.dsp.exec_cmd("uwsm app -- keepassxc"))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. "E", hl.dsp.exec_cmd("vicinae vicinae://extensions/vicinae/vicinae/search-emojis"))

hl.bind(mainMod .. " + " .. "R", hl.dsp.exec_cmd("vicinae toggle"))

hl.bind(mainMod .. " + " .. "V", hl.dsp.exec_cmd("QT_QPA_PLATFORM=xcb copyq toggle"))

hl.bind(mainMod .. " + " .. "N", hl.dsp.exec_cmd("swaync-client -t -sw"))

-- Change wallpaper

hl.bind(mainMod .. " + " .. "ALT" .. " + " .. "P", hl.dsp.exec_cmd("~/.config/bin/change-wall.sh ~/Pictures/Wallpapers"))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. "P", hl.dsp.exec_cmd("~/.config/bin/wall-selector.sh ~/Pictures/Wallpapers"))

-- Toggle Waybar

hl.bind(mainMod .. " + " .. "ESCAPE", hl.dsp.exec_cmd("killall waybar && waybar"))

-- Toggle Microphone

hl.bind(mainMod .. " + " .. "M", hl.dsp.exec_cmd("~/.config/bin/mic-control.sh m"))

-- Screen Recording

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. "R", hl.dsp.exec_cmd("~/.config/bin/record.sh"))

-- Toggle NoScreenShare

hl.bind(mainMod .. " + " .. "H", hl.dsp.exec_cmd("~/.config/bin/toggle-noscreenshare.sh"))

-- Sessions and power

hl.bind(mainMod .. " + " .. "L", hl.dsp.exec_cmd("loginctl lock-session"))

hl.bind(mainMod .. " + " .. "P", hl.dsp.exec_cmd("~/.config/bin/logout-launch.sh"))

hl.bind(mainMod .. " + " .. "ALT" .. " + " .. "D", hl.dsp.exec_cmd("hyprctl dispatch dpms toggle"), { locked = true })

-- Toggle display

hl.bind(mainMod .. " + " .. "ALT" .. " + " .. "S", hl.dsp.exec_cmd("systemctl suspend"), { locked = true })

-- Screenshots

hl.bind("Print", hl.dsp.exec_cmd("hyprshot -m output -t 1500 -o ~/Pictures/Screen -f $(date +%F_%H-%M-%S)_hyprshot.png"))

hl.bind("SHIFT" .. " + " .. "Print", hl.dsp.exec_cmd("hyprshot -m region -t 1500 -o ~/Pictures/Screen -f $(date +%F_%H-%M-%S)_hyprshot.png"))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. "S", hl.dsp.exec_cmd("grim -g $(slurp -d) -t ppm-| satty --filename- --actions-on-enter save-to-clipboard,save-to-file,exit"))

hl.bind(mainMod .. " + " .. "PRINT", hl.dsp.exec_cmd("~/.config/bin/screenshot-zipline.sh"))

-- Zoom

hl.bind(mainMod .. " + " .. "Z", hl.dsp.exec_cmd("hyprctl keyword cursor:zoom_factor $(awk BEGIN {print $(hyprctl getoption cursor:zoom_factor | grep 'float:' | awk '{print local_var_2}') + 0.3} )"))

hl.bind(mainMod .. " + " .. "mouse_down", hl.dsp.exec_cmd("hyprctl keyword cursor:zoom_factor $(awk BEGIN {print $(hyprctl getoption cursor:zoom_factor | grep 'float:' | awk '{print local_var_2}') + 0.5} )"), { pass = true })

hl.bind(mainMod .. " + " .. "mouse_up", hl.dsp.exec_cmd("hyprctl keyword cursor:zoom_factor $(awk BEGIN {print $(hyprctl getoption cursor:zoom_factor | grep 'float:' | awk '{print local_var_2}') - 0.5} )"), { pass = true })

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. "Z", hl.dsp.exec_cmd("hyprctl keyword cursor:zoom_factor 1.0"))

-- Window management

hl.bind(mainMod .. " + " .. "Q", hl.dsp.window.close())

hl.bind(mainMod .. " + " .. "D", hl.dsp.layout("togglesplit"))

-- dwindle

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. "A", hl.dsp.window.pseudo())

-- dwindle

hl.bind(mainMod .. " + " .. "F", hl.dsp.window.float())

hl.bind(mainMod .. " + " .. "S", hl.dsp.window.pin())

hl.bind(mainMod .. " + " .. "A", hl.dsp.window.fullscreen())

-- maximize

hl.bind("F11", hl.dsp.window.fullscreen())

hl.bind(mainMod .. " + " .. "ALT" .. " + " .. "F", hl.dsp.window.fullscreen())

hl.bind("ALT" .. " + " .. "Tab", hl.dsp.window.cycle_next())

-- TODO: manual review (unknown dispatcher: bringactivetotop)
-- hl.bind("ALT + Tab", hl.dsp.bringactivetotop())

-- Move focus with mainMod + arrow keys

hl.bind(mainMod .. " + " .. "left", hl.dsp.focus({ direction = "left" }))

hl.bind(mainMod .. " + " .. "right", hl.dsp.focus({ direction = "right" }))

hl.bind(mainMod .. " + " .. "up", hl.dsp.focus({ direction = "up" }))

hl.bind(mainMod .. " + " .. "down", hl.dsp.focus({ direction = "down" }))

-- Resize with mainMod + CONTROL + arrow keys

hl.bind("$mainMod + CONTROL + right", hl.dsp.window.resize({ params = "24 0" }))

hl.bind("$mainMod + CONTROL + left",  hl.dsp.window.resize({ params = "-24 0" }))

hl.bind("$mainMod + CONTROL + up",    hl.dsp.window.resize({ params = "0 -24" }))

hl.bind("$mainMod + CONTROL + down",  hl.dsp.window.resize({ params = "0 24" }))

-- Move windows with mainMod + SHIFT + arrow keys

hl.bind("SUPER + SHIFT" .. " + " .. "right", { direction = "r" })

hl.bind("SUPER + SHIFT" .. " + " .. "left", { direction = "l" })

hl.bind("SUPER + SHIFT" .. " + " .. "up", { direction = "u" })

hl.bind("SUPER + SHIFT" .. " + " .. "down", { direction = "d" })

-- Switch workspaces with mainMod + [0-9]

hl.bind(mainMod .. " + " .. 1, hl.dsp.focus({ workspace = 1 }))

hl.bind(mainMod .. " + " .. 2, hl.dsp.focus({ workspace = 2 }))

hl.bind(mainMod .. " + " .. 3, hl.dsp.focus({ workspace = 3 }))

hl.bind(mainMod .. " + " .. 4, hl.dsp.focus({ workspace = 4 }))

hl.bind(mainMod .. " + " .. 5, hl.dsp.focus({ workspace = 5 }))

hl.bind("$mainMod_CTRL" .. " + " .. 1, hl.dsp.focus({ workspace = 6 }))

hl.bind("$mainMod_CTRL" .. " + " .. 2, hl.dsp.focus({ workspace = 7 }))

hl.bind("$mainMod_CTRL" .. " + " .. 3, hl.dsp.focus({ workspace = 8 }))

hl.bind("$mainMod_CTRL" .. " + " .. 4, hl.dsp.focus({ workspace = 9 }))

hl.bind("$mainMod_CTRL" .. " + " .. 5, hl.dsp.focus({ workspace = 10 }))

-- Move active window to a workspace with mainMod + SHIFT + [0-9]

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. 1, hl.dsp.window.move({ workspace = 1 }))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. 2, hl.dsp.window.move({ workspace = 2 }))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. 3, hl.dsp.window.move({ workspace = 3 }))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. 4, hl.dsp.window.move({ workspace = 4 }))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. 5, hl.dsp.window.move({ workspace = 5 }))

hl.bind("$mainMod_CTRL_SHIFT" .. " + " .. 1, hl.dsp.window.move({ workspace = 6 }))

hl.bind("$mainMod_CTRL_SHIFT" .. " + " .. 2, hl.dsp.window.move({ workspace = 7 }))

hl.bind("$mainMod_CTRL_SHIFT" .. " + " .. 3, hl.dsp.window.move({ workspace = 8 }))

hl.bind("$mainMod_CTRL_SHIFT" .. " + " .. 4, hl.dsp.window.move({ workspace = 9 }))

hl.bind("$mainMod_CTRL_SHIFT" .. " + " .. 5, hl.dsp.window.move({ workspace = 10 }))

-- Special workspace (scratchpad)

hl.bind(mainMod .. " + " .. "TAB", hl.dsp.workspace.toggle_special("scratchpad"))

hl.bind(mainMod .. " + " .. "SHIFT" .. " + " .. "TAB", hl.dsp.window.move({ workspace = "special:scratchpad" }))

-- Scroll through existing workspaces with mainMod + scroll

-- bind = $mainMod, mouse_down, workspace, e+1

-- bind = $mainMod, mouse_up, workspace, e-1

-- Move/resize windows with mainMod + LMB/RMB and dragging

hl.bind(mainMod .. " + " .. "mouse:272", hl.dsp.window.drag(), { mouse = true })

hl.bind(mainMod .. " + " .. "mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Multimedia keys

hl.bind(mainMod .. " + " .. "F3", hl.dsp.exec_cmd("~/.config/bin/volume-control.sh d"), { locked = true })

hl.bind(mainMod .. " + " .. "F4", hl.dsp.exec_cmd("~/.config/bin/volume-control.sh i"), { locked = true })

hl.bind(mainMod .. " + " .. "F5", hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"), { locked = true })

-- Laptop multimedia keys for volume and LCD brightness

hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("~/.config/bin/volume-control.sh d"), { locked = true })

hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("~/.config/bin/volume-control.sh i"), { locked = true })

hl.bind("XF86AudioMute", hl.dsp.exec_cmd("~/.config/bin/volume-control.sh m"), { locked = true })

hl.bind("XF86AudioMicMute", hl.dsp.exec_cmd("~/.config/bin/mic-control.sh m"), { locked = true })

hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("~/.config/bin/brightness-control.sh -o d"), { locked = true })

hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd("~/.config/bin/brightness-control.sh -o i"), { locked = true })

-- Requires playerctl

hl.bind("XF86AudioNext", hl.dsp.exec_cmd("playerctl next"), { locked = true })

hl.bind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })

hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })

hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("playerctl previous"), { locked = true })

hl.bind(mainMod .. " + " .. "A", hl.dsp.exec_cmd("cool-retro-term"))
