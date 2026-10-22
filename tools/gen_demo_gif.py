#!/usr/bin/env python3
"""生成 README 用的终端演示 GIF（打字机效果 + 块光标）。

用法（需要 Pillow，仅开发机使用，不是运行依赖）：
    python tools/gen_demo_gif.py [--out examples/demo.gif]

实现要点：
- 双字体混排：ASCII 用 Consolas（等宽，终端质感），CJK 用微软雅黑
- 逐字符揭示 + 块光标 + 结尾停顿
- 深色终端卡片，macOS 风格三色标题点
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import unicodedata
from contextlib import redirect_stdout
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

LATIN_FONT = "C:/Windows/Fonts/consola.ttf"
CJK_FONT = "C:/Windows/Fonts/msyh.ttc"

FONT_SIZE = 15
LINE_H = 23
PAD_X = 18
PAD_Y = 14
TITLE_H = 34
FPS = 10
CHARS_PER_FRAME = 20
HOLD_FRAMES = 18  # 结尾停顿

BG = (24, 26, 38)
TITLE_BG = (18, 20, 30)
FG = (226, 232, 240)
DIM = (140, 148, 164)
ACCENT = (255, 199, 44)
CURSOR = (255, 199, 44)


def _is_cjk(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


def _load_fonts(size: int):
    latin = ImageFont.truetype(LATIN_FONT, size)
    cjk = ImageFont.truetype(CJK_FONT, size)
    return latin, cjk


def _line_width(line: str, latin, cjk) -> float:
    w = 0.0
    for ch in line:
        w += (cjk if _is_cjk(ch) else latin).getlength(ch)
    return w


def capture_dashboard_output() -> str:
    """在子进程中运行 demo dashboard，捕获纯文本输出。"""
    code = (
        "import sys; sys.path.insert(0, 'src');"
        "from mcd_asset_butler.cli import main;"
        "sys.argv = ['mcd-asset-butler', 'dashboard', '--demo'];"
        "main()"
    )
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    return proc.stdout


def render_frame(lines_done: str, cursor_on: bool, width: int, height: int, latin, cjk) -> Image.Image:
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    # 标题栏
    d.rectangle([0, 0, width, TITLE_H], fill=TITLE_BG)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = PAD_X + i * 18
        cy = TITLE_H // 2
        d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=color)
    d.text((PAD_X + 62, TITLE_H // 2), "麦麦资产管家 — mcd-asset-butler", font=cjk, fill=DIM, anchor="lm")
    d.line([(0, TITLE_H), (width, TITLE_H)], fill=(50, 54, 70), width=1)
    # 内容
    y = TITLE_H + PAD_Y
    for line in lines_done.split("\n"):
        x = PAD_X
        for ch in line:
            font = cjk if _is_cjk(ch) else latin
            color = ACCENT if ch in "★⚠" else FG
            d.text((x, y), ch, font=font, fill=color)
            x += font.getlength(ch)
        y += LINE_H
    if cursor_on:
        d.rectangle([PAD_X, y + 2, PAD_X + 8, y + LINE_H - 4], fill=CURSOR)
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "examples" / "demo.gif"))
    args = ap.parse_args()

    output = capture_dashboard_output()
    output = output.strip("\n")
    lines = output.split("\n")
    latin, cjk = _load_fonts(FONT_SIZE)

    command = "$ python -m mcd_asset_butler dashboard --demo"
    full_lines = [command, ""] + lines
    max_w = max(_line_width(l, latin, cjk) for l in full_lines)
    width = int(max_w + PAD_X * 2 + 20)
    height = TITLE_H + PAD_Y * 2 + LINE_H * (len(full_lines) + 1)

    frames = []
    shown: list = []
    for li, line in enumerate(full_lines):
        # 命令行慢打（8 字符/帧），正文快进（每行约 2 帧）
        if li == 0:
            step = 8
        else:
            step = max(1, (len(line) + 1) // 2)
        typed = ""
        for i in range(0, len(line), step):
            typed = line[: i + step]
            frames.append(render_frame("\n".join(shown + [typed]), True, width, height, latin, cjk))
        if not line:
            frames.append(render_frame("\n".join(shown), True, width, height, latin, cjk))
        shown.append(line)
        frames.append(render_frame("\n".join(shown), True, width, height, latin, cjk))

    # 结尾：光标闪烁几次后定稿
    final = "\n".join(shown)
    for k in range(HOLD_FRAMES):
        frames.append(render_frame(final, k % 8 < 4, width, height, latin, cjk))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # 全局调色板量化：终端配色有限，48 色足够且大幅压缩体积
    pal = frames[0].convert("P", palette=Image.ADAPTIVE, colors=48)
    quantized = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    quantized[0].save(
        out,
        save_all=True,
        append_images=quantized[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=True,
    )
    size_kb = out.stat().st_size // 1024
    print(f"GIF 已生成: {out} ({len(frames)} 帧, {size_kb} KB)")


if __name__ == "__main__":
    main()
