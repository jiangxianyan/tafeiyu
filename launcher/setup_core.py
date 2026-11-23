"""Configuration persistence for the tafeiyu first-run wizard."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP_MARKER = ROOT / ".setup_complete"
FORCE_SETUP_MARKER = ROOT / ".setup_required"
ASTRBOT_CONFIG = ROOT / "astrbot" / "data" / "cmd_config.json"
DEPLOY_STATE = ROOT / "deploy_state.json"
GROUP_CONFIG = (
    ROOT
    / "astrbot"
    / "data"
    / "config"
    / "astrbot_plugin_group_chat_plus_config.json"
)
VOICE_CONFIG = (
    ROOT
    / "astrbot"
    / "data"
    / "plugin_data"
    / "tafei_voice"
    / "config.json"
)

MODEL_PRESETS = {
    "DeepSeek": {
        "source_id": "deepseek",
        "provider": "deepseek",
        "api_base": "https://api.deepseek.com",
        "model": "deepseek-flash",
    },
    "OpenAI": {
        "source_id": "openai",
        "provider": "openai",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
    },
    "自定义 OpenAI 兼容": {
        "source_id": "custom",
        "provider": "openai",
        "api_base": "",
        "model": "",
    },
}


def _voice_engine() -> Path:
    candidates = [
        ROOT / "voice" / "GPT-SoVITS-run",
        ROOT / "runtime" / "GPT-SoVITS-run",
    ]
    return next((path for path in candidates if path.is_dir()), candidates[0])


def _default_tts_config() -> Path:
    return _voice_engine() / "GPT_SoVITS" / "configs" / "tts_infer.yaml"


def _default_voice_manifest() -> Path:
    return _voice_engine() / "voices" / "tafei_v2" / "manifest.json"


def _vision_provider_id(source_id: str) -> str:
    if source_id == "deepseek":
        return "deepseek/deepseek-vision"
    return f"{source_id}/vision"


def _load_json(path: Path, default=None):
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {} if default is None else default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def parse_ids(value: str) -> list[str]:
    parts = re.split(r"[\s,，;；]+", value.strip())
    return list(dict.fromkeys(part for part in parts if part))


def validate_user_id(value: str, label: str) -> str:
    value = value.strip()
    if not value.isdigit():
        raise ValueError(f"{label}必须是纯数字 QQ 号")
    return value


def setup_required() -> bool:
    if FORCE_SETUP_MARKER.is_file():
        return True
    if SETUP_MARKER.is_file():
        return False
    deploy = _load_json(DEPLOY_STATE)
    config = _load_json(ASTRBOT_CONFIG)
    sources = {
        str(item.get("id")): item
        for item in config.get("provider_sources", [])
        if isinstance(item, dict)
    }
    configured_provider = any(
        item.get("enable", True)
        and source_id in sources
        and bool(sources[source_id].get("key"))
        for item in config.get("provider", [])
        if isinstance(item, dict)
        for source_id in [str(item.get("provider_source_id") or "")]
    )
    complete = bool(
        str(deploy.get("qq") or "").strip()
        and str(deploy.get("admin_qq") or "").strip()
        and str(deploy.get("astrbot_exe") or "").strip()
        and str(deploy.get("napcat_shell_dir") or "").strip()
        and configured_provider
    )
    return not complete


def current_model_settings() -> dict:
    config = _load_json(ASTRBOT_CONFIG)
    providers = config.get("provider", [])
    sources = config.get("provider_sources", [])
    text_provider = next(
        (
            provider
            for provider in providers
            if provider.get("enable", True)
            and "text" in provider.get("modalities", ["text"])
        ),
        providers[0] if providers else {},
    )
    source_id = str(text_provider.get("provider_source_id") or "")
    source = next(
        (item for item in sources if str(item.get("id")) == source_id),
        sources[0] if sources else {},
    )
    vision_provider = next(
        (
            provider
            for provider in providers
            if provider.get("enable", True)
            and "image" in provider.get("modalities", [])
        ),
        {},
    )
    preset_name = next(
        (
            name
            for name, preset in MODEL_PRESETS.items()
            if preset["source_id"] == source_id
        ),
        "自定义 OpenAI 兼容",
    )
    return {
        "preset": preset_name,
        "source_id": source_id,
        "provider": source.get("provider", "openai"),
        "api_base": source.get("api_base", ""),
        "model": text_provider.get("model", ""),
        "vision_model": vision_provider.get(
            "model",
            text_provider.get("model", ""),
        ),
        "vision_provider_id": vision_provider.get("id", ""),
        "api_key_configured": bool(source.get("key")),
    }


def current_qq_settings() -> dict:
    deploy = _load_json(DEPLOY_STATE)
    group = _load_json(GROUP_CONFIG)
    white = deploy.get("group_whitelist")
    if white is None:
        white = group.get("enabled_groups", [])
    black = deploy.get("group_blacklist", [])
    return {
        "bot_qq": str(deploy.get("qq") or ""),
        "owner_qq": str(deploy.get("admin_qq") or ""),
        "whitelist": " ".join(str(item) for item in white),
        "blacklist": " ".join(str(item) for item in black),
    }


def apply_model_settings(
    *,
    preset: str,
    api_base: str,
    model: str,
    api_key: str,
    vision_model: str = "",
    config_path: Path = ASTRBOT_CONFIG,
) -> dict:
    preset_data = MODEL_PRESETS.get(preset)
    if preset_data is None:
        raise ValueError("未知的模型服务")
    api_base = api_base.strip().rstrip("/")
    model = model.strip()
    vision_model = (vision_model or model).strip() or model
    if not api_base:
        raise ValueError("API Base 不能为空")
    if not model:
        raise ValueError("模型名称不能为空")

    config = _load_json(config_path)
    if not config:
        raise RuntimeError("找不到 AstrBot 配置，请先完成 AstrBot 初始化")
    sources = config.setdefault("provider_sources", [])
    providers = config.setdefault("provider", [])

    source_id = preset_data["source_id"]
    source = next(
        (item for item in sources if str(item.get("id")) == source_id), None
    )
    if source is None:
        source = {"id": source_id}
        sources.append(source)

    old_keys = source.get("key") or []
    key_value = api_key.strip()
    if key_value:
        old_keys = [key_value]
    if not old_keys:
        raise ValueError("请填写 API Key；若使用已有服务，留空可保留原 Key")

    source.update(
        {
            "provider": preset_data["provider"],
            "type": "openai_chat_completion",
            "provider_type": "chat_completion",
            "key": old_keys,
            "api_base": api_base,
            "timeout": int(source.get("timeout") or 120),
            "proxy": source.get("proxy", ""),
            "custom_headers": source.get("custom_headers", {}),
            "enable": True,
        }
    )

    provider = next(
        (
            item
            for item in providers
            if item.get("enable", True)
            and "text" in item.get("modalities", ["text"])
        ),
        providers[0] if providers else None,
    )
    if provider is None:
        provider = {}
        providers.insert(0, provider)
    modality = [
        item
        for item in provider.get("modalities", ["text", "tool_use"])
        if item != "image"
    ]
    if "text" not in modality:
        modality.insert(0, "text")
    if "tool_use" not in modality:
        modality.append("tool_use")
    provider.update(
        {
            "id": f"{source_id}/{model}",
            "enable": True,
            "provider_source_id": source_id,
            "model": model,
            "modalities": modality,
            "max_context_tokens": int(
                provider.get("max_context_tokens") or 12000
            ),
        }
    )

    vision_id = _vision_provider_id(source_id)
    vision_provider = next(
        (
            item
            for item in providers
            if str(item.get("id") or "") == vision_id
        ),
        None,
    )
    if vision_provider is None:
        vision_provider = {}
        providers.append(vision_provider)
    vision_provider.update(
        {
            "id": vision_id,
            "enable": True,
            "provider_source_id": source_id,
            "model": vision_model,
            "modalities": ["text", "image", "tool_use"],
            "max_context_tokens": int(
                vision_provider.get("max_context_tokens")
                or provider.get("max_context_tokens")
                or 12000
            ),
        }
    )
    if isinstance(provider.get("custom_extra_body"), dict):
        vision_provider["custom_extra_body"] = dict(
            provider["custom_extra_body"]
        )

    provider_settings = config.setdefault("provider_settings", {})
    provider_settings["enable"] = True
    provider_settings["default_image_caption_provider_id"] = vision_id
    _save_json(config_path, config)
    if config_path.resolve() == ASTRBOT_CONFIG.resolve():
        _apply_vision_provider_id(vision_id)
    return {
        "preset": preset,
        "source_id": source_id,
        "api_base": api_base,
        "model": model,
        "vision_model": vision_model,
        "vision_provider_id": vision_id,
    }


def _apply_vision_provider_id(provider_id: str) -> None:
    group = _load_json(GROUP_CONFIG)
    if group:
        group["image_to_text_provider_id"] = provider_id
        _save_json(GROUP_CONFIG, group)

    vision_path = (
        ROOT
        / "astrbot"
        / "data"
        / "plugin_data"
        / "tafei_vision"
        / "config.json"
    )
    vision = _load_json(
        vision_path,
        {
            "enabled": True,
            "private_enabled": True,
            "group_fallback_enabled": False,
            "max_images_per_message": 4,
            "timeout_seconds": 60,
            "cache_max_entries": 300,
        },
    )
    vision["provider_id"] = provider_id
    _save_json(vision_path, vision)


def _existing_path(value) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        path = Path(raw).expanduser().resolve()
    except OSError:
        return None
    return path if path.exists() else None


def _find_astrbot_exe(current: str = "") -> str:
    candidates: list[Path] = [
        ROOT / "runtime" / "astrbot-tool" / "Scripts" / "astrbot.exe",
        ROOT / "runtime" / "astrbot-tool" / "astrbot.exe",
    ]
    existing = _existing_path(current)
    if existing is not None:
        candidates.append(existing)
    command = shutil.which("astrbot")
    if command:
        candidates.append(Path(command))
    candidates.extend(
        [
            Path.home() / ".local" / "bin" / "astrbot.exe",
            Path(os.environ.get("APPDATA", ""))
            / "uv"
            / "tools"
            / "astrbot"
            / "Scripts"
            / "astrbot.exe",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return str(current or "").strip()


def _find_napcat_paths(deploy: dict) -> tuple[str, str]:
    current_root = _existing_path(deploy.get("napcat_root"))
    bundled_root = ROOT / "runtime" / "napcat-shell"
    project_root = ROOT / "napcat"

    def has_boot(path: Path | None) -> bool:
        if path is None or not path.is_dir():
            return False
        return (path / "NapCatWinBootMain.exe").is_file() or any(
            (candidate / "NapCatWinBootMain.exe").is_file()
            for candidate in path.glob("NapCat*.Shell")
        )

    root = next(
        (
            candidate
            for candidate in (current_root, bundled_root, project_root)
            if has_boot(candidate)
        ),
        current_root or bundled_root or project_root,
    )
    candidates = []
    current_shell = _existing_path(deploy.get("napcat_shell_dir"))
    if current_shell is not None:
        candidates.append(current_shell)
    if root.is_dir():
        candidates.append(root)
        candidates.extend(root.glob("NapCat*.Shell"))

    def modified(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0

    for candidate in sorted(
        candidates,
        key=modified,
        reverse=True,
    ):
        if (candidate / "NapCatWinBootMain.exe").is_file():
            return str(root.resolve()), str(candidate.resolve())
    return (
        str(root.resolve()) if root.exists() else "",
        str(current_shell.resolve()) if current_shell is not None else "",
    )


def _ensure_runtime_state(deploy: dict) -> dict:
    deploy["install_root"] = str(ROOT)
    astrbot_root = ROOT / "astrbot"
    deploy["astrbot_root"] = str(astrbot_root.resolve())
    deploy["astrbot_exe"] = _find_astrbot_exe(
        str(deploy.get("astrbot_exe") or "")
    )
    napcat_root, napcat_shell = _find_napcat_paths(deploy)
    deploy["napcat_root"] = napcat_root
    deploy["napcat_shell_dir"] = napcat_shell
    return deploy


def _validate_runtime_state(deploy: dict) -> None:
    astrbot_exe = _existing_path(deploy.get("astrbot_exe"))
    if astrbot_exe is None or not astrbot_exe.is_file():
        raise RuntimeError(
            "未找到 AstrBot 可执行文件。请先完成 AstrBot 安装，"
            "再重新打开配置向导。"
        )
    napcat_shell = _existing_path(deploy.get("napcat_shell_dir"))
    if (
        napcat_shell is None
        or not (napcat_shell / "NapCatWinBootMain.exe").is_file()
    ):
        raise RuntimeError(
            "未找到 NapCat Shell。请先完成 NapCat 安装，"
            "再重新打开配置向导。"
        )


def apply_qq_and_groups(
    *,
    bot_qq: str,
    owner_qq: str,
    whitelist: str,
    blacklist: str,
) -> dict:
    bot_qq = validate_user_id(bot_qq, "机器人 QQ")
    owner_qq = validate_user_id(owner_qq, "主人 QQ")
    white = parse_ids(whitelist)
    black = parse_ids(blacklist)
    overlap = sorted(set(white) & set(black))
    if overlap:
        raise ValueError("以下群同时出现在黑白名单中：" + "、".join(overlap))
    for group_id in white + black:
        if not group_id.isdigit():
            raise ValueError(f"群号必须是纯数字：{group_id}")

    cmd = _load_json(ASTRBOT_CONFIG)
    if not cmd:
        raise RuntimeError("找不到 AstrBot 配置，请先完成 AstrBot 初始化")
    platform = cmd.setdefault("platform_settings", {})
    platform["enable_id_white_list"] = True
    platform["id_whitelist"] = list(dict.fromkeys([owner_qq, *white]))
    platform["wl_ignore_admin_on_group"] = False
    segmented = platform.setdefault("segmented_reply", {})
    segmented["enable"] = True
    segmented["interval_method"] = "random"
    segmented["interval"] = "0,0"
    cmd["admins_id"] = [owner_qq]
    _save_json(ASTRBOT_CONFIG, cmd)

    group = _load_json(GROUP_CONFIG)
    if group:
        group["enabled_groups"] = white
        group["poke_enabled_groups"] = white
        group["proactive_enabled_groups"] = white
        group["enable_group_chat"] = bool(white)
        group["image_message_force_reply_user_ids"] = [owner_qq]
        _save_json(GROUP_CONFIG, group)

    voice = _load_json(VOICE_CONFIG)
    if voice:
        voice["enabled_groups"] = white
        voice["owner_user_ids"] = [owner_qq]
        _save_json(VOICE_CONFIG, voice)

    deploy = _ensure_runtime_state(_load_json(DEPLOY_STATE))
    _validate_runtime_state(deploy)
    deploy["qq"] = bot_qq
    deploy["admin_qq"] = owner_qq
    deploy["group_whitelist"] = white
    deploy["group_blacklist"] = black
    _save_json(DEPLOY_STATE, deploy)
    return {
        "bot_qq": bot_qq,
        "owner_qq": owner_qq,
        "whitelist": white,
        "blacklist": black,
    }


def existing_voice_settings() -> dict:
    config = _load_json(VOICE_CONFIG)
    manifest = Path(config.get("manifest_path") or _default_voice_manifest())
    tts_config = Path(config.get("tts_config_path") or _default_tts_config())
    configured = manifest.is_file() and tts_config.is_file()
    return {
        "enabled": bool(config.get("enabled", configured)) and configured,
        "manifest_path": str(manifest) if manifest.is_file() else "",
        "tts_config_path": str(tts_config) if tts_config.is_file() else "",
    }


def import_voice_pack(
    *,
    gpt_weights: str,
    sovits_weights: str,
    reference_audio: str,
    reference_text: str,
    version: str = "v2",
    persona_id: str = "tafei",
    voice_config_path: Path = VOICE_CONFIG,
    pack_root: Path | None = None,
) -> dict:
    try:
        import yaml
    except ImportError as error:
        raise RuntimeError(
            "语音配置需要 PyYAML；请先运行 "
            "python -m pip install -r requirements-launcher.txt"
        ) from error
    gpt_path = Path(gpt_weights.strip()).expanduser().resolve()
    sovits_path = Path(sovits_weights.strip()).expanduser().resolve()
    reference_path = Path(reference_audio.strip()).expanduser().resolve()
    reference_text = reference_text.strip()
    if not gpt_path.is_file():
        raise ValueError("GPT 权重文件不存在")
    if not sovits_path.is_file():
        raise ValueError("SoVITS 权重文件不存在")
    if not reference_path.is_file():
        raise ValueError("参考音频文件不存在")
    if not reference_text:
        raise ValueError("请填写参考音频对应的文字")
    if version not in {"v1", "v2", "v2Pro", "v2ProPlus", "v3", "v4"}:
        raise ValueError("不支持的 GPT-SoVITS 版本")

    base_yaml = _voice_engine() / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
    if not base_yaml.is_file():
        raise RuntimeError("未找到 GPT-SoVITS 引擎配置")
    with base_yaml.open(encoding="utf-8") as handle:
        tts_data = yaml.safe_load(handle) or {}
    custom = dict(tts_data.get("custom") or {})
    custom.update(
        {
            "bert_base_path": "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
            "cnhuhbert_base_path": "GPT_SoVITS/pretrained_models/chinese-hubert-base",
            "device": "cuda",
            "is_half": True,
            "version": version,
            "t2s_weights_path": str(gpt_path),
            "vits_weights_path": str(sovits_path),
        }
    )
    tts_data["custom"] = custom

    signature = hashlib.sha256(
        f"{gpt_path}|{sovits_path}|{reference_path}|{reference_text}|{version}".encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    pack_root = pack_root or ROOT / "voice" / "packs"
    pack_dir = pack_root / f"tafei_{signature}"
    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = pack_dir / "manifest.json"
    tts_config_path = pack_dir / "tts_infer.yaml"

    manifest = {
        "name": persona_id,
        "engine": "gpt-sovits",
        "model_version": version,
        "gpt_model": str(gpt_path),
        "sovits_model": str(sovits_path),
        "reference_sample_rate": 32000,
        "references": [
            {
                "id": "ref_01",
                "file": reference_path.as_posix(),
                "text": reference_text,
            }
        ],
    }
    _save_json(manifest_path, manifest)
    with tts_config_path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(tts_data, handle, allow_unicode=True, sort_keys=False)

    config = _load_json(voice_config_path)
    config.update(
        {
            "enabled": True,
            "manifest_path": str(manifest_path),
            "tts_config_path": str(tts_config_path),
            "style_refs": {
                "normal": "ref_01",
                "cute": "ref_01",
                "happy": "ref_01",
                "annoyed": "ref_01",
                "soft": "ref_01",
            },
        }
    )
    config.setdefault("voice_bindings", {})[persona_id] = {
        "provider": "gpt_sovits",
        "enabled": True,
        "manifest_path": str(manifest_path),
        "tts_config_path": str(tts_config_path),
        "style_refs": dict(config["style_refs"]),
    }
    _save_json(voice_config_path, config)
    return {
        "enabled": True,
        "manifest_path": str(manifest_path),
        "tts_config_path": str(tts_config_path),
    }


def import_voice_bundle(
    archive: str | Path,
    *,
    persona_id: str = "tafei",
    voice_config_path: Path = VOICE_CONFIG,
    pack_root: Path | None = None,
) -> dict:
    """Install a signed-by-content .tafeivoice.zip as a persona voice pack."""

    try:
        import yaml
    except ImportError as error:
        raise RuntimeError(
            "语音配置需要 PyYAML；请先运行 "
            "python -m pip install -r requirements-launcher.txt"
        ) from error

    archive_path = Path(archive).expanduser().resolve()
    if not archive_path.is_file():
        raise ValueError("语音包不存在")
    if archive_path.suffix.lower() != ".zip":
        raise ValueError("语音包必须是 .tafeivoice.zip 文件")

    allowed_suffixes = {".ckpt", ".pth", ".wav", ".json", ".txt", ".md"}
    max_total = 600 * 1024 * 1024
    with zipfile.ZipFile(archive_path) as source:
        infos = source.infolist()
        total_size = sum(info.file_size for info in infos if not info.is_dir())
        if total_size > max_total:
            raise ValueError("语音包解压后超过 600MB，已拒绝导入")
        for info in infos:
            name = info.filename.replace("\\", "/")
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"语音包包含不安全路径：{name}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("语音包不能包含符号链接")
            if not info.is_dir() and path.suffix.lower() not in allowed_suffixes:
                raise ValueError(f"语音包包含不允许的文件：{name}")
        try:
            pack = json.loads(source.read("pack.json").decode("utf-8-sig"))
        except KeyError as error:
            raise ValueError("语音包缺少 pack.json") from error
        if str(pack.get("format") or "") != "tafeiyu.voice_pack":
            raise ValueError("不是塔菲鱼语音包")
        pack_persona = str(pack.get("persona_id") or "").strip()
        if pack_persona != persona_id:
            raise ValueError(
                f"语音包绑定的角色是 {pack_persona or '未知'}，"
                f"当前角色是 {persona_id}"
            )
        version = str(pack.get("model_version") or "").strip()
        if version not in {"v1", "v2", "v2Pro", "v2ProPlus", "v3", "v4"}:
            raise ValueError("语音包模型版本无效")
        gpt_member = str(pack.get("gpt_model") or "").replace("\\", "/")
        sovits_member = str(pack.get("sovits_model") or "").replace("\\", "/")
        references = pack.get("references")
        if not isinstance(references, list) or not references:
            raise ValueError("语音包没有参考音频")
        required_members = {gpt_member, sovits_member}
        reference_rows = []
        for reference in references:
            if not isinstance(reference, dict):
                raise ValueError("语音包参考音频格式无效")
            member = str(reference.get("file") or "").replace("\\", "/")
            text = str(reference.get("text") or "").strip()
            reference_id = str(reference.get("id") or "").strip()
            if not member or not text or not reference_id:
                raise ValueError("语音包参考音频缺少编号、文件或文本")
            required_members.add(member)
            reference_rows.append(
                {"id": reference_id, "file": member, "text": text}
            )
        names = {info.filename.replace("\\", "/") for info in infos}
        missing = sorted(required_members - names)
        if missing:
            raise ValueError("语音包缺少文件：" + "、".join(missing))

        hasher = hashlib.sha256()
        for member in sorted(required_members):
            hasher.update(member.encode("utf-8"))
            with source.open(member) as handle:
                for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                    hasher.update(chunk)
        signature = hasher.hexdigest()[:16]

        pack_root = pack_root or ROOT / "voice" / "packs"
        pack_root.mkdir(parents=True, exist_ok=True)
        pack_dir = pack_root / f"{persona_id}_{signature}"
        if not pack_dir.is_dir():
            staging = Path(
                tempfile.mkdtemp(prefix=f".{persona_id}-{signature[:8]}-", dir=pack_root)
            )
            try:
                for member in required_members:
                    destination = staging / Path(member)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as reader, destination.open("wb") as writer:
                        shutil.copyfileobj(reader, writer)
                staging.replace(pack_dir)
            finally:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)

    base_yaml = _voice_engine() / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
    if not base_yaml.is_file():
        raise RuntimeError("未找到 GPT-SoVITS 引擎配置")
    with base_yaml.open(encoding="utf-8") as handle:
        tts_data = yaml.safe_load(handle) or {}
    custom = dict(tts_data.get("custom") or {})
    custom.update(
        {
            "bert_base_path": "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
            "cnhuhbert_base_path": "GPT_SoVITS/pretrained_models/chinese-hubert-base",
            "device": "cuda",
            "is_half": True,
            "version": version,
            "t2s_weights_path": str(pack_dir / gpt_member),
            "vits_weights_path": str(pack_dir / sovits_member),
        }
    )
    tts_data["custom"] = custom
    tts_config_path = pack_dir / "tts_infer.yaml"
    with tts_config_path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(tts_data, handle, allow_unicode=True, sort_keys=False)

    manifest = {
        "name": str(pack.get("display_name") or persona_id),
        "engine": "gpt-sovits",
        "model_version": version,
        "gpt_model": str(pack_dir / gpt_member),
        "sovits_model": str(pack_dir / sovits_member),
        "reference_sample_rate": int(pack.get("reference_sample_rate") or 32000),
        "references": reference_rows,
    }
    manifest_path = pack_dir / "manifest.json"
    _save_json(manifest_path, manifest)

    configured_styles = pack.get("style_refs")
    default_styles = {
        "normal": reference_rows[0]["id"],
        "cute": reference_rows[0]["id"],
        "happy": reference_rows[min(8, len(reference_rows) - 1)]["id"],
        "annoyed": reference_rows[min(9, len(reference_rows) - 1)]["id"],
        "soft": reference_rows[min(14, len(reference_rows) - 1)]["id"],
    }
    style_refs = {
        str(key): str(value)
        for key, value in (
            configured_styles.items()
            if isinstance(configured_styles, dict)
            else default_styles.items()
        )
    }
    reference_ids = {row["id"] for row in reference_rows}
    style_refs = {
        key: value for key, value in style_refs.items() if value in reference_ids
    }
    for key, value in default_styles.items():
        style_refs.setdefault(key, value)

    config = _load_json(voice_config_path)
    config.update(
        {
            "enabled": True,
            "manifest_path": str(manifest_path),
            "tts_config_path": str(tts_config_path),
            "style_refs": style_refs,
        }
    )
    config.setdefault("voice_bindings", {})[persona_id] = {
        "provider": "gpt_sovits",
        "enabled": True,
        "manifest_path": str(manifest_path),
        "tts_config_path": str(tts_config_path),
        "style_refs": dict(style_refs),
    }
    _save_json(voice_config_path, config)
    return {
        "enabled": True,
        "manifest_path": str(manifest_path),
        "tts_config_path": str(tts_config_path),
        "style_refs": style_refs,
        "references": len(reference_rows),
    }


def keep_existing_voice() -> dict:
    current = existing_voice_settings()
    config = _load_json(VOICE_CONFIG)
    if current["enabled"]:
        config["enabled"] = True
        config["manifest_path"] = current["manifest_path"]
        config["tts_config_path"] = current["tts_config_path"]
    else:
        config["enabled"] = False
    _save_json(VOICE_CONFIG, config)
    return current


def disable_voice() -> dict:
    config = _load_json(VOICE_CONFIG)
    config["enabled"] = False
    _save_json(VOICE_CONFIG, config)
    return {"enabled": False}


def write_setup_complete(
    *,
    model: dict,
    qq: dict,
    voice: dict,
) -> None:
    marker = {
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project": "tafeiyu",
        "model": model,
        "qq": qq,
        "voice": voice,
    }
    _save_json(SETUP_MARKER, marker)
    FORCE_SETUP_MARKER.unlink(missing_ok=True)


def reset_setup_for_test(root: Path | None = None) -> None:
    marker = root / ".setup_complete" if root else SETUP_MARKER
    marker.unlink(missing_ok=True)
    force_marker = root / ".setup_required" if root else FORCE_SETUP_MARKER
    force_marker.write_text("reset\n", encoding="utf-8")
