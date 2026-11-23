"""Regression tests for clean-machine setup contracts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launcher"
if str(LAUNCHER) not in sys.path:
    sys.path.insert(0, str(LAUNCHER))

import setup_core  # noqa: E402


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class SetupCoreTest(unittest.TestCase):
    def test_empty_paths_do_not_resolve_to_current_directory(self) -> None:
        self.assertIsNone(setup_core._existing_path(""))
        self.assertIsNone(setup_core._existing_path(None))

    def test_bundled_napcat_is_found_from_a_clean_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shell = root / "runtime" / "napcat-shell"
            shell.mkdir(parents=True)
            (shell / "NapCatWinBootMain.exe").write_bytes(b"test")
            with patch.object(setup_core, "ROOT", root):
                napcat_root, shell_dir = setup_core._find_napcat_paths({})
            self.assertEqual(Path(napcat_root), shell.resolve())
            self.assertEqual(Path(shell_dir), shell.resolve())

    def test_existing_complete_install_skips_wizard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config_path = temp / "cmd_config.json"
            deploy_path = temp / "deploy_state.json"
            setup_marker = temp / ".setup_complete"
            force_marker = temp / ".setup_required"
            write_json(
                config_path,
                {
                    "provider_sources": [
                        {"id": "deepseek", "key": ["test-key"]}
                    ],
                    "provider": [
                        {
                            "id": "deepseek/test",
                            "enable": True,
                            "provider_source_id": "deepseek",
                        }
                    ],
                },
            )
            write_json(
                deploy_path,
                {
                    "qq": "123456",
                    "admin_qq": "987654",
                    "astrbot_exe": str(temp / "astrbot.exe"),
                    "napcat_shell_dir": str(temp / "napcat"),
                },
            )
            with (
                patch.object(setup_core, "ASTRBOT_CONFIG", config_path),
                patch.object(setup_core, "DEPLOY_STATE", deploy_path),
                patch.object(setup_core, "SETUP_MARKER", setup_marker),
                patch.object(setup_core, "FORCE_SETUP_MARKER", force_marker),
            ):
                self.assertFalse(setup_core.setup_required())
                config = json.loads(config_path.read_text(encoding="utf-8"))
                config["provider_sources"][0]["key"] = []
                write_json(config_path, config)
                self.assertTrue(setup_core.setup_required())

    def test_model_setup_creates_text_and_vision_providers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "cmd_config.json"
            write_json(
                config_path,
                {
                    "provider_sources": [
                        {
                            "id": "deepseek",
                            "key": ["existing-key"],
                        }
                    ],
                    "provider": [
                        {
                            "id": "deepseek/old",
                            "provider_source_id": "deepseek",
                            "model": "old",
                            "modalities": ["text", "tool_use"],
                        }
                    ],
                },
            )
            result = setup_core.apply_model_settings(
                preset="DeepSeek",
                api_base="https://api.deepseek.com",
                model="text-model",
                vision_model="vision-model",
                api_key="",
                config_path=config_path,
            )
            data = json.loads(config_path.read_text(encoding="utf-8"))
            providers = {item["id"]: item for item in data["provider"]}
            self.assertIn("deepseek/text-model", providers)
            self.assertIn("deepseek/deepseek-vision", providers)
            self.assertEqual(
                providers["deepseek/deepseek-vision"]["model"],
                "vision-model",
            )
            self.assertIn(
                "image",
                providers["deepseek/deepseek-vision"]["modalities"],
            )
            self.assertEqual(
                data["provider_settings"]["default_image_caption_provider_id"],
                "deepseek/deepseek-vision",
            )
            self.assertEqual(result["vision_provider_id"], "deepseek/deepseek-vision")

    def test_qq_setup_writes_runtime_paths_and_personal_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            config_path = temp / "cmd_config.json"
            group_path = temp / "group.json"
            voice_path = temp / "voice.json"
            deploy_path = temp / "deploy_state.json"
            astrbot_exe = temp / "astrbot.exe"
            napcat_shell = temp / "napcat" / "NapCat.52230.Shell"
            napcat_shell.mkdir(parents=True)
            (napcat_shell / "NapCatWinBootMain.exe").write_bytes(b"test")
            astrbot_exe.write_bytes(b"test")
            write_json(config_path, {"provider_settings": {}})
            write_json(group_path, {"enabled_groups": [], "poke_enabled_groups": []})
            write_json(voice_path, {"enabled": False})

            with (
                patch.object(setup_core, "ROOT", temp),
                patch.object(setup_core, "ASTRBOT_CONFIG", config_path),
                patch.object(setup_core, "GROUP_CONFIG", group_path),
                patch.object(setup_core, "VOICE_CONFIG", voice_path),
                patch.object(setup_core, "DEPLOY_STATE", deploy_path),
                patch.object(
                    setup_core,
                    "_find_astrbot_exe",
                    return_value=str(astrbot_exe),
                ),
                patch.object(
                    setup_core,
                    "_find_napcat_paths",
                    return_value=(
                        str(napcat_shell.parent),
                        str(napcat_shell),
                    ),
                ),
            ):
                result = setup_core.apply_qq_and_groups(
                    bot_qq="123456",
                    owner_qq="987654",
                    whitelist="111111 222222",
                    blacklist="333333",
                )

            deploy = json.loads(deploy_path.read_text(encoding="utf-8"))
            config = json.loads(config_path.read_text(encoding="utf-8"))
            group = json.loads(group_path.read_text(encoding="utf-8"))
            voice = json.loads(voice_path.read_text(encoding="utf-8"))
            self.assertEqual(result["owner_qq"], "987654")
            self.assertEqual(deploy["qq"], "123456")
            self.assertEqual(deploy["admin_qq"], "987654")
            self.assertEqual(Path(deploy["install_root"]).resolve(), temp.resolve())
            self.assertEqual(
                Path(deploy["astrbot_root"]).resolve(),
                (temp / "astrbot").resolve(),
            )
            self.assertEqual(group["enabled_groups"], ["111111", "222222"])
            self.assertEqual(
                group["image_message_force_reply_user_ids"],
                ["987654"],
            )
            self.assertEqual(
                config["platform_settings"]["segmented_reply"]["interval"],
                "0,0",
            )
            self.assertEqual(voice["owner_user_ids"], ["987654"])


if __name__ == "__main__":
    unittest.main()
