"""Start the tafeiyu components that are not already running."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".bot_runtime"
sys.path.insert(0, str(RUNTIME))

import bot_manager as manager  # noqa: E402

DASH_PORT = 6185
WS_PORT = 6199
TTS_PORT = 9880
WATCHDOG_LOCK_PORT = 47654
LAUNCH_LOCK_PORT = 47656
WATCHDOG_HEARTBEAT = RUNTIME / "watchdog.heartbeat"
VOICE_CONFIG = (
    ROOT / "astrbot" / "data" / "plugin_data" / "tafei_voice" / "config.json"
)
PERSONA_CONFIG = ROOT / "config" / "personas.json"
NO_WINDOW = 0x08000000
NEW_CONSOLE = 0x00000010

Progress = Callable[[str, object], None]


def _voice_engine_root() -> Path:
    candidates = [
        ROOT / "voice" / "GPT-SoVITS-run",
        ROOT / "runtime" / "GPT-SoVITS-run",
    ]
    return next((path for path in candidates if path.is_dir()), candidates[0])


def _port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _acquire_launch_lock():
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", LAUNCH_LOCK_PORT))
        lock.listen(1)
        return lock
    except OSError:
        lock.close()
        return None


def _http_ready(port: int, path: str = "/") -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}", timeout=1.5
        ) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def _remote_service_ready(binding: dict) -> bool:
    base_url = str(binding.get("base_url") or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    request = urllib.request.Request(base_url + "/v1/capabilities")
    api_key = str(binding.get("api_key") or "").strip()
    if api_key:
        request.add_header("Authorization", "Bearer " + api_key)
    try:
        with urllib.request.urlopen(request, timeout=1.2) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _pythonw() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    if candidate.is_file():
        return str(candidate)
    local_apps = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    candidates = sorted(local_apps.glob("Python*/pythonw.exe"), reverse=True)
    return str(candidates[0]) if candidates else "pythonw.exe"


def _append_launcher_log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with (ROOT / "launcher.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        pass


def _emit(progress: Progress, kind: str, value: object) -> None:
    try:
        progress(kind, value)
    except Exception:
        pass


def load_config() -> dict:
    config, _ = manager.load_config()
    return config


def active_voice_runtime() -> dict:
    """Return the voice binding of the currently active persona."""
    try:
        with PERSONA_CONFIG.open(encoding="utf-8-sig") as handle:
            catalog = json.load(handle)
    except (OSError, ValueError):
        catalog = {}
    persona_id = str(catalog.get("active") or "tafei")
    persona = next(
        (
            item
            for item in catalog.get("personas", [])
            if str(item.get("id")) == persona_id
        ),
        {},
    )
    try:
        with VOICE_CONFIG.open(encoding="utf-8-sig") as handle:
            voice_config = json.load(handle)
    except (OSError, ValueError):
        voice_config = {}
    binding = dict(
        (voice_config.get("voice_bindings") or {}).get(persona_id) or {}
    )
    meta = persona.get("voice_binding") or {}
    binding = {**meta, **binding}
    provider = str(binding.get("provider") or "")
    if provider == "gpt_sovits":
        manifest = Path(str(binding.get("manifest_path") or ""))
        tts_config = Path(str(binding.get("tts_config_path") or ""))
        installed = manifest.is_file() and tts_config.is_file()
        detail = "塔菲 GPT-SoVITS 已安装" if installed else "塔菲声线未安装"
    elif provider == "feiyu_voice_http":
        installed = bool(str(binding.get("base_url") or "").strip())
        detail = "肥鱼声音服务已配置" if installed else "肥鱼声音服务未连接"
    else:
        installed = False
        detail = "未绑定语音"
    return {
        "persona_id": persona_id,
        "persona_name": str(persona.get("display_name") or persona_id),
        "provider": provider,
        "enabled": bool(binding.get("enabled", False)) and installed,
        "installed": installed,
        "detail": detail,
        "binding": binding,
    }


def get_status(config: dict | None = None) -> dict:
    config = config or load_config()
    napcat_root = manager.norm_win_path(config.get("napcat_root"))
    napcat_pids = manager.qq_pids_by_image_path(napcat_root) if napcat_root else []
    ws_clients = manager.pids_connected_to(WS_PORT)
    voice = active_voice_runtime()
    if voice["provider"] == "gpt_sovits":
        voice_service_online = _port_open(TTS_PORT)
    elif voice["provider"] == "feiyu_voice_http":
        voice_service_online = _remote_service_ready(voice["binding"])
    else:
        voice_service_online = False
    return {
        "astrbot_online": _port_open(DASH_PORT),
        "tts_online": voice_service_online,
        "voice_enabled": voice["enabled"],
        "voice_provider": voice["provider"],
        "voice_detail": voice["detail"],
        "napcat_process": bool(napcat_pids),
        "napcat_online": bool(ws_clients),
        "napcat_pids": napcat_pids,
        "ws_pids": ws_clients,
        "watchdog_running": _watchdog_running(),
    }


def _watchdog_running() -> bool:
    try:
        return time.time() - WATCHDOG_HEARTBEAT.stat().st_mtime < 120
    except OSError:
        return False


def qr_is_fresh(
    path: Path,
    *,
    not_before: float,
    max_age_seconds: float = 120,
    now: float | None = None,
) -> bool:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    current = time.time() if now is None else now
    # Filesystem timestamps can be rounded by a second on some drives.
    return mtime >= not_before - 2 and 0 <= current - mtime <= max_age_seconds


def latest_login_qr(
    config: dict | None = None,
    *,
    not_before: float | None = None,
    max_age_seconds: float | None = None,
) -> Path | None:
    config = config or load_config()
    shell_dir = Path(manager.norm_win_path(config.get("napcat_shell_dir")))
    candidates = list(
        shell_dir.glob("versions/*/resources/app/napcat/cache/qrcode.png")
    )
    if not_before is not None:
        candidates = [
            path
            for path in candidates
            if qr_is_fresh(
                path,
                not_before=not_before,
                max_age_seconds=(
                    120 if max_age_seconds is None else max_age_seconds
                ),
            )
        ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _wait_until(
    predicate: Callable[[], bool],
    timeout: int,
    stop_event: threading.Event | None,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stop_event and stop_event.is_set():
            return False
        if predicate():
            return True
        time.sleep(1)
    return predicate()


def _start_astrbot(config: dict) -> None:
    root = Path(config["astrbot_root"])
    exe = Path(config["astrbot_exe"])
    if not exe.is_file():
        raise RuntimeError(f"AstrBot 启动文件不存在: {exe}")
    env = os.environ.copy()
    env["ASTRBOT_ROOT"] = str(root)
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    with (ROOT / "launcher-astrbot.log").open("ab") as output:
        subprocess.Popen(
            [str(exe), "run"],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
        )


def _start_napcat(config: dict) -> None:
    shell_dir = Path(manager.norm_win_path(config.get("napcat_shell_dir")))
    boot_exe = shell_dir / "NapCatWinBootMain.exe"
    if not boot_exe.is_file():
        raise RuntimeError(f"NapCat 启动文件不存在: {boot_exe}")
    arguments = [str(boot_exe)]
    qq = str(config.get("qq") or "").strip()
    manager.claim_napcat_start(str(ROOT))
    if qq:
        arguments.append(qq)
    subprocess.Popen(
        arguments,
        cwd=shell_dir,
        stdin=subprocess.DEVNULL,
        creationflags=NO_WINDOW,
    )


def _start_tts() -> None:
    if _port_open(TTS_PORT):
        return
    voice_root = _voice_engine_root()
    python_exe = voice_root / ".venv" / "Scripts" / "python.exe"
    api_script = voice_root / "api_v2.py"
    runtime = active_voice_runtime()
    if runtime["provider"] != "gpt_sovits" or not runtime["enabled"]:
        raise RuntimeError(
            f"{runtime['persona_name']}没有可启动的本地 GPT-SoVITS 声线"
        )
    configured_path = str(runtime["binding"].get("tts_config_path") or "").strip()
    config_path = (
        Path(configured_path)
        if configured_path
        else voice_root / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
    )
    missing = [
        str(path)
        for path in (python_exe, api_script, config_path)
        if not path.exists()
    ]
    if missing:
        raise RuntimeError("语音环境不完整: " + ", ".join(missing))
    if _port_open(TTS_PORT):
        return
    log_dir = voice_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    with (log_dir / "api.launcher.log").open("ab") as output:
        subprocess.Popen(
            [
                str(python_exe),
                str(api_script),
                "-a",
                "127.0.0.1",
                "-p",
                str(TTS_PORT),
                "-c",
                str(config_path),
            ],
            cwd=voice_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
        )


def _start_watchdog() -> None:
    watchdog = RUNTIME / "tafei_watchdog.py"
    if not watchdog.is_file():
        raise RuntimeError(f"守护脚本不存在: {watchdog}")
    subprocess.Popen(
        [_pythonw(), str(watchdog)],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=NO_WINDOW,
    )


def display_status(status: dict) -> dict:
    if status["astrbot_online"]:
        astrbot = "在线"
    else:
        astrbot = "未运行"
    if status["napcat_online"]:
        napcat = "在线"
    elif status["napcat_process"]:
        napcat = "已掉线，等待重新扫码"
    else:
        napcat = "未运行"
    if not status.get("voice_enabled", False):
        voice = "未配置"
    elif status.get("tts_online", False):
        voice = "在线"
    elif status.get("voice_provider") == "feiyu_voice_http":
        voice = "已配置，未连接"
    else:
        voice = "未运行"
    return {
        "AstrBot": astrbot,
        "NapCat / QQ": napcat,
        "角色语音": voice,
        "自动守护": "运行中" if status["watchdog_running"] else "未运行",
        "_raw": status,
    }


def _ensure_all_impl(
    progress: Progress,
    stop_event: threading.Event | None = None,
    *,
    include_tts: bool = True,
) -> dict:
    launch_started = time.time()
    config = load_config()
    runtime = active_voice_runtime()
    voice_enabled = (
        include_tts
        and runtime["provider"] == "gpt_sovits"
        and runtime["enabled"]
    )
    (ROOT / ".pause_watchdog").unlink(missing_ok=True)

    status = get_status(config)
    _emit(progress, "status", display_status(status))
    _emit(progress, "log", "正在检查塔菲运行状态...")

    astrbot_started = False
    tts_started = False
    napcat_started = False

    if status["astrbot_online"]:
        _emit(progress, "log", "AstrBot 已在线，保持运行。")
    else:
        _emit(progress, "log", "AstrBot 未运行，正在启动...")
        _start_astrbot(config)
        astrbot_started = True

    if not include_tts:
        _emit(progress, "log", "本次配置暂不启动语音服务。")
    elif status["tts_online"]:
        _emit(
            progress,
            "log",
            f"{runtime['persona_name']}绑定的语音已在线，保持运行。",
        )
    elif voice_enabled:
        _emit(
            progress,
            "log",
            f"{runtime['persona_name']}绑定的本地语音未运行，"
            "等待 AstrBot 插件自动启动...",
        )
        if not _wait_until(
            lambda: _http_ready(TTS_PORT, "/docs"),
            20,
            stop_event,
        ):
            _emit(progress, "log", "语音插件未自动启动，客户端正在启动语音服务...")
            _start_tts()
            tts_started = True
    else:
        _emit(progress, "log", "尚未配置语音，跳过语音服务。")

    if astrbot_started:
        astrbot_ready = _wait_until(
            lambda: _port_open(DASH_PORT), 120, stop_event
        )
        if astrbot_ready:
            _emit(progress, "log", "AstrBot 已就绪。")
        else:
            _emit(progress, "log", "AstrBot 尚未就绪，请查看 launcher-astrbot.log。")

    current = get_status(config)
    _emit(progress, "status", display_status(current))
    if current["napcat_online"]:
        _emit(progress, "log", "NapCat 与 QQ 已在线，保持运行。")
    elif current["napcat_process"]:
        _emit(progress, "log", "NapCat 进程已存在，等待 QQ 登录或重连...")
    else:
        _emit(progress, "log", "NapCat 未运行，正在启动...")
        _start_napcat(config)
        napcat_started = True

    if not current["napcat_online"]:
        _wait_until(
            lambda: bool(manager.pids_connected_to(WS_PORT)),
            8,
            stop_event,
        )
        qr_path = latest_login_qr(
            config,
            not_before=launch_started,
            max_age_seconds=120,
        )
        if qr_path and not manager.pids_connected_to(WS_PORT):
            _emit(progress, "qr", str(qr_path))
            _emit(progress, "log", "已发现登录二维码，请使用 QQ 扫码登录。")

    if tts_started:
        tts_ready = _wait_until(
            lambda: _http_ready(TTS_PORT, "/docs"), 150, stop_event
        )
        if tts_ready:
            _emit(progress, "log", "本地语音模型已就绪。")
        else:
            _emit(progress, "log", "语音服务尚未就绪，请查看语音日志。")

    if napcat_started or current["napcat_process"]:
        napcat_ready = _wait_until(
            lambda: bool(manager.pids_connected_to(WS_PORT)), 90, stop_event
        )
        if napcat_ready:
            _emit(progress, "log", "NapCat 已连接 AstrBot，QQ 在线。")
        else:
            _emit(
                progress,
                "log",
                "QQ 尚未连接：如弹出登录窗口，请完成扫码或确认登录。",
            )

    latest = get_status(config)
    if not latest["watchdog_running"]:
        _emit(progress, "log", "自动守护未运行，正在启动...")
        _start_watchdog()
        _wait_until(lambda: _port_open(WATCHDOG_LOCK_PORT), 10, stop_event)

    latest = get_status(config)
    if latest["napcat_online"]:
        (ROOT / ".manual_login_required").unlink(missing_ok=True)
    shown = display_status(latest)
    _emit(progress, "status", shown)
    _emit(progress, "done", shown)
    _append_launcher_log(
        "status "
        f"astrbot={shown['AstrBot']} napcat={shown['NapCat / QQ']} "
        f"voice={shown['角色语音']} watchdog={shown['自动守护']}"
    )
    return shown


def ensure_all(
    progress: Progress,
    stop_event: threading.Event | None = None,
    *,
    include_tts: bool = True,
) -> dict:
    lock = _acquire_launch_lock()
    if lock is None:
        _emit(progress, "log", "另一个启动流程正在进行，本次不会重复启动服务。")
        shown = display_status(get_status())
        _emit(progress, "status", shown)
        _emit(progress, "done", shown)
        return shown
    try:
        return _ensure_all_impl(
            progress,
            stop_event,
            include_tts=include_tts,
        )
    finally:
        lock.close()


def restart_after_setup(
    progress: Progress,
    stop_event: threading.Event | None = None,
    *,
    restart_napcat: bool = False,
) -> dict:
    config = load_config()
    _emit(progress, "log", "配置已保存，正在重启服务以应用新设置...")
    manager.cmd_kill_astrbot(config, ROOT)
    for pid in manager.listening_pids(TTS_PORT):
        manager.kill_tree(pid)
    if restart_napcat:
        manager.cmd_kill_napcat(config, ROOT)
    return ensure_all(progress, stop_event)


def stop_all(
    progress: Progress,
    stop_event: threading.Event | None = None,
) -> dict:
    config = load_config()
    (ROOT / ".pause_watchdog").unlink(missing_ok=True)
    _emit(progress, "log", "正在停止 NapCat、AstrBot 和本地语音服务...")
    manager.cmd_kill_napcat(config, ROOT)
    for pid in manager.listening_pids(TTS_PORT):
        manager.kill_tree(pid)
    manager.cmd_kill_astrbot(config, ROOT)
    shown = display_status(get_status(config))
    _emit(progress, "status", shown)
    _emit(progress, "done", shown)
    _emit(progress, "log", "服务已停止。")
    return shown
