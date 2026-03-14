from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
