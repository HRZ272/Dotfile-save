---@module 'hl'

--###############

--##   EXEC    ###

--################

--## Required
hl.on("hyprland.start", function()
  hl.exec_cmd("uwsm app -- swww-daemon")
end)

--## User programs
hl.on("hyprland.start", function()
  hl.exec_cmd("uwsm app -- kdeconnectd")
  hl.exec_cmd("uwsm app -- kdeconnect-indicator")
  hl.exec_cmd("uwsm app -- keepassxc")
end)

-- keepassxc: тихо закинуть на 5-й воркспейс при открытии
hl.window_rule({
  name = "keepassxc-silent-workspace",
  match = { class = "keepassxc" },
  workspace = "5 silent",
})

-- Autostart
hl.on("hyprland.start", function()
    hl.exec_cmd("systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP")
    hl.exec_cmd("dbus-update-activation-environment --all")
    hl.exec_cmd("sleep 1 && dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP")
    hl.exec_cmd("uwsm app -- gnome-keyring-daemon --start --components=secrets")
    hl.exec_cmd("uwsm app -- /usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1")
    hl.exec_cmd("uwsm app -- sleep 0.3; ~/.config/bin/change-wall.sh ~/Pictures/Wallpapers")
    hl.exec_cmd("uwsm app -- nwg-look -a")
    hl.exec_cmd("uwsm app -- vicinae server")
    hl.exec_cmd("uwsm app -- swaync -c ~/.config/swaync/config.json")
    hl.exec_cmd("uwsm app -- waybar -c ~/.config/waybar/config.jsonc -s ~/.config/waybar/style.css")
    hl.exec_cmd("uwsm app -- nm-applet")
    hl.exec_cmd("uwsm app -- blueman-applet")
end)
