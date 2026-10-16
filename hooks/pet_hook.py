# -*- coding: utf-8 -*-
"""
Claude Code hook 入口 —— 把事件原样写进 status.json，由桌宠读取并映射成动作。

这个脚本每次工具调用都会被拉起一次，所以：
  * 只用标准库
  * 无论如何都 exit 0，绝不往 stderr 输出东西（避免干扰 Claude Code）
  * 用「写临时文件 + 原子替换」避免桌宠读到写了一半的内容

手动测试：
    python pet_hook.py --test done
"""
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_PATH = os.path.join(BASE_DIR, "status.json")

MAX_DETAIL = 48


def pick_detail(event, data):
    """给事件挑一个适合显示在桌宠气泡里的细节文字。"""
    if event in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
        return data.get("tool_name") or ""
    if event == "Notification":
        return data.get("message") or ""
    if event in ("SessionStart", "SessionEnd"):
        return data.get("source") or data.get("reason") or ""
    if event == "PreCompact":
        return data.get("trigger") or ""
    return ""


def write_status(payload):
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, STATUS_PATH)


# --------------------------------------------------------------------------
# 跟随 Claude 生命周期：Claude 启动时把桌宠拉起来
# （关闭是桌宠自己盯着 claude.exe 进程做的，不靠 SessionEnd —— 因为可能同时
#   开着多个会话，单个会话结束不该把桌宠关掉）
# --------------------------------------------------------------------------
PIPE_NAME = "xiaolemi-claude-pet"
PET_PY = os.path.join(BASE_DIR, "pet.py")


def pet_running():
    """桌宠的单实例锁是个命名管道，能连上就说明它已经在跑。"""
    try:
        f = open("\\\\.\\pipe\\" + PIPE_NAME, "r+b", buffering=0)
        f.close()
        return True
    except OSError:
        return False


def launch_pet():
    """后台拉起桌宠并立刻返回，不阻塞 hook。"""
    import subprocess

    # 解释器交给 _env 去找（不写死 D:\Anaconda\...），这样整包能拷到别的电脑用。
    # 放在函数里按需导入，避免给每次工具调用的热路径加开销。
    sys.path.insert(0, BASE_DIR)
    try:
        import _env
        exe = _env.find(windowless=True)
    except Exception:
        exe = None
    if not exe:
        exe = sys.executable
    if not exe:
        return False

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    try:
        subprocess.Popen(
            [exe, PET_PY],
            cwd=BASE_DIR,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True
    except Exception:
        return False


def hook_log(msg):
    try:
        with open(os.path.join(BASE_DIR, "pet.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')}  [hook]  {msg}\n")
    except Exception:
        pass


def ensure_pet():
    """SessionStart 时调用：没在跑就拉起来。已经在跑就什么都不做。"""
    try:
        cfg_path = os.path.join(BASE_DIR, "pet_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            life = json.load(f).get("lifecycle", {})
        if not life.get("launchWithClaude", True):
            hook_log("SessionStart：配置里关掉了自动启动，跳过")
            return
        if pet_running():
            hook_log("SessionStart：桌宠已经在跑")
            return
        ok = launch_pet()
        hook_log(f"SessionStart：拉起桌宠 {'成功' if ok else '失败'}")
    except Exception as e:
        hook_log(f"SessionStart：拉起出错 {e!r}")


def main():
    # 手动测试模式： python pet_hook.py --test <事件名或状态名>
    # 既可以是事件（Stop / PreToolUse），也可以是状态（done / error），后者直接强制切换
    if len(sys.argv) >= 3 and sys.argv[1] == "--test":
        name = sys.argv[2]
        write_status({
            "event": name,
            "state": name,
            "detail": sys.argv[3] if len(sys.argv) > 3 else "",
            "ts": time.time(),
            "manual": True,
        })
        return 0

    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    try:
        data = json.loads(raw) if raw and raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    event = data.get("hook_event_name") or ""
    if not event and len(sys.argv) > 1:
        event = sys.argv[1]
    if not event:
        return 0

    detail = pick_detail(event, data)
    if not isinstance(detail, str):
        detail = str(detail)
    detail = " ".join(detail.split())[:MAX_DETAIL]

    try:
        write_status({
            "event": event,
            "detail": detail,
            "ts": time.time(),
            "session_id": data.get("session_id", ""),
            "cwd": data.get("cwd", ""),
        })
    except Exception:
        pass  # 桌宠是锦上添花，绝不能因为写不进去而影响 Claude Code

    # Claude 启动成功 → 确保桌宠也在
    if event == "SessionStart":
        ensure_pet()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
