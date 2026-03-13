#!/bin/sh
set -eu

cd /home/pihole/zero2dash/
echo "Refreshing all modules and rendering new images where necessary"

systemctl daemon-reload
echo "Daemon-reload completed"

python3 /home/pihole/zero2dash/modules/calendash/calendash-api.py
python3 /home/pihole/zero2dash/modules/currency/currency-rate.py --force-refresh
python3 /home/pihole/zero2dash/modules/weather/weather_refresh.py

echo "Images rendered, restarting display.service to test output."
systemctl restart display.service
echo "Task complete."
