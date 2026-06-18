"""韌體實用包：STM32 Timer/PWM (PSC/ARR) / UART baud 誤差 / ADC 解析度。"""

from __future__ import annotations

import tkinter as tk

import engine
import schematic as sch
from base_frame import CalcFrame, Incomplete
from units import format_eng


class TimerFrame(CalcFrame):
    TITLE = "STM32 Timer / PWM (PSC / ARR)"
    HINT = "f = f_clk / ((PSC+1)(ARR+1))。由目標頻率反推 16-bit 計時器設定，保留最高解析度。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入計時器時脈與目標頻率)"

    def build(self) -> None:
        self.add_row("fclk", "計時器時脈", "frequency", "64", "MHz")
        self.add_row("ftgt", "目標 PWM 頻率", "frequency", "1", "kHz")
        self.add_plain_row("duty", "占空比", "50", "%")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        x, yt, yb, w = 45, 48, 108, 300
        sch.square_wave(cv, x, yt, yb, w, duty=0.4, periods=2)
        pw = w / 2
        sch.arrow(cv, x, 128, x + pw, 128, color=sch.GND_C)
        sch.arrow(cv, x + pw, 128, x, 128, color=sch.GND_C)
        sch.text(cv, x + pw / 2, 136, "T = 1 / f", small=True)
        sch.text(cv, x + pw * 0.2, 38, "ton = 占空比 × T", small=True, color=sch.HOT)

    def compute(self) -> None:
        fclk, ftgt = self.base("fclk", "ftgt")
        res = engine.timer_psc_arr(fclk, ftgt)
        warn = "  ★ 誤差偏大" if abs(res["error"]) > 0.01 else ""
        lines = [
            f"PSC = {res['psc']}    ARR = {res['arr']}",
            f"實際頻率 = {format_eng(res['actual'], 'Hz')}   誤差 {res['error'] * 100:+.4f} %{warn}",
            f"PWM 解析度 = {res['resolution_bits']:.2f} bit  (ARR+1 = {res['arr_plus1']} 階)",
        ]
        dtxt = self.plain["duty"].get().strip()
        if dtxt:
            try:
                duty = float(dtxt)
            except ValueError:
                raise ValueError("占空比格式錯誤")
            ccr = engine.pwm_ccr(res["arr_plus1"], duty)
            lines += [
                "",
                f"CCR = {ccr['ccr']}   實際占空比 = {ccr['actual_duty']:.4f} %",
            ]
        self.show("\n".join(lines))


class UartFrame(CalcFrame):
    TITLE = "UART Baud Rate 誤差"
    HINT = "USARTDIV = f_ck / baud，分頻取整後算實際 baud 與誤差。一般要求誤差 < 2%。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入時脈與目標 baud)"

    def build(self) -> None:
        self.over8 = tk.StringVar(value="16")
        self.add_row("fck", "USART 時脈", "frequency", "64", "MHz")
        self.add_plain_row("baud", "目標 baud", "115200", "bps")
        self.add_mode(self.over8, [("16", "OVER16"), ("8", "OVER8")], self.recompute,
                      label="過取樣：")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        yt, yb = 48, 100
        x0, bw = 30, 30
        pattern = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1]  # idle, start, D0..D7
        labels = ["", "start", "D0", "D1", "D2", "D3", "D4", "D5", "D6", "stop"]
        px = x0
        pts = [px, yt if pattern[0] else yb]
        for i, b in enumerate(pattern):
            yy = yt if b else yb
            pts += [px, yy, px + bw, yy]
            if labels[i]:
                sch.text(cv, px + bw / 2, yb + 12, labels[i], small=True,
                         color=sch.HOT if labels[i] in ("start", "stop") else sch.LBL)
            px += bw
        cv.create_line(*pts, fill=sch.LINE, width=2)
        sch.arrow(cv, x0 + bw, 36, x0 + 2 * bw, 36, color=sch.GND_C)
        sch.arrow(cv, x0 + 2 * bw, 36, x0 + bw, 36, color=sch.GND_C)
        sch.text(cv, x0 + 1.5 * bw, 28, "Tbit", small=True)

    def compute(self) -> None:
        (fck,) = self.base("fck")
        (baud,) = self.pnum("baud")
        res = engine.uart_baud(fck, baud, over8=(self.over8.get() == "8"))
        warn = "  ★ 超過 2%，可能通訊不穩" if abs(res["error"]) > 0.02 else ""
        lines = [
            f"USARTDIV  = {res['usartdiv']:.4f}  (過取樣 ×{res['osr']})",
            f"分頻整數值 = {res['div']}",
            f"實際 baud = {res['actual']:.2f} bps",
            f"誤差      = {res['error'] * 100:+.4f} %{warn}",
        ]
        self.show("\n".join(lines))


class AdcFrame(CalcFrame):
    TITLE = "ADC 解析度 / 電壓換算"
    HINT = "LSB = Vref / 2ⁿ。raw↔電壓互換；raw 範圍 0 ~ 2ⁿ−1。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入 Vref 與位元數)"

    def build(self) -> None:
        self.add_row("vref", "Vref", "voltage", "3.3", "V")
        self.add_plain_row("bits", "解析度", "12", "bit")
        self.add_plain_row("raw", "raw 碼 →電壓", "", "(可空)")
        self.add_row("volt", "電壓 →raw", "voltage", "", "V")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        ax, top, bot = 90, 30, 120
        sch.wire(cv, ax, top, ax, bot)
        sch.text(cv, ax - 8, top, "Vref", anchor="e", small=True, color=sch.HOT)
        sch.text(cv, ax - 8, bot, "0", anchor="e", small=True)
        steps = 6
        for k in range(steps + 1):
            y = bot - (bot - top) * k / steps
            sch.wire(cv, ax - 5, y, ax + 5, y, color=sch.GND_C, width=1)
        # 一階 LSB 標示
        y1 = bot
        y2 = bot - (bot - top) / steps
        sch.arrow(cv, ax + 40, y1, ax + 40, y2, color=sch.HOT)
        sch.arrow(cv, ax + 40, y2, ax + 40, y1, color=sch.HOT)
        sch.text(cv, ax + 48, (y1 + y2) / 2, "1 LSB = Vref / 2ⁿ", anchor="w", small=True, color=sch.HOT)

    def compute(self) -> None:
        (vref,) = self.base("vref")
        (bits_f,) = self.pnum("bits")
        bits = int(round(bits_f))
        lsb = engine.adc_lsb(vref, bits)
        full = 2 ** bits
        lines = [
            f"LSB     = {format_eng(lsb, 'V')}  ({format_eng(lsb, 'V')}/碼)",
            f"碼範圍  = 0 ~ {full - 1}  (滿刻度 {full} 階)",
            f"滿刻度  = {format_eng(vref, 'V')}",
        ]
        rawtxt = self.plain["raw"].get().strip()
        if rawtxt:
            try:
                raw = float(rawtxt)
            except ValueError:
                raise ValueError("raw 碼格式錯誤")
            lines += ["", f"raw {raw:g} → {format_eng(engine.adc_raw_to_volt(raw, vref, bits), 'V')}"]
        volt = self.opt_base("volt")
        if volt is not None:
            lines.append(f"{format_eng(volt, 'V')} → raw {engine.adc_volt_to_raw(volt, vref, bits)}")
        self.show("\n".join(lines))
