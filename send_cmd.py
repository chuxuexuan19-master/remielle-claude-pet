# -*- coding: utf-8 -*-
"""
给正在运行的桌宠发一条指令。

    python send_cmd.py reload    改完 pet_config.json 后重新读取，不用重启
    python send_cmd.py show      把桌宠叫到前面
    python send_cmd.py hide      临时隐藏
    python send_cmd.py toggle    显示/隐藏切换

原理：桌宠的单实例锁是个命名管道，这里连上去写一条指令就行。
"""
import os
import sys
import time

PIPE_NAME = "xiaolemi-claude-pet"
PIPE = "\\\\.\\pipe\\" + PIPE_NAME
VALID = ("reload", "show", "hide", "toggle")


def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if cmd not in VALID:
        print(__doc__.strip())
        return 1

    try:
        f = open(PIPE, "r+b", buffering=0)
    except OSError:
        print("连不上桌宠 —— 它没在跑？（双击 启动小蕾米.bat 可以拉起来）")
        return 1

    try:
        f.write(cmd.encode())
        f.flush()
        time.sleep(0.8)
    finally:
        f.close()

    print(f"已发送: {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
