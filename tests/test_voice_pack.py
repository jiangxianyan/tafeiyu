"""Regression tests for one-file tafeiyu voice-pack installation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launcher"
if str(LAUNCHER) not in sys.path:
    sys.path.insert(0, str(LAUNCHER))

import setup_core  # noqa: E402


def write_pack(path: Path, *, unsafe_member: str = "") -> None:
    pack = {
        "format": "tafeiyu.voice_pack",
        "format_version": 1,
        "id": "tafei-v2-test",
        "persona_id": "tafei",
        "display_name": "小菲测试声线",
        "engine": "gpt-sovits",
        "model_version": "v2",
        "gpt_model": "models/voice.ckpt",
        "sovits_model": "models/voice.pth",
        "reference_sample_rate": 32000,
        "references": [
            {
                "id": "ref_01",
                "file": "references/ref_01.wav",
                "text": "第一段参考文字",
            },
            {
                "id": "ref_02",
                "file": "references/ref_02.wav",
                "text": "第二段参考文字",
            },
        ],
        "style_refs": {
            "normal": "ref_01",
            "cute": "ref_01",
            "happy": "ref_02",
            "annoyed": "ref_02",
            "soft": "ref_01",
        },
    }
    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr("pack.json", json.dumps(pack, ensure_ascii=False))
        handle.writestr("models/voice.ckpt", b"gpt-test")
        handle.writestr("models/voice.pth", b"sovits-test")
        handle.writestr("references/ref_01.wav", b"RIFF-test-1")
        handle.writestr("references/ref_02.wav", b"RIFF-test-2")
        if unsafe_member:
            handle.writestr(unsafe_member, b"unsafe")


class VoicePackInstallTest(unittest.TestCase):
    def test_voice_pack_installs_manifest_styles_and_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine = root / "runtime" / "GPT-SoVITS-run" / "GPT_SoVITS"
            base_config = engine / "configs" / "tts_infer.yaml"
            base_config.parent.mkdir(parents=True)
            base_config.write_text(
                "custom:\n"
                "  device: cpu\n"
                "v2:\n"
                "  version: v2\n",
                encoding="utf-8",
            )
            voice_config = root / "voice-config.json"
            archive = root / "tafei.tafeivoice.zip"
            write_pack(archive)
            with patch.object(setup_core, "ROOT", root):
                result = setup_core.import_voice_bundle(
                    archive,
                    persona_id="tafei",
                    voice_config_path=voice_config,
                    pack_root=root / "voice" / "packs",
                )
            manifest = json.loads(
                Path(result["manifest_path"]).read_text(encoding="utf-8")
            )
            config = json.loads(voice_config.read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["references"]), 2)
            self.assertEqual(config["style_refs"]["happy"], "ref_02")
            self.assertTrue(
                config["voice_bindings"]["tafei"]["enabled"]
            )
            self.assertEqual(result["references"], 2)

    def test_voice_pack_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "unsafe.tafeivoice.zip"
            write_pack(archive, unsafe_member="../escape.txt")
            with self.assertRaisesRegex(ValueError, "不安全路径"):
                setup_core.import_voice_bundle(
                    archive,
                    persona_id="tafei",
                    voice_config_path=root / "voice-config.json",
                    pack_root=root / "voice" / "packs",
                )


if __name__ == "__main__":
    unittest.main()
