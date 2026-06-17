"""為 launcher 與每個子工具產生圖示（.ico + 給卡片用的 icon.png）。

零第三方依賴，全部用 iconkit 的純標準函式庫渲染。每個工具有專屬色系與 glyph：
  launcher  靛藍 / 2x2 工具磚
  serial    綠   / 方波（序列資料）
  netscan   青   / 節點與連線（網路）
  ft232h    紫   / IC 晶片含接腳
  calculator藍   / 顯示區 + 按鈕格 + 橘色等號
  commbench 藍綠 / 開發板晶片 + 排針

用法：
    python make_icons.py
"""

from __future__ import annotations

from pathlib import Path

import iconkit as ik

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"

M = 0.06
R = 0.22
WHITE = (255, 255, 255, 255)
SOFT = (255, 255, 255, 238)
AMBER = (255, 198, 84, 255)
ORANGE = (255, 156, 61, 255)


def bg(top, bot):
    return (ik.rrect(M, M, 1 - M, 1 - M, R), ik.vgrad(top, bot, M, 1 - M))


# ---------------- 各工具 glyph ----------------

def glyph_launcher() -> list:
    tiles = [
        (0.22, 0.22, 0.46, 0.46, WHITE),
        (0.54, 0.22, 0.78, 0.46, WHITE),
        (0.22, 0.54, 0.46, 0.78, WHITE),
        (0.54, 0.54, 0.78, 0.78, AMBER),
    ]
    return [(ik.rrect(x0, y0, x1, y1, 0.05), c) for x0, y0, x1, y1, c in tiles]


def glyph_serial() -> list:
    hw = 0.05
    lo, hi = 0.63, 0.40
    pts = [(0.17, lo), (0.32, lo), (0.32, hi), (0.50, hi),
           (0.50, lo), (0.68, lo), (0.68, hi), (0.83, hi)]
    layers = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        layers.append((ik.segment(x0, y0, x1, y1, hw), WHITE))
    return layers


def glyph_netscan() -> list:
    cx, cy = 0.5, 0.5
    sats = [(0.25, 0.29), (0.75, 0.29), (0.25, 0.71), (0.75, 0.71)]
    layers = []
    for sx, sy in sats:
        layers.append((ik.segment(cx, cy, sx, sy, 0.022), SOFT))
    for sx, sy in sats:
        layers.append((ik.circle(sx, sy, 0.058), WHITE))
    layers.append((ik.circle(cx, cy, 0.085), AMBER))
    return layers


def glyph_ft232h() -> list:
    layers = []
    # 左右接腳（DIP 風）
    for y in (0.36, 0.50, 0.64):
        layers.append((ik.rect(0.17, y - 0.025, 0.32, y + 0.025), SOFT))
        layers.append((ik.rect(0.68, y - 0.025, 0.83, y + 0.025), SOFT))
    # 晶片本體
    layers.append((ik.rrect(0.30, 0.30, 0.70, 0.70, 0.05), WHITE))
    # pin1 標記
    layers.append((ik.circle(0.385, 0.385, 0.03), ORANGE))
    return layers


def glyph_calculator() -> list:
    layers = []
    layers.append((ik.rrect(0.20, 0.17, 0.80, 0.31, 0.04), (236, 243, 255, 255)))
    bx0, by0, bx1, by1 = 0.18, 0.38, 0.82, 0.84
    gap = 0.045
    bw = ((bx1 - bx0) - gap * 2) / 3
    bh = ((by1 - by0) - gap * 2) / 3
    br = min(bw, bh) * 0.26
    for ri in range(3):
        for ci in range(3):
            x0 = bx0 + ci * (bw + gap)
            y0 = by0 + ri * (bh + gap)
            accent = (ri == 2 and ci == 2)
            color = ORANGE if accent else SOFT
            layers.append((ik.rrect(x0, y0, x0 + bw, y0 + bh, br), color))
    return layers


def glyph_commbench() -> list:
    layers = []
    # 晶片
    layers.append((ik.rrect(0.34, 0.28, 0.66, 0.52, 0.05), WHITE))
    # 晶片到排針的引線
    for x in (0.40, 0.50, 0.60):
        layers.append((ik.segment(x, 0.52, x, 0.63, 0.018), SOFT))
    # 排針（一排小方塊）
    n = 6
    x0, x1 = 0.18, 0.82
    pw = 0.066
    step = (x1 - x0 - pw) / (n - 1)
    for i in range(n):
        px = x0 + i * step
        layers.append((ik.rect(px, 0.66, px + pw, 0.76), WHITE))
    return layers


def glyph_netpriority() -> list:
    # 遞減長條，代表優先序清單（上長下短）
    layers = []
    x0 = 0.24
    rights = [0.76, 0.66, 0.56, 0.46]
    ys = [0.30, 0.43, 0.56, 0.69]
    h = 0.085
    for y, x1 in zip(ys, rights):
        layers.append((ik.rrect(x0, y, x1, y + h, 0.035), WHITE))
    return layers


DESIGNS = {
    "launcher":   {"out": ROOT / "launcher.ico",            "png": None,
                   "bg": ((101, 115, 255), (47, 58, 160)),  "glyph": glyph_launcher},
    "serial":     {"out": TOOLS / "serial" / "serial.ico",  "png": TOOLS / "serial" / "icon.png",
                   "bg": ((54, 194, 110), (17, 133, 74)),   "glyph": glyph_serial},
    "netscan":    {"out": TOOLS / "netscan" / "netscan.ico", "png": TOOLS / "netscan" / "icon.png",
                   "bg": ((34, 196, 230), (10, 111, 149)),  "glyph": glyph_netscan},
    "ft232h":     {"out": TOOLS / "ft232h" / "ft232h.ico",  "png": TOOLS / "ft232h" / "icon.png",
                   "bg": ((168, 107, 255), (90, 45, 176)),  "glyph": glyph_ft232h},
    "calculator": {"out": TOOLS / "calculator" / "calculator.ico", "png": TOOLS / "calculator" / "icon.png",
                   "bg": ((43, 136, 255), (20, 74, 207)),   "glyph": glyph_calculator},
    "commbench":  {"out": TOOLS / "CommBench" / "commbench.ico", "png": TOOLS / "CommBench" / "icon.png",
                   "bg": ((31, 208, 173), (12, 143, 120)),  "glyph": glyph_commbench},
    "netpriority": {"out": TOOLS / "netpriority" / "netpriority.ico", "png": TOOLS / "netpriority" / "icon.png",
                    "bg": ((255, 150, 60), (208, 92, 25)),  "glyph": glyph_netpriority},
}


def main() -> None:
    for name, d in DESIGNS.items():
        top, bot = d["bg"]
        glyph = d["glyph"]()

        def layers_for(_size, _g=glyph, _t=top, _b=bot):
            return [bg(_t, _b)] + _g

        d["out"].parent.mkdir(parents=True, exist_ok=True)
        ik.build_icon(d["out"], layers_for, d["png"], png_size=48)
        extra = f" + {d['png'].name}" if d["png"] else ""
        print(f"  {name:11s} -> {d['out'].relative_to(ROOT)}{extra}")
    print("OK 全部圖示已產生")


if __name__ == "__main__":
    main()
