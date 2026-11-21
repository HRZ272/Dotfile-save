
---@module 'hl'

--##############

--## GENERAL ###

--##############



--############################

--## ENVIRONMENT VARIABLES ###

--############################

-- https://wiki.hyprland.org/Configuring/Environment-variables/

hl.env("XCURSOR_THEME", "Bibata-Modern-Classic")

hl.env("XCURSOR_SIZE", 20)

hl.env("QT_QPA_PLATFORM", "wayland;xcb")

hl.env("QT_QPA_PLATFORMTHEME", "qt6ct")

hl.env("QT_WAYLAND_DISABLE_WINDOWDECORATION", 1)

hl.env("QT_AUTO_SCREEN_SCALE_FACTOR", 1)

hl.env("MOZ_ENABLE_WAYLAND", 1)

hl.env("ELECTRON_OZONE_PLATFORM_HINT", "wayland")

hl.env("OZONE_PLATFORM", "wayland")

hl.env("XDG_SESSION_TYPE", "wayland")

-- env = GDK_BACKEND,wayland,x11,*

-- env = SDL_VIDEODRIVER,wayland

hl.env("XDG_CURRENT_DESKTOP", "Hyprland")

hl.env("XDG_SESSION_DESKTOP", "Hyprland")

--####################

--## LOOK AND FEEL ###

--####################

-- https://wiki.hyprland.org/Configuring/Variables/

-- https://wiki.hypr.land/Configuring/Variables/#general

hl.config({
    general = {
        gaps_in = 4,
        gaps_out = 7,
        gaps_workspaces = 20,
        border_size = 2,
        resize_on_border = true,
        no_focus_fallback = true,
        allow_tearing = false,
        layout = "dwindle",
        snap = {
            enabled = true,
            window_gap = 20,
            monitor_gap = 10,
            respect_gaps = true,
        },
        col = {
            active_border = "rgba(b4befeee)",
            inactive_border = "rgb(000000)",
        },
    },
})

-- https://wiki.hyprland.org/Configuring/Variables/#decoration

hl.config({
    decoration = {
        rounding = 13,
        active_opacity = 0.92,
        inactive_opacity = 0.92,
        blur = {
            enabled = true,
            new_optimizations = true,
            xray = true,
            special = false,
            size = 13,
            passes = 2,
            brightness = 1,
            noise = 0.04,
            contrast = 0.9,
        },
        shadow = {
            enabled = false,
        },
    },
})

-- https://wiki.hyprland.org/Configuring/Variables/#animations

hl.config({
    animations = {
        enabled = true,
        -- animation = border, 1, 1, liner
        -- animation = borderangle, 1, 20, liner, loop
    },
})

-- https://wiki.hyprland.org/Configuring/Dwindle-Layout/

hl.config({
    dwindle = {
        preserve_split = true,
    },
})

-- https://wiki.hyprland.org/Configuring/Master-Layout/

hl.config({
    master = {
        new_status = "master",
    },
})

-- https://wiki.hyprland.org/Configuring/Variables/#misc

hl.config({
    misc = {
        focus_on_activate = false,
        force_default_wallpaper = 0,
        disable_hyprland_logo = true,
        animate_manual_resizes = false,
        on_focus_under_fullscreen = 2,
        allow_session_lock_restore = true,
    },
})

-- https://wiki.hypr.land/Configuring/Variables/#binds

hl.config({
    binds = {
        hide_special_on_workspace_change = true,
        drag_threshold = 10,
    },
})

-- https://wiki.hypr.land/Configuring/Variables/#cursor

hl.config({
    cursor = {
        zoom_factor = 1,
        zoom_rigid = false,
        hotspot_padding = 1,
        zoom_disable_aa = false,
    },
})

-- https://wiki.hypr.land/Configuring/Variables/#ecosystem

hl.config({
    ecosystem = {
        no_update_news = true,
    },
})

--############

--## INPUT ###

--############

-- https://wiki.hyprland.org/Configuring/Variables/#input

hl.config({
    input = {
        kb_layout = { "us", "ru" },
        kb_variant = {  },
        kb_model = {  },
        kb_options = "grp:caps_toggle",
        kb_rules = {  },
        scroll_factor = 1,
        numlock_by_default = true,
        follow_mouse = true,
        sensitivity = 0,
        touchpad = {
            natural_scroll = true,
            scroll_factor = 1,
        },
    },
})

--###############

--## GESTURES ###

--###############

-- https://wiki.hyprland.org/Configuring/Variables/#gestures

hl.config({
    gestures = {
        workspace_swipe_distance = 600,
        workspace_swipe_cancel_ratio = 0.2,
        workspace_swipe_min_speed_to_force = 5,
        workspace_swipe_direction_lock = true,
        workspace_swipe_direction_lock_threshold = 10,
        workspace_swipe_create_new = true,
    },
})

hl.gesture({ fingers = 3, direction = "swipe", action = "move" })
hl.gesture({ fingers = 4, direction = "horizontal", action = "workspace" })
hl.gesture({ fingers = 4, direction = "up", action = "fullscreen", scale = 1.5 })
hl.gesture({ fingers = 4, direction = "down", action = "maximize", scale = 1.5 })

hl.layer_rule({
    match = {
        namespace = "match:namespace waybar",
    },
    no_anim = "on",
})

hl.layer_rule({
    match = {
        namespace = "match:namespace waybar",
    },
    blur = "off",
})

hl.window_rule({
    name  = "waybar-notes",
    match = {
        class = "Waybar-notes",
    },
    float = true,
    size = { 700, 500 },
    center = true,
})

hl.workspace_rule({
    workspace = 1,
    monitor = "HDMI-A-1",
})

hl.workspace_rule({
    workspace = 2,
    monitor = "HDMI-A-1",
})

hl.workspace_rule({
    workspace = 3,
    monitor = "HDMI-A-1",
})

hl.workspace_rule({
    workspace = 4,
    monitor = "HDMI-A-1",
})

hl.workspace_rule({
    workspace = 5,
    monitor = "HDMI-A-1",
})

hl.workspace_rule({
    workspace = 6,
    monitor = "DP-2",
})

hl.workspace_rule({
    workspace = 7,
    monitor = "DP-2",
})

hl.workspace_rule({
    workspace = 8,
    monitor = "DP-2",
})

hl.workspace_rule({
    workspace = 9,
    monitor = "DP-2",
})

hl.workspace_rule({
    workspace = 10,
    monitor = "DP-2",
})

-- Autostart
hl.on("hyprland.start", function()
    hl.exec_cmd("swaybg -i /home/horizon/Загрузки/dark-star.jpg -m fill")
    hl.exec_cmd("QT_QPA_PLATFORM=xcb copyq")
end)
