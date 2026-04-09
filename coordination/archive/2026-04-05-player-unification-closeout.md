# Player Unification Closeout Archive

Archived: 2026-04-05
Scope: unified Credits / Vault player delivery closeout

Summary:
- The split Credits and Vault playback paths were replaced with a single Python framebuffer player integrated into the shell.
- The shell now launches the same player runtime for both workflows while preserving Vault-only access to `~/x`.
- The delivered player contract, UI tuning, and operational cleanup were accepted by the operator.

Delivered outcomes:
- Credits launch the unified player against `~/vid`
- Vault success launches the same player against `~/x`
- active theme `player.png` remains the normal player background
- Vault mode uses `themes/global_images/vault.png` as the background override
- list rendering, selection highlight, touch alignment, and playback controls were tuned to the approved layout
- deprecated overlay handling was removed from runtime, asset requirements, and theme files
- stale `player.sh` configuration no longer remains the intended path for Credits / Vault playback

Operational notes:
- `~/x` remains confidential operator data and should not be inspected or logged
- local workspace changes still need to be synced manually to `/home/pihole/zero2dash` on the Pi when applicable
- Python code changes require `systemctl restart boot-selector.service` on the Pi, not `daemon-reload`, unless the unit file changes

Known residuals at closeout:
- repo cleanup candidates were identified separately but not deleted
- framebuffer playback remains hardware-sensitive by nature, even though the accepted flow is complete

Archived so the active control plane can move on to the next task.
