# -*- coding: utf-8 -*-
"""
把小蕾米桌宠的 hook 注册进 Claude Code 的 ~/.claude/settings.json。

  python install_hooks.py              安装（默认 async 后台执行，不拖慢 Claude Code）
  python install_hooks.py --no-async   改成同步执行（每次工具调用多 ~65ms）
  python install_hooks.py --uninstall  卸载
  python install_hooks.py --status     查看当前装了哪些

特点：
  * 只追加，不动你已有的 hook（例如 ComfyUI 自启那个）
  * 可重复执行，不会重复注册（按 hook 命令里的 pet_hook.py 识别）
  * 改之前自动备份成 settings.json.bak-<时间戳>
  * hook 事件列表直接读 pet_config.json 的 events 段，改配置就能改注册范围
"""
import argparse
import json
import os
import shutil
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "pet_config.json")
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

# 用来识别「这条 hook 是小蕾米装的」——卸载和去重都靠它。
# 用脚本文件名而不是目录名，这样整包改名、换路径都不影响识别。
MARK = "pet_hook.py"


def find_python():
    """
    找一个可用的解释器并记录下来。
    优先用 _env 的自动发现（python.txt → 环境变量 → PATH → 常见安装位置），
    这样复制到别的电脑也能自己找到，不用改代码。
    """
    try:
        sys.path.insert(0, BASE_DIR)
        import _env
        py = _env.find(windowless=False, verify=True)
        if py:
            _env.record(py)
            return py
    except Exception:
        pass
    return sys.executable


def build_command(python_exe):
    script = os.path.join(BASE_DIR, "hooks", "pet_hook.py")
    # Claude Code 在 Windows 上通过 cmd.exe 执行，双引号包裹即可处理路径空格
    return f'"{python_exe}" "{script}"'


def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {}
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def backup_settings():
    if not os.path.exists(SETTINGS_PATH):
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = SETTINGS_PATH + f".bak-{stamp}"
    shutil.copy2(SETTINGS_PATH, dst)
    return dst


def save_settings(data, backup=True):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    path = backup_settings() if backup else None
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_PATH)
    return path


def is_ours_group(group):
    """这个 matcher 组是不是小蕾米装的。"""
    if not isinstance(group, dict):
        return False
    for h in group.get("hooks", []) or []:
        if isinstance(h, dict) and MARK in str(h.get("command", "")):
            return True
    return False


def strip_ours(settings):
    """把所有小蕾米装的 hook 摘掉，返回摘掉的条数。"""
    removed = 0
    hooks = settings.get("hooks", {})
    for ev in list(hooks.keys()):
        groups = hooks[ev]
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if not is_ours_group(g)]
        removed += len(groups) - len(kept)
        if kept:
            hooks[ev] = kept
        else:
            del hooks[ev]
    if not hooks and "hooks" in settings:
        del settings["hooks"]
    return removed


def config_events():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return [e["event"] for e in cfg.get("events", []) if e.get("event")]


def cmd_install(use_async=True, force=False):
    if not os.path.exists(SETTINGS_PATH) and not force:
        print(f"找不到 {SETTINGS_PATH}")
        print("（如果 Claude Code 还没生成过这个文件，加 --force 可以新建。）")
        return 1

    python_exe = find_python()
    command = build_command(python_exe)
    events = config_events()

    settings = load_settings()

    # 先摘掉旧的，保证可重复执行
    n_old = strip_ours(settings)

    hooks = settings.setdefault("hooks", {})
    entry = {
        "type": "command",
        "command": command,
        "timeout": 10,
    }
    if use_async:
        entry["async"] = True

    added = []
    for ev in events:
        hooks.setdefault(ev, []).append({"hooks": [dict(entry)]})
        added.append(ev)

    bak = save_settings(settings)

    print(f"解释器   : {python_exe}")
    print(f"hook 命令: {command}")
    print(f"备份     : {bak or '(原文件不存在，新建)'}")
    if n_old:
        print(f"清理旧项 : {n_old} 条")
    print(f"已注册 {len(added)} 个事件（{'async 后台执行' if use_async else '同步执行'}）：")
    for ev in added:
        print(f"  + {ev}")
    print()
    print("改完 settings.json 后需要重启 Claude Code 才会生效。")
    return 0


def cmd_uninstall():
    if not os.path.exists(SETTINGS_PATH):
        print("没有 settings.json，无需卸载。")
        return 0
    settings = load_settings()
    n = strip_ours(settings)
    if not n:
        print("没有找到小蕾米注册的 hook。")
        return 0
    bak = save_settings(settings)
    print(f"已移除 {n} 条小蕾米 hook。备份：{bak}")
    print("重启 Claude Code 后生效。")
    return 0


def cmd_status():
    settings = load_settings()
    hooks = settings.get("hooks", {})
    found = []
    for ev, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for g in groups:
            if is_ours_group(g):
                found.append(ev)
                break
    if found:
        print(f"小蕾米已注册 {len(found)} 个事件：")
        for ev in found:
            print(f"  · {ev}")
    else:
        print("小蕾米尚未注册任何 hook。")
    other = [ev for ev in hooks if ev not in found]
    if other:
        print(f"\n其它 hook（未改动）：{', '.join(other)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="注册小蕾米桌宠的 Claude Code hook")
    ap.add_argument("--uninstall", action="store_true", help="卸载")
    ap.add_argument("--status", action="store_true", help="查看状态")
    ap.add_argument("--no-async", action="store_true", help="同步执行而非后台执行")
    ap.add_argument("--force", action="store_true", help="settings.json 不存在时也新建")
    a = ap.parse_args()

    if a.status:
        return cmd_status()
    if a.uninstall:
        return cmd_uninstall()
    return cmd_install(use_async=not a.no_async, force=a.force)


if __name__ == "__main__":
    sys.exit(main())
