function wps --wraps='flatpak run com.wps.Office' --description 'alias wps=flatpak run com.wps.Office'
    flatpak run com.wps.Office $argv
end
