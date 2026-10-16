# -*- coding: utf-8 -*-
"""
把桌宠打包成可以直接拷到别的电脑的 zip。

    python 打包.py

产物默认放在 D:\\Claude project\\小蕾米桌宠-便携版.zip。
运行时产生的文件（python.txt / pet.log / pet.pid / status.json）不会进包 ——
它们是每台机器自己的，带过去反而会误导新机器上的解释器查找。
"""
import os
import sys
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(BASE), "小蕾米桌宠-便携版.zip")
ROOT = "小蕾米桌宠"                       # 解压出来的顶层文件夹名

EXCLUDE_FILES = {"pet.log", "pet.pid", "status.json", "python.txt", "打包.py"}
EXCLUDE_DIRS = {"__pycache__", ".git"}


def main():
    n = total = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, dirnames, filenames in os.walk(BASE):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn in EXCLUDE_FILES or fn.endswith(".pyc"):
                    continue
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.join(ROOT, os.path.relpath(full, BASE)))
                n += 1
                total += os.path.getsize(full)

    print(f"打包完成: {OUT}")
    print(f"  文件数  : {n}")
    print(f"  原始大小: {total/1024/1024:.1f} MB")
    print(f"  压缩后  : {os.path.getsize(OUT)/1024/1024:.1f} MB")
    print()
    print("  拷到别的电脑后：解压 → 双击 install.bat → 重启 Claude Code")
    print("  详细说明见 移植说明.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
