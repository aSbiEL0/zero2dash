# PLAN

Status: completed
Updated: 2026-04-05

Task: replace the split credits / vault video playback flow with a single Python framebuffer player that integrates into the shell and keeps `~/x` reachable only through the vault path.

Acceptance criteria:
- Credits launch the new player against `~/vid`
- Vault success launches the same player against `~/x`
- Normal launches use the active theme `player.png`
- Vault mode overrides only the background image with `themes/global_images/vault.png`
- File list, scroll strip, play button, back strip, and playback gestures match the approved contract
- Playback stays foreground and returns cleanly to the shell on exit

File boundaries:
- shell integration: `boot/boot_selector.py`
- player implementation: `player.py`
- focused regression coverage: `tests/`
- stale docs only: `README.md`, `docs/wiki/Runtime.md`, `docs/wiki/Validation.md`, `docs/wiki/Home.md`

Key risks:
- child app must own touch exit correctly or the shell cannot reclaim the session
- framebuffer playback remains device-sensitive and needs Pi validation
- vault background failure must be explicit and safe

Validation plan:
- `python3 boot/boot_selector.py --dump-contracts --no-framebuffer --skip-gif`
- `python3 player.py --self-test`
- `python3 -m unittest discover -s tests -v`
- Pi manual checks for credits, vault, scrolling, playback gestures, and exit behavior

Completion note:
- This slice has been completed and accepted by the operator.
- Recorded closeout: `coordination/archive/2026-04-05-player-unification-closeout.md`
