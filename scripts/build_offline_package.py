#!/usr/bin/env python3
"""Build an offline tafeiyu package without embedding live user data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import string
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist"
EXCLUDED_TOP_LEVEL = {
    ".git",
    ".secrets",
    ".visual_tmp",
    "backup_20261024_013726",
    "downloads",
    "dist",
    "local",
    "napcat",
    "stickers",
    "voice",
    "wcf",
}
EXCLUDED_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".jsonl",
    ".lock",
    ".log",
    ".pyc",
    ".tmp",
}
EXCLUDED_NAMES = {
    ".astrbot",
    ".manual_login_required",
    ".pause_watchdog",
    ".setup_complete",
    "cmd_config.json",
    "deploy_state.json",
    "memory.db",
    "napcat_start_attempts.json",
    "start_astrbot.bat",
    "start_napcat.bat",
    "tafei.env.json",
    "watchdog.heartbeat",
}
MAX_SPLIT_BYTES = 1800 * 1024 * 1024


def _generate_dashboard_password() -> str:
    alphabet = string.ascii_letters + string.digits
    characters = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        *(secrets.choice(alphabet) for _ in range(21)),
    ]
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _should_skip(path: Path) -> bool:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return False
    if relative.parts and relative.parts[0] in EXCLUDED_TOP_LEVEL:
        return True
    if relative.parts and (
        relative.parts[0] == "dist"
        or relative.parts[0].startswith("dist-")
    ):
        return True
    if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if (
        path.suffix.lower() in {".gif", ".jpeg", ".jpg", ".png", ".webp"}
        and relative.parts[:2] not in {("assets", "ui"), ("assets", "local")}
    ):
        return True
    if "__pycache__" in relative.parts:
        return True
    if (
        len(relative.parts) >= 3
        and relative.parts[0] == "astrbot"
        and relative.parts[1] == "data"
    ):
        allowed = {
            ("personas",),
            ("plugins",),
            ("persona_visuals",),
            ("plugin_data", "tafei_persona"),
        }
        nested = tuple(relative.parts[2:-1])
        if not any(
            nested == candidate
            or (candidate and nested[: len(candidate)] == candidate)
            for candidate in allowed
        ):
            return True
    if path.is_file() and path.stat().st_size > 512 * 1024 * 1024:
        return True
    return False


def _copy_tree(source: Path, destination: Path) -> None:
    for directory, folders, files in os.walk(source):
        current = Path(directory)
        folders[:] = [
            name for name in folders if not _should_skip(current / name)
        ]
        destination.mkdir(parents=True, exist_ok=True)
        for name in files:
            path = current / name
            if _should_skip(path):
                continue
            relative = path.relative_to(ROOT)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _copy_runtime(source: str | None, destination: Path, label: str) -> None:
    if not source:
        return
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"{label}不存在：{path}")
    target = destination / "runtime" / label
    if path.is_dir():
        ignored = [
            ".git",
            ".github",
            "__pycache__",
            "*.db",
            "*.db-shm",
            "*.db-wal",
            "*.pyc",
            "*.log",
            "cache",
            "config",
            "data",
            "log",
            "logs",
            "output",
            "outputs",
            "temp",
        ]
        if label == "GPT-SoVITS-run":
            ignored.extend(["voices", "logs"])
        shutil.copytree(
            path,
            target,
            ignore=shutil.ignore_patterns(*ignored),
        )
        for config in target.rglob("pyvenv.cfg"):
            try:
                lines = config.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).splitlines()
                retained = [
                    line
                    for line in lines
                    if not line.strip().lower().startswith(("home =", "uv ="))
                ]
                config.write_text(
                    "\n".join(retained) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        for receipt in target.rglob("uv-receipt.toml"):
            receipt.unlink(missing_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _sanitize_live_defaults(stage: Path) -> None:
    cmd_source = ROOT / "astrbot" / "data" / "cmd_config.json"
    if cmd_source.is_file():
        try:
            cmd = json.loads(cmd_source.read_text(encoding="utf-8-sig"))
            for source in cmd.get("provider_sources", []):
                source["key"] = []
                source["custom_headers"] = {}
                source["proxy"] = ""
            cmd["admins_id"] = []
            cmd["http_proxy"] = ""
            cmd["t2i_endpoint"] = ""
            platform = cmd.setdefault("platform_settings", {})
            platform["id_whitelist"] = []
            platform["path_mapping"] = []
            for adapter in cmd.get("platform", []):
                if isinstance(adapter, dict):
                    adapter["ws_reverse_token"] = ""
            provider_settings = cmd.setdefault("provider_settings", {})
            for key in (
                "websearch_tavily_key",
                "websearch_bocha_key",
                "websearch_brave_key",
                "websearch_baidu_app_builder_key",
                "websearch_firecrawl_key",
                "websearch_exa_key",
                "websearch_anysearch_key",
                "websearch_deepseek_key",
                "websearch_serpapi_key",
            ):
                provider_settings[key] = ""
            dashboard = cmd.setdefault("dashboard", {})
            initial_password = _generate_dashboard_password()
            salt = secrets.token_hex(16)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                initial_password.encode("utf-8"),
                bytes.fromhex(salt),
                600000,
            ).hex()
            dashboard["password"] = initial_password
            dashboard["pbkdf2_password"] = (
                f"pbkdf2_sha256$600000${salt}${digest}"
            )
            dashboard["password_change_required"] = True
            dashboard["password_storage_upgraded"] = True
            dashboard["jwt_secret"] = secrets.token_hex(32)
            target = stage / "astrbot" / "data" / "cmd_config.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(cmd, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (stage / "首次运行说明.txt").write_text(
                "管理员页只监听本机。首次登录密码如下，请登录后立即修改：\n"
                + initial_password
                + "\n",
                encoding="utf-8",
            )
        except (OSError, ValueError):
            pass

    group_source = (
        ROOT
        / "astrbot"
        / "data"
        / "config"
        / "astrbot_plugin_group_chat_plus_config.json"
    )
    if group_source.is_file():
        try:
            group = json.loads(group_source.read_text(encoding="utf-8-sig"))
            group["enabled_groups"] = []
            group["poke_enabled_groups"] = []
            group["proactive_enabled_groups"] = []
            group["blacklist_user_ids"] = []
            group["image_message_force_reply_user_ids"] = []
            target = (
                stage
                / "astrbot"
                / "data"
                / "config"
                / "astrbot_plugin_group_chat_plus_config.json"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(group, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, ValueError):
            pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_directory(source: Path, output: Path, prefix: str) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    archives = []
    current = None
    current_size = 0
    part = 1
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if current is None or current_size + path.stat().st_size > MAX_SPLIT_BYTES:
            if current is not None:
                current.close()
            archive = output / f"{prefix}-part{part:02d}.zip"
            current = zipfile.ZipFile(
                archive,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            )
            archives.append(archive)
            current_size = 0
            part += 1
        current.write(path, path.relative_to(source).as_posix())
        current_size += path.stat().st_size
    if current is not None:
        current.close()
    return archives


def build(args) -> Path:
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tafeiyu-offline-") as temp:
        stage = Path(temp) / "tafeiyu"
        stage.mkdir(parents=True)
        _copy_tree(ROOT, stage)
        _sanitize_live_defaults(stage)
        _copy_runtime(args.astrbot_tool, stage, "astrbot-tool")
        _copy_runtime(args.napcat_shell, stage, "napcat-shell")
        _copy_runtime(args.voice_engine, stage, "GPT-SoVITS-run")
        if args.python_installer:
            _copy_runtime(args.python_installer, stage, "python-installer.exe")
        offline = bool(
            args.astrbot_tool
            or args.napcat_shell
            or args.voice_engine
            or args.python_installer
        )
        manifest = {
            "name": "tafeiyu",
            "package_type": "offline" if offline else "source",
            "offline": offline,
            "voice_weights_included": False,
            "runtimes": {
                "astrbot": bool(args.astrbot_tool),
                "napcat": bool(args.napcat_shell),
                "gpt_sovits": bool(args.voice_engine),
                "python_installer": bool(args.python_installer),
            },
        }
        (stage / "offline-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if offline:
            (stage / "安装说明.txt").write_text(
                "1. 安装 python-installer.exe（如果包内有）。\n"
                "2. 运行 安装塔菲鱼.bat 或 启动塔菲.bat。\n"
                "3. 按配置向导填写 API Key 和主人 QQ。\n"
                "4. 使用独立机器人 QQ 扫码登录。\n"
                "5. 声线权重和参考音频需用户自行导入，公开包不包含角色声线。\n",
                encoding="utf-8",
            )
            (stage / "安装塔菲鱼.bat").write_text(
                "@echo off\r\n"
                "chcp 936 >nul\r\n"
                "cd /d \"%~dp0\"\r\n"
                "if exist \"%~dp0runtime\\python-installer.exe\" (\r\n"
                "  start /wait \"\" \"%~dp0runtime\\python-installer.exe\" "
                "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 "
                "Include_test=0\r\n"
                ")\r\n"
                "if exist \"%~dp0requirements-launcher.txt\" (\r\n"
                "  where py >nul 2>&1\r\n"
                "  if not errorlevel 1 (\r\n"
                "    py -3.12 -m pip install -r "
                "\"%~dp0requirements-launcher.txt\" --disable-pip-version-check\r\n"
                "    if errorlevel 1 py -3 -m pip install -r "
                "\"%~dp0requirements-launcher.txt\" --disable-pip-version-check\r\n"
                "  ) else (\r\n"
                "    python -m pip install -r "
                "\"%~dp0requirements-launcher.txt\" --disable-pip-version-check\r\n"
                "  )\r\n"
                ")\r\n"
                "call \"%~dp0启动塔菲.bat\"\r\n",
                encoding="gbk",
            )
        prefix = "tafeiyu-offline" if offline else "tafeiyu-source"
        archives = _zip_directory(stage, output, prefix)
    checksums = {
        archive.name: {
            "size": archive.stat().st_size,
            "sha256": _sha256(archive),
        }
        for archive in archives
    }
    (output / "SHA256SUMS.json").write_text(
        json.dumps(checksums, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--astrbot-tool")
    parser.add_argument("--napcat-shell")
    parser.add_argument("--voice-engine")
    parser.add_argument("--python-installer")
    args = parser.parse_args()
    output = build(args)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
