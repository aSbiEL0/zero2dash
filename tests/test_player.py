from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
