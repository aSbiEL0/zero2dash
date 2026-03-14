zero2dash module authoring rules (modules/)
Module contract
Each module lives in modules/<module_name>/ and must provide an entrypoint file named display.py by default. The rotation order is defined in /modules.txt at the repository root. Changing the entrypoint naming requires updating:
    • The ROTATOR_MODULE_ENTRYPOINT environment variable and documenting the change.
    • README.md and .env.example if new environment variables are introduced.
Expectations for new or modified modules
    • Provide a stable CLI using argparse with a helpful --help description.
    • Implement safe validation flags:
    • --check-config for environment validation.
    • --self-test for deterministic unit‑like checks.
    • --no-framebuffer and/or --output for non‑hardware testing.
    • Avoid tight loops and heavy CPU usage; this runs on a Pi Zero‑class device.
    • Keep framebuffer write code consistent. If refactoring shared framebuffer helpers, treat it as a separate, explicitly approved change (large ripple risk).
Configuration conventions
    • Use .env and python‑dotenv where the module already follows that pattern.
    • Validate required environment variables and produce clear error messages.
    • Never log secrets (Pi‑hole credentials, OAuth client secrets, tokens).
Done criteria for module pull requests
    • Updated modules.txt (when adding/removing/reordering a module).
    • Updated .env.example and README.md for any new environment variables or behaviour changes.
    • Added or updated at least one safe validation command example (e.g., --check-config or --self-test).
Ask first
Always ask for approval before:
    • Introducing new dependencies.
    • Changing behaviour that affects page order, timers or systemd units.
    • Refactoring shared framebuffer conversion logic or other cross‑module utilities.
