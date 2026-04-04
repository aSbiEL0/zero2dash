# zero2dash Wiki

`PLAN.md` is the active source of truth only when a task is open.

## Current Runtime

- `boot/boot_selector.py` is the parent shell
- `display_rotator.py` is the Dashboards child entrypoint
- `modules/photos/slideshow.py` is the Photos child entrypoint
- `player.py` is the credits/vault framebuffer player child
- Shell modes are `menu`, `dashboards`, `photos`, and `night`
- The shell baseline is working on the Pi
- Active task state belongs in `PLAN.md`

## Theme Contract

- Shell assets currently come from `themes/carbon`, `themes/comic`, `themes/frosty`, and `themes/steele`
- Theme selection persists only
- The Themes selector mapping has been verified on hardware
- The right-side stripe/back behavior has been verified on hardware
- Root-page return state is session-only
- `keypad.png` is a 4x3 grid with `tick` in the top-right and `red X` in the bottom-right

## Validation

- `python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif`
- `python3 player.py --self-test`
- `python3 -m unittest discover -s tests -v`
- `python3 modules/trams/display.py --self-test`

Shell acceptance for the finished slice is based on device confirmation for Themes mapping, right-side stripe behavior, and Settings layout.

## Related Pages

- [Runtime](Runtime.md)
- [Validation](Validation.md)
