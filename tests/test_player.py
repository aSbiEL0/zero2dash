from __future__ import annotations

import itertools
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import player


class PlayerLogicTests(unittest.TestCase):
    def test_supported_videos_are_filtered_and_sorted_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for name in ["z-last.mov", "A-first.MP4", "ignore.txt", "middle.mkv", "clip.AVI"]:
                (root / name).write_text("x", encoding="utf-8")

            files = player.list_supported_videos(root)

        self.assertEqual(
            [path.name for path in files],
            ["A-first.MP4", "clip.AVI", "middle.mkv", "z-last.mov"],
        )

    def test_missing_directory_is_treated_as_empty(self) -> None:
        files = player.list_supported_videos(Path("Z:/definitely/missing/path"))
        self.assertEqual(files, [])

    def test_playlist_scroll_does_not_wrap(self) -> None:
        files = [Path(f"file-{index}.mp4") for index in range(5)]
        state = player.PlaylistState(files)

        self.assertTrue(state.scroll(1))
        self.assertEqual(state.top_index, 1)
        self.assertTrue(state.scroll(1))
        self.assertEqual(state.top_index, 2)
        self.assertFalse(state.scroll(1))
        self.assertEqual(state.top_index, 2)
        self.assertTrue(state.scroll(-1))
        self.assertEqual(state.top_index, 1)
        self.assertTrue(state.scroll(-1))
        self.assertEqual(state.top_index, 0)
        self.assertFalse(state.scroll(-1))
        self.assertEqual(state.top_index, 0)

    def test_visible_rows_and_selection_follow_window(self) -> None:
        files = [Path(f"file-{index}.mp4") for index in range(4)]
        state = player.PlaylistState(files)
        state.scroll(1)

        self.assertEqual([path.name for _index, path in state.visible_rows()], ["file-1.mp4", "file-2.mp4", "file-3.mp4"])
        self.assertTrue(state.select_visible_row(2))
        self.assertEqual(state.selected_index, 3)
        self.assertFalse(state.select_visible_row(3))

    def test_playback_starts_from_selection_and_wraps(self) -> None:
        files = [Path(f"file-{index}.mp4") for index in range(3)]
        state = player.PlaylistState(files, selected_index=2)

        self.assertEqual(state.start_from_selection(), 2)
        self.assertEqual(state.current_file(), files[2])
        self.assertEqual(state.advance(1), 0)
        self.assertEqual(state.current_file(), files[0])
        self.assertEqual(state.advance(-1), 2)
        self.assertEqual(state.current_file(), files[2])


class TouchHandoffTests(unittest.TestCase):
    def test_wait_for_touch_idle_consumes_inherited_press_before_returning(self) -> None:
        samples = [object(), object(), None, None, None, None, None, None]
        active_states = [True, True, False, False, False, False, False, False]

        class FakeTouchInput:
            def poll(self, _timeout_secs: float):
                return samples.pop(0) if samples else None

            def is_touch_active(self) -> bool:
                return active_states.pop(0) if active_states else False

        monotonic_values = itertools.chain(
            [0.00, 0.00, 0.05, 0.10, 0.15, 0.21, 0.26, 0.31, 0.36, 0.41, 0.46, 0.51],
            itertools.count(0.56, 0.05),
        )
        with mock.patch.object(player.time, "monotonic", side_effect=lambda: next(monotonic_values)):
            player.wait_for_touch_idle(FakeTouchInput(), idle_secs=0.20, max_wait_secs=1.50)


if __name__ == "__main__":
    unittest.main()
