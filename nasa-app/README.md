# NASA / ISS App

Standalone framebuffer app entrypoint: `app.py`

Validation:
- `C:\ISS\.venv\Scripts\python.exe nasa-app\app.py --self-test`
- `C:\ISS\.venv\Scripts\python.exe nasa-app\tests\test_nasa_app.py`
- `C:\ISS\.venv\Scripts\python.exe nasa-app\app.py --page details --no-framebuffer --output preview.png`

Notes:
- The app keeps its own assets, fonts, and caches inside this directory.
- Observer coordinates are read from the repo `.env` via `WEATHER_LAT` and `WEATHER_LON`.
- The details page shows `Visibility` and crew-derived `Expedition Reason`; flyover prediction has been removed.
