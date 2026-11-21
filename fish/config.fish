source /usr/share/cachyos-fish-config/cachyos-config.fish

# overwrite greeting
# potentially disabling fastfetch
#function fish_greeting
#    # smth smth
#end

abbr -a fs 'flatpak run com.github.tchx84.Flatseal'
abbr -a wps 'flatpak run com.wps.Office'

# 💜 VIOLET ABYSS

# Основные цвета
set -g fish_color_normal C7B1FF
set -g fish_color_command A879E8
set -g fish_color_keyword B58AFF
set -g fish_color_quote 8DCAFF
set -g fish_color_redirection 9D83E8
set -g fish_color_end 8060C9
set -g fish_color_error FF6B9D
set -g fish_color_param D5C4FF
set -g fish_color_comment 65527D
set -g fish_color_operator B58AFF
set -g fish_color_escape 8DCAFF
set -g fish_color_autosuggestion 594875
set -g fish_color_selection --background=38205A
set -g fish_color_search_match --background=52317D

# Prompt
function fish_prompt
    set_color A879E8
    echo -n '╭─ '

    set_color 8DCAFF
    echo -n (prompt_pwd)

    set_color C7B1FF
    echo -n ' λ '

    set_color normal
end
