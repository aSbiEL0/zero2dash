"""Module discovery helpers for the dashboard rotator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from rotator.defaults import (
    DASHBOARD_EXCLUDED_MODULES,
    DEFAULT_MODULE_ENTRYPOINT,
    DEFAULT_MODULE_METADATA_FILE,
    DEFAULT_MODULE_ORDER_FILE,
    DEFAULT_MODULES_DIR,
    DISCOVERY_CONFIG_DOCS,
    MIN_DWELL_SECS,
)


def _read_module_manifest(order_file: Path) -> list[tuple[int, str]]:
    modules: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(order_file.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        modules.append((line_number, line))
    return modules


def _module_entrypoint(module_dir: Path, entrypoint_name: str) -> Path:
    return module_dir / entrypoint_name


def _discover_module_entrypoints(modules_dir: Path, entrypoint_name: str) -> list[Path]:
    discovered: list[Path] = []
    for child in sorted(modules_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.lower() in DASHBOARD_EXCLUDED_MODULES:
            continue
        entrypoint = _module_entrypoint(child, entrypoint_name)
        if entrypoint.is_file():
            discovered.append(entrypoint)
    return discovered


def _load_module_metadata(module_dir: Path) -> dict[str, object] | None:
    metadata_path = module_dir / DEFAULT_MODULE_METADATA_FILE
    if not metadata_path.is_file():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[rotator] Ignoring invalid metadata file {metadata_path}: {exc}", flush=True)
        return None
    if not isinstance(payload, dict):
        print(f"[rotator] Ignoring invalid metadata file {metadata_path}: expected a JSON object", flush=True)
        return None
    return payload


def resolve_page_dwell_secs(
    script_path: str,
    base_dir: Path,
    default_dwell_secs: int,
    *,
    resolve_path: Callable[[str, Path], Path],
) -> int:
    modules_dir_raw = os.environ.get("ROTATOR_MODULES_DIR", DEFAULT_MODULES_DIR).strip() or DEFAULT_MODULES_DIR
    modules_dir = resolve_path(modules_dir_raw, base_dir)
    script = Path(script_path)
    try:
        relative_parts = script.relative_to(modules_dir).parts
    except ValueError:
        return default_dwell_secs
    if len(relative_parts) < 2:
        return default_dwell_secs
    module_dir = modules_dir / relative_parts[0]
    metadata = _load_module_metadata(module_dir)
    if metadata is None or "dwell_secs" not in metadata:
        return default_dwell_secs
    raw_dwell_secs = metadata.get("dwell_secs")
    try:
        dwell_secs = int(raw_dwell_secs)
    except (TypeError, ValueError):
        dwell_secs = -1
    if dwell_secs < MIN_DWELL_SECS:
        print(
            (
                f"[rotator] Invalid dwell_secs for {script_path} in "
                f"{module_dir / DEFAULT_MODULE_METADATA_FILE}: {raw_dwell_secs!r}; "
                f"using ROTATOR_SECS={default_dwell_secs}"
            ),
            flush=True,
        )
        return default_dwell_secs
    print(
        (
            f"[rotator] dwell_secs override for {script_path}: {dwell_secs} "
            f"via {module_dir / DEFAULT_MODULE_METADATA_FILE}"
        ),
        flush=True,
    )
    return dwell_secs


def resolve_page_specs(
    page_entries: list[str],
    base_dir: Path,
    default_dwell_secs: int,
    *,
    resolve_script: Callable[[str, Path], str | None],
    resolve_path: Callable[[str, Path], Path],
) -> list[tuple[str, int]]:
    page_specs: list[tuple[str, int]] = []
    for item in page_entries:
        resolved = resolve_script(item, base_dir)
        if resolved is None:
            continue
        page_specs.append((resolved, resolve_page_dwell_secs(resolved, base_dir, default_dwell_secs, resolve_path=resolve_path)))
    return page_specs


def discover_pages(
    base_dir: Path,
    *,
    list_pages: bool = False,
    resolve_path: Callable[[str, Path], Path],
) -> list[str]:
    modules_dir_raw = os.environ.get("ROTATOR_MODULES_DIR", DEFAULT_MODULES_DIR).strip() or DEFAULT_MODULES_DIR
    module_order_file_raw = os.environ.get("ROTATOR_MODULE_ORDER_FILE", DEFAULT_MODULE_ORDER_FILE).strip() or DEFAULT_MODULE_ORDER_FILE
    module_entrypoint = os.environ.get("ROTATOR_MODULE_ENTRYPOINT", DEFAULT_MODULE_ENTRYPOINT).strip() or DEFAULT_MODULE_ENTRYPOINT
    modules_dir = resolve_path(modules_dir_raw, base_dir)
    if not modules_dir.exists():
        print(f"[rotator] Modules directory does not exist: {modules_dir}", flush=True)
        return []

    included: list[str] = []
    discovery_report: list[tuple[str, str]] = []
    seen_modules: set[str] = set()
    order_file = resolve_path(module_order_file_raw, base_dir)
    discovery_source = "fallback scan"

    if order_file.exists():
        try:
            order_file_display = order_file.relative_to(base_dir).as_posix()
        except ValueError:
            order_file_display = str(order_file)
        discovery_source = f"manifest {order_file_display}"
        for line_number, module_name in _read_module_manifest(order_file):
            if "/" in module_name or "\\" in module_name:
                discovery_report.append((module_name, f"skipped (invalid module name at line {line_number})"))
                continue
            if module_name.lower() in DASHBOARD_EXCLUDED_MODULES:
                discovery_report.append((module_name, f"skipped (excluded dashboard module at line {line_number})"))
                continue
            if module_name in seen_modules:
                discovery_report.append((module_name, f"skipped (duplicate module at line {line_number})"))
                continue
            seen_modules.add(module_name)
            module_dir = modules_dir / module_name
            entrypoint = _module_entrypoint(module_dir, module_entrypoint)
            if not module_dir.is_dir():
                discovery_report.append((module_name, f"skipped (missing module directory at line {line_number})"))
                continue
            if not entrypoint.is_file():
                discovery_report.append((module_name, f"skipped (missing {module_entrypoint} at line {line_number})"))
                continue
            relative = entrypoint.relative_to(base_dir).as_posix()
            included.append(relative)
            discovery_report.append((relative, f"included (manifest line {line_number})"))
    else:
        for entrypoint in _discover_module_entrypoints(modules_dir, module_entrypoint):
            relative = entrypoint.relative_to(base_dir).as_posix()
            included.append(relative)
            discovery_report.append((relative, "included (fallback alphabetical scan)"))

    print("[rotator] Discovery config:", flush=True)
    for item in DISCOVERY_CONFIG_DOCS:
        value = os.environ.get(item["env"], str(item["default"])).strip() or str(item["default"])
        print(f"[rotator]   {item['env']}={value} ({item['description']})", flush=True)
    print(f"[rotator]   source={discovery_source}", flush=True)
    print("[rotator] Discovery result:", flush=True)
    for script, status in discovery_report:
        print(f"[rotator]   {script}: {status}", flush=True)
    if list_pages:
        print("[rotator] --list-pages summary:", flush=True)
        for script, status in discovery_report:
            print(f"{script}\t{status}", flush=True)
    return included
