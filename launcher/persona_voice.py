"""Persona switching and one-to-one voice bindings."""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from setup_core import import_voice_bundle, import_voice_pack

ROOT = Path(__file__).resolve().parent.parent
PERSONA_INDEX = ROOT / "config" / "personas.json"
VOICE_CONFIG = (
    ROOT
    / "astrbot"
    / "data"
    / "plugin_data"
    / "tafei_voice"
    / "config.json"
)


def _load(path: Path, default=None):
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {} if default is None else default


def _save(path: Path, data) -> None:
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


def persona_catalog() -> list[dict]:
    data = _load(PERSONA_INDEX, {})
    return [
        item
        for item in data.get("personas", [])
        if isinstance(item, dict) and item.get("id")
    ]


def active_persona_id() -> str:
    data = _load(PERSONA_INDEX, {})
    active = str(data.get("active") or "tafei")
    valid = {str(item["id"]) for item in persona_catalog()}
    return active if active in valid else next(iter(valid), "tafei")


def _ensure_binding(voice_config: dict, persona: dict) -> dict:
    persona_id = str(persona["id"])
    bindings = voice_config.setdefault("voice_bindings", {})
    meta = dict(persona.get("voice_binding") or {})
    binding = dict(bindings.get(persona_id) or {})
    if persona_id == "tafei" and not binding:
        binding = {
            "provider": "gpt_sovits",
            "enabled": bool(voice_config.get("enabled", False)),
            "manifest_path": str(voice_config.get("manifest_path") or ""),
            "tts_config_path": str(voice_config.get("tts_config_path") or ""),
            "style_refs": dict(voice_config.get("style_refs") or {}),
        }
    binding = {**meta, **binding}
    bindings[persona_id] = binding
    return binding


def get_voice_binding(persona_id: str) -> dict:
    persona = next(
        (item for item in persona_catalog() if str(item["id"]) == persona_id),
        None,
    )
    if persona is None:
        raise ValueError(f"未知人格：{persona_id}")
    voice_config = _load(VOICE_CONFIG)
    return _ensure_binding(voice_config, persona)


def voice_status(persona_id: str) -> dict:
    persona = next(
        (item for item in persona_catalog() if str(item["id"]) == persona_id),
        None,
    )
    if persona is None:
        return {"installed": False, "enabled": False, "detail": "人格不存在"}
    voice_config = _load(VOICE_CONFIG)
    binding = _ensure_binding(voice_config, persona)
    provider = str(binding.get("provider") or "")
    enabled = bool(binding.get("enabled", False))
    if provider == "gpt_sovits":
        manifest = Path(str(binding.get("manifest_path") or ""))
        tts_config = Path(str(binding.get("tts_config_path") or ""))
        installed = manifest.is_file() and tts_config.is_file()
        detail = "已安装" if installed else "尚未导入本地声线包"
    elif provider == "feiyu_voice_http":
        base_url = str(binding.get("base_url") or "").strip().rstrip("/")
        installed = bool(base_url)
        reachable = False
        authorized = False
        parsed = urlparse(base_url)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            request = urllib.request.Request(base_url + "/v1/capabilities")
            api_key = str(binding.get("api_key") or "").strip()
            if api_key:
                request.add_header("Authorization", "Bearer " + api_key)
            try:
                with urllib.request.urlopen(request, timeout=1.2) as response:
                    reachable = 200 <= response.status < 500
                    authorized = 200 <= response.status < 300
            except urllib.error.HTTPError as error:
                reachable = error.code in {401, 403}
                authorized = False
            except Exception:
                reachable = False
        detail = (
            "声音服务已连接"
            if installed and authorized
            else "声音服务在线，但 API Key 无效"
            if installed and reachable
            else "已配置地址，声音服务未连接"
            if installed
            else "尚未连接肥鱼声音服务"
        )
    else:
        installed = False
        detail = "未知声线类型"
    return {
        "installed": installed,
        "reachable": reachable if provider == "feiyu_voice_http" else True,
        "ready": authorized if provider == "feiyu_voice_http" else installed,
        "enabled": enabled and installed,
        "detail": detail,
        "binding": binding,
    }


def set_active_persona(persona_id: str) -> dict:
    catalog = _load(PERSONA_INDEX, {})
    personas = catalog.get("personas", [])
    persona = next(
        (item for item in personas if str(item.get("id")) == persona_id),
        None,
    )
    if persona is None:
        raise ValueError(f"未知人格：{persona_id}")
    catalog["active"] = persona_id
    _save(PERSONA_INDEX, catalog)

    voice_config = _load(VOICE_CONFIG)
    voice_config["active_persona"] = persona_id
    binding = _ensure_binding(voice_config, persona)
    _save(VOICE_CONFIG, voice_config)
    return {
        "persona": persona,
        "binding": binding,
        "status": voice_status(persona_id),
    }


def set_binding_enabled(persona_id: str, enabled: bool) -> dict:
    catalog = _load(PERSONA_INDEX, {})
    persona = next(
        (
            item
            for item in catalog.get("personas", [])
            if str(item.get("id")) == persona_id
        ),
        None,
    )
    if persona is None:
        raise ValueError(f"未知人格：{persona_id}")
    voice_config = _load(VOICE_CONFIG)
    binding = _ensure_binding(voice_config, persona)
    if enabled:
        status = voice_status(persona_id)
        if not status["installed"]:
            raise ValueError("请先完成该人格的声线安装或服务连接")
    binding["enabled"] = bool(enabled)
    # enabled 是总开关；从语音中心启用任一人格时同步打开它。
    if enabled:
        voice_config["enabled"] = True
    _save(VOICE_CONFIG, voice_config)
    return binding


def configure_feiyu_service(
    base_url: str,
    api_key: str,
    *,
    persona_id: str = "dafeiyu",
    enabled: bool = True,
) -> dict:
    base_url = base_url.strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("声音服务地址必须以 http:// 或 https:// 开头")
    voice_config = _load(VOICE_CONFIG)
    persona = next(
        (
            item
            for item in persona_catalog()
            if str(item["id"]) == str(persona_id)
        ),
        None,
    )
    if persona is None:
        raise ValueError(f"未知人格：{persona_id}")
    binding = voice_config.setdefault("voice_bindings", {}).setdefault(
        persona_id, {}
    )
    binding.update(
        {
            "provider": "feiyu_voice_http",
            "enabled": bool(enabled),
            "base_url": base_url,
            "api_key": api_key.strip(),
            "voice": "feiyu",
            "default_style": "cute",
            "style_map": {
                "normal": "cute",
                "cute": "cute",
                "happy": "cute",
                "annoyed": "cute",
                "soft": "gentle",
            },
        }
    )
    voice_config["enabled"] = True
    _save(VOICE_CONFIG, voice_config)
    return binding


def import_local_voice(
    *,
    persona_id: str,
    gpt_weights: str,
    sovits_weights: str,
    reference_audio: str,
    reference_text: str,
    version: str,
) -> dict:
    persona = next(
        (
            item
            for item in persona_catalog()
            if str(item["id"]) == str(persona_id)
        ),
        None,
    )
    if persona is None:
        raise ValueError(f"未知人格：{persona_id}")
    result = import_voice_pack(
        gpt_weights=gpt_weights,
        sovits_weights=sovits_weights,
        reference_audio=reference_audio,
        reference_text=reference_text,
        version=version,
        persona_id=persona_id,
    )
    voice_config = _load(VOICE_CONFIG)
    binding = voice_config.setdefault("voice_bindings", {}).setdefault(
        persona_id, {}
    )
    binding.update(
        {
            "provider": "gpt_sovits",
            "enabled": True,
            "manifest_path": result["manifest_path"],
            "tts_config_path": result["tts_config_path"],
        }
    )
    voice_config["enabled"] = True
    _save(VOICE_CONFIG, voice_config)
    return result


def import_voice_bundle_file(
    archive_path: str,
    *,
    persona_id: str,
) -> dict:
    persona = next(
        (
            item
            for item in persona_catalog()
            if str(item["id"]) == str(persona_id)
        ),
        None,
    )
    if persona is None:
        raise ValueError(f"未知人格：{persona_id}")
    return import_voice_bundle(
        archive_path,
        persona_id=persona_id,
    )


def import_tafei_voice(**kwargs) -> dict:
    """Backward-compatible convenience wrapper for the default persona."""
    return import_local_voice(persona_id="tafei", **kwargs)


def open_url(url: str) -> None:
    url = url.strip()
    if not url:
        raise ValueError("该项目没有公开下载地址")
    webbrowser.open(url)


def open_guide(value: str) -> None:
    value = value.strip()
    if not value:
        raise ValueError("尚未配置教程")
    if value.startswith(("http://", "https://")):
        webbrowser.open(value)
        return
    path = ROOT / value.replace("/", os.sep)
    if not path.exists():
        raise ValueError(f"教程文件不存在：{path}")
    os.startfile(str(path))
