"""接線圖分頁 — 用 tkinter Canvas 畫 NUCLEO-G071RB Phase 1 的接線示意。

顯示要素：
    - NUCLEO 板輪廓 + 板載 ST-Link USB（接 PC）
    - G071RB MCU 區塊 + Phase 1 啟用的腳位（PA2/PA3 VCP、PA5 LD4、
      PC13 B1、PB8 SCL、PB9 SDA）
    - 4.7k pull-up 從 PB8/PB9 拉到 3V3
    - DUT 端 (SCL/SDA/GND)
    - Arduino header 對照（PB8=D15, PB9=D14）

連線狀態（連到才知道）會用顏色點亮 ST-Link 那條線。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


COLOR_BOARD       = "#e8eff7"
COLOR_BOARD_EDGE  = "#5a78a8"
COLOR_MCU         = "#f3e9d8"
COLOR_MCU_EDGE    = "#8a6d2a"
COLOR_PIN_ACTIVE  = "#1a7f37"
COLOR_PIN_INACTIVE= "#888888"
COLOR_WIRE        = "#2d4a8a"
COLOR_WIRE_HOT    = "#c34a00"        # 連線中顏色
COLOR_PULLUP      = "#b8860b"
COLOR_DUT         = "#fff4d1"
COLOR_DUT_EDGE    = "#a07a18"
COLOR_PC          = "#dcefff"
COLOR_PC_EDGE     = "#3a6aa8"


class PinoutTab(ttk.Frame):
    def __init__(self, master: tk.Misc, get_connected: Callable[[], bool]) -> None:
        super().__init__(master)
        self._get_connected = get_connected

        # 上方說明
        hdr = ttk.Frame(self)
        hdr.pack(side="top", fill="x", padx=8, pady=(8, 4))
        ttk.Label(
            hdr,
            text="CommBench Phase 1 接線圖 — STM32G071RB NUCLEO",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")
        ttk.Label(
            hdr,
            text="(Phase 1：LPUART1 VCP + I2C1 DUT)",
            foreground="#666",
        ).pack(side="left", padx=8)

        # Canvas
        self._canvas = tk.Canvas(self, bg="white", highlightthickness=0)
        self._canvas.pack(side="top", fill="both", expand=True, padx=8, pady=4)
        self._canvas.bind("<Configure>", self._on_resize)

        # 底部圖例
        self._legend = ttk.Frame(self)
        self._legend.pack(side="bottom", fill="x", padx=8, pady=(2, 8))
        self._status_var = tk.StringVar(value="● 未連線")
        ttk.Label(self._legend, textvariable=self._status_var, foreground="#666",
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(
            self._legend,
            text="    說明：綠＝Phase 1 啟用腳位　橘＝連線中　灰＝Phase 2 預留",
            foreground="#666",
        ).pack(side="left")

        self.after(300, self.refresh)

    def refresh(self) -> None:
        """重畫整張圖（外部呼叫以反映連線狀態變化）。"""
        connected = bool(self._get_connected())
        self._status_var.set("● 已連線 (VCP)" if connected else "● 未連線")
        self._draw(connected)

    # ----------------- internal -----------------

    def _on_resize(self, _event: tk.Event) -> None:
        self.refresh()

    def _draw(self, connected: bool) -> None:
        c = self._canvas
        c.delete("all")
        w = max(c.winfo_width(), 100)
        h = max(c.winfo_height(), 100)

        # 邏輯座標 1100 x 660，依視窗等比例縮放
        LOGICAL_W, LOGICAL_H = 1100.0, 660.0
        sx = w / LOGICAL_W
        sy = h / LOGICAL_H
        s = min(sx, sy)
        ox = (w - LOGICAL_W * s) / 2
        oy = (h - LOGICAL_H * s) / 2

        def L(x: float, y: float) -> tuple[float, float]:
            return (ox + x * s, oy + y * s)

        wire_color = COLOR_WIRE_HOT if connected else COLOR_WIRE
        wire_width = 3 if connected else 2

        # ===== Host PC =====
        c.create_rectangle(*L(20, 60), *L(160, 200),
                           fill=COLOR_PC, outline=COLOR_PC_EDGE, width=2)
        c.create_text(*L(90, 85), text="Host PC", font=("Segoe UI", 12, "bold"))
        c.create_text(*L(90, 108), text="(本程式)", font=("Segoe UI", 8), fill="#666")
        c.create_text(*L(90, 138), text="SCPI / VCP", font=("Consolas", 9), fill="#444")
        c.create_text(*L(90, 158), text="115200 8N1", font=("Consolas", 9), fill="#444")
        c.create_text(*L(90, 178), text="LF / CRLF", font=("Consolas", 9), fill="#444")

        # USB cable
        c.create_line(*L(160, 130), *L(225, 130), fill=wire_color, width=wire_width)
        c.create_text(*L(192, 116), text="USB", font=("Segoe UI", 9, "bold"), fill=wire_color)

        # ===== NUCLEO-G071RB board =====
        bx1, by1 = L(225, 40)
        bx2, by2 = L(845, 600)
        c.create_rectangle(bx1, by1, bx2, by2, fill=COLOR_BOARD, outline=COLOR_BOARD_EDGE, width=2)
        c.create_text(*L(535, 62), text="NUCLEO-G071RB",
                      font=("Segoe UI", 11, "bold"), fill=COLOR_BOARD_EDGE)

        # ST-Link (board top-left)
        c.create_rectangle(*L(238, 85), *L(305, 175),
                           fill="#ffffff", outline=COLOR_BOARD_EDGE)
        c.create_text(*L(272, 105), text="ST-Link", font=("Segoe UI", 8, "bold"))
        c.create_text(*L(272, 122), text="V2-1", font=("Segoe UI", 8))
        c.create_text(*L(272, 145), text="VCP", font=("Segoe UI", 8), fill="#666")
        c.create_text(*L(272, 162), text="(USB)", font=("Segoe UI", 7), fill="#888")

        # MCU
        mx1, my1 = L(450, 95)
        mx2, my2 = L(620, 380)
        c.create_rectangle(mx1, my1, mx2, my2, fill=COLOR_MCU, outline=COLOR_MCU_EDGE, width=2)
        c.create_text(*L(535, 118), text="STM32G071RB",
                      font=("Segoe UI", 10, "bold"))
        c.create_text(*L(535, 136), text="LQFP64", font=("Segoe UI", 8), fill="#666")

        # ST-Link → MCU 內部 trace (PA2/PA3 VCP)
        c.create_line(*L(305, 125), *L(450, 125), fill=wire_color,
                      width=1 + (1 if connected else 0), dash=(4, 3))
        c.create_text(*L(378, 113), text="PA2/PA3", font=("Consolas", 7),
                      fill=wire_color)
        c.create_text(*L(378, 137), text="LPUART1", font=("Consolas", 7),
                      fill=wire_color)

        # 板上 LD4 圖示
        lx, ly = L(490, 200)
        c.create_oval(lx - 10, ly - 6, lx + 10, ly + 6,
                      fill="#ffd24d" if connected else "#e8e0c0",
                      outline="#8a6d2a")
        c.create_text(*L(470, 200), text="LD4", font=("Segoe UI", 8), anchor="e")
        c.create_text(*L(510, 200), text="PA5", font=("Consolas", 7), anchor="w", fill="#888")

        # 板上 B1 按鈕
        c.create_rectangle(*L(480, 228), *L(500, 244),
                           fill="#dcdcdc", outline="#666")
        c.create_text(*L(470, 236), text="B1", font=("Segoe UI", 8), anchor="e")
        c.create_text(*L(510, 236), text="PC13", font=("Consolas", 7), anchor="w", fill="#888")

        # ===== CN6 (Arduino Power header, 板內 ST-Link 下方) =====
        cn6_pins = [
            ("1", "NC",    False),
            ("2", "IOREF", False),
            ("3", "NRST",  False),
            ("4", "+3V3",  True),
            ("5", "+5V",   False),
            ("6", "GND",   True),
            ("7", "GND",   False),
            ("8", "VIN",   False),
        ]
        cn6_x = 285
        cn6_ytop = 215
        self._draw_header(c, L, x=cn6_x, y_top=cn6_ytop, n_pins=8,
                          pins=cn6_pins, name="CN6",
                          subtitle="(Arduino Power)",
                          highlight_color=wire_color)

        # ===== CN5 (Arduino Digital high header, 板內右側) =====
        cn5_pins = [
            ("10", "D15  PB8",  True),
            ("9",  "D14  PB9",  True),
            ("8",  "AVDD",      False),
            ("7",  "GND",       False),
            ("6",  "AREF",      False),
            ("5",  "D13  PA12", False),
            ("4",  "D12  PA11", False),
            ("3",  "D11  PB0",  False),
            ("2",  "D10  PA7",  False),
            ("1",  "D9   PA6",  False),
        ]
        cn5_x = 705
        cn5_ytop = 95
        self._draw_header(c, L, x=cn5_x, y_top=cn5_ytop, n_pins=10,
                          pins=cn5_pins, name="CN5",
                          subtitle="(Arduino Digital)",
                          highlight_color=wire_color)

        # ===== 從 CN 拉到 DUT — 計算 active pin 中心 Y =====
        # _draw_header pin Y 公式：y_top + 39 + i*pitch + 9 + ...
        # 實際 pin center y = y_top + 30 + i*pitch + 9
        pitch = 27
        cn5_p10_y = cn5_ytop + 39 + 0 * pitch
        cn5_p9_y  = cn5_ytop + 39 + 1 * pitch
        cn6_p4_y  = cn6_ytop + 39 + 3 * pitch
        cn6_p6_y  = cn6_ytop + 39 + 5 * pitch

        # header pin box 右側邊緣 x = center + 9
        cn5_out_x = cn5_x + 9
        cn6_out_x = cn6_x + 9

        # DUT 位置：x=895~1075，Y 範圍包住 SCL → GND rail
        dut_x1, dut_x2 = 895, 1075
        dut_y1, dut_y2 = 130, 620

        # 主 bus 線：SCL/SDA 走原本 Y；3V3 rail 走 460；GND rail 走 510
        scl_y = cn5_p10_y
        sda_y = cn5_p9_y
        rail_y = 470
        gnd_y  = 510

        # SCL/SDA bus（CN5 → 4.7k → DUT）
        c.create_line(*L(cn5_out_x, scl_y), *L(dut_x1, scl_y),
                      fill=wire_color, width=wire_width)
        c.create_text(*L(820, scl_y - 11), text="SCL",
                      font=("Segoe UI", 8, "bold"), fill=wire_color)

        c.create_line(*L(cn5_out_x, sda_y), *L(dut_x1, sda_y),
                      fill=wire_color, width=wire_width)
        c.create_text(*L(820, sda_y - 11), text="SDA",
                      font=("Segoe UI", 8, "bold"), fill=wire_color)

        # +3V3 rail（CN6.4 → 往右往下 → DUT.VDD）
        c.create_line(*L(cn6_out_x, cn6_p4_y), *L(430, cn6_p4_y),
                      fill="#b04a00", width=2)
        c.create_line(*L(430, cn6_p4_y), *L(430, rail_y),
                      fill="#b04a00", width=2)
        c.create_line(*L(430, rail_y), *L(dut_x1, rail_y),
                      fill="#b04a00", width=2)
        c.create_text(*L(660, rail_y - 11), text="+3V3",
                      font=("Segoe UI", 8, "bold"), fill="#b04a00")

        # GND rail（CN6.6 → 往右往下 → DUT.GND）
        c.create_line(*L(cn6_out_x, cn6_p6_y), *L(415, cn6_p6_y),
                      fill="#444444", width=2)
        c.create_line(*L(415, cn6_p6_y), *L(415, gnd_y),
                      fill="#444444", width=2)
        c.create_line(*L(415, gnd_y), *L(dut_x1, gnd_y),
                      fill="#444444", width=2)
        c.create_text(*L(660, gnd_y - 11), text="GND",
                      font=("Segoe UI", 8, "bold"), fill="#444444")

        # ===== 4.7k pull-ups（從 SCL/SDA bus 拉到 3V3 rail）=====
        # 放在板外明顯處：x=855 / 875，垂直跨越 SCL-rail
        self._draw_resistor(c, L, x=855, y=scl_y + 6,
                            x2=855, y2=rail_y - 6, label="4.7k")
        self._draw_resistor(c, L, x=875, y=sda_y + 6,
                            x2=875, y2=rail_y - 6, label="4.7k")

        # ===== DUT block =====
        c.create_rectangle(*L(dut_x1, dut_y1), *L(dut_x2, dut_y2),
                           fill=COLOR_DUT, outline=COLOR_DUT_EDGE, width=2)
        c.create_text(*L((dut_x1 + dut_x2) / 2, dut_y1 + 25), text="DUT",
                      font=("Segoe UI", 12, "bold"))
        c.create_text(*L((dut_x1 + dut_x2) / 2, dut_y1 + 45), text="(待測 IC)",
                      font=("Segoe UI", 8), fill="#666")

        for pin_name, src_y, line_color in [
            ("SCL", scl_y,  wire_color),
            ("SDA", sda_y,  wire_color),
            ("VDD", rail_y, "#b04a00"),
            ("GND", gnd_y,  "#444444"),
        ]:
            # DUT 內接腳標籤
            c.create_text(*L(dut_x1 + 18, src_y), text=pin_name,
                          font=("Consolas", 10, "bold"), anchor="w")
            # 小接腳方塊
            c.create_rectangle(*L(dut_x1 - 4, src_y - 5),
                               *L(dut_x1 + 4, src_y + 5),
                               fill="#fff7d0", outline=COLOR_DUT_EDGE)

        # ===== Footer 提示 =====
        c.create_text(
            *L(550, 635),
            text="Phase 1 接線：CN5.10 (D15/PB8)→SCL  CN5.9 (D14/PB9)→SDA  "
                 "CN6.4 (+3V3)  CN6.6 (GND)　必須外接 4.7k 上拉到 3V3",
            font=("Segoe UI", 9), fill="#444",
        )
        c.create_text(
            *L(550, 650),
            text="Morpho CN7/CN10 同腳位亦可用；腳位來源：UM2324 NUCLEO-G071RB + CommBench_PinTable.xlsx",
            font=("Segoe UI", 8), fill="#888",
        )

    def _draw_pin(self, c: tk.Canvas, L, *, x: float, y: float, name: str,
                  func: str, side: str, active: bool, hot: bool = False) -> None:
        """畫一個腳位點（含名稱與功能標籤）。side='L'/'R'。"""
        if hot:
            fill = COLOR_WIRE_HOT
        elif active:
            fill = COLOR_PIN_ACTIVE
        else:
            fill = COLOR_PIN_INACTIVE
        px, py = L(x, y)
        c.create_oval(px - 5, py - 5, px + 5, py + 5, fill=fill, outline="")
        if side == "L":
            c.create_text(*L(x - 10, y), text=name, font=("Consolas", 9, "bold"),
                          anchor="e", fill=fill)
            c.create_text(*L(x - 55, y), text=func, font=("Segoe UI", 8),
                          anchor="e", fill="#444")
        else:
            c.create_text(*L(x + 10, y), text=name, font=("Consolas", 9, "bold"),
                          anchor="w", fill=fill)
            c.create_text(*L(x + 55, y), text=func, font=("Segoe UI", 8),
                          anchor="w", fill="#444")

    def _draw_header(self, c: tk.Canvas, L, *, x: float, y_top: float, n_pins: int,
                     pins: list[tuple[str, str, bool]], name: str,
                     subtitle: str, highlight_color: str) -> None:
        """畫垂直 connector header strip。

        x           : header 中心 X（logical）
        y_top       : header 區塊頂端 Y
        n_pins      : pin 數
        pins        : [(pin_no_str, label_str, is_active)] 由上到下
        name        : 連接器名稱（CN5 / CN6 等）
        subtitle    : 副標（Arduino Power 之類）
        highlight_color : Phase 1 active pin 的顏色
        """
        pitch = 27
        pin_box_w = 18
        pin_box_h = 18

        # 標題
        c.create_text(*L(x, y_top + 8), text=name,
                      font=("Segoe UI", 10, "bold"), fill=COLOR_BOARD_EDGE)
        c.create_text(*L(x, y_top + 22), text=subtitle,
                      font=("Segoe UI", 7), fill="#888")

        # header 邊框
        body_y1 = y_top + 30
        body_y2 = body_y1 + pitch * n_pins
        c.create_rectangle(*L(x - 14, body_y1 - 4),
                           *L(x + 14, body_y2),
                           fill="#ffffff", outline=COLOR_BOARD_EDGE, width=1)

        for i, (pin_no, label, active) in enumerate(pins):
            pin_y = body_y1 + i * pitch + 9
            # pin square
            if active:
                fill = "#cfe9d6"
                outline = COLOR_PIN_ACTIVE
                text_color = COLOR_PIN_ACTIVE
            else:
                fill = "#f3f3f3"
                outline = "#999"
                text_color = "#444"
            c.create_rectangle(*L(x - pin_box_w / 2, pin_y - pin_box_h / 2),
                               *L(x + pin_box_w / 2, pin_y + pin_box_h / 2),
                               fill=fill, outline=outline, width=1)
            c.create_text(*L(x, pin_y), text=pin_no,
                          font=("Consolas", 8, "bold"), fill=text_color)

            # 右側 label
            c.create_text(*L(x + 14, pin_y), text=label, anchor="w",
                          font=("Consolas", 8, "bold" if active else "normal"),
                          fill=text_color)

    def _draw_resistor(self, c: tk.Canvas, L, *, x: float, y: float,
                       x2: float, y2: float, label: str) -> None:
        """畫一個簡化 zigzag 電阻。目前 x==x2（純垂直）。"""
        # 直線 + 中段方塊（取代真的 zigzag，簡單清楚）
        c.create_line(*L(x, y), *L(x, y + 15), fill=COLOR_PULLUP, width=2)
        c.create_rectangle(*L(x - 8, y + 15), *L(x + 8, y2 - 15),
                           fill="#fff7e0", outline=COLOR_PULLUP, width=2)
        c.create_line(*L(x, y2 - 15), *L(x, y2), fill=COLOR_PULLUP, width=2)
        c.create_text(*L(x + 18, (y + y2) / 2), text=label,
                      font=("Segoe UI", 8, "bold"), anchor="w", fill=COLOR_PULLUP)
