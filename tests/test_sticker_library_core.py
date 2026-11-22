"""Safety and persistence tests for the desktop sticker library."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sticker_library_core as stickers  # noqa: E402


PNG_BYTES = (
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360f8cfc0f01f0005000201a3f0a5e7"
        "0000000049454e44ae426082"
    )
    + (b"\0" * 1500)
)


class StickerLibraryCoreTest(unittest.TestCase):
    def test_import_tag_list_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.bin"
            source.write_bytes(PNG_BYTES)
            library = temp / "library"
            meta_path = library / "meta.json"
            with (
                patch.object(stickers, "STICKER_DIR", library),
                patch.object(stickers, "META_PATH", meta_path),
            ):
                target = stickers.import_sticker(str(source))
                stickers.save_sticker_metadata(
                    target.name,
                    keywords="喵，可爱",
                    emotion="开心",
                    intent="卖萌",
                    tone="软萌",
                    note="想撒娇时使用",
                )
                items = stickers.list_stickers()
                self.assertEqual(len(items), 1)
                self.assertTrue(items[0]["tagged"])
                stickers.remove_sticker(target.name)
                self.assertEqual(stickers.list_stickers(), [])

    def test_non_image_library_file_cannot_be_deleted_or_tagged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            library = Path(temp_dir)
            meta_path = library / "meta.json"
            meta_path.write_text(
                json.dumps({"protected": True}),
                encoding="utf-8",
            )
            with (
                patch.object(stickers, "STICKER_DIR", library),
                patch.object(stickers, "META_PATH", meta_path),
            ):
                with self.assertRaises(ValueError):
                    stickers.remove_sticker("meta.json")
                with self.assertRaises(ValueError):
                    stickers.save_sticker_metadata(
                        "meta.json",
                        keywords="截图",
                        emotion="",
                        intent="",
                        tone="",
                        note="",
                    )
            self.assertTrue(meta_path.is_file())
            self.assertEqual(
                json.loads(meta_path.read_text(encoding="utf-8")),
                {"protected": True},
            )


if __name__ == "__main__":
    unittest.main()
