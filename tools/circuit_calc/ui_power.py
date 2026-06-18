"""電源 / 熱包：穩壓器回授分壓 / LDO 功耗發熱 / 電池續航。"""

from __future__ import annotations

import tkinter as tk

import engine
import schematic as sch
from base_frame import CalcFrame, Incomplete
from units import format_eng


class RegFeedbackFrame(CalcFrame):
    TITLE = "穩壓器回授分壓"
    HINT = "Vout = Vref × (1 + R1/R2)。R1 上（Vout→FB）、R2 下（FB→GND）。"
    DIAGRAM = (390, 200)
    PROMPT = "(請輸入 Vref 與相關電阻 / 目標 Vout)"

    def build(self) -> None:
        self.mode = tk.StringVar(value="vout")
        self.add_mode(self.mode, [("vout", "求 Vout"), ("r1", "反推 R1"), ("r2", "反推 R2")],
                      self._on_mode)
        self.add_row("vref", "Vref", "voltage", "0.8", "V")
        self.add_row("vout", "目標 Vout", "voltage", "3.3", "V")
        self.add_row("r1", "R1 (上)", "resistance", "30", "kΩ")
        self.add_row("r2", "R2 (下)", "resistance", "10", "kΩ")

    def _on_mode(self) -> None:
        vis = {"vout": ("vref", "r1", "r2"), "r1": ("vref", "vout", "r2"),
               "r2": ("vref", "vout", "r1")}[self.mode.get()]
        for key in ("vref", "vout", "r1", "r2"):
            if key in vis:
                self._rows[key].grid()
            else:
                self._rows[key].grid_remove()
        self.recompute()

    def draw_diagram(self, cv: tk.Canvas) -> None:
        sch.block(cv, 24, 70, 104, 120, "穩壓器")
        vx = 180
        sch.wire(cv, 104, 84, vx, 84)
        sch.node(cv, vx, 84, "Vout", anchor="e")
        rt, rb = sch.resistor_v(cv, vx, 110, "R1")
        sch.wire(cv, vx, 84, *rt)
        fb_y = 140
        sch.wire(cv, *rb, vx, fb_y)
        sch.node(cv, vx, fb_y, "", anchor="e")
        sch.wire(cv, vx, fb_y, 104, fb_y)
        sch.text(cv, 100, fb_y - 9, "FB=Vref", anchor="e", small=True, color=sch.HOT)
        rt2, rb2 = sch.resistor_v(cv, vx, 166, "R2")
        sch.wire(cv, vx, fb_y, *rt2)
        sch.wire(cv, *rb2, vx, 186)
        sch.ground(cv, vx, 186)

    def compute(self) -> None:
        mode = self.mode.get()
        if mode == "vout":
            vref, r1, r2 = self.base("vref", "r1", "r2")
            vout = engine.reg_feedback_vout(vref, r1, r2)
            self.show(f"Vout = {format_eng(vout, 'V')}\n"
                      f"增益 = 1 + R1/R2 = {1 + r1 / r2:.6g}")
            return
        if mode == "r1":
            vref, vout, r2 = self.base("vref", "vout", "r2")
            solved = engine.reg_feedback_solve_r1(vref, vout, r2)
            name, other = "R1", ("r2", r2)
        else:
            vref, vout, r1 = self.base("vref", "vout", "r1")
            solved = engine.reg_feedback_solve_r2(vref, vout, r1)
            name, other = "R2", ("r1", r1)
        lines = [f"{name}（理論值） = {format_eng(solved, 'Ω')}"]
        for series in ("E24", "E96"):
            std = engine.nearest_e_series(solved, series)
            if name == "R1":
                check = engine.reg_feedback_vout(vref, std, other[1])
            else:
                check = engine.reg_feedback_vout(vref, other[1], std)
            lines.append(f"最接近 {series} = {format_eng(std, 'Ω')}"
                         f"  → 實際 Vout {format_eng(check, 'V')}")
        self.show("\n".join(lines))


class LdoFrame(CalcFrame):
    TITLE = "LDO 功耗 / 發熱"
    HINT = "壓差功耗 P = (Vin − Vout) × Iout。給 θJA 可估接面溫度 Tj = Tamb + P×θJA。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入 Vin、Vout、Iout)"

    def build(self) -> None:
        self.add_row("vin", "Vin", "voltage", "5", "V")
        self.add_row("vout", "Vout", "voltage", "3.3", "V")
        self.add_row("iout", "Iout", "current", "200", "mA")
        self.add_plain_row("theta", "θJA", "", "°C/W (可空)")
        self.add_plain_row("tamb", "Tamb", "25", "°C")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        sch.block(cv, 70, 58, 170, 108, "LDO")
        sch.wire(cv, 30, 78, 70, 78)
        sch.node(cv, 30, 78, "Vin", anchor="s")
        sch.wire(cv, 170, 78, 240, 78)
        sch.node(cv, 240, 78, "Vout", anchor="s")
        sch.wire(cv, 120, 108, 120, 130)
        sch.ground(cv, 120, 130)
        sch.arrow(cv, 120, 58, 120, 28, color=sch.HOT)
        sch.text(cv, 210, 28, "P = (Vin−Vout)·Iout", anchor="w", small=True, color=sch.HOT)

    def compute(self) -> None:
        vin, vout, iout = self.base("vin", "vout", "iout")
        theta = None
        ttxt = self.plain["theta"].get().strip()
        if ttxt:
            try:
                theta = float(ttxt)
            except ValueError:
                raise ValueError("θJA 格式錯誤")
        (tamb,) = self.pnum("tamb")
        res = engine.ldo_analysis(vin, vout, iout, theta_ja=theta, t_amb=tamb)
        lines = [
            f"壓差功耗 P  = {format_eng(res['p_pass'], 'W')}",
            f"效率        = {res['efficiency'] * 100:.2f} %  (≈ Vout/Vin)",
        ]
        if res["t_junction"] is not None:
            hot = "  ★ 偏高" if res["t_junction"] > 125 else ""
            lines.append(f"接面溫度 Tj = {res['t_junction']:.1f} °C{hot}")
        else:
            lines.append("接面溫度 Tj = (填 θJA 才計算)")
        self.show("\n".join(lines))


class BatteryFrame(CalcFrame):
    TITLE = "電池續航"
    HINT = "運行時間 = 容量(Ah) / 負載(A)。可用比例打折反映實際可放電量。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入電池容量與負載電流)"

    def build(self) -> None:
        self.add_row("cap", "電池容量", "capacity", "2000", "mAh")
        self.add_row("load", "負載電流", "current", "200", "mA")
        self.add_plain_row("usable", "可用比例", "80", "%")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        bt, bb = sch.battery_v(cv, 80, 78, "BAT")
        sch.wire(cv, 80, 65, 80, 48, 250, 48)
        sch.wire(cv, 80, 91, 80, 112, 250, 112)
        sch.block(cv, 250, 58, 330, 102, "負載")
        sch.wire(cv, 250, 48, 290, 48, 290, 58)
        sch.wire(cv, 250, 112, 290, 112, 290, 102)
        sch.arrow(cv, 150, 48, 200, 48, "I_load")

    def compute(self) -> None:
        cap, load = self.base("cap", "load")
        (usable_pct,) = self.pnum("usable")
        usable = usable_pct / 100.0
        res = engine.battery_life(cap, load, usable=usable)

        def fmt_hours(h: float) -> str:
            if h >= 48:
                return f"{h:.1f} 小時  (≈ {h / 24:.2f} 天)"
            mins = int(round((h - int(h)) * 60))
            return f"{h:.2f} 小時  (≈ {int(h)} 小時 {mins} 分)"

        lines = [
            f"理論續航   = {fmt_hours(res['hours'])}",
            f"可用續航   = {fmt_hours(res['usable_hours'])}  (×{usable:.2f})",
        ]
        self.show("\n".join(lines))
