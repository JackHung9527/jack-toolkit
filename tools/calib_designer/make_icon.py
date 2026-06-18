"""產生 calib_designer.ico（工具圖示）。

圖示意象：一張小卡片上有原始曲線（灰）與分段線性折線（藍）+ 節點圓點，
節點明顯往左側（曲率大、較不線性處）集中，呼應工具的核心功能。

只在「重新產生圖示」時需要執行，且需要 Pillow（matplotlib 會一併帶入）：
    python make_icon.py
產出的 .ico 為二進位資產，runtime（main.py 用 tk iconbitmap）不需要 Pillow。
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

S = 4  # 超取樣倍率，畫大張再縮小以求邊緣平滑
BASE = 256
SZ = BASE * S

ACCENT = (0, 95, 184, 255)       # #005fb8
CURVE = (174, 184, 194, 255)     # 原始曲線灰
AXIS = (200, 206, 214, 255)
CARD = (255, 255, 255, 255)
WHITE = (255, 255, 255, 255)

# 繪圖區（base 座標）
PX0, PX1 = 60, 214
PYT, PYB = 60, 196
YMAX = 1000.0 * (1.0 - math.exp(-100.0 / 18.0)) + 0.15 * 100.0


def curve_y(x: float) -> float:
    return 1000.0 * (1.0 - math.exp(-x / 18.0)) + 0.15 * x


def mx(x: float) -> float:
    return (PX0 + (x / 100.0) * (PX1 - PX0)) * S


def my(yv: float) -> float:
    return (PYB - (yv / YMAX) * (PYB - PYT)) * S


def main() -> None:
    img = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 卡片底
    d.rounded_rectangle([16 * S, 16 * S, 240 * S, 240 * S], radius=30 * S,
                        fill=CARD, outline=ACCENT, width=3 * S)

    # 座標軸
    d.line([PX0 * S, PYT * S, PX0 * S, PYB * S], fill=AXIS, width=2 * S)
    d.line([PX0 * S, PYB * S, PX1 * S, PYB * S], fill=AXIS, width=2 * S)

    # 原始曲線（密集取樣）
    pts = [(mx(x / 2.0), my(curve_y(x / 2.0))) for x in range(0, 201)]
    d.line(pts, fill=CURVE, width=3 * S, joint="curve")

    # 分段線性折線（節點往左集中）
    nodes_x = [0.0, 8.0, 20.0, 45.0, 100.0]
    poly = [(mx(x), my(curve_y(x))) for x in nodes_x]
    d.line(poly, fill=ACCENT, width=5 * S, joint="curve")

    # 節點圓點（甜甜圈：外藍內白）
    r_out, r_in = 9 * S, 4 * S
    for cx, cy in poly:
        d.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], fill=ACCENT)
        d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=WHITE)

    here = Path(__file__).resolve().parent

    # 視窗用 .ico（多尺寸）
    ico = here / "calib_designer.ico"
    img.resize((BASE, BASE), Image.LANCZOS).save(
        ico, format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

    # launcher 卡片用 icon.png（48x48，與其他工具一致；由超取樣大圖直接縮較銳利）
    png = here / "icon.png"
    img.resize((48, 48), Image.LANCZOS).save(png, format="PNG")

    print("wrote", ico.name, ico.stat().st_size, "bytes;", png.name, png.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
