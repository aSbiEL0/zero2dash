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
- Live position is sourced from Open Notify first; wheretheiss.at enriches velocity, altitude, visibility, and trail when available.
- `Currently over:` now uses the local country boundary dataset in `nasa-app/assets/countries/`. Over land it shows the country name; over water it shows `Ocean`.
- Important: the raw world boundary files in `nasa-app/assets/countries/` are intentionally ignored in git because the source dataset is too large for GitHub. A fresh clone on the Pi will not contain them automatically.
- If you want offline country lookup on the Pi, you must copy the local boundary files into `nasa-app/assets/countries/` on that device yourself.
- The long-term intent is to replace the raw boundary source files with a smaller derived offline artifact that is safe to ship in the repo.
- The details page now shows `Longitude`, `Latitude`, `Currently over`, `Altitude`, `Velocity`, and `Day/Night`.
- Layout tuning lives in the constants near the top of `app.py`; `# notes:` comments there explain which values move the labels, values, rows, stale badge, loading text box, and page display timing.
