"""單位系統：SI 字首換算、工程記號格式化，以及可切換單位的 ValueEntry 元件。

設計重點：
  - 所有數值對外一律以「基本單位」（Ω / V / A / F / H / Hz / W / s）為準，
    UI 只是換上不同字首；計算引擎拿到的永遠是基本單位的 float。
  - ValueEntry = 數值輸入框 + 單位下拉選單，get_base() 回傳基本單位值。
"""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk

import theme

# SI 字首對基本單位的倍率。內部 key 用 ASCII 'u' 不會出現，顯示一律用 'µ'。
PREFIX_FACTOR = {
    "T": 1e12,
    "G": 1e9,
    "M": 1e6,
    "k": 1e3,
    "": 1.0,
    "m": 1e-3,
    "µ": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}

# 工程記號階梯（每 1000 一階），由大到小，用於 format_eng 自動挑字首。
_ENG_LADDER = [
    ("T", 1e12), ("G", 1e9), ("M", 1e6), ("k", 1e3), ("", 1.0),
    ("m", 1e-3), ("µ", 1e-6), ("n", 1e-9), ("p", 1e-12), ("f", 1e-15),
]


@dataclass
class Quantity:
    key: str
    name: str          # 中文名
    base: str          # 基本單位符號，例如 "Ω"
    prefixes: list[str]  # 允許的字首（由大到小）

    def unit_labels(self) -> list[str]:
        return [pfx + self.base for pfx in self.prefixes]

    def factor_of(self, label: str) -> float:
        for pfx in self.prefixes:
            if pfx + self.base == label:
                return PREFIX_FACTOR[pfx]
        raise KeyError(label)


# 各物理量與其常用字首範圍。
QUANTITIES: dict[str, Quantity] = {
    "resistance": Quantity("resistance", "電阻", "Ω", ["G", "M", "k", "", "m", "µ", "n", "p"]),
    "voltage":    Quantity("voltage", "電壓", "V", ["k", "", "m", "µ", "n"]),
    "current":    Quantity("current", "電流", "A", ["k", "", "m", "µ", "n", "p"]),
    "capacitance": Quantity("capacitance", "電容", "F", ["", "m", "µ", "n", "p", "f"]),
    "inductance": Quantity("inductance", "電感", "H", ["", "m", "µ", "n"]),
    "frequency":  Quantity("frequency", "頻率", "Hz", ["G", "M", "k", ""]),
    "power":      Quantity("power", "功率", "W", ["M", "k", "", "m", "µ"]),
    "time":       Quantity("time", "時間", "s", ["", "m", "µ", "n", "p"]),
    # 電池容量 Ah 非 SI，僅供電池續航分頁使用，不列入換算器下拉。
    "capacity":   Quantity("capacity", "電池容量", "Ah", ["k", "", "m"]),
}

# 單位換算器分頁的下拉順序。
QUANTITY_ORDER = [
    "resistance", "voltage", "current", "capacitance",
    "inductance", "frequency", "power", "time",
]


def parse_number(text: str) -> float:
    """解析使用者輸入的數字，接受一般小數與科學記號（4.7e3）。失敗丟 ValueError。"""
    cleaned = text.strip().replace("_", "")
    if not cleaned:
        raise ValueError("empty")
    return float(cleaned)


def fmt_plain(value: float, sig: int = 6) -> str:
    """把純數字格式化，去掉多餘 0；非有限值直接轉字串。"""
    if not math.isfinite(value):
        return "∞" if value > 0 else "-∞"
    return f"{value:.{sig}g}"


def format_eng(value: float, sym: str, sig: int = 4) -> str:
    """工程記號格式化：自動挑字首讓尾數落在 [1, 1000)。例如 4700 Ω -> '4.7 kΩ'。"""
    if not math.isfinite(value):
        return ("∞ " if value > 0 else "-∞ ") + sym
    if value == 0:
        return f"0 {sym}"
    neg = value < 0
    v = abs(value)
    label, factor = _ENG_LADDER[-1]  # 落在最小字首以下時的兜底
    for lab, fac in _ENG_LADDER:
        if v >= fac:
            label, factor = lab, fac
            break
    mant = v / factor
    return f"{'-' if neg else ''}{fmt_plain(mant, sig)} {label}{sym}"


class ValueEntry(tk.Frame):
    """數值 + 單位下拉的組合輸入元件。對外一律以基本單位 float 溝通。"""

    def __init__(self, parent: tk.Widget, quantity_key: str, default_text: str = "",
                 default_unit: str | None = None, on_change=None, entry_width: int = 11) -> None:
        super().__init__(parent, bg=theme.BG)
        self.q = QUANTITIES[quantity_key]
        self._labels = self.q.unit_labels()

        self.var = tk.StringVar(value=default_text)
        self.unit_var = tk.StringVar()
        if default_unit and default_unit in self._labels:
            self.unit_var.set(default_unit)
        elif self.q.base in self._labels:
            self.unit_var.set(self.q.base)
        else:
            self.unit_var.set(self._labels[0])

        self.entry = theme.make_entry(self, self.var, width=entry_width)
        self.entry.pack(side="left", ipady=3)

        combo_width = max(len(lbl) for lbl in self._labels) + 2
        self.combo = ttk.Combobox(
            self, textvariable=self.unit_var, values=self._labels,
            state="readonly", width=combo_width, font=(theme.UI, 10),
        )
        self.combo.pack(side="left", padx=(4, 0))

        self._on_change = on_change
        if on_change is not None:
            self.var.trace_add("write", lambda *_: on_change())
            self.combo.bind("<<ComboboxSelected>>", lambda _e: on_change())

    # --- 查詢 ---
    def is_blank(self) -> bool:
        return not self.var.get().strip()

    def is_invalid(self) -> bool:
        if self.is_blank():
            return False
        try:
            parse_number(self.var.get())
            return False
        except ValueError:
            return True

    def get_base(self) -> float | None:
        """回傳基本單位的值；空白或格式錯誤回 None。"""
        if self.is_blank():
            return None
        try:
            value = parse_number(self.var.get())
        except ValueError:
            return None
        return value * self.q.factor_of(self.unit_var.get())

    # --- 設定 ---
    def set_base(self, base_value: float) -> None:
        """以目前選用的單位顯示一個基本單位值。"""
        factor = self.q.factor_of(self.unit_var.get())
        self.var.set(fmt_plain(base_value / factor))

    def set_unit(self, label: str) -> None:
        if label in self._labels:
            self.unit_var.set(label)
