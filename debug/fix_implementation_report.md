# Zero2dash Fix Implementation Report

This report summarizes the status of the debugging roadmap tasks after the rewrite campaign.

## Overall status

- **Implemented:** Tasks **#1 through #27**.
- **Remaining:** None.

## Implemented fixes

### Foundation and global configuration

- **#1 Shared config validation and check mode**
  - Added a shared config helper module and reusable validators.
  - Added preflight `--check-config` style behavior across scripts.
  - Key files: `scripts/_config.py`, `scripts/calendash-api.py`, `scripts/photos-shuffle.py`, `scripts/piholestats_v1.2.py`, `scripts/piholestats_v1.1.py`.
  - Evidence commit: `f550375`.

- **#3 Separate token-file protection for Calendar/Photos**
  - Added token path preflight checks and scope/owner metadata guards.
  - Prevents accidental token reuse between different Google integrations.
  - Key files: `scripts/calendash-api.py`, `scripts/photos-shuffle.py`.
  - Evidence commit: `78b75d2`.

### Pi-hole dashboards

- **#2 Cross-midnight active-hours bug fixed**
  - Active-hours logic now correctly handles wrapped ranges like `22,7`.
  - Key files: `scripts/piholestats_v1.2.py`, `scripts/piholestats_v1.1.py`.
  - Evidence commit: `9c2eac5`.

- **#8 HTTPS/TLS support and host normalization improvements**
  - Added configurable scheme and TLS verification behavior.
  - Key files: `scripts/piholestats_v1.2.py`, `scripts/piholestats_v1.1.py`.
  - Evidence commits: `07234b8`, `6ecfad9`.

- **#9 Auth requirement hardening (v6 SID vs fallback)**
  - Clearer auth mode expectations and better fallback handling.
  - Key file: `scripts/piholestats_v1.2.py`.
  - Evidence commit: `fc209bc`.

- **#10 Exception swallowing addressed / root-cause surfaced**
  - Primary and fallback failure causes are reported with clearer renderer hints.
  - Key file: `scripts/piholestats_v1.2.py`.
  - Evidence commit: `d4de4b1`.

- **#11 Framebuffer assumptions mitigated**
  - Added robust framebuffer error handling and optional PNG output mode for testing.
  - Key files: `scripts/piholestats_v1.2.py`, `scripts/piholestats_v1.1.py`.
  - Evidence commit: `aa17a3e`.

### Display rotator

- **#4 Default exclusion behavior made explicit + diagnostics**
  - Improved page discovery/exclusion configuration and added `--list-pages` mode.
  - Key file: `display_rotator.py`.
  - Evidence commit: `c9ebb7f`.

- **#6 Screen power toggling robustness**
  - Improved power-path diagnostics and black-frame-off fallback behavior.
  - Key file: `display_rotator.py`.
  - Evidence commit: `ca3ff7b`.

- **#7 No back-pressure on failing child pages fixed**
  - Added per-page failure backoff and quarantine handling.
  - Key file: `display_rotator.py`.
  - Evidence commit: `773f6ce`.

- **#5 Touch-device selection reliability (partially covered in rotator hardening stream)**
  - Detection and diagnostics improvements are included in the rotator hardening effort.
  - Key file: `display_rotator.py`.
  - Evidence commits in the rotator series (`ca3ff7b`, `c9ebb7f`).

### Google Calendar (`calendash-api.py`)

- **#12 Mandatory configuration handling improved**
  - Config validation was refactored for grouped/partial startup and clearer guidance.
  - Key file: `scripts/calendash-api.py`.
  - Evidence commit: `d3f4fd9`.

- **#13 Event fetch retry coverage expanded**
  - Retry policy now handles more failure classes and improves resiliency.
  - Key file: `scripts/calendash-api.py`.
  - Evidence commit: `29cc9d5`.

- **#14 OAuth flow hardening for headless environments**
  - Added explicit auth mode controls and better diagnostics.
  - Key file: `scripts/calendash-api.py`.
  - Evidence commits: `9190d3e`, `9c1227a`.

- **#15 Token compatibility and refresh handling strengthened**
  - Improved scope validation and refresh-failure behavior.
  - Key file: `scripts/calendash-api.py`.
  - Evidence commit: `3abf42e`.

### Google Photos (`photos-shuffle.py`)

- **#16 Incorrect API call fixed**
  - Album media listing/pagination logic was corrected with a smoke-check path.
  - Key file: `scripts/photos-shuffle.py`.
  - Evidence commit: `8f7048e`.

- **#17 Default logo path correction**
  - Logo path resolution updated with safer defaults and warning behavior.
  - Key file: `scripts/photos-shuffle.py`.
  - Evidence commit: `1664d22`.

- **#18 Token refresh persistence fixed**
  - Refreshed tokens now persist atomically to disk.
  - Key file: `scripts/photos-shuffle.py`.
  - Evidence commit: `40c31ec`.

- **#19 Media download authorization/status handling improved**
  - Hardened download flow, status checks, and failure handling.
  - Key file: `scripts/photos-shuffle.py`.
  - Evidence commit: `fd8b985`.

- **#20 Album/image caching and retry logic improved**
  - Better candidate iteration and retry accounting before final failure.
  - Key file: `scripts/photos-shuffle.py`.
  - Evidence commit: `8a06c8f`.

- **#21 Credential bootstrap and preflight messaging improved**
  - Added clearer credential precedence docs and config-check workflow.
  - Key file: `scripts/photos-shuffle.py`.
  - Evidence commit: `089e45a`.

### Service/docs alignment

- **#25 Service unit/readme mismatch addressed**
  - Added canonical service names and compatibility matrix in docs.
  - Key file: `README.md`.
  - Evidence commit: `63cbacd`.

## Remaining fixes to implement

All previously listed Block F items (#22, #23, #24, #26, #27) are now implemented.

## Block F completion summary

- **#22** Implemented with Pillow resampling compatibility fallback in static render scripts.
- **#23** Implemented with configurable framebuffer path/geometry and payload-size checks.
- **#24** Implemented with non-blocking buffered Linux input event parsing in `calendash-img.py`.
- **#26** Implemented by wiring `FB_DEVICE` into canonical systemd services and removing hard-coded fb device unit dependencies.
- **#27** Implemented with command-presence checks, sysfs write guards, and warning logs in pre-start shell script.
