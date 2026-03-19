# zero2dash Wiki

`PLAN.md` is the active source of truth for the rebuild.

## Current Runtime

- `boot/boot_selector.py` is the parent shell
- `display_rotator.py` is the Dashboards child entrypoint
- `modules/photos/slideshow.py` is the Photos child entrypoint
- Shell modes are `menu`, `dashboards`, `photos`, and `night`

## Theme Contract

- Shell assets come from `themes/default`, `themes/comic`, and `themes/steele`
- Theme selection persists only
- Root-page return state is session-only

## Validation

- `python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif`
- `python3 -m unittest tests.test_display_rotator tests.test_boot_selector`
- `python3 modules/trams/display.py --self-test`

## Related Pages

- [Runtime](Runtime.md)
- [Validation](Validation.md)
