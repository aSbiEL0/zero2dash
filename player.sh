#!/bin/sh
set -eu

FBDEV="${FBDEV:-/dev/fb1}"
VIDEO_DIR="${VIDEO_DIR:-/home/pihole/vid}"

usage() {
  cat <<'USAGE'
Usage:
  ./player.sh --dir /path/to/video-folder
  ./player.sh /path/to/video-folder
  ./player.sh

Behavior:
  - Starts playback immediately
  - Plays all compatible videos in the selected folder in sorted order
  - Center-crops 426x240 to 320x240 (53 px removed from each side)
  - Repeats the whole folder forever until you stop it (Ctrl+C)
USAGE
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

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
esac

if [ ! -e "$FBDEV" ]; then
  echo "Framebuffer device not found: $FBDEV" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required but not installed." >&2
  exit 1
fi

TARGET_DIR="$VIDEO_DIR"
if [ "${1:-}" = "--dir" ]; then
  if [ -z "${2:-}" ]; then
    echo "Missing directory path after --dir" >&2
    usage
    exit 1
  fi
  TARGET_DIR="$2"
elif [ -n "${1:-}" ]; then
  TARGET_DIR="$1"
fi

if [ -x /usr/local/bin/pihole-display-pre.sh ]; then
  /usr/local/bin/pihole-display-pre.sh || true
fi

auto_crop_filter="fps=15,crop=320:240:(in_w-320)/2:0,format=rgb565le"

echo "Playing all videos on $FBDEV from: $TARGET_DIR"

list_file="$(mktemp)"
trap 'rm -f "$list_file"' EXIT INT TERM

while true; do
  collect_videos_to_list "$TARGET_DIR" "$list_file"

  while IFS= read -r video; do
    [ -n "$video" ] || continue
    echo "Now playing: $video"
	ffmpeg -hide_banner -loglevel error -stats \
	  -re \
	  -threads 2 \
	  -i "$video" \
	  -vf "$auto_crop_filter" \
	  -an -sn -dn \
	  -f fbdev "$FBDEV"
 done < "$list_file"
done
