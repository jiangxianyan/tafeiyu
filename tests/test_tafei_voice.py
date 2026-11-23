"""Regression tests for deterministic owner voice replies and cache isolation."""

from __future__ import annotations

import asyncio
import importlib.util
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, call, patch

try:
    from astrbot.api.message_components import Plain, Record

    ASTRBOT_AVAILABLE = True
except ImportError:
    Plain = None
    Record = None
    ASTRBOT_AVAILABLE = False


PLUGIN_PATH = (
    Path(__file__).resolve().parents[1]
    / "astrbot"
    / "data"
    / "plugins"
    / "tafei_voice"
    / "main.py"
)
if ASTRBOT_AVAILABLE:
    SPEC = importlib.util.spec_from_file_location(
        "tafei_voice_test_module",
        PLUGIN_PATH,
    )
    VOICE = importlib.util.module_from_spec(SPEC)
    assert SPEC.loader is not None
    SPEC.loader.exec_module(VOICE)
else:
    VOICE = None


class FakeEvent:
    unified_msg_origin = "aiocqhttp:FriendMessage:10001"
    message_str = "塔菲在吗"

    def __init__(
        self,
        *,
        private: bool = True,
        sender: str = "10001",
        session: str = "aiocqhttp:FriendMessage:10001",
        text: str = "塔菲在的喵",
    ) -> None:
        self.private = private
        self.sender = sender
        self.session = session
        self.result = types.SimpleNamespace(chain=[Plain(text)])
        self.extra = {}
        self.message_obj = types.SimpleNamespace(
            sender=types.SimpleNamespace(user_id=sender),
        )
        self.sent = []

    def is_private_chat(self) -> bool:
        return self.private

    def get_sender_id(self) -> str:
        return self.sender

    def get_session_id(self) -> str:
        return self.session

    def get_group_id(self) -> str:
        return "" if self.private else "123456"

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    def get_result(self):
        return self.result

    def set_extra(self, key, value) -> None:
        self.extra[key] = value

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    async def send(self, message) -> None:
        self.sent.append(message)


@unittest.skipUnless(ASTRBOT_AVAILABLE, "AstrBot runtime is not installed")
class VoiceRoutingTest(unittest.TestCase):
    def make_plugin(self):
        plugin = object.__new__(VOICE.TafeiVoice)
        plugin.config = {
            "enabled": True,
            "auto_probability": 0.0,
            "max_chars": 60,
            "force_max_chars": 300,
            "owner_user_ids": ["10001"],
            "force_voice_keywords": ["发语音", "说话"],
            "punctuation_pauses_ms": {
                key: 0 for key in VOICE.DEFAULT_PUNCTUATION_PAUSES_MS
            },
        }
        plugin.binding = {}
        return plugin

    def test_owner_private_reply_uses_voice_beyond_group_limit(self) -> None:
        plugin = self.make_plugin()
        plugin._voice_enabled = lambda: True
        plugin._synthesize = AsyncMock(return_value="C:/tmp/test.wav")
        event = FakeEvent(text="喵" * 72)

        with patch.object(
            VOICE.Record,
            "fromFileSystem",
            return_value=object(),
        ):
            asyncio.run(plugin.add_voice(event))

        plugin._synthesize.assert_awaited_once_with(
            "喵" * 72,
            style="cute",
        )
        self.assertEqual(len(event.result.chain), 2)

    def test_owner_can_be_found_in_private_session_id(self) -> None:
        plugin = self.make_plugin()
        event = FakeEvent(
            sender="",
            session="aiocqhttp:FriendMessage:10001",
        )
        self.assertTrue(plugin._is_owner_private_chat(event))

    def test_group_sender_is_not_treated_as_owner_private(self) -> None:
        plugin = self.make_plugin()
        event = FakeEvent(
            private=False,
            session="aiocqhttp:GroupMessage:123456",
        )
        self.assertFalse(plugin._is_owner_private_chat(event))

    def test_cache_key_changes_with_persona_and_reference(self) -> None:
        manifest = {
            "gpt_model": "gpt.ckpt",
            "sovits_model": "sovits.pth",
        }
        reference = {
            "id": "ref_01",
            "file": "reference/ref_01.wav",
            "text": "参考文本",
        }
        first = VOICE.TafeiVoice._gpt_cache_key(
            persona_id="tafei",
            manifest=manifest,
            reference=reference,
            style="cute",
            text="你好喵",
        )
        other_persona = VOICE.TafeiVoice._gpt_cache_key(
            persona_id="dafeiyu",
            manifest=manifest,
            reference=reference,
            style="cute",
            text="你好喵",
        )
        other_reference = VOICE.TafeiVoice._gpt_cache_key(
            persona_id="tafei",
            manifest=manifest,
            reference={**reference, "file": "reference/ref_02.wav"},
            style="cute",
            text="你好喵",
        )
        self.assertNotEqual(first, other_persona)
        self.assertNotEqual(first, other_reference)

    def test_sentence_splitter_handles_emoji_space_boundary(self) -> None:
        parts = VOICE._split_voice_segments(
            "诶，塔菲在呢，专门给雏草姬说一句喵😉 "
            "准备好了没，听完给点反应啊！"
        )
        self.assertEqual(len(parts), 2)
        self.assertIn("准备好", parts[1])

    def test_three_sentences_are_limited_to_two_voice_parts(self) -> None:
        parts = VOICE._split_voice_segments(
            "第一句。第二句！第三句？",
            max_segments=2,
        )
        self.assertEqual(parts, ["第一句。", "第二句！第三句？"])

    def test_owner_reply_sends_first_then_prefetched_second(self) -> None:
        plugin = self.make_plugin()
        plugin.config["max_voice_segments"] = 2
        plugin.config["sentence_split_enabled"] = True
        plugin._voice_enabled = lambda: True
        plugin._synthesize = AsyncMock(
            side_effect=["C:/tmp/first.wav", "C:/tmp/second.wav"]
        )
        event = FakeEvent(
            text=(
                "晚安，辛苦啦。"
                "好耶！太棒了！"
            )
        )

        def make_record(path, text=None):
            return types.SimpleNamespace(path=path, text=text)

        async def run_case():
            await plugin.add_voice(event)
            self.assertEqual(len(event.result.chain), 2)
            self.assertEqual(event.result.chain[0].text, "晚安，辛苦啦。")
            self.assertEqual(event.result.chain[1].path, "C:/tmp/first.wav")
            pending = event.get_extra(VOICE.PENDING_VOICE_EXTRA)
            self.assertIsNotNone(pending)
            self.assertEqual(pending["text"], "好耶！太棒了！")
            await plugin.send_prefetched_voice(event)

        with patch.object(
            VOICE.Record,
            "fromFileSystem",
            side_effect=make_record,
        ):
            asyncio.run(run_case())

        self.assertEqual(len(event.sent), 1)
        sent_chain = event.sent[0].chain
        self.assertEqual(sent_chain[0].text, "好耶！太棒了！")
        self.assertEqual(sent_chain[1].path, "C:/tmp/second.wav")
        plugin._synthesize.assert_has_awaits(
            [
                call("晚安，辛苦啦。", style="soft"),
                call("好耶！太棒了！", style="happy"),
            ]
        )

    def test_punctuation_controls_pause_duration(self) -> None:
        pauses = VOICE._normalize_pause_settings(
            {
                "comma": 120,
                "ellipsis": 600,
                "exclamation": 250,
            }
        )
        self.assertEqual(VOICE._pause_after_text("诶，", pauses), 120)
        self.assertEqual(VOICE._pause_after_text("等等……", pauses), 600)
        self.assertEqual(VOICE._pause_after_text("好耶！", pauses), 250)
        self.assertEqual(VOICE._pause_after_text("好耶！😉", pauses), 250)
        self.assertEqual(
            VOICE._split_pause_clauses("诶，真的吗……好耶！"),
            ["诶，", "真的吗……", "好耶！"],
        )

    def test_wav_concatenation_inserts_configured_silence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for index in range(3):
                path = str(Path(temp_dir) / f"part-{index}.wav")
                with wave.open(path, "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(1000)
                    handle.writeframes(b"\x00\x01" * 1000)
                paths.append(path)
            output = VOICE._concat_wav_with_pauses(
                paths,
                [100, 200, 0],
                str(Path(temp_dir) / "joined.wav"),
            )
            with wave.open(output, "rb") as handle:
                self.assertEqual(handle.getnframes(), 3300)


if __name__ == "__main__":
    unittest.main()
