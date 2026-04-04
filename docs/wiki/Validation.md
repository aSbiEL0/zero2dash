# Validation

## Covered

- Rotator touch and power behavior
- Themed shell routing and asset validation
- Theme persistence
- Mode request handling
- Player playlist filtering, sorting, and wrap logic
- Shell launch-contract checks for credits and vault player modes
- Tram render smoke tests
- Pi-side shell validation for the current shell slice is complete

## Commands

```sh
python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif
python3 player.py --self-test
python3 -m unittest discover -s tests -v
python3 modules/trams/display.py --self-test
```

## Device Validation Evidence

- Themes selector mapping confirmed on hardware
- Right-side stripe/back behavior confirmed on hardware
- Settings layout rendering confirmed on hardware

## Notes

- The player and shell contract tests now live in top-level `tests/`.
- Full Pi validation is still required for framebuffer playback, touch timing, and vault background correctness.
