# -*- coding: utf-8 -*-
"""
素材体检：逐帧检查每个动作 GIF 的透明通道是否正常。

为什么需要它：PIL 存 GIF 时会丢 alpha，只认 `transparency=<索引>`。当调色板里
那个索引恰好被画面用掉时，**只有部分帧**的透明会失效（表现为黑底/白底方块）。
只查第 0 帧是查不出来的，必须逐帧看。

    python check_assets.py
"""
import json
import os
import sys

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(BASE, "pet_config.json")


def check(path):
    """返回 (总帧数, 有问题的帧号列表, 各帧透明像素占比)"""
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    bad, ratios = [], []
    for i in range(n):
        im.seek(i)
        rgba = im.convert("RGBA")
        w, h = rgba.size
        # 只查四角：这些图角色都居中，四角必定是背景。
        # 不要查底边中点 —— 有的动作角色本来就顶到画面底部（比如 smug），会误报。
        probes = [rgba.getpixel((2, 2)), rgba.getpixel((w - 3, 2)),
                  rgba.getpixel((2, h - 3)), rgba.getpixel((w - 3, h - 3))]
        clear = sum(1 for p in probes if p[3] == 0)
        data = list(rgba.getdata())
        ratio = sum(1 for p in data if p[3] == 0) / len(data)
        ratios.append(ratio)
        # 四角必须全透明，且至少有 5% 是背景
        if clear < len(probes) or ratio < 0.05:
            bad.append((i, clear, ratio))
    return n, bad, ratios


def main():
    cfg = json.load(open(CFG, encoding="utf-8"))
    seen, problems = set(), 0

    print(f"{'动作':<10}{'文件':<28}{'帧':>4}{'透明占比':>22}  判定")
    print("-" * 78)
    for name, st in cfg["states"].items():
        rel = st["gif"]
        if rel in seen:
            continue
        seen.add(rel)
        path = os.path.join(BASE, rel.replace("/", os.sep))
        if not os.path.exists(path):
            print(f"{name:<10}{rel:<28}  文件不存在！")
            problems += 1
            continue
        n, bad, ratios = check(path)
        lo, hi = min(ratios) * 100, max(ratios) * 100
        if bad:
            problems += 1
            frames = ", ".join(f"帧{i}({c}/4角,{r*100:.0f}%)" for i, c, r in bad)
            print(f"{name:<10}{os.path.basename(rel):<28}{n:>4}   {lo:5.1f}% ~ {hi:5.1f}%   "
                  f"有问题 -> {frames}")
        else:
            print(f"{name:<10}{os.path.basename(rel):<28}{n:>4}   {lo:5.1f}% ~ {hi:5.1f}%   正常")

    print()
    if problems:
        print(f"发现 {problems} 个素材有问题。多半是生成 GIF 时透明索引没设对 —— ")
        print("参考 pet.py 附近的说明：需要统一量化调色板 + 预留一个索引给透明。")
    else:
        print("全部正常。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
