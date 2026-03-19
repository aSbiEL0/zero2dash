# Validation

## Covered

- Rotator touch and power behavior
- Themed shell routing and asset validation
- Theme persistence
- Mode request handling
- Tram render smoke tests

## Commands

```sh
python3 -m unittest tests.test_display_rotator tests.test_boot_selector
python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif
python3 modules/trams/display.py --self-test
```

## Remaining Manual Checks

- Touch hardware on the Pi
- Framebuffer ownership handoff
- Service interactions under `systemd`
