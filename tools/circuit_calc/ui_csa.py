"""分流電阻電流量測：I → Rshunt 壓差 → CSA 放大 G → MCU ADC。

訊號鏈：Vshunt = I·Rshunt；Vout = G·Vshunt + Voffset；ADC 碼 = Vout / LSB。
算靈敏度、滿量程電流、每 LSB 電流解析度、指定電流的 ADC 碼與 shunt 功耗，
並支援雙向量測（輸出偏壓 Voffset，常設為 Vref/2）。

機型預設取自規格書（2026-06 查證）：
  FP130A —— 遠翔 Feeling Tech，增益由外部電阻可調，共模/供電 2.7~28V，
            CMRR 120dB，SOT23-5L，可替換 NCS213R 腳位。
  NCS213R/214R/210R/211R —— onsemi 零漂移固定增益 50/100/200/500 V/V，
            共模 −0.3~26V，供電 2.2~26V。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import engine
import schematic as sch
import theme
from base_frame import CalcFrame
from units import format_eng

# 名稱 -> (固定增益 V/V 或 None 表示可調, 說明)
AMP_PRESETS: dict[str, tuple[float | None, str]] = {
    "自訂（自行設增益）": (None, "增益 G 由你自行輸入。"),
    "FP130A（遠翔，可調增益）": (None, "FP130A：增益由外部電阻設定；共模/供電 2.7~28V、CMRR 120dB、SOT23-5L，可替換 NCS213R 腳位。"),
    "NCS213R（50 V/V）": (50.0, "onsemi NCS213R 固定增益 50 V/V；共模 −0.3~26V、零漂移。"),
    "NCS214R（100 V/V）": (100.0, "onsemi NCS214R 固定增益 100 V/V；共模 −0.3~26V、零漂移。"),
    "NCS210R（200 V/V）": (200.0, "onsemi NCS210R 固定增益 200 V/V；共模 −0.3~26V、零漂移。"),
    "NCS211R（500 V/V）": (500.0, "onsemi NCS211R 固定增益 500 V/V；共模 −0.3~26V、零漂移。"),
}
_AMP_KEYS = list(AMP_PRESETS.keys())


class CurrentSenseFrame(CalcFrame):
    TITLE = "分流電阻電流量測（Shunt → OPA → ADC）"
    HINT = "Vshunt = I·Rshunt → Vout = G·Vshunt(+偏壓) → ADC 碼 = Vout / LSB。"
    DIAGRAM = (390, 165)
    RESULT_HEIGHT = 11
    PROMPT = "(請輸入 Rshunt、增益、Vref、位元)"

    def build(self) -> None:
        # 機型預設列
        self.amp_var = tk.StringVar(value=_AMP_KEYS[1])  # 預設 FP130A
        self.amp_note = AMP_PRESETS[self.amp_var.get()][1]
        rowf = tk.Frame(self.inbox, bg=theme.BG)
        rowf.grid(row=self._claim(None), column=0, sticky="w", pady=(0, 4))
        tk.Label(rowf, text="放大器：", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 11), width=14, anchor="e").pack(side="left", padx=(0, 8))
        self.amp_combo = ttk.Combobox(rowf, textvariable=self.amp_var, values=_AMP_KEYS,
                                      state="readonly", width=22, font=(theme.UI, 10))
        self.amp_combo.pack(side="left")
        self.amp_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_amp())

        self.add_row("rshunt", "分流電阻 Rshunt", "resistance", "10", "mΩ", label_width=14)
        self.add_plain_row("gain", "放大增益 G", "50", "V/V", label_width=14)
        self.add_row("vref", "ADC Vref", "voltage", "3.3", "V", label_width=14)
        self.add_plain_row("bits", "ADC 解析度", "12", "bit", label_width=14)
        self.add_row("voffset", "輸出偏壓（雙向）", "voltage", "0", "V", label_width=14)
        self.add_row("imeas", "量測電流 I", "current", "1", "A", label_width=14)
        self.add_plain_row("code", "ADC 碼 →電流", "", "(可空)", label_width=14)

    def _on_amp(self) -> None:
        gain, note = AMP_PRESETS[self.amp_var.get()]
        self.amp_note = note
        if gain is not None:
            self.plain["gain"].set(f"{gain:g}")  # 觸發 trace 重算
        self.recompute()

    def draw_diagram(self, cv: tk.Canvas) -> None:
        y = 40
        sch.node(cv, 36, y, "VBUS", anchor="s")
        lt, rt = sch.resistor_h(cv, 120, y, "Rshunt")
        sch.wire(cv, 36, y, lt[0], y)
        sch.arrow(cv, 58, y, 92, y, "I")
        sch.wire(cv, rt[0], y, 300, y)
        sch.text(cv, 316, y, "→ 負載", anchor="w", small=True)
        # CSA 放大器方塊，兩輸入接 shunt 兩端
        sch.block(cv, 150, 95, 225, 135, "CSA ×G")
        sch.wire(cv, lt[0], y, lt[0], 108, 150, 108)
        sch.wire(cv, rt[0], y, rt[0], 122, 150, 122)
        sch.text(cv, 147, 108, "+", anchor="e", small=True, color=sch.HOT)
        sch.text(cv, 147, 122, "−", anchor="e", small=True)
        # 輸出進 MCU ADC
        sch.block(cv, 265, 95, 345, 135, "MCU ADC")
        sch.wire(cv, 225, 115, 265, 115)
        sch.node(cv, 245, 115, "Vout", anchor="s")

    def compute(self) -> None:
        rshunt, vref = self.base("rshunt", "vref")
        voffset = self.opt_base("voffset") or 0.0
        gain, bits_f = self.pnum("gain", "bits")
        bits = int(round(bits_f))
        base = engine.current_sense(rshunt, gain, vref, bits, voffset)

        lines = [f"[{self.amp_var.get()}]", self.amp_note, ""]
        lines += [
            f"輸出靈敏度  = {base['sens_v']:.4g} V/A  ({base['sens_v'] * 1000:.4g} mV/A)",
            f"ADC 靈敏度  = {base['counts_per_a']:.4g} 碼/A",
            f"電流解析度  = {format_eng(base['per_lsb'], 'A')} / LSB",
            f"滿量程電流  = {format_eng(base['i_fs_pos'], 'A')}  (Vout→Vref)",
        ]
        if voffset != 0.0:
            lines.append(f"反向滿量程  = {format_eng(abs(base['i_fs_neg']), 'A')}  (Vout→0，雙向)")

        imeas = self.opt_base("imeas")
        if imeas is not None:
            at = engine.current_sense_at(imeas, rshunt, gain, vref, bits, voffset)
            sat = "  ★ 飽和(超出 0~Vref)" if at["saturated"] else ""
            lines += [
                "",
                f"@ I = {format_eng(imeas, 'A')}：",
                f"  Vshunt = {format_eng(at['vshunt'], 'V')}  (shunt 壓降)",
                f"  Vout   = {format_eng(at['vout'], 'V')}  ({at['frac'] * 100:.1f}% FS){sat}",
                f"  ADC 碼 = {at['code']} / {base['full_count'] - 1}",
                f"  shunt 功耗 = {format_eng(at['p_shunt'], 'W')}",
            ]

        ctxt = self.plain["code"].get().strip()
        if ctxt:
            try:
                code = float(ctxt)
            except ValueError:
                raise ValueError("ADC 碼格式錯誤")
            irev = engine.current_sense_code_to_current(code, rshunt, gain, vref, bits, voffset)
            lines += ["", f"ADC 碼 {code:g} → I = {format_eng(irev, 'A')}"]

        self.show("\n".join(lines))
