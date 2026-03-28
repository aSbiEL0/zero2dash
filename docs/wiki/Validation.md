# Validation

## Covered

- Rotator touch and power behavior
- Themed shell routing and asset validation
- Theme persistence
- Mode request handling
- Tram render smoke tests
- Pi-side shell validation for the current shell slice is complete

## Commands

```sh
python3 -m unittest tests.test_display_rotator
python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif
python3 modules/trams/display.py --self-test
```

## Device Validation Evidence

- Themes selector mapping confirmed on hardware
- Right-side stripe/back behavior confirmed on hardware
- Settings layout rendering confirmed on hardware

## Notes

- `tests/test_boot_selector.py` is not currently checked in, so shell acceptance for this slice relied on device validation plus targeted runtime checks.
