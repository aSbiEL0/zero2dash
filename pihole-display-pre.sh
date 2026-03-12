#!/bin/sh
# Keep the Linux console off the configured framebuffer and hide the cursor.

FB_DEVICE="${FB_DEVICE:-/dev/fb1}"
FB_NUM="${FB_DEVICE#/dev/fb}"

if command -v con2fbmap >/dev/null 2>&1; then
    if ! con2fbmap 1 "${FB_NUM}" 2>/dev/null; then
        echo "[pre] warning: con2fbmap failed for ${FB_DEVICE}" >&2
    fi
else
    echo "[pre] warning: con2fbmap not found; skipping console remap" >&2
fi

if command -v setterm >/dev/null 2>&1; then
    if ! setterm -cursor off < /dev/tty1 2>/dev/null; then
        echo "[pre] warning: setterm failed on /dev/tty1" >&2
    fi
else
    echo "[pre] warning: setterm not found; skipping cursor hide" >&2
fi

CURSOR_BLINK_PATH=/sys/class/graphics/fbcon/cursor_blink
if [ -w "${CURSOR_BLINK_PATH}" ]; then
    if ! echo 0 > "${CURSOR_BLINK_PATH}" 2>/dev/null; then
        echo "[pre] warning: unable to disable cursor blink" >&2
    fi
else
    echo "[pre] warning: ${CURSOR_BLINK_PATH} is not writable; skipping" >&2
fi

# Give the fb driver a moment to settle.
sleep 2
