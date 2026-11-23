import asyncio
import hashlib
import io
import json
import os
import random
import re
import socket
import subprocess
import time
import unicodedata
import wave
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.star.filter.command import GreedyStr

PLUGIN_NAME = "tafei_voice"
DEFAULT_API = "http://127.0.0.1:9880"
MAX_CACHE_FILES = 200
FEIYU_JOB_TIMEOUT = 180
MAX_AUDIO_BYTES = 128 * 1024 * 1024
MAX_VOICE_SEGMENTS = 2
PENDING_VOICE_EXTRA = "_tafei_voice_pending_prefetch"
DEFAULT_PUNCTUATION_PAUSES_MS = {
    "comma": 140,
    "ellipsis": 520,
    "exclamation": 260,
    "question": 320,
    "period": 420,
    "semicolon": 240,
    "colon": 180,
    "default": 200,
}


def _data_dir() -> str:
    root = os.environ.get("ASTRBOT_ROOT") or ""
    if root:
        return os.path.join(root, "data")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "data")


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(_data_dir()))


def _voice_root() -> str:
    configured = os.environ.get("TAFEI_VOICE_ROOT")
    if configured:
        return configured
    root = _project_root()
    candidates = [
        os.path.join(root, "voice", "GPT-SoVITS-run"),
        os.path.join(root, "runtime", "GPT-SoVITS-run"),
    ]
    return next((path for path in candidates if os.path.isdir(path)), candidates[0])


def _load_json(path: str) -> dict:
    try:
        with io.open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _unique_ids(values) -> list[str]:
    result = []
    seen = set()
    if isinstance(values, (str, int)):
        values = [values]
    elif not isinstance(values, (list, tuple, set)):
        values = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _deployment_defaults() -> tuple[list[str], list[str]]:
    root = _project_root()
    deploy = _load_json(os.path.join(root, "deploy_state.json"))
    group = _load_json(
        os.path.join(
            root,
            "astrbot",
            "data",
            "config",
            "astrbot_plugin_group_chat_plus_config.json",
        )
    )
    astrbot = _load_json(
        os.path.join(root, "astrbot", "data", "cmd_config.json")
    )
    groups = deploy.get("group_whitelist")
    if not isinstance(groups, list):
        groups = group.get("enabled_groups", [])
    admin_ids = _unique_ids(astrbot.get("admins_id"))
    return (
        _unique_ids(groups),
        _unique_ids(
            [
                deploy.get("admin_qq"),
                *admin_ids,
            ]
        ),
    )


def _plain_text(chain: list) -> str:
    parts = []
    for segment in chain:
        text = getattr(segment, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip()


def _speech_text(text: str) -> str:
    """Return text that the local GPT-SoVITS service can safely synthesize."""
    text = re.sub(r"```[\s\S]*?```", "", text or "")
    text = re.sub(r"https?://\S+", "", text)
    text = "".join(
        char
        for char in text
        if char not in "\ufe0f\u200d"
        and ord(char) <= 0xFFFF
        and unicodedata.category(char) not in {"So", "Sk", "Cs", "Co", "Cn"}
    )
    return re.sub(r"\s+", " ", text).strip()


def _split_voice_segments(text: str, max_segments: int = 2) -> list[str]:
    """Split a reply at natural sentence boundaries, never at commas alone."""

    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    boundary = re.compile(
        r"(?<=[。！？!?；;…~])|(?<=[^\w\s])\s+(?=[\u4e00-\u9fff])"
    )
    parts = [part.strip() for part in boundary.split(cleaned) if part.strip()]
    if not parts:
        return [cleaned]

    merged = []
    for part in parts:
        visible = re.sub(r"[\W_]+", "", part, flags=re.UNICODE)
        if merged and len(visible) < 2:
            merged[-1] += part
        else:
            merged.append(part)

    limit = max(1, min(MAX_VOICE_SEGMENTS, int(max_segments)))
    if len(merged) > limit:
        merged = [*merged[: limit - 1], "".join(merged[limit - 1 :])]
    return merged


def _normalize_pause_settings(value) -> dict[str, int]:
    settings = dict(DEFAULT_PUNCTUATION_PAUSES_MS)
    if isinstance(value, dict):
        for key in settings:
            if key not in value:
                continue
            try:
                settings[key] = max(0, min(2000, int(value[key])))
            except (TypeError, ValueError):
                continue
    return settings


def _pause_after_text(text: str, pauses: dict[str, int]) -> int:
    tail = (text or "").rstrip()
    while tail and (
        unicodedata.category(tail[-1]) in {"So", "Sk"}
        or tail[-1] in "\ufe0f\u200d"
    ):
        tail = tail[:-1].rstrip()
    tail = re.sub(r"[\s\"'“”‘’）)\]】》]+$", "", tail)
    if re.search(r"(?:…+|\.{3,})$", tail):
        kind = "ellipsis"
    elif tail.endswith(("！", "!")):
        kind = "exclamation"
    elif tail.endswith(("？", "?")):
        kind = "question"
    elif tail.endswith(("，", ",", "、")):
        kind = "comma"
    elif tail.endswith(("；", ";")):
        kind = "semicolon"
    elif tail.endswith(("：", ":")):
        kind = "colon"
    elif tail.endswith("。"):
        kind = "period"
    else:
        return int(pauses.get("default", 0))
    return int(pauses.get(kind, pauses.get("default", 0)))


def _split_pause_clauses(text: str) -> list[str]:
    """Keep punctuation with each clause so every pause kind stays distinct."""

    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    clauses = re.findall(
        r".+?(?:[，,、；;：:！!？?。…]+|$)",
        cleaned,
        flags=re.DOTALL,
    )
    return [clause.strip() for clause in clauses if clause.strip()]


def _concat_wav_with_pauses(
    audio_paths: list[str],
    pause_ms: list[int],
    output_path: str,
) -> str:
    """Join WAV clauses with deterministic silence instead of random waits."""

    if not audio_paths:
        raise ValueError("no audio files to concatenate")
    if len(audio_paths) == 1:
        return audio_paths[0]
    if len(pause_ms) < len(audio_paths):
        pause_ms = [*pause_ms, *([0] * (len(audio_paths) - len(pause_ms)))]

    with wave.open(audio_paths[0], "rb") as first:
        expected = (
            first.getnchannels(),
            first.getsampwidth(),
            first.getframerate(),
            first.getcomptype(),
        )

    temp_path = output_path + ".tmp"
    try:
        with wave.open(temp_path, "wb") as output:
            output.setnchannels(expected[0])
            output.setsampwidth(expected[1])
            output.setframerate(expected[2])
            output.setcomptype(expected[3], "not compressed")
            for index, path in enumerate(audio_paths):
                with wave.open(path, "rb") as source:
                    current = (
                        source.getnchannels(),
                        source.getsampwidth(),
                        source.getframerate(),
                        source.getcomptype(),
                    )
                    if current != expected:
                        raise ValueError("TTS WAV formats do not match")
                    output.writeframes(source.readframes(source.getnframes()))
                if index >= len(audio_paths) - 1:
                    continue
                silence_frames = int(
                    expected[2]
                    * max(0, int(pause_ms[index]))
                    / 1000
                )
                silence = b"\x00" * (
                    silence_frames * expected[0] * expected[1]
                )
                output.writeframes(silence)
        os.replace(temp_path, output_path)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
    return output_path


def _pick_style(text: str) -> str:
    if re.search(r"生气|讨厌|烦|气死|不理你|滚|笨蛋|坏蛋|才不要", text):
        return "annoyed"
    if re.search(
        r"累|难过|哭|晚安|想你|陪着|抱抱|心疼|辛苦|乖|别怕|没事的",
        text,
    ):
        return "soft"
    if re.search(
        r"哈哈|嘿嘿|好耶|开心|太棒|笑死|喜欢|好玩|冲|赢了|太好了",
        text,
    ):
        return "happy"
    if re.search(r"喵|呀|诶|才不|哼哼|可爱|贴贴", text):
        return "cute"
    return "cute"


class TafeiVoice(star.Star):
    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.dir = os.path.join(_data_dir(), "plugin_data", PLUGIN_NAME)
        os.makedirs(self.dir, exist_ok=True)
        self.cache_dir = os.path.join(self.dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.config_path = os.path.join(self.dir, "config.json")
        self.config = self._load_config()
        self.active_persona_id = "tafei"
        self.active_persona_name = "塔菲"
        self.binding = {}
        self.manifest_path = (
            str(self.config.get("manifest_path") or "").strip()
            or os.environ.get("TAFEI_VOICE_MANIFEST")
            or os.path.join(_voice_root(), "voices", "tafei_v2", "manifest.json")
        )
        self.tts_config_path = (
            str(self.config.get("tts_config_path") or "").strip()
            or os.path.join(
                _voice_root(),
                "GPT_SoVITS",
                "configs",
                "tts_infer.yaml",
            )
        )
        self._refresh_binding()
        self._ensure_tts_service()

    def _load_config(self) -> dict:
        default_groups, default_owners = _deployment_defaults()
        defaults = {
            "enabled": True,
            "active_persona": "tafei",
            "auto_probability": 0.15,
            "max_chars": 60,
            "force_max_chars": 300,
            "sentence_split_enabled": True,
            "max_voice_segments": MAX_VOICE_SEGMENTS,
            "punctuation_pauses_ms": DEFAULT_PUNCTUATION_PAUSES_MS,
            "tts_api": os.environ.get("TAFEI_TTS_API", DEFAULT_API).rstrip("/"),
            "manifest_path": "",
            "tts_config_path": "",
            "enabled_groups": default_groups,
            "owner_user_ids": default_owners,
            "force_voice_keywords": [
                "说话",
                "你说",
                "塔菲说",
                "塔菲再说",
                "发语音",
                "语音回复",
                "用语音",
                "说一句",
                "说句话",
                "说两句",
                "念出来",
                "读一下",
                "说给我听",
                "出声",
                "听听声音",
                "唱一句",
                "再说一遍",
                "再讲一遍",
                "再念一遍",
                "重说一遍",
                "重讲一遍",
                "没听到",
                "没听见",
                "没声音",
                "语音呢",
            ],
            "style_refs": {
                "normal": "ref_01",
                "cute": "ref_01",
                "happy": "ref_09",
                "annoyed": "ref_10",
                "soft": "ref_15",
            },
            "voice_bindings": {},
        }
        try:
            with io.open(self.config_path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                defaults.update(data)
        except (OSError, ValueError):
            pass
        try:
            defaults["auto_probability"] = max(
                0.0, min(1.0, float(defaults["auto_probability"]))
            )
        except (TypeError, ValueError):
            defaults["auto_probability"] = 0.15
        defaults["enabled_groups"] = [
            str(group) for group in defaults.get("enabled_groups", [])
        ]
        defaults["owner_user_ids"] = _unique_ids(
            [*default_owners, defaults.get("owner_user_ids")]
        )
        defaults["force_voice_keywords"] = [
            str(keyword)
            for keyword in defaults.get("force_voice_keywords", [])
            if str(keyword).strip()
        ]
        defaults["punctuation_pauses_ms"] = _normalize_pause_settings(
            defaults.get("punctuation_pauses_ms")
        )
        return defaults

    def _save_config(self) -> None:
        with io.open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle, ensure_ascii=False, indent=2)

    def _refresh_binding(self) -> dict:
        self.config = self._load_config()
        catalog_path = os.path.join(_project_root(), "config", "personas.json")
        persona_id = str(self.config.get("active_persona") or "tafei")
        persona_name = persona_id
        persona_voice = {}
        try:
            with io.open(catalog_path, encoding="utf-8-sig") as handle:
                catalog = json.load(handle)
            persona_id = str(catalog.get("active") or persona_id)
            persona = next(
                (
                    item
                    for item in catalog.get("personas", [])
                    if str(item.get("id")) == persona_id
                ),
                None,
            )
            if persona:
                persona_name = str(persona.get("display_name") or persona_id)
                if isinstance(persona.get("voice_binding"), dict):
                    persona_voice = dict(persona["voice_binding"])
        except (OSError, ValueError):
            pass
        self.active_persona_id = persona_id
        self.active_persona_name = persona_name
        binding = (self.config.get("voice_bindings") or {}).get(persona_id, {})
        if not binding and persona_id == "tafei":
            # Backwards compatibility for the original single-persona config.
            binding = {
                "provider": "gpt_sovits",
                "enabled": bool(self.config.get("enabled", True)),
                "manifest_path": self.config.get("manifest_path", ""),
                "tts_config_path": self.config.get("tts_config_path", ""),
                "style_refs": self.config.get("style_refs", {}),
            }
        binding = {**persona_voice, **binding}
        self.binding = binding
        # Never retain a previous persona's local model paths.
        self.manifest_path = ""
        self.tts_config_path = ""
        configured_manifest = str(binding.get("manifest_path") or "").strip()
        configured_tts = str(binding.get("tts_config_path") or "").strip()
        if configured_manifest:
            self.manifest_path = configured_manifest
        if configured_tts:
            self.tts_config_path = configured_tts
        return binding

    def _voice_enabled(self) -> bool:
        self._refresh_binding()
        if not self.config.get("enabled", True) or not self.binding.get(
            "enabled",
            False,
        ):
            return False
        provider = str(self.binding.get("provider") or "")
        if provider == "gpt_sovits":
            return bool(
                self.manifest_path
                and self.tts_config_path
                and os.path.isfile(self.manifest_path)
                and os.path.isfile(self.tts_config_path)
            )
        if provider == "feiyu_voice_http":
            return bool(str(self.binding.get("base_url") or "").strip())
        return False

    def _load_manifest(self) -> dict:
        if not self.manifest_path or not os.path.isfile(self.manifest_path):
            raise RuntimeError("当前人格的本地声线清单不存在")
        with io.open(self.manifest_path, encoding="utf-8") as handle:
            return json.load(handle)

    def _in_enabled_group(self, event: AstrMessageEvent) -> bool:
        group_id = str(event.get_group_id() or "")
        groups = self.config.get("enabled_groups", [])
        return bool(groups) and group_id in groups

    def _is_owner_private_chat(self, event: AstrMessageEvent) -> bool:
        if not event.is_private_chat():
            return False
        owners = set(self.config.get("owner_user_ids", []))
        if not owners:
            return False
        candidates = [
            event.get_sender_id(),
            getattr(event, "get_session_id", lambda: "")(),
        ]
        message_obj = getattr(event, "message_obj", None)
        sender = getattr(message_obj, "sender", None)
        if sender is not None:
            candidates.append(getattr(sender, "user_id", None))
        values = {
            str(value or "").strip()
            for value in candidates
            if str(value or "").strip()
        }
        for owner in owners:
            for value in values:
                if value == owner or re.search(
                    rf"(?<!\d){re.escape(owner)}(?!\d)",
                    value,
                ):
                    return True
        return False

    @staticmethod
    def _gpt_cache_key(
        *,
        persona_id: str,
        manifest: dict,
        reference: dict,
        style: str,
        text: str,
        manifest_path: str = "",
        reference_path: str = "",
    ) -> str:
        def file_state(path: str):
            if not path:
                return None
            absolute = os.path.abspath(path)
            try:
                return [
                    absolute,
                    os.path.getsize(absolute),
                    os.path.getmtime(absolute),
                ]
            except OSError:
                return [absolute]

        model_states = []
        for value in (
            manifest.get("gpt_model"),
            manifest.get("sovits_model"),
        ):
            if not value:
                continue
            path = str(value)
            if not os.path.isabs(path):
                path = os.path.join(_voice_root(), path)
            model_states.append(file_state(path))
        identity = {
            "provider": "gpt_sovits",
            "persona": persona_id,
            "gpt_model": manifest.get("gpt_model"),
            "sovits_model": manifest.get("sovits_model"),
            "models": model_states,
            "manifest": file_state(manifest_path),
            "reference_id": reference.get("id"),
            "reference_file": reference.get("file"),
            "reference_text": reference.get("text"),
            "reference_audio": file_state(reference_path),
            "style": style,
            "text": text,
        }
        return hashlib.sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

    def _is_voice_requested(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text or "")
        return any(
            keyword in normalized
            for keyword in self.config.get("force_voice_keywords", [])
        )

    def _cleanup_cache(self) -> None:
        try:
            files = sorted(
                Path(self.cache_dir).glob("*.wav"),
                key=lambda path: path.stat().st_mtime,
            )
            for path in files[:-MAX_CACHE_FILES]:
                path.unlink(missing_ok=True)
        except Exception:
            pass

    def _tts_service_up(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", 9880), timeout=0.5):
                return True
        except OSError:
            return False

    def _ensure_tts_service(self) -> None:
        if (
            self.binding.get("provider") != "gpt_sovits"
            or not self.binding.get("enabled", False)
        ):
            return
        if self._tts_service_up():
            return
        voice_root = _voice_root()
        python_exe = os.path.join(voice_root, ".venv", "Scripts", "python.exe")
        api_script = os.path.join(voice_root, "api_v2.py")
        config_path = self.tts_config_path
        if not all(os.path.exists(path) for path in (python_exe, api_script, config_path)):
            return
        log_dir = os.path.join(voice_root, "logs")
        os.makedirs(log_dir, exist_ok=True)
        output = open(os.path.join(log_dir, "api.plugin.log"), "ab")
        try:
            env = os.environ.copy()
            env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
            subprocess.Popen(
                [
                    python_exe,
                    api_script,
                    "-a",
                    "127.0.0.1",
                    "-p",
                    "9880",
                    "-c",
                    config_path,
                ],
                cwd=voice_root,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=0x08000000,
            )
            logger.info("tafei_voice: started local TTS service")
        except Exception as error:
            logger.warning(f"tafei_voice: failed to start TTS service: {error}")
        finally:
            output.close()

    async def _synthesize_provider(
        self,
        text: str,
        style: str,
    ) -> str:
        self._refresh_binding()
        provider = str(self.binding.get("provider") or "")
        if provider == "feiyu_voice_http":
            return await self._synthesize_feiyu(text, style)
        if provider != "gpt_sovits":
            raise RuntimeError(f"{self.active_persona_name}没有绑定可用的声线")
        return await self._synthesize_gpt_sovits(text, style)

    async def _synthesize(self, text: str, style: str | None = None) -> str:
        self._refresh_binding()
        style = style or _pick_style(text)
        pauses = _normalize_pause_settings(
            self.config.get("punctuation_pauses_ms")
        )
        clauses = []
        for clause in _split_pause_clauses(text):
            spoken = _speech_text(clause)
            if spoken:
                clauses.append(
                    (spoken, _pause_after_text(clause, pauses))
                )
        if not clauses:
            raise RuntimeError("这段内容没有可朗读的文字")
        if len(clauses) == 1:
            return await self._synthesize_provider(clauses[0][0], style)

        audio_paths = []
        for spoken, _pause in clauses:
            audio_paths.append(
                await self._synthesize_provider(spoken, style)
            )
        identity = {
            "provider": self.binding.get("provider"),
            "persona": self.active_persona_id,
            "style": style,
            "text": text,
            "pauses": pauses,
            "parts": [
                [
                    os.path.basename(path),
                    os.path.getsize(path),
                    os.path.getmtime(path),
                ]
                for path in audio_paths
            ],
        }
        cache_key = hashlib.sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        output_path = os.path.join(self.cache_dir, f"{cache_key}.wav")
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            return output_path
        pause_ms = [pause for _spoken, pause in clauses]
        return await asyncio.to_thread(
            _concat_wav_with_pauses,
            audio_paths,
            pause_ms,
            output_path,
        )

    async def _synthesize_gpt_sovits(
        self, text: str, style: str | None = None
    ) -> str:
        manifest = self._load_manifest()
        style = style or _pick_style(text)
        ref_id = self.binding.get("style_refs", {}).get(style, "ref_06")
        ref_entry = next(
            (item for item in manifest.get("references", []) if item["id"] == ref_id),
            None,
        )
        if ref_entry is None:
            raise RuntimeError(f"reference {ref_id} not found")

        base_dir = os.path.dirname(self.manifest_path)
        ref_audio = os.path.join(base_dir, ref_entry["file"].replace("/", os.sep))
        cache_key = self._gpt_cache_key(
            persona_id=self.active_persona_id,
            manifest=manifest,
            reference=ref_entry,
            style=style,
            text=text,
            manifest_path=self.manifest_path,
            reference_path=ref_audio,
        )
        output_path = os.path.join(self.cache_dir, f"{cache_key}.wav")
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            return output_path

        payload = {
            "text": text,
            "text_lang": "zh",
            "ref_audio_path": ref_audio,
            "prompt_lang": "zh",
            "prompt_text": ref_entry["text"],
            "top_k": 15,
            "top_p": 1.0,
            "temperature": 0.8,
            "text_split_method": "cut5",
            "batch_size": 1,
            "speed_factor": 1.0,
            "seed": 2026,
            "media_type": "wav",
            "streaming_mode": False,
            "parallel_infer": False,
            "repetition_penalty": 1.35,
        }

        def request_tts():
            return requests.post(
                f"{self.config['tts_api'].rstrip('/')}/tts",
                json=payload,
                timeout=40,
            )

        try:
            response = await asyncio.to_thread(request_tts)
        except requests.ConnectionError:
            self._ensure_tts_service()
            for _ in range(20):
                await asyncio.sleep(1)
                try:
                    response = await asyncio.to_thread(request_tts)
                    break
                except requests.ConnectionError:
                    continue
            else:
                raise RuntimeError("local TTS service is not reachable")
        if response.status_code != 200:
            raise RuntimeError(
                f"TTS HTTP {response.status_code}: {response.text[:300]}"
            )
        if not response.headers.get("content-type", "").startswith("audio"):
            raise RuntimeError("TTS response is not audio")
        audio = response.content
        if len(audio) <= 44 or not audio.startswith(b"RIFF"):
            raise RuntimeError("TTS response is not a valid WAV file")
        temp_path = output_path + ".tmp"
        with open(temp_path, "wb") as handle:
            handle.write(audio)
        os.replace(temp_path, output_path)
        self._cleanup_cache()
        return output_path

    async def _synthesize_feiyu(
        self, text: str, style: str | None = None
    ) -> str:
        base_url = str(self.binding.get("base_url") or "").strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise RuntimeError("肥鱼声音服务地址无效")
        style = style or _pick_style(text)
        style_map = self.binding.get("style_map") or {}
        service_style = str(
            style_map.get(
                style,
                self.binding.get("default_style") or "cute",
            )
        )
        voice = str(self.binding.get("voice") or "feiyu")
        api_key = str(self.binding.get("api_key") or "").strip()
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = "Bearer " + api_key

        cache_key = hashlib.sha256(
            (
                f"feiyu|{self.active_persona_id}|{voice}|"
                f"{service_style}|{text}"
            ).encode("utf-8")
        ).hexdigest()
        output_path = os.path.join(self.cache_dir, f"{cache_key}.wav")
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            return output_path

        payload = {"voice": voice, "text": text, "style": service_style}

        def submit_job():
            response = requests.post(
                f"{base_url}/v1/speech",
                json=payload,
                headers=headers,
                timeout=40,
            )
            if not response.ok:
                detail = response.text[:300]
                try:
                    detail = str(response.json().get("detail") or detail)
                except ValueError:
                    pass
                raise RuntimeError(
                    f"肥鱼声音服务 HTTP {response.status_code}: {detail}"
                )
            data = response.json()
            job_id = str(data.get("id") or data.get("job_id") or "")
            if not re.fullmatch(r"[0-9a-f]{32}", job_id):
                raise RuntimeError("肥鱼声音服务没有返回有效任务编号")
            return job_id

        try:
            job_id = await asyncio.to_thread(submit_job)
        except requests.ConnectionError as error:
            raise RuntimeError("无法连接肥鱼声音服务，请检查地址和服务是否启动") from error

        deadline = time.monotonic() + FEIYU_JOB_TIMEOUT
        job = {}
        while time.monotonic() < deadline:
            await asyncio.sleep(1.5)

            def get_job():
                response = requests.get(
                    f"{base_url}/v1/jobs/{job_id}",
                    headers=headers,
                    timeout=20,
                )
                if not response.ok:
                    raise RuntimeError(
                        f"肥鱼任务查询失败 HTTP {response.status_code}"
                    )
                return response.json()

            try:
                job = await asyncio.to_thread(get_job)
            except requests.ConnectionError as error:
                raise RuntimeError("肥鱼声音服务在生成过程中断开连接") from error
            status = str(job.get("status") or "")
            if status == "success":
                break
            if status in {"failed", "interrupted"}:
                raise RuntimeError(
                    f"肥鱼语音生成失败：{job.get('error') or status}"
                )
        else:
            raise RuntimeError("肥鱼语音生成超时，请检查声音服务日志")

        raw_audio_url = str(job.get("audio_url") or f"/v1/jobs/{job_id}/audio")
        audio_url = urljoin(base_url + "/", raw_audio_url)
        base_origin = urlsplit(base_url)
        audio_origin = urlsplit(audio_url)
        if (
            audio_origin.scheme,
            audio_origin.hostname,
            audio_origin.port,
        ) != (
            base_origin.scheme,
            base_origin.hostname,
            base_origin.port,
        ):
            raise RuntimeError("肥鱼声音服务返回了跨域音频地址，已拒绝下载")

        def download_audio():
            with requests.get(
                audio_url,
                headers=headers,
                timeout=90,
                allow_redirects=False,
                stream=True,
            ) as response:
                if not response.ok:
                    raise RuntimeError(
                        f"肥鱼语音下载失败 HTTP {response.status_code}"
                    )
                declared = int(response.headers.get("Content-Length") or 0)
                if declared > MAX_AUDIO_BYTES:
                    raise RuntimeError("肥鱼声音服务返回的 WAV 文件过大")
                audio = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    audio.extend(chunk)
                    if len(audio) > MAX_AUDIO_BYTES:
                        raise RuntimeError("肥鱼声音服务返回的 WAV 文件过大")
            if len(audio) < 44 or bytes(audio[:4]) != b"RIFF":
                raise RuntimeError("肥鱼声音服务返回的 WAV 无效")
            return bytes(audio)

        try:
            audio = await asyncio.to_thread(download_audio)
        except requests.ConnectionError as error:
            raise RuntimeError("无法下载肥鱼生成的语音") from error
        temp_path = output_path + ".tmp"
        with open(temp_path, "wb") as handle:
            handle.write(audio)
        os.replace(temp_path, output_path)
        self._cleanup_cache()
        return output_path

    @filter.on_decorating_result()
    async def add_voice(self, event: AstrMessageEvent) -> None:
        if not self._voice_enabled():
            return
        owner_private = self._is_owner_private_chat(event)
        if event.is_private_chat() and not owner_private:
            return
        if not event.is_private_chat() and not self._in_enabled_group(event):
            return
        if event.get_platform_name() != "aiocqhttp":
            return
        result = event.get_result()
        chain = getattr(result, "chain", None) if result else None
        if not chain or any(isinstance(seg, (Image, Record)) for seg in chain):
            return
        text = _plain_text(chain)
        force_voice = self._is_voice_requested(
            str(getattr(event, "message_str", "") or "")
        )
        max_chars = (
            int(self.config.get("force_max_chars", 300))
            if force_voice
            else (
                200 if owner_private else int(self.config.get("max_chars", 60))
            )
        )
        logger.debug(
            "tafei_voice route: private=%s owner=%s force=%s chars=%s "
            "limit=%s sender=%s",
            event.is_private_chat(),
            owner_private,
            force_voice,
            len(text),
            max_chars,
            event.get_sender_id(),
        )
        if not text or len(text) > max_chars:
            return
        if (
            not force_voice
            and (
                "\n" in text
                or "```" in text
                or "http://" in text
                or "https://" in text
            )
        ):
            return
        if (
            not owner_private
            and not force_voice
            and random.random()
            >= float(self.config.get("auto_probability", 0.15))
        ):
            return
        try:
            split_enabled = bool(
                self.config.get("sentence_split_enabled", True)
            )
            try:
                configured_segments = int(
                    self.config.get("max_voice_segments", MAX_VOICE_SEGMENTS)
                )
            except (TypeError, ValueError):
                configured_segments = MAX_VOICE_SEGMENTS
            allowed_segments = (
                configured_segments
                if owner_private or force_voice
                else 1
            )
            segments = (
                _split_voice_segments(text, allowed_segments)
                if split_enabled
                else [text]
            )
            speech_segments = []
            for segment in segments:
                spoken = _speech_text(segment)
                if spoken:
                    speech_segments.append(
                        (segment, spoken, _pick_style(segment))
                    )
            if not speech_segments:
                return
            first_text, first_spoken, first_style = speech_segments[0]
            first_audio = await self._synthesize(
                first_spoken,
                style=first_style,
            )
            prefix = [
                segment for segment in chain if not isinstance(segment, Plain)
            ]
            first_pair = [
                Plain(first_text),
                Record.fromFileSystem(first_audio, text=first_text),
            ]
            if len(speech_segments) > 1:
                second_text, second_spoken, second_style = speech_segments[1]
                background_task = asyncio.create_task(
                    self._synthesize(second_spoken, style=second_style)
                )
                pauses = _normalize_pause_settings(
                    self.config.get("punctuation_pauses_ms")
                )
                event.set_extra(
                    PENDING_VOICE_EXTRA,
                    {
                        "task": background_task,
                        "text": second_text,
                        "style": second_style,
                        "pause_after_ms": _pause_after_text(
                            first_text,
                            pauses,
                        ),
                    },
                )
            chain[:] = [*prefix, *first_pair]
            logger.info(
                "tafei_voice: first voice ready style=%s file=%s; "
                "second_prefetched=%s",
                first_style,
                os.path.basename(first_audio),
                len(speech_segments) > 1,
            )
        except Exception as error:
            logger.warning(f"tafei_voice: synthesis skipped: {error}")

    @filter.after_message_sent()
    async def send_prefetched_voice(self, event: AstrMessageEvent) -> None:
        pending = event.get_extra(PENDING_VOICE_EXTRA, None)
        if not isinstance(pending, dict):
            return
        event.set_extra(PENDING_VOICE_EXTRA, None)
        task = pending.get("task")
        text = str(pending.get("text") or "")
        if not text or task is None:
            return
        try:
            audio_path = await task
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning(
                "tafei_voice: prefetched second voice failed: %s",
                error,
            )
            await event.send(MessageChain([Plain(text)]))
            return

        pause_ms = max(0, int(pending.get("pause_after_ms") or 0))
        if pause_ms:
            await asyncio.sleep(pause_ms / 1000)
        await event.send(
            MessageChain(
                [
                    Plain(text),
                    Record.fromFileSystem(audio_path, text=text),
                ]
            )
        )
        logger.info(
            "tafei_voice: sent prefetched second voice style=%s file=%s",
            pending.get("style"),
            os.path.basename(audio_path),
        )

    @filter.on_llm_request()
    async def inject_voice_capability(self, event: AstrMessageEvent, req) -> None:
        if not self._voice_enabled():
            return
        owner_private = self._is_owner_private_chat(event)
        if event.is_private_chat() and not owner_private:
            return
        if not event.is_private_chat() and not self._in_enabled_group(event):
            return
        marker = "【角色语音能力】"
        system_prompt = req.system_prompt or ""
        if marker in system_prompt:
            return
        req.system_prompt = system_prompt + (
            "\n\n【角色语音能力】"
            f"你当前使用的是{self.active_persona_name}绑定的"
            f"{self.binding.get('display_name', '独立声线')}。"
            "你可以发送真实语音消息。主人私聊时每条回复会附带语音。"
            "系统会按自然句拆分语音，每条语音只对应一段文字，通常最多两条。"
            "群聊中如果群友明确要求你发语音、说一句、念出来、读一下、"
            "说给他听、出声或唱一句，就自然答应并用口头化方式回答；"
            "系统会自动把你的回复合成为当前人格绑定的声线。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_voice")
    async def tf_voice(self, event: AstrMessageEvent, text: GreedyStr) -> None:
        self._refresh_binding()
        content = str(text).strip()
        if not content:
            yield event.plain_result("用法：/tf_voice 你想让塔菲说的话")
            return
        try:
            spoken_text = _speech_text(content[:120])
            if not spoken_text:
                yield event.plain_result("这段内容没有可朗读的文字")
                return
            audio_path = await self._synthesize(spoken_text)
            yield event.chain_result(
                [Plain(content[:120]), Record.fromFileSystem(audio_path, text=content[:120])]
            )
        except Exception as error:
            yield event.plain_result(f"语音生成失败：{error}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_voice_on")
    async def tf_voice_on(self, event: AstrMessageEvent) -> None:
        self._refresh_binding()
        self.config.setdefault("voice_bindings", {}).setdefault(
            self.active_persona_id, self.binding
        )["enabled"] = True
        self._save_config()
        yield event.plain_result("自动语音已开启")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_voice_off")
    async def tf_voice_off(self, event: AstrMessageEvent) -> None:
        self._refresh_binding()
        self.config.setdefault("voice_bindings", {}).setdefault(
            self.active_persona_id, self.binding
        )["enabled"] = False
        self._save_config()
        yield event.plain_result("自动语音已关闭")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("tf_voice_p")
    async def tf_voice_p(self, event: AstrMessageEvent, value: str = "") -> None:
        try:
            probability = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            yield event.plain_result(
                f"当前语音概率 {self.config['auto_probability']}，用法 /tf_voice_p 0.15"
            )
            return
        self.config["auto_probability"] = probability
        self._save_config()
        yield event.plain_result(f"自动语音概率已设为 {probability:.2f}")
