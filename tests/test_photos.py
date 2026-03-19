from __future__ import annotations

import importlib.util
import queue
import threading
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


photos_display = _load_module("photos_display", "modules/photos/display.py")
photos_slideshow = _load_module("photos_slideshow", "modules/photos/slideshow.py")


class _FakeInputFile:
    def __init__(self, events: list[tuple[int, int, int]]) -> None:
        payload = bytearray()
        for ev_type, ev_code, ev_value in events:
            payload.extend(photos_slideshow.INPUT_EVENT_STRUCT.pack(0, 0, ev_type, ev_code, ev_value))
        self._payload = bytes(payload)
        self._offset = 0

    def read(self, size: int) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += size
        return chunk


class PhotosTests(unittest.TestCase):
    def _make_config(self, root: Path) -> photos_display.Config:
        fallback = root / "fallback.png"
        Image.new("RGB", (320, 240), color=(1, 2, 3)).save(fallback)
        return photos_display.Config(
            local_photos_dir=root / "local",
            album_id="",
            drive_folder_id="",
            drive_sync_state_path=root / "drive-sync-state.json",
            client_secrets_path=root / "client_secret.json",
            client_id="",
            client_secret="",
            token_path=root / "token_photos.json",
            fb_device="/dev/null",
            width=320,
            height=240,
            cache_dir=root / "cache",
            fallback_image=fallback,
            logo_path=root / ".no-logo",
            oauth_port=8080,
            oauth_open_browser=False,
        )

    def test_select_source_image_falls_back_to_offline_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cached = root / "cache" / "offline.png"
            cached.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (20, 20), color=(9, 9, 9)).save(cached)
            config = self._make_config(root)
            log = photos_display.Log()

            calls: list[str] = []
            original_local = photos_display.choose_local_image
            original_online = photos_display.choose_online_image
            original_offline = photos_display.choose_offline_image
            try:
                def _local(_config, _log):
                    calls.append("local")
                    raise RuntimeError("no local images")

                def _online(_config, _log):
                    calls.append("online")
                    raise RuntimeError("no online images")

                def _offline(_config, _log):
                    calls.append("offline")
                    return cached

                photos_display.choose_local_image = _local
                photos_display.choose_online_image = _online
                photos_display.choose_offline_image = _offline

                selected = photos_display.select_source_image(config, log)
            finally:
                photos_display.choose_local_image = original_local
                photos_display.choose_online_image = original_online
                photos_display.choose_offline_image = original_offline

            self.assertEqual(selected, cached)
            self.assertEqual(calls, ["local", "online", "offline"])

    def test_select_source_image_uses_static_fallback_when_all_sources_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._make_config(root)
            log = photos_display.Log()

            original_local = photos_display.choose_local_image
            original_online = photos_display.choose_online_image
            original_offline = photos_display.choose_offline_image
            try:
                def _boom(_config, _log):
                    raise RuntimeError("boom")

                photos_display.choose_local_image = _boom
                photos_display.choose_online_image = _boom
                photos_display.choose_offline_image = _boom

                selected = photos_display.select_source_image(config, log)
            finally:
                photos_display.choose_local_image = original_local
                photos_display.choose_online_image = original_online
                photos_display.choose_offline_image = original_offline

            self.assertEqual(selected, config.fallback_image)

    def test_run_slideshow_stops_cleanly_during_wait(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_dir = root / "local"
            local_dir.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (640, 480), color=(20, 40, 60)).save(local_dir / "sample.png")
            config = self._make_config(root)
            output = root / "latest.png"
            log = photos_display.Log()

            stop_state = {"value": False}

            def _stop_requested() -> bool:
                return stop_state["value"]

            def _sleep(_seconds: float) -> None:
                stop_state["value"] = True

            rc = photos_slideshow.run_slideshow(
                config,
                log,
                advance_secs=30.0,
                no_framebuffer=True,
                output_path=output,
                stop_requested=_stop_requested,
                sleep_fn=_sleep,
            )

            self.assertEqual(rc, 0)
            self.assertTrue(output.exists())

    def test_request_parent_menu_writes_menu_request_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            request_path = Path(temp_dir) / "mode-request"

            self.assertTrue(photos_slideshow.request_parent_menu(str(request_path)))
            self.assertEqual(request_path.read_text(encoding="utf-8").strip(), "menu")

    def test_touch_worker_emits_previous_next_and_menu_commands(self) -> None:
        events = queue.Queue()
        stop_evt = threading.Event()
        fake_input = _FakeInputFile(
            [
                (photos_slideshow.EV_ABS, photos_slideshow.ABS_X, 10),
                (photos_slideshow.EV_ABS, photos_slideshow.ABS_Y, 20),
                (photos_slideshow.EV_KEY, photos_slideshow.BTN_TOUCH, 1),
                (photos_slideshow.EV_KEY, photos_slideshow.BTN_TOUCH, 0),
                (photos_slideshow.EV_ABS, photos_slideshow.ABS_X, 300),
                (photos_slideshow.EV_ABS, photos_slideshow.ABS_Y, 20),
                (photos_slideshow.EV_KEY, photos_slideshow.BTN_TOUCH, 1),
                (photos_slideshow.EV_KEY, photos_slideshow.BTN_TOUCH, 0),
                (photos_slideshow.EV_ABS, photos_slideshow.ABS_X, 10),
                (photos_slideshow.EV_ABS, photos_slideshow.ABS_Y, 20),
                (photos_slideshow.EV_KEY, photos_slideshow.BTN_TOUCH, 1),
                (photos_slideshow.EV_KEY, photos_slideshow.BTN_TOUCH, 0),
            ]
        )
        times = iter([0.0, 0.0, 0.0, 0.1, 1.0, 1.0, 1.0, 1.1, 2.0, 2.0, 2.0, 4.0])

        def _now() -> float:
            return next(times, 8.0)

        def _select(*_args, **_kwargs):
            return ([fake_input], [], []) if fake_input._offset < len(fake_input._payload) else ([], [], [])

        def _map(raw_x: int, raw_y: int, *, width: int, height: int):
            return (0, 0) if raw_x < 100 else (width - 1, 0)

        with mock.patch.object(photos_slideshow, "select_touch_device", return_value="/dev/input/event0"), \
            mock.patch.object(photos_slideshow.select, "select", side_effect=_select), \
            mock.patch("builtins.open", return_value=fake_input), \
            mock.patch.object(photos_slideshow.time, "monotonic", side_effect=_now), \
            mock.patch.object(photos_slideshow.touch_calibration, "map_to_screen", side_effect=_map):
            thread = threading.Thread(
                target=photos_slideshow.touch_worker,
                args=(events, stop_evt, 320, 240),
                kwargs={"hold_to_menu_secs": 1.5, "poll_timeout_secs": 0.01},
                daemon=True,
            )
            thread.start()
            self.assertEqual(events.get(timeout=1.0), "previous")
            self.assertEqual(events.get(timeout=1.0), "next")
            self.assertEqual(events.get(timeout=1.0), "menu")
            stop_evt.set()
            thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())

    def test_run_slideshow_rewinds_and_advances_with_touch_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._make_config(root)
            frame_a = root / "a.png"
            frame_b = root / "b.png"
            Image.new("RGB", (320, 240), color=(10, 20, 30)).save(frame_a)
            Image.new("RGB", (320, 240), color=(30, 20, 10)).save(frame_b)
            output = root / "latest.png"
            touch_events = queue.Queue()
            touch_events.put("next")
            touch_events.put("previous")
            rendered: list[Path] = []
            image_iter = iter([frame_a, frame_b])

            def _select(_config, _log):
                return next(image_iter)

            def _render(source_image, _config, _log):
                rendered.append(source_image)
                return Image.new("RGB", (320, 240), color=(1, 1, 1))

            with mock.patch.object(photos_display, "select_source_image", side_effect=_select), \
                mock.patch.object(photos_display, "render_frame_with_fallback", side_effect=_render):
                rc = photos_slideshow.run_slideshow(
                    config,
                    photos_display.Log(),
                    advance_secs=0.01,
                    no_framebuffer=True,
                    output_path=output,
                    max_frames=3,
                    touch_event_q=touch_events,
                    sleep_fn=lambda _seconds: None,
                )

            self.assertEqual(rc, 0)
            self.assertEqual(rendered, [frame_a, frame_b, frame_a])
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
