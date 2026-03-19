"""Shared defaults for the dashboard rotator."""

from __future__ import annotations


DEFAULT_MODULES_DIR = "modules"
DEFAULT_MODULE_ORDER_FILE = "modules.txt"
DEFAULT_MODULE_ENTRYPOINT = "display.py"
DEFAULT_MODULE_METADATA_FILE = "rotator.json"
DEFAULT_ROTATE_SECS = 13
MIN_DWELL_SECS = 5
DEFAULT_WIDTH = 320
TAP_DEBOUNCE_SECS = 0.20
DEFAULT_BACKOFF_STEPS = (10, 30, 60)
DEFAULT_BACKOFF_MAX_SECS = 300
DEFAULT_QUARANTINE_FAILURE_THRESHOLD = 3
DEFAULT_QUARANTINE_CYCLES = 3
DASHBOARD_EXCLUDED_MODULES = frozenset({"photos"})

DISCOVERY_CONFIG_DOCS = [
    {
        "env": "ROTATOR_MODULES_DIR",
        "default": DEFAULT_MODULES_DIR,
        "description": "Directory containing rotator module folders.",
    },
    {
        "env": "ROTATOR_MODULE_ORDER_FILE",
        "default": DEFAULT_MODULE_ORDER_FILE,
        "description": "Optional module-order manifest. When absent, modules are discovered alphabetically.",
    },
    {
        "env": "ROTATOR_MODULE_ENTRYPOINT",
        "default": DEFAULT_MODULE_ENTRYPOINT,
        "description": "Entrypoint filename expected inside each module directory.",
    },
]
