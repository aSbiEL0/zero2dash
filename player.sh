#!/bin/sh
set -eu

FBDEV="${FBDEV:-/dev/fb1}"
VIDEO_DIR="/home/pihole/vid/"
PID_FILE="${PLAYER_PID_FILE:-/tmp/player.sh.pid}"
FRAME_WIDTH="${FRAME_WIDTH:-320}"
FRAME_HEIGHT="${FRAME_HEIGHT:-240}"
BYTES_PER_PIXEL="${BYTES_PER_PIXEL:-2}"
FRAME_BYTES=$((FRAME_WIDTH * FRAME_HEIGHT * BYTES_PER_PIXEL))

ffmpeg_pid=""

usage() {
  cat <<'USAGE'
Usage:
  ./player.sh
  ./player.sh --stop
  ./player.sh --clear-screen
  ./player.sh --stop --clear-screen

Behavior:
  - Plays videos only from /home/pihole/vid/
  - Starts playback immediately
  - Plays all compatible videos in sorted order
  - Centre-crops 426x240 to 320x240 (53 px removed from each side)
  - Repeats the whole folder forever until you stop it (Ctrl+C)
  - --stop stops the currently running player instance via pidfile
  - --clear-screen fills the framebuffer with black and exits
USAGE
}

clear_screen() {
  if [ ! -e "$FBDEV" ]; then
    echo "Framebuffer device not found: $FBDEV" >&2
    exit 1
  fi

  if ! dd if=/dev/zero of="$FBDEV" bs="$FRAME_BYTES" count=1 conv=notrunc 2>/dev/null; then
    echo "Failed to clear framebuffer: $FBDEV" >&2
    exit 1
  fi

  echo "Cleared framebuffer: $FBDEV"
}

stop_player() {
  if [ ! -f "$PID_FILE" ]; then
    echo "No running player instance found."
    return 1
  fi

  player_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -z "$player_pid" ]; then
    rm -f "$PID_FILE"
    echo "Player pidfile is empty; removed stale pidfile."
    return 1
  fi

  if ! kill -0 "$player_pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Player pidfile was stale; removed $PID_FILE."
    return 1
  fi

  kill "$player_pid"
  echo "Stopped player instance: $player_pid"
}

cleanup() {
  if [ -n "$ffmpeg_pid" ] && kill -0 "$ffmpeg_pid" 2>/dev/null; then
    kill "$ffmpeg_pid" 2>/dev/null || true
    wait "$ffmpeg_pid" 2>/dev/null || true
  fi

  if [ -f "$PID_FILE" ] && [ "$(cat "$PID_FILE" 2>/dev/null || true)" = "$$" ]; then
    rm -f "$PID_FILE"
  fi
}

collect_videos_to_list() {
  dir="$1"
  list_file="$2"

  if [ ! -d "$dir" ]; then
    echo "Video directory not found: $dir" >&2
    exit 1
  fi

  find "$dir" -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.mov' -o -iname '*.avi' \) \
    | sort > "$list_file"

  if [ ! -s "$list_file" ]; then
    echo "No videos found in: $dir" >&2
    exit 1
  fi
}

stop_requested=0
clear_requested=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --stop)
      stop_requested=1
      shift
      ;;
    --clear-screen)
      clear_requested=1
      shift
      ;;
    --dir)
      echo "Custom video directories are not supported. Videos must be in $VIDEO_DIR" >&2
      exit 1
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      echo "Unexpected argument: $1" >&2
      echo "Videos must be in $VIDEO_DIR" >&2
      exit 1
      ;;
  esac
done

if [ "$stop_requested" -eq 1 ]; then
  stop_player || true
fi

if [ "$clear_requested" -eq 1 ]; then
  clear_screen
fi

if [ "$stop_requested" -eq 1 ] || [ "$clear_requested" -eq 1 ]; then
  exit 0
fi

if [ ! -e "$FBDEV" ]; then
  echo "Framebuffer device not found: $FBDEV" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required but not installed." >&2
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "Player is already running with PID $existing_pid. Use --stop first." >&2
    exit 1
  fi
  rm -f "$PID_FILE"
fi

echo "$$" > "$PID_FILE"

if [ -x /usr/local/bin/pihole-display-pre.sh ]; then
  /usr/local/bin/pihole-display-pre.sh || true
fi

auto_crop_filter="fps=15,crop=320:240:(in_w-320)/2:0,format=rgb565le"

echo "Playing all videos on $FBDEV from: $VIDEO_DIR"

list_file="$(mktemp)"
trap 'cleanup; rm -f "$list_file"' EXIT INT TERM HUP

while true; do
  collect_videos_to_list "$VIDEO_DIR" "$list_file"

  while IFS= read -r video; do
    [ -n "$video" ] || continue
    echo "Now playing: $video"
    ffmpeg -hide_banner -loglevel error -stats \
      -re \
      -threads 2 \
      -i "$video" \
      -vf "$auto_crop_filter" \
      -an -sn -dn \
      -f fbdev "$FBDEV" &
    ffmpeg_pid=$!
    wait "$ffmpeg_pid"
    ffmpeg_pid=""
  done < "$list_file"
done
