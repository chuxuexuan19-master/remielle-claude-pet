# -*- coding: utf-8 -*-
"""
找一个可用的 Python 解释器。

为什么需要它：这个包要能直接拷到别的电脑上用，不能写死 D:\\Anaconda\\python.exe。
查找顺序：
    1. 上次安装时记录在 python.txt 里的路径
    2. 环境变量 XIAOLEMI_PYTHON
    3. 当前正在运行的解释器
    4. PATH 里的 pythonw / python
    5. 常见安装位置（Anaconda / Miniconda / 官方安装器）
全都找不到就返回 None。

为了不给 hook 增加启动开销，重量级模块（shutil/subprocess）都是按需导入的。
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PY_FILE = os.path.join(BASE_DIR, "python.txt")


def read_recorded():
    """读上次记录的解释器路径；失效了返回 None。"""
    try:
        with open(PY_FILE, "r", encoding="utf-8") as f:
            p = f.read().strip().strip('"')
        return p if p and os.path.isfile(p) else None
    except Exception:
        return None


def record(path):
    """把选定的解释器记下来，下次直接用。"""
    try:
        with open(PY_FILE, "w", encoding="utf-8") as f:
            f.write(path)
    except Exception:
        pass


def _with_w(exe):
    """给 python.exe 配一个同目录的 pythonw.exe（有的话），用来无窗口启动。"""
    d, n = os.path.split(exe)
    if n.lower() == "python.exe":
        w = os.path.join(d, "pythonw.exe")
        if os.path.isfile(w):
            return w
    return exe


def _with_console(exe):
    """
    反过来：把 pythonw.exe 换成 python.exe。

    跑 hook 时必须用 console 版 —— hook 要从 stdin 读 JSON，而 pythonw 是 GUI
    子系统程序，只有在 stdin 恰好是管道时才能读；换成别的调用方式就会拿到无效
    句柄，hook 会静默失效。python.exe 没这个问题。
    """
    d, n = os.path.split(exe)
    if n.lower() == "pythonw.exe":
        c = os.path.join(d, "python.exe")
        if os.path.isfile(c):
            return c
    return exe


def _candidates():
    rec = read_recorded()
    if rec:
        yield rec, False

    env = os.environ.get("XIAOLEMI_PYTHON")
    if env and os.path.isfile(env):
        yield env, False

    if sys.executable and os.path.isfile(sys.executable):
        yield sys.executable, False

    import shutil
    for name in ("pythonw.exe", "python.exe", "python3.exe"):
        w = shutil.which(name)
        if w:
            yield w, False

    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")
    roots = [
        os.path.join(local, "Programs", "Python"),
        os.path.join(home, "anaconda3"), os.path.join(home, "miniconda3"),
        os.path.join(home, "Anaconda3"), os.path.join(home, "Miniconda3"),
        r"C:\ProgramData\Anaconda3", r"C:\ProgramData\miniconda3",
        r"C:\Anaconda3", r"C:\Miniconda3",
        r"D:\Anaconda", r"D:\Anaconda3", r"D:\Miniconda3",
        r"C:\Python313", r"C:\Python312", r"C:\Python311", r"C:\Python310",
    ]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        # 官方安装器会建 Python3xx 子目录
        try:
            subs = sorted(os.listdir(root), reverse=True)
        except Exception:
            subs = []
        for sub in subs + [""]:
            for exe in ("pythonw.exe", "python.exe"):
                p = os.path.join(root, sub, exe) if sub else os.path.join(root, exe)
                if os.path.isfile(p):
                    yield p, False

    # 最后的兜底：交给 shell 解析（PATH 里可能有但 which 没找到）
    yield "pythonw", True
    yield "python", True


def find(windowless=True, verify=False):
    """
    找一个可用的解释器。返回路径字符串，找不到返回 None。
    windowless=True 时优先返回 pythonw.exe（不弹控制台窗口）。
    verify=True 会真的启动一次解释器确认可用 —— 慢（多 10~20ms），
    安装时用，hook 每次调用不要用。
    """
    subprocess = None
    if verify:
        import subprocess          # 只在需要时才导入，hook 走的路径要尽量轻
    seen = set()
    for path, bare in _candidates():
        if not path or path in seen:
            continue
        seen.add(path)
        if bare:
            import shutil
            if not shutil.which(path):
                continue
            return path if windowless else path.replace("pythonw", "python")
        if not os.path.isfile(path):
            continue
        if verify:
            try:
                r = subprocess.run([path, "-c", "pass"], capture_output=True, timeout=20)
                if r.returncode != 0:
                    continue
            except Exception:
                continue
        return _with_w(path) if windowless else _with_console(path)
    return None


def has_pyside6(python_exe):
    import subprocess
    try:
        r = subprocess.run([python_exe, "-c", "import PySide6"],
                           capture_output=True, timeout=40)
        return r.returncode == 0
    except Exception:
        return False


def install_pyside6(python_exe):
    """装 PySide6。优先走国内镜像，失败再试官方源。"""
    import subprocess
    mirrors = [
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "https://mirrors.aliyun.com/pypi/simple/",
        None,      # 官方源
    ]
    for m in mirrors:
        cmd = [python_exe, "-m", "pip", "install", "PySide6"]
        if m:
            cmd += ["-i", m]
        print(f"  正在安装 PySide6（{m or '官方源'}）...")
        try:
            r = subprocess.run(cmd, timeout=900)
            if r.returncode == 0 and has_pyside6(python_exe):
                return True
        except Exception as e:
            print(f"    失败：{e}")
    return False


if __name__ == "__main__":
    py = find(windowless=True)
    print("找到的解释器:", py or "（没找到）")
    if py:
        print("PySide6 可用 :", has_pyside6(py))
        print("已记录到    :", PY_FILE)
        record(py)
