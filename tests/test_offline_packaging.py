"""Regression tests for safe and correctly named release packages."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from astrbot.core.utils.auth_password import verify_dashboard_password
except ImportError:
    verify_dashboard_password = None


ROOT = Path(__file__).resolve().parents[1]
PACKAGING_PATH = ROOT / "scripts" / "build_offline_package.py"
SPEC = importlib.util.spec_from_file_location(
    "tafeiyu_packaging_test",
    PACKAGING_PATH,
)
PACKAGING = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PACKAGING)


class OfflinePackagingTest(unittest.TestCase):
    def test_live_passwords_and_secrets_are_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source"
            stage = temp / "stage"
            cmd_path = source / "astrbot" / "data" / "cmd_config.json"
            group_path = (
                source
                / "astrbot"
                / "data"
                / "config"
                / "astrbot_plugin_group_chat_plus_config.json"
            )
            cmd_path.parent.mkdir(parents=True)
            group_path.parent.mkdir(parents=True)
            cmd_path.write_text(
                json.dumps(
                    {
                        "admins_id": ["123456"],
                        "provider_sources": [
                            {
                                "id": "deepseek",
                                "key": ["secret-key"],
                                "custom_headers": {"Authorization": "secret"},
                            }
                        ],
                        "dashboard": {
                            "username": "astrbot",
                            "password": "old-password",
                            "pbkdf2_password": "old-hash",
                            "jwt_secret": "old-jwt",
                        },
                        "platform_settings": {
                            "id_whitelist": ["123456", "999999"],
                            "path_mapping": [["C:\\Users\\developer", "D:\\"]],
                        },
                        "platform": [
                            {
                                "id": "qq-napcat",
                                "ws_reverse_token": "private-token",
                            }
                        ],
                        "provider_settings": {
                            "websearch_tavily_key": "private-search-key",
                        },
                        "http_proxy": "http://user:pass@example.invalid",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            group_path.write_text(
                json.dumps(
                    {
                        "enabled_groups": ["111"],
                        "poke_enabled_groups": ["111"],
                        "proactive_enabled_groups": ["111"],
                        "blacklist_user_ids": ["222"],
                        "image_message_force_reply_user_ids": ["123456"],
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(PACKAGING, "ROOT", source):
                PACKAGING._sanitize_live_defaults(stage)

            sanitized = json.loads(
                (stage / "astrbot" / "data" / "cmd_config.json").read_text(
                    encoding="utf-8"
                )
            )
            group = json.loads(
                (
                    stage
                    / "astrbot"
                    / "data"
                    / "config"
                    / "astrbot_plugin_group_chat_plus_config.json"
                ).read_text(encoding="utf-8")
            )
            dashboard = sanitized["dashboard"]
            self.assertEqual(sanitized["admins_id"], [])
            self.assertEqual(sanitized["platform_settings"]["id_whitelist"], [])
            self.assertEqual(sanitized["provider_sources"][0]["key"], [])
            self.assertEqual(
                sanitized["provider_sources"][0]["custom_headers"],
                {},
            )
            self.assertEqual(sanitized["http_proxy"], "")
            self.assertEqual(
                sanitized["platform_settings"]["path_mapping"],
                [],
            )
            self.assertEqual(
                sanitized["platform"][0]["ws_reverse_token"],
                "",
            )
            self.assertEqual(
                sanitized["provider_settings"]["websearch_tavily_key"],
                "",
            )
            self.assertNotEqual(dashboard["password"], "old-password")
            self.assertNotEqual(dashboard["pbkdf2_password"], "old-hash")
            self.assertNotEqual(dashboard["jwt_secret"], "old-jwt")
            algorithm, iterations, salt, digest = dashboard[
                "pbkdf2_password"
            ].split("$", 3)
            expected = hashlib.pbkdf2_hmac(
                "sha256",
                dashboard["password"].encode("utf-8"),
                bytes.fromhex(salt),
                int(iterations),
            ).hex()
            self.assertEqual(algorithm, "pbkdf2_sha256")
            self.assertEqual(digest, expected)
            if verify_dashboard_password is not None:
                self.assertTrue(
                    verify_dashboard_password(
                        dashboard["pbkdf2_password"],
                        dashboard["password"],
                    )
                )
            self.assertEqual(
                group["image_message_force_reply_user_ids"],
                [],
            )
            self.assertIn(
                dashboard["password"],
                (stage / "首次运行说明.txt").read_text(encoding="utf-8"),
            )

    def test_transient_runtime_files_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transient = root / ".bot_runtime" / "watchdog.heartbeat"
            old_dist = root / "dist-final" / "checksums.json"
            stale_launcher = root / "legacy_launchers" / "start7.ps1"
            stray_file = root / "500')"
            transient.parent.mkdir(parents=True)
            old_dist.parent.mkdir(parents=True)
            stale_launcher.parent.mkdir(parents=True)
            transient.write_text("1", encoding="ascii")
            old_dist.write_text("{}", encoding="utf-8")
            stale_launcher.write_text("old", encoding="utf-8")
            stray_file.write_text("stray", encoding="utf-8")
            with patch.object(PACKAGING, "ROOT", root):
                self.assertTrue(PACKAGING._should_skip(transient))
                self.assertTrue(PACKAGING._should_skip(old_dist))
                self.assertTrue(PACKAGING._should_skip(stale_launcher))
                self.assertTrue(PACKAGING._should_skip(stray_file))

    def test_astrbot_plugins_are_included_but_private_voice_data_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plugins = root / "astrbot" / "data" / "plugins"
            voice = plugins / "tafei_voice" / "main.py"
            persona_data = (
                root
                / "astrbot"
                / "data"
                / "plugin_data"
                / "tafei_persona"
                / "style.txt"
            )
            voice_data = (
                root
                / "astrbot"
                / "data"
                / "plugin_data"
                / "tafei_voice"
                / "config.json"
            )
            for path in (voice, persona_data, voice_data):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            with patch.object(PACKAGING, "ROOT", root):
                self.assertFalse(PACKAGING._should_skip(plugins))
                self.assertFalse(PACKAGING._should_skip(voice))
                self.assertFalse(PACKAGING._should_skip(persona_data))
                self.assertTrue(PACKAGING._should_skip(voice_data))

    def test_runtime_copy_removes_developer_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "astrbot-tool"
            scripts = source / "Scripts"
            scripts.mkdir(parents=True)
            (source / "pyvenv.cfg").write_text(
                "home = C:\\Users\\developer\\Python312\n"
                "implementation = CPython\n"
                "uv = 0.13.4\n"
                "version_info = 3.12.2\n",
                encoding="utf-8",
            )
            (source / "uv-receipt.toml").write_text(
                "python = 'C:\\Users\\developer\\Python312\\python.exe'\n",
                encoding="utf-8",
            )
            nested_data = (
                source
                / "Lib"
                / "site-packages"
                / "torch"
                / "utils"
                / "data"
                / "__init__.py"
            )
            nested_data.parent.mkdir(parents=True)
            nested_data.write_text("VALUE = 1\n", encoding="utf-8")
            (source / "data").mkdir()
            (source / "data" / "private.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (scripts / "activate.bat").write_text(
                "set VIRTUAL_ENV=C:\\Users\\developer\n",
                encoding="utf-8",
            )
            (source / "marker.txt").write_text("ok", encoding="utf-8")
            destination = temp / "stage"

            PACKAGING._copy_runtime(
                str(source),
                destination,
                "astrbot-tool",
            )

            copied = destination / "runtime" / "astrbot-tool"
            config = (copied / "pyvenv.cfg").read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users\\developer", config)
            self.assertNotIn("home =", config)
            self.assertFalse((copied / "uv-receipt.toml").exists())
            self.assertFalse((copied / "Scripts" / "activate.bat").exists())
            self.assertTrue(
                (
                    copied
                    / "Lib"
                    / "site-packages"
                    / "torch"
                    / "utils"
                    / "data"
                    / "__init__.py"
                ).is_file()
            )
            self.assertFalse((copied / "data").exists())
            self.assertTrue((copied / "marker.txt").is_file())

    def test_voice_runtime_keeps_base_but_excludes_persona_weights(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "GPT-SoVITS-run"
            base = source / "GPT_SoVITS" / "pretrained_models" / "base.ckpt"
            custom_gpt = source / "GPT_SoVITS" / "GPT_weights_v2" / "tafei.ckpt"
            custom_sovits = (
                source / "GPT_SoVITS" / "SoVITS_weights_v2" / "tafei.pth"
            )
            references = source / "voices" / "tafei" / "ref.wav"
            for path in (base, custom_gpt, custom_sovits, references):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test")
            destination = temp / "stage"

            PACKAGING._copy_runtime(
                str(source),
                destination,
                "GPT-SoVITS-run",
            )

            copied = destination / "runtime" / "GPT-SoVITS-run"
            self.assertTrue(
                (copied / "GPT_SoVITS" / "pretrained_models" / "base.ckpt").is_file()
            )
            self.assertFalse(
                (copied / "GPT_SoVITS" / "GPT_weights_v2").exists()
            )
            self.assertFalse(
                (copied / "GPT_SoVITS" / "SoVITS_weights_v2").exists()
            )
            self.assertFalse((copied / "voices").exists())

    def test_voice_defaults_use_the_bundled_base_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stage = Path(temp_dir)
            config = (
                stage
                / "runtime"
                / "GPT-SoVITS-run"
                / "GPT_SoVITS"
                / "configs"
                / "tts_infer.yaml"
            )
            config.parent.mkdir(parents=True)
            config.write_text(
                "custom:\n"
                "  version: v2\n"
                "  t2s_weights_path: custom/persona.ckpt\n"
                "  vits_weights_path: custom/persona.pth\n"
                "v2:\n"
                "  bert_base_path: base/bert\n"
                "  cnhuhbert_base_path: base/hubert\n"
                "  t2s_weights_path: base/model.ckpt\n"
                "  vits_weights_path: base/model.pth\n"
                "  version: v2\n",
                encoding="utf-8",
            )

            PACKAGING._sanitize_voice_defaults(stage)

            import yaml

            data = yaml.safe_load(config.read_text(encoding="utf-8"))
            self.assertEqual(
                data["custom"]["t2s_weights_path"],
                "base/model.ckpt",
            )
            self.assertEqual(
                data["custom"]["vits_weights_path"],
                "base/model.pth",
            )
            self.assertNotIn("persona", config.read_text(encoding="utf-8"))

    def test_generated_installer_requires_python_312(self) -> None:
        installer = PACKAGING._installer_batch()
        start = (ROOT / "启动塔菲.bat").read_text(encoding="utf-8")
        self.assertIn("py -3.12", installer)
        self.assertIn("py -3.12", start)
        self.assertNotIn("Python313", start)
        self.assertNotIn("py -3 ", start)
        self.assertNotIn("\r\r\n", installer)


if __name__ == "__main__":
    unittest.main()
