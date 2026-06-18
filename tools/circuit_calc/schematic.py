"""用 tkinter Canvas 畫簡易電路示意圖的繪圖原語。

座標系與 Canvas 相同（左上為原點，y 往下）。每個元件函式以「中心點」或
「起點」為基準畫出，並回傳接腳座標方便接線。純 stdlib，無需 PIL。
"""

from __future__ import annotations

import tkinter as tk

import theme

LINE = "#2a2a2a"
FILL = "#ffffff"
LBL = "#1b1b1b"
HOT = theme.ACCENT       # 重點節點（Vin/Vout 等）
GND_C = "#444444"
F = ("Segoe UI", 9)
FB = ("Segoe UI", 9, "bold")
FS = ("Segoe UI", 8)


def wire(cv: tk.Canvas, *pts, color: str = LINE, width: int = 2) -> None:
    cv.create_line(*pts, fill=color, width=width, capstyle="round", joinstyle="round")


def dot(cv: tk.Canvas, x: float, y: float, r: float = 3.0, color: str = LINE) -> None:
    cv.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=color)


def text(cv: tk.Canvas, x: float, y: float, s: str, anchor: str = "center",
         bold: bool = False, small: bool = False, color: str = LBL) -> None:
    font = FB if bold else (FS if small else F)
    cv.create_text(x, y, text=s, fill=color, font=font, anchor=anchor)


def node(cv: tk.Canvas, x: float, y: float, name: str = "", anchor: str = "s",
         color: str = HOT) -> None:
    """高亮節點：實心點 + 標籤。"""
    dot(cv, x, y, 3.5, color)
    if name:
        dx, dy = 0, -7
        if anchor == "n":
            dy = 7
        elif anchor == "w":
            dx, dy = 8, 0
        elif anchor == "e":
            dx, dy = -8, 0
        text(cv, x + dx, y + dy, name, anchor=anchor if anchor in ("w", "e") else "center",
             bold=True, color=color)


def resistor_h(cv: tk.Canvas, cx: float, cy: float, name: str = "", w: float = 44, h: float = 16):
    """水平電阻（IEC 矩形），中心 (cx,cy)。回傳 (左腳, 右腳)。"""
    x1, x2 = cx - w / 2, cx + w / 2
    cv.create_rectangle(x1, cy - h / 2, x2, cy + h / 2, outline=LINE, width=2, fill=FILL)
    if name:
        text(cv, cx, cy - h / 2 - 8, name, bold=True)
    return (x1, cy), (x2, cy)


def resistor_v(cv: tk.Canvas, cx: float, cy: float, name: str = "", h: float = 44, w: float = 16):
    """垂直電阻，中心 (cx,cy)。回傳 (上腳, 下腳)。"""
    y1, y2 = cy - h / 2, cy + h / 2
    cv.create_rectangle(cx - w / 2, y1, cx + w / 2, y2, outline=LINE, width=2, fill=FILL)
    if name:
        text(cv, cx + w / 2 + 6, cy, name, anchor="w", bold=True)
    return (cx, y1), (cx, y2)


def cap_v(cv: tk.Canvas, cx: float, cy: float, name: str = "", gap: float = 7, plate: float = 20):
    """垂直電容（兩平行板），中心 (cx,cy)。回傳 (上腳, 下腳)。"""
    top = cy - gap / 2
    bot = cy + gap / 2
    cv.create_line(cx - plate / 2, top, cx + plate / 2, top, fill=LINE, width=2)
    cv.create_line(cx - plate / 2, bot, cx + plate / 2, bot, fill=LINE, width=2)
    if name:
        text(cv, cx + plate / 2 + 6, cy, name, anchor="w", bold=True)
    return (cx, cy - gap / 2 - 8), (cx, cy + gap / 2 + 8)


def inductor_h(cv: tk.Canvas, cx: float, cy: float, name: str = "", w: float = 44, loops: int = 4):
    """水平電感（連續半圓），中心 (cx,cy)。回傳 (左腳, 右腳)。"""
    x1 = cx - w / 2
    d = w / loops
    for k in range(loops):
        x = x1 + k * d
        cv.create_arc(x, cy - d / 2, x + d, cy + d / 2, start=0, extent=180,
                      style="arc", outline=LINE, width=2)
    if name:
        text(cv, cx, cy - d / 2 - 8, name, bold=True)
    return (x1, cy), (cx + w / 2, cy)


def inductor_v(cv: tk.Canvas, cx: float, cy: float, name: str = "", h: float = 44, loops: int = 4):
    """垂直電感（連續半圓，向右凸），中心 (cx,cy)。回傳 (上腳, 下腳)。"""
    y1 = cy - h / 2
    d = h / loops
    for k in range(loops):
        y = y1 + k * d
        cv.create_arc(cx - d / 2, y, cx + d / 2, y + d, start=90, extent=-180,
                      style="arc", outline=LINE, width=2)
    if name:
        text(cv, cx + d / 2 + 8, cy, name, anchor="w", bold=True)
    return (cx, y1), (cx, cy + h / 2)


def led_h(cv: tk.Canvas, cx: float, cy: float, name: str = "", s: float = 11):
    """水平 LED（三角形 + cathode 線 + 兩箭頭），陽極在左。回傳 (左腳, 右腳)。"""
    cv.create_polygon(cx - s, cy - s, cx - s, cy + s, cx + s, cy,
                      outline=LINE, width=2, fill=FILL)
    cv.create_line(cx + s, cy - s, cx + s, cy + s, fill=LINE, width=2)
    # 發光箭頭
    cv.create_line(cx + 2, cy - s - 2, cx + 10, cy - s - 10, fill=LINE, width=1, arrow="last")
    cv.create_line(cx + 9, cy - s - 1, cx + 17, cy - s - 9, fill=LINE, width=1, arrow="last")
    if name:
        text(cv, cx, cy + s + 9, name, bold=True)
    return (cx - s, cy), (cx + s, cy)


def ground(cv: tk.Canvas, x: float, y: float, lead: float = 9) -> None:
    """接地符號，上方接點在 (x,y)。"""
    yy = y + lead
    wire(cv, x, y, x, yy)
    cv.create_line(x - 12, yy, x + 12, yy, fill=GND_C, width=2)
    cv.create_line(x - 8, yy + 4, x + 8, yy + 4, fill=GND_C, width=2)
    cv.create_line(x - 4, yy + 8, x + 4, yy + 8, fill=GND_C, width=2)


def opamp(cv: tk.Canvas, x: float, cy: float, size: float = 26, inv_top: bool = True):
    """運算放大器三角形，左側為輸入、右頂點為輸出。

    inv_top=True 時上輸入為「−」、下輸入為「+」（反相在上）。
    回傳 dict：in_minus / in_plus / out 三個接腳座標。
    """
    apex_x = x + size * 1.7
    top = (x, cy - size)
    bot = (x, cy + size)
    out = (apex_x, cy)
    cv.create_polygon(top[0], top[1], bot[0], bot[1], out[0], out[1],
                      outline=LINE, width=2, fill=FILL)
    in_top = (x, cy - size * 0.5)
    in_bot = (x, cy + size * 0.5)
    sym_top = "−" if inv_top else "+"
    sym_bot = "+" if inv_top else "−"
    text(cv, x + 9, in_top[1], sym_top, bold=True)
    text(cv, x + 9, in_bot[1], sym_bot, bold=True)
    if inv_top:
        return {"in_minus": in_top, "in_plus": in_bot, "out": out}
    return {"in_minus": in_bot, "in_plus": in_top, "out": out}


def block(cv: tk.Canvas, x1: float, y1: float, x2: float, y2: float, title: str = ""):
    """方塊（IC / 模組），回傳中心點。"""
    cv.create_rectangle(x1, y1, x2, y2, outline=LINE, width=2, fill="#f4f7fa")
    if title:
        text(cv, (x1 + x2) / 2, (y1 + y2) / 2, title, bold=True)
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def battery_v(cv: tk.Canvas, cx: float, cy: float, name: str = ""):
    """垂直電池（長短線各一對），正極在上。回傳 (上腳, 下腳)。"""
    ys = [cy - 9, cy - 3, cy + 3, cy + 9]
    longs = [True, False, True, False]
    for y, lng in zip(ys, longs):
        half = 11 if lng else 6
        cv.create_line(cx - half, y, cx + half, y, fill=LINE, width=2)
    text(cv, cx + 14, cy - 9, "+", bold=True)
    if name:
        text(cv, cx - 16, cy, name, anchor="e", bold=True)
    return (cx, cy - 13), (cx, cy + 13)


def arrow(cv: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
          label: str = "", color: str = HOT) -> None:
    cv.create_line(x1, y1, x2, y2, fill=color, width=2, arrow="last")
    if label:
        text(cv, (x1 + x2) / 2, (y1 + y2) / 2 - 8, label, small=True, color=color)


def square_wave(cv: tk.Canvas, x: float, y_top: float, y_bot: float, w: float,
                duty: float = 0.5, periods: int = 2, color: str = HOT) -> None:
    """方波，y_top 為高準位線、y_bot 為低準位線。"""
    pw = w / periods
    hi = pw * max(0.0, min(1.0, duty))
    px = x
    pts = [px, y_bot]
    for _ in range(periods):
        pts += [px, y_top, px + hi, y_top, px + hi, y_bot, px + pw, y_bot]
        px += pw
    cv.create_line(*pts, fill=color, width=2)
