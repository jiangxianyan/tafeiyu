import os
import socket
import subprocess
import sys
import time
import io

BASE = r"C:\tafei"
BOT = os.path.join(BASE, ".bot_runtime", "bot_manager.py")
LOG = os.path.join(BASE, "watchdog.log")
PAUSE_FLAG = os.path.join(BASE, ".pause_watchdog")
MANUAL_LOGIN_FLAG = os.path.join(BASE, ".manual_login_required")
PY = sys.executable
LOCK_PORT = 47654
CHECK_SECONDS = 45
FAILS_BEFORE_RESTART = 3
RESTART_COOLDOWN = 300
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


def start_bot():
    log("尝试启动机器人 ...")
    try:
        subprocess.Popen([PY, BOT, "start"], cwd=BASE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=NO_WINDOW)
        return True
    except Exception as e:
        log("启动失败: %s" % e)
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
    time.sleep(60)
    fails = FAILS_BEFORE_RESTART - 1
    last_restart = 0
    paused_logged = False
    while True:
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
        else:
            fails += 1
            log("状态异常 第%d次" % fails)
            if fails >= FAILS_BEFORE_RESTART and time.time() - last_restart > RESTART_COOLDOWN:
                last_restart = time.time()
                start_bot()
                time.sleep(60)
                if online():
                    log("自动重连成功")
                    fails = 0
                else:
                    log("自动重连失败，停止重复重试，等待人工登录")
                    try:
                        io.open(MANUAL_LOGIN_FLAG, "a").close()
                    except OSError:
                        pass
                    notify(
                        "塔菲掉线了",
                        "自动重连失败。请处理后双击「启动塔菲」重新登录。",
                    )
                    time.sleep(600)
                    fails = 0
        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
