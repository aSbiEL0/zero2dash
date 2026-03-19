from __future__ import annotations

import importlib.util
import os
import queue
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


blackout = _load_module("blackout_test", "modules/blackout/blackout.py")


class _FakeInputFile:
    def __init__(self, events: list[tuple[int, int, int]]) -> None:
        payload = bytearray()
        for ev_type, ev_code, ev_value in events:
            payload.extend(blackout.INPUT_EVENT_STRUCT.pack(0, 0, ev_type, ev_code, ev_value))
        self._payload = bytes(payload)
        self._offset = 0

    def read(self, size: int) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += size
        return chunk

    def __enter__(self) -> "_FakeInputFile":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class BlackoutTests(unittest.TestCase):
    def test_touch_worker_accepts_abs_syn_fallback_without_btn_touch(self) -> None:
        fake_input = _FakeInputFile(
            [
                (blackout.EV_ABS, blackout.ABS_X, 12),
                (blackout.EV_SYN, 0, 0),
            ]
        )
        events: queue.Queue[str] = queue.Queue()
        stop_evt = threading.Event()

        with patch.object(blackout, "select_touch_device", return_value="/dev/input/event0"), \
            patch.object(blackout.select, "select", side_effect=lambda *_args, **_kwargs: ([fake_input], [], []) if fake_input._offset < len(fake_input._payload) else ([], [], [])), \
            patch("builtins.open", return_value=fake_input), \
            patch.object(blackout.time, "monotonic", side_effect=[0.0, 0.5, 0.5]):
            thread = threading.Thread(target=blackout.touch_worker, args=(events, stop_evt), daemon=True)
            thread.start()
            self.assertEqual(events.get(timeout=1.0), "tap")
            stop_evt.set()
            thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())

    def test_activate_boot_selector_requests_parent_menu_when_shell_managed(self) -> None:
        result = types.SimpleNamespace(returncode=0, stderr="", stdout="")

        with patch.dict(os.environ, {"ZERO2DASH_PARENT_SHELL": "1"}, clear=False), \
            patch.object(blackout, "PARENT_SHELL_MODE_REQUEST_PATH", "/tmp/zero2dash-shell-mode-request"), \
            patch.object(blackout.subprocess, "run", return_value=result) as run_mock:
            rc = blackout.activate_boot_selector()

        self.assertEqual(rc, 0)
        self.assertEqual(
            run_mock.call_args.args[0],
            [
                sys.executable,
                "-u",
                str(blackout.BOOT_SELECTOR_SCRIPT),
                "--request-mode",
                "menu",
                "--mode-request-path",
                "/tmp/zero2dash-shell-mode-request",
            ],
        )


if __name__ == "__main__":
    unittest.main()
