# zero2dash Wiki

`PLAN.md` is the active source of truth for the rebuild.

## Current Runtime

- `boot/boot_selector.py` is the parent shell
- `display_rotator.py` is the Dashboards child entrypoint
- `modules/photos/slideshow.py` is the Photos child entrypoint
- Shell modes are `menu`, `dashboards`, `photos`, and `night`
- The shell baseline is working on the Pi and the remaining work has moved to app-specific issues

## Theme Contract

- Shell assets come from `themes/default`, `themes/comic`, and `themes/steele`
- Theme selection persists only
- Root-page return state is session-only
- `keypad.png` is a 4x3 grid with `tick` in the top-right and `red X` in the bottom-right

## Validation

- `python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif`
- `python3 -m unittest tests.test_display_rotator tests.test_boot_selector`
- `python3 modules/trams/display.py --self-test`

The shell validation gate is effectively complete; remaining validation now belongs to app-specific streams.

## Related Pages

- [Runtime](Runtime.md)
- [Validation](Validation.md)
