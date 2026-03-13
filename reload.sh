#!/bin/sh
cd /home/pihole/zero2dash/
echo Refreshing all modules and rendering new images where necessary
sleep 0.1
systemctl /etc/systemd/system/daemon-reload
sleep 1
Daemon-reload completed
python3 /home/pihole/zero2dash/modules/calendash/calendash-api.py
python3 /home/pihole/zero2dash/modules/currency/currency-rate.py --force-refresh
python3 /home/pihole/zero2dash/modules/weather/weather_refresh.py
echo Images rendered, reloading display.service to test output. 
systemctl reload display.service
echo Task complete.
