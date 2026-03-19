zero2dash shell rules (boot/)

Current active shell scope
    • `boot/boot_selector.py`
    • shell menu routing
    • Themes mapping
    • Settings rendering
    • menu-touch sign-off support and calibration guidance

In scope for the current slice
    • fix top-row Themes order to match visible art
    • make lower-row Themes zones inactive
    • keep theme persistence behavior unchanged
    • reformat Settings text rendering only
    • support operator calibration/validation flow for menu touches

Out of scope for the current slice
    • NASA app work
    • Photos behavior changes
    • rotator changes
    • systemd edits
    • visual calibration UI
    • theme asset redesign

Ask first
Always ask before:
    • changing touch-mapping math instead of calibration guidance
    • changing Settings content providers instead of rendering only
    • re-enabling hidden lower-row theme zones
    • touching child-app entrypoints or non-shell runtime paths

Validation expectations
    • `tests.test_boot_selector` protects top-row theme order and lower-row inactivity
    • on-device touch sign-off happens only after `--probe-touch` and `--calibrate-touch`
    • shell edits stay minimal and reversible
