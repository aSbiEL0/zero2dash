[1mdiff --git a/display_layout.py b/display_layout.py[m
[1mindex 99f341c..724d5c8 100644[m
[1m--- a/display_layout.py[m
[1m+++ b/display_layout.py[m
[36m@@ -12,9 +12,9 @@[m [mCANVAS_HEIGHT = 240[m
 HEADER_HEIGHT = 80[m
 ROW_HEIGHT = 32[m
 BODY_ROWS = 5[m
[31m-SIDE_MARGIN = 15[m
[32m+[m[32mSIDE_MARGIN = 10[m
 BODY_WIDTH = CANVAS_WIDTH - (SIDE_MARGIN * 2)[m
[31m-RIGHT_EXTRA_INSET = 0[m
[32m+[m[32mRIGHT_EXTRA_INSET = 5[m
 [m
 [m
 @dataclass(frozen=True)[m
[1mdiff --git a/modules/calendash/calendash.png b/modules/calendash/calendash.png[m
[1mindex fc41508..82a19fe 100644[m
Binary files a/modules/calendash/calendash.png and b/modules/calendash/calendash.png differ
[1mdiff --git a/modules/weather/weather-cache.json b/modules/weather/weather-cache.json[m
[1mindex a73e0a4..0eba7b2 100644[m
[1m--- a/modules/weather/weather-cache.json[m
[1m+++ b/modules/weather/weather-cache.json[m
[36m@@ -1 +1 @@[m
[31m-{"location": "Manchester", "max_temp_c": 10, "min_temp_c": 4, "observed_at": "2026-03-15T02:00:00", "rain_probability": 0, "temperature_c": 4, "timezone_name": "Europe/London", "wind_kmh": 12}[m
[32m+[m[32m{"location": "Manchester", "max_temp_c": 17, "min_temp_c": 8, "observed_at": "2026-03-19T15:00:00", "rain_probability": 0, "temperature_c": 17, "timezone_name": "Europe/London", "wind_kmh": 9}[m
[1mdiff --git a/modules/weather/weather.png b/modules/weather/weather.png[m
[1mindex dd91ce3..e28bb38 100644[m
Binary files a/modules/weather/weather.png and b/modules/weather/weather.png differ
