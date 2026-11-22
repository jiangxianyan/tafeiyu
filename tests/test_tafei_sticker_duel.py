"""Contract tests for bounded sticker-duel replies."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from astrbot.api.message_components import Image, Plain

    ASTRBOT_AVAILABLE = True
except ImportError:
    Image = None
    Plain = None
    ASTRBOT_AVAILABLE = False


PLUGIN_PATH = (
    Path(__file__).resolve().parents[1]
    / "astrbot"
    / "data"
    / "plugins"
    / "tafei_sticker"
    / "main.py"
)
if ASTRBOT_AVAILABLE:
    SPEC = importlib.util.spec_from_file_location(
        "tafei_sticker_duel_test",
        PLUGIN_PATH,
    )
    STICKER = importlib.util.module_from_spec(SPEC)
    assert SPEC.loader is not None
    SPEC.loader.exec_module(STICKER)
else:
    STICKER = None

PNG_BYTES = (
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360f8cfc0f01f0005000201a3f0a5e7"
        "0000000049454e44ae426082"
    )
    + (b"\0" * 1500)
)


class FakeEvent:
    unified_msg_origin = "aiocqhttp:GroupMessage:100"
    message_str = "震惊"

    def __init__(self, image_path: str) -> None:
        image = Image.fromFileSystem(image_path)
        self.message_obj = types.SimpleNamespace(
            message=[image],
            raw_message=types.SimpleNamespace(
                message=[
                    {
                        "type": "image",
                        "data": {"sub_type": 1, "summary": "[动画表情]"},
                    }
                ]
            ),
        )
        self.result = types.SimpleNamespace(
            chain=[Plain("你这也太震惊了吧")]
        )
        self.extra = {}

    def get_sender_id(self):
        return "123456"

    def get_result(self):
        return self.result

    def set_extra(self, key, value):
        self.extra[key] = value


class FakeProvider:
    def __init__(self, meta_path: Path, payload: dict) -> None:
        self.meta_path = meta_path
        self.payload = payload

    async def text_chat(self, **_kwargs):
        self.meta_path.write_text(
            json.dumps(self.payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return types.SimpleNamespace(
            completion_text=json.dumps(
                {
                    "keywords": ["新表情"],
                    "emotion": ["开心"],
                    "intent": ["卖萌"],
                    "tone": ["可爱"],
                    "note": "轻松聊天时使用",
                },
                ensure_ascii=False,
            )
        )


class FakeContext:
    def __init__(self, provider) -> None:
        self.provider = provider

    def get_provider_by_id(self, _provider_id: str):
        return self.provider


@unittest.skipUnless(ASTRBOT_AVAILABLE, "AstrBot runtime is not installed")
class StickerDuelTest(unittest.TestCase):
    def test_auto_tag_response_is_normalized(self) -> None:
        info = STICKER.TafeiSticker._parse_tag_response(
            """
            {
              "keywords": ["震惊", "真的假的", "x"],
              "emotion": ["震惊", "无语"],
              "intent": ["吐槽"],
              "tone": ["可爱"],
              "note": "群友说了离谱内容时使用"
            }
            """
        )
        self.assertEqual(info["kw"], ["震惊", "真的假的"])
        self.assertEqual(info["emotion"], ["震惊", "无语"])
        self.assertTrue(info["auto_tagged"])
        self.assertIn("离谱内容", info["note"])

    def test_detects_emotion_sticker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shock.png"
            path.write_bytes(PNG_BYTES)
            self.assertTrue(STICKER._is_emoji_message(FakeEvent(str(path))))

    def test_remote_image_format_uses_magic_bytes(self) -> None:
        webp = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + (b"\0" * 1200)
        self.assertEqual(
            STICKER._remote_image_extension(webp),
            ".webp",
        )
        self.assertEqual(
            STICKER._remote_image_extension(PNG_BYTES),
            ".png",
        )
        self.assertEqual(
            STICKER._remote_image_extension(b"not an image"),
            "",
        )

    def test_invalid_meta_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            (temp / "meta.json").write_text("[]", encoding="utf-8")
            plugin = object.__new__(STICKER.TafeiSticker)
            with patch.object(STICKER, "STICKER_DIR", str(temp)):
                self.assertEqual(plugin._load_meta(), {})

    def test_auto_tag_preserves_concurrent_client_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            target = temp / "new.png"
            target.write_bytes(PNG_BYTES)
            meta_path = temp / "meta.json"
            initial = {
                "new.png": {"q": 1},
                "edited.png": {"q": 9, "kw": ["旧标签"]},
            }
            meta_path.write_text(
                json.dumps(initial, ensure_ascii=False),
                encoding="utf-8",
            )
            concurrent = {
                "new.png": {"q": 1},
                "edited.png": {"q": 9, "kw": ["用户刚改的标签"]},
            }
            provider = FakeProvider(meta_path, concurrent)
            plugin = object.__new__(STICKER.TafeiSticker)
            plugin.context = FakeContext(provider)
            plugin.cfg = {
                "auto_tag_provider_id": "test/vision",
            }
            with patch.object(STICKER, "STICKER_DIR", str(temp)):
                plugin.meta = plugin._load_meta()
                added = asyncio.run(plugin._tag_sticker(str(target)))
                saved = json.loads(meta_path.read_text(encoding="utf-8"))

            self.assertTrue(added)
            self.assertEqual(saved["edited.png"]["kw"], ["用户刚改的标签"])
            self.assertIn("新表情", saved["new.png"]["kw"])

    def test_duel_replaces_text_and_stops_after_three_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            image_path = temp / "shock.png"
            image_path.write_bytes(PNG_BYTES)
            (temp / "meta.json").write_text(
                json.dumps(
                    {
                        "shock.png": {
                            "q": 1,
                            "kw": ["震惊"],
                            "emotion": ["震惊"],
                            "intent": ["吃惊"],
                            "tone": ["夸张"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            plugin = object.__new__(STICKER.TafeiSticker)
            plugin.cfg = {
                "enabled": True,
                "probability": 0.0,
                "cooldown_seconds": 0,
                "duel_enabled": True,
                "duel_probability": 1.0,
                "duel_max_rounds": 3,
                "duel_window_seconds": 180,
                "duel_cooldown_seconds": 0,
                "duel_sticker_only": True,
            }
            plugin.meta = {}
            plugin._recent = {}
            plugin._last_ts = {}
            plugin._duel_state = {}
            plugin._meta_mtime = 0

            with patch.object(STICKER, "STICKER_DIR", str(temp)):
                async def run():
                    results = []
                    for _ in range(4):
                        event = FakeEvent(str(image_path))
                        await plugin.maybe_sticker(event)
                        results.append(event.result.chain)
                    return results

                results = asyncio.run(run())

            for chain in results[:3]:
                self.assertEqual(len(chain), 1)
                self.assertIsInstance(chain[0], Image)
            self.assertEqual(len(results[3]), 1)
            self.assertIsInstance(results[3][0], Plain)


if __name__ == "__main__":
    unittest.main()
