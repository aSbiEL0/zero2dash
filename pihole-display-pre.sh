#!/bin/sh
# Keep the Linux console off the SPI framebuffer and hide the cursor
con2fbmap 1 0 2>/dev/null || true
setterm -cursor off < /dev/tty1 2>/dev/null || true
echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true
# Give the fb driver a moment to settle
sleep 2