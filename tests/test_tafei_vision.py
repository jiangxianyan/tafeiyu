"""Focused contract test for the private-chat vision hook.

Run with AstrBot's runtime Python:

    python -m unittest tests.test_tafei_vision
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import tempfile
import types
import unittest
from pathlib import Path

try:
    from astrbot.api.message_components import Image

    ASTRBOT_AVAILABLE = True
except ImportError:
    Image = None
    ASTRBOT_AVAILABLE = False


PLUGIN_PATH = (
    Path(__file__).resolve().parents[1]
    / "astrbot"
    / "data"
    / "plugins"
    / "tafei_vision"
    / "main.py"
)
if ASTRBOT_AVAILABLE:
    SPEC = importlib.util.spec_from_file_location(
        "tafei_vision_test_module",
        PLUGIN_PATH,
    )
    VISION = importlib.util.module_from_spec(SPEC)
    assert SPEC.loader is not None
    SPEC.loader.exec_module(VISION)
else:
    VISION = None

ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0f01f0005000201a3f0a5e70000000049454e44ae426082"
)


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def text_chat(self, **_kwargs):
        self.calls += 1
        return types.SimpleNamespace(completion_text="粉色头发、金色眼睛的动漫角色")


class FakeContext:
    def __init__(self, provider) -> None:
        self.provider = provider

    def get_provider_by_id(self, _provider_id: str):
        return self.provider


class FakeEvent:
    session_id = "test-session"

    def __init__(self, image) -> None:
        self.message_obj = types.SimpleNamespace(message=[image])

    def is_private_chat(self) -> bool:
        return True


@unittest.skipUnless(ASTRBOT_AVAILABLE, "AstrBot runtime is not installed")
class VisionHookTest(unittest.TestCase):
    def test_private_image_is_injected_and_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.png"
            image_path.write_bytes(ONE_PIXEL_PNG)
            provider = FakeProvider()
            plugin = object.__new__(VISION.TafeiVision)
            plugin.context = FakeContext(provider)
            plugin.dir = temp_dir
            plugin.config_path = os.path.join(temp_dir, "config.json")
            plugin.cache_path = os.path.join(temp_dir, "cache.json")
            plugin.config = {
                "enabled": True,
                "private_enabled": True,
                "group_fallback_enabled": False,
                "provider_id": "test/vision",
                "max_images_per_message": 4,
                "timeout_seconds": 10,
                "cache_max_entries": 20,
            }
            plugin.cache = {}
            image = Image.fromFileSystem(str(image_path))

            async def run() -> tuple[str, str, int]:
                plugin._cache_lock = asyncio.Lock()
                first = types.SimpleNamespace(
                    prompt="看看这张图",
                    system_prompt="",
                    contexts=[],
                )
                await plugin.inject_image_descriptions(FakeEvent(image), first)
                second = types.SimpleNamespace(
                    prompt="再看看这张图",
                    system_prompt="",
                    contexts=[],
                )
                await plugin.inject_image_descriptions(FakeEvent(image), second)
                return first.prompt, second.prompt, provider.calls

            first_prompt, second_prompt, calls = asyncio.run(run())
            self.assertIn("【用户发送的图片】", first_prompt)
            self.assertIn("粉色头发、金色眼睛的动漫角色", first_prompt)
            self.assertIn("【用户发送的图片】", second_prompt)
            self.assertEqual(calls, 1)
            with open(plugin.cache_path, encoding="utf-8") as handle:
                cache = json.load(handle)
            self.assertEqual(len(cache), 1)


if __name__ == "__main__":
    unittest.main()
