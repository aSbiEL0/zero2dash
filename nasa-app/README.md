# NASA / ISS App

Standalone framebuffer app entrypoint: `app.py`

Validation:
- `python nasa-app\app.py --self-test`
- `python nasa-app\tests\test_nasa_app.py`
- `python nasa-app\app.py --health-check`
- `python nasa-app\app.py --page loading --no-framebuffer --output preview-loading.png`
- `python nasa-app\app.py --page details --no-framebuffer --output preview-details.png`
- `python nasa-app\app.py --page crew --no-framebuffer --output preview-crew.png`

Notes:
- The app keeps its own assets, fonts, and caches inside this directory.
- Live position is sourced from Open Notify first; wheretheiss.at enriches velocity, altitude, visibility, geocode, and trail when available.
- The details page shows `Visibility` and crew-derived `Expedition Reason`; flyover prediction has been removed.
