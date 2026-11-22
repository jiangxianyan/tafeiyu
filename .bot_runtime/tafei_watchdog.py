import os
import socket
import subprocess
import sys
import time
import io

BASE = r"C:\tafei"
BOT = os.path.join(BASE, ".bot_runtime", "bot_manager.py")
LOG = os.path.join(BASE, "watchdog.log")
HEARTBEAT = os.path.join(BASE, ".bot_runtime", "watchdog.heartbeat")
PAUSE_FLAG = os.path.join(BASE, ".pause_watchdog")
MANUAL_LOGIN_FLAG = os.path.join(BASE, ".manual_login_required")
PY = sys.executable
LOCK_PORT = 47654
CHECK_SECONDS = 45
FAILS_BEFORE_RESTART = 3
RESTART_COOLDOWN = 600
BRIDGE_NOTICE_COOLDOWN = 1800
NO_WINDOW = 0x08000000


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    print(line)
    try:
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def single_instance():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


def heartbeat():
    try:
        with io.open(HEARTBEAT, "w", encoding="ascii") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def ws_state(port):
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             encoding="gbk", errors="ignore", timeout=20,
                             creationflags=NO_WINDOW).stdout
    except Exception:
        return False, False
    listening = established = False
    for line in out.splitlines():
        if ":%d" % port not in line:
            continue
        if "LISTENING" in line:
            listening = True
        elif "ESTABLISHED" in line:
            established = True
    return listening, established


def online():
    l, e = ws_state(6199)
    a, _ = ws_state(6185)
    return l and e and a


def restart_astrbot_only():
    log("仅重启 AstrBot，NapCat/QQ 保持运行 ...")
    try:
        result = subprocess.run(
            [PY, BOT, "restart-astrbot"],
            cwd=BASE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
            timeout=150,
        )
        return result.returncode == 0
    except Exception as e:
        log("AstrBot 重启失败: %s" % e)
        return False


def notify(title, text):
    try:
        script = (
            "import ctypes,sys;"
            "ctypes.windll.user32.MessageBoxW(None,sys.argv[1],sys.argv[2],0x40)"
        )
        subprocess.Popen([PY, "-c", script, text, title],
                         creationflags=NO_WINDOW)
    except Exception:
        pass


def main():
    lock = single_instance()
    if lock is None:
        return
    log("watchdog 启动")
    heartbeat()
    time.sleep(60)
    fails = FAILS_BEFORE_RESTART - 1
    last_restart = 0
    last_bridge_notice = 0
    paused_logged = False
    while True:
        heartbeat()
        if os.path.exists(MANUAL_LOGIN_FLAG):
            if online():
                try:
                    os.remove(MANUAL_LOGIN_FLAG)
                except OSError:
                    pass
                log("检测到登录已恢复，清除人工登录标记")
            else:
                time.sleep(CHECK_SECONDS)
                continue
        if os.path.exists(PAUSE_FLAG):
            if online():
                try:
                    os.remove(PAUSE_FLAG)
                except Exception:
                    pass
                log("检测到机器人已手动启动，恢复守护")
                paused_logged = False
            else:
                if not paused_logged:
                    log("守护已暂停（用户手动关闭），等待手动启动")
                    paused_logged = True
                time.sleep(CHECK_SECONDS)
                continue
        if online():
            fails = 0
            last_bridge_notice = 0
        else:
            astrbot_listening, _ = ws_state(6185)
            _, bridge_established = ws_state(6199)
            fails += 1
            log(
                "状态异常 第%d次 astrbot=%s bridge=%s"
                % (
                    fails,
                    "listening" if astrbot_listening else "down",
                    "established" if bridge_established else "down",
                )
            )
            if not astrbot_listening:
                if (
                    fails >= FAILS_BEFORE_RESTART
                    and time.time() - last_restart > RESTART_COOLDOWN
                ):
                    last_restart = time.time()
                    restart_astrbot_only()
                    time.sleep(60)
                    astrbot_listening, _ = ws_state(6185)
                    if online():
                        log("AstrBot 重启后 QQ 桥已自动重连")
                        fails = 0
                        continue
                    if not astrbot_listening:
                        log("AstrBot 重启失败；停止自动重试，等待人工处理")
                        try:
                            io.open(MANUAL_LOGIN_FLAG, "a").close()
                        except OSError:
                            pass
                        notify(
                            "AstrBot 没有恢复",
                            "守护程序已停止自动重启。请检查 AstrBot 日志后，"
                            "使用唯一入口「启动塔菲鱼」手动恢复。",
                        )
                        time.sleep(600)
                        fails = 0
            else:
                # AstrBot 正常但 QQ 桥没连上：不要自动重启 QQ，否则容易反复扫码/同号互踢。
                if time.time() - last_bridge_notice > BRIDGE_NOTICE_COOLDOWN:
                    log("AstrBot 在线，但 QQ 桥未连接；只提醒，不自动拉起 NapCat")
                    notify(
                        "QQ 桥未连接",
                        "AstrBot 本身在线。守护程序不会自动重启 NapCat/QQ。"
                        "请检查 QQ 是否仍登录；需要恢复时只使用唯一入口启动一次。",
                    )
                    last_bridge_notice = time.time()
                try:
                    io.open(MANUAL_LOGIN_FLAG, "a").close()
                except OSError:
                    pass
                time.sleep(60)
                fails = 0
        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
