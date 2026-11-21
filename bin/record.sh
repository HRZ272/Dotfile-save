#!/bin/bash

###
# Source: https://github.com/basecamp/omarchy/blob/master/bin/omarchy-cmd-screenrecord
###

OUTPUT_DIR="$HOME/Videos/Recordings"
LOG_FILE="/tmp/gsr.log"

if [[ ! -d "$OUTPUT_DIR" ]]; then
    notify-send "Screen recording" "Directory does not exist: $OUTPUT_DIR" -u critical -t 3000
    exit 1
fi

SCOPE=""
AUDIO="true"
WEBCAM="false"

for arg in "$@"; do
    case "$arg" in
    --with-audio) AUDIO="true" ;;
    --with-webcam) WEBCAM="true" ;;
    output | region) SCOPE="$arg" ;;
    esac
done

cleanup_webcam() {
    pkill -f "WebcamOverlay" 2>/dev/null
}

start_webcam_overlay() {
    cleanup_webcam

    local scale target_width preferred_resolutions video_size_arg available_formats

    # Get monitor scale
    scale=$(hyprctl monitors -j | jq -r '.[] | select(.focused == true) | .scale')

    # Target width (base 360px, scaled to monitor)
    target_width=$(awk "BEGIN {printf \"%.0f\", 360 * $scale}")

    # Try preferred 16:9 resolutions in order, use first available
    preferred_resolutions=("640x360" "1280x720" "1920x1080")
    available_formats=$(v4l2-ctl --list-formats-ext -d /dev/video0 2>/dev/null)

    for resolution in "${preferred_resolutions[@]}"; do
        if echo "$available_formats" | grep -q "$resolution"; then
            video_size_arg="-video_size $resolution"
            break
        fi
    done

    ffplay -f v4l2 $video_size_arg -framerate 30 /dev/video0 \
        -vf "scale=${target_width}:-1" \
        -window_title "WebcamOverlay" \
        -noborder \
        -fflags nobuffer -flags low_delay \
        -probesize 32 -analyzeduration 0 \
        -loglevel quiet &
    sleep 1
}

start_screenrecording() {
    local filename audio_args gsr_pid

    filename="$OUTPUT_DIR/$(date +%Y-%m-%d_%H-%M-%S).mp4"

    # Merge audio tracks into one - separate tracks only play one at a time in most players
    [[ "$AUDIO" == "true" ]] && audio_args="-a default_output|default_input"

    notify-send "Screen recording" "Starting recording to $filename" -t 1000
    sleep 1.1

    # Log the command and gsr output so crashes are visible
    {
        echo "=== $(date) ==="
        echo "cmd: gpu-screen-recorder -w $* -f 60 -c mp4 -o $filename $audio_args"
    } >"$LOG_FILE"

    gpu-screen-recorder -w "$@" -f 60 -c mp4 -o "$filename" $audio_args >>"$LOG_FILE" 2>&1 &
    gsr_pid=$!

    # Give it a moment to fail, then check if it is still alive
    sleep 1
    if ! kill -0 "$gsr_pid" 2>/dev/null; then
        notify-send "Screen recording" "gpu-screen-recorder crashed:\n$(tail -n 4 "$LOG_FILE")" -u critical -t 10000
        cleanup_webcam
        toggle_screenrecording_indicator
        exit 1
    fi

    toggle_screenrecording_indicator
}

stop_screenrecording() {
    pkill -SIGINT -f "gpu-screen-recorder" # SIGINT required to save video properly

    # Wait a maximum of 5 seconds to finish before hard killing
    local count=0
    while pgrep -f "gpu-screen-recorder" >/dev/null && [ $count -lt 50 ]; do
        sleep 0.1
        count=$((count + 1))
    done

    if pgrep -f "gpu-screen-recorder" >/dev/null; then
        pkill -9 -f "gpu-screen-recorder"
        cleanup_webcam
        notify-send "Screen recording" "Recording process had to be force-killed. Video may be corrupted." -u critical -t 5000
    else
        cleanup_webcam
        notify-send "Screen recording" "Saved to $OUTPUT_DIR" -t 2000
    fi
    toggle_screenrecording_indicator
}

toggle_screenrecording_indicator() {
    pkill -RTMIN+8 waybar
}

screenrecording_active() {
    pgrep -f "gpu-screen-recorder" >/dev/null || pgrep -x slurp >/dev/null || pgrep -f "WebcamOverlay" >/dev/null
}

if screenrecording_active; then
    if pgrep -x slurp >/dev/null; then
        pkill -x slurp 2>/dev/null
    elif pgrep -f "WebcamOverlay" >/dev/null && ! pgrep -f "gpu-screen-recorder" >/dev/null; then
        cleanup_webcam
    else
        stop_screenrecording
    fi
elif [[ "$SCOPE" == "output" ]]; then
    [[ "$WEBCAM" == "true" ]] && start_webcam_overlay

    if ! output=$(slurp -o -f "%o"); then
        [[ "$WEBCAM" == "true" ]] && cleanup_webcam
        exit 1
    fi

    if [[ -z "$output" ]]; then
        notify-send "Screen recording" "Could not detect monitor" -u critical
        [[ "$WEBCAM" == "true" ]] && cleanup_webcam
        exit 1
    fi

    start_screenrecording "$output"
else
    [[ "$WEBCAM" == "true" ]] && start_webcam_overlay

    if ! region=$(slurp -f "%wx%h+%x+%y"); then
        [[ "$WEBCAM" == "true" ]] && cleanup_webcam
        exit 1
    fi

    # Allow negative X/Y (monitor to the left/above primary)
    if [[ "$region" =~ ^([0-9]+)x([0-9]+)\+(-?[0-9]+)\+(-?[0-9]+)$ ]]; then
        rw="${BASH_REMATCH[1]}"
        rh="${BASH_REMATCH[2]}"
        rx="${BASH_REMATCH[3]}"
        ry="${BASH_REMATCH[4]}"

        # Find scale of the monitor that actually contains the selection,
        # not just the focused one.
        cx=$(( rx + rw / 2 ))
        cy=$(( ry + rh / 2 ))

        monitors_json=$(hyprctl monitors -j)
        scale=$(echo "$monitors_json" | jq -r \
            --argjson cx "$cx" --argjson cy "$cy" '
            .[] | select(
                .x <= $cx and $cx < (.x + (.width  / .scale)) and
                .y <= $cy and $cy < (.y + (.height / .scale))
            ) | .scale' | head -1)

        # Fallback to focused monitor if region centre didn't land on any monitor
        if [[ -z "$scale" ]]; then
            scale=$(echo "$monitors_json" | jq -r '.[] | select(.focused == true) | .scale')
        fi

        w=$(awk "BEGIN {printf \"%.0f\", $rw * $scale}")
        h=$(awk "BEGIN {printf \"%.0f\", $rh * $scale}")
        x=$(awk "BEGIN {printf \"%.0f\", $rx * $scale}")
        y=$(awk "BEGIN {printf \"%.0f\", $ry * $scale}")
        scaled_region="${w}x${h}+${x}+${y}"
    else
        scaled_region="$region"
    fi

    start_screenrecording region -region "$scaled_region"
fi
