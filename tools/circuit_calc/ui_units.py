"""單位換算器分頁。

選一個物理量（電阻 / 電壓 / 電流 / 電容 / 電感 / 頻率 / 功率 / 時間），
輸入一個數值與來源單位，列出該物理量所有字首的等值，外加工程記號。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import theme
from units import PREFIX_FACTOR, QUANTITIES, QUANTITY_ORDER, fmt_plain, format_eng, parse_number


class UnitsFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=theme.BG)
        # 物理量下拉的顯示字串 -> key
        self._disp_to_key: dict[str, str] = {}
        for key in QUANTITY_ORDER:
            q = QUANTITIES[key]
            self._disp_to_key[f"{q.name}（{q.base}）"] = key

        self.q_var = tk.StringVar()
        self.value_var = tk.StringVar(value="4.7")
        self.unit_var = tk.StringVar()
        self._build()
        # 預設電阻、kΩ
        self.q_combo.current(QUANTITY_ORDER.index("resistance"))
        self._on_quantity()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        pad = tk.Frame(self, bg=theme.BG)
        pad.grid(row=0, column=0, sticky="nsew", padx=12, pady=10)
        pad.columnconfigure(0, weight=1)
        pad.rowconfigure(4, weight=1)

        theme.title_label(pad, "單位換算器").grid(row=0, column=0, sticky="w")
        theme.hint_label(
            pad, "選物理量、輸入數值與單位，立即換算成所有 SI 字首等值。",
        ).grid(row=1, column=0, sticky="w", pady=(4, 8))

        qrow = tk.Frame(pad, bg=theme.BG)
        qrow.grid(row=2, column=0, sticky="w", pady=(0, 4))
        tk.Label(qrow, text="物理量：", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 11), width=8, anchor="e").pack(side="left", padx=(0, 8))
        self.q_combo = ttk.Combobox(
            qrow, textvariable=self.q_var, values=list(self._disp_to_key.keys()),
            state="readonly", width=14, font=(theme.UI, 10),
        )
        self.q_combo.pack(side="left")
        self.q_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_quantity())

        vrow = tk.Frame(pad, bg=theme.BG)
        vrow.grid(row=3, column=0, sticky="w", pady=(2, 8))
        tk.Label(vrow, text="數值：", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 11), width=8, anchor="e").pack(side="left", padx=(0, 8))
        ent = theme.make_entry(vrow, self.value_var, width=14)
        ent.pack(side="left", ipady=3)
        self.focus_widget = ent
        self.value_var.trace_add("write", lambda *_: self._recompute())
        self.unit_combo = ttk.Combobox(
            vrow, textvariable=self.unit_var, state="readonly", width=8, font=(theme.UI, 10),
        )
        self.unit_combo.pack(side="left", padx=(4, 0))
        self.unit_combo.bind("<<ComboboxSelected>>", lambda _e: self._recompute())

        self.out = theme.make_result_text(pad, height=13)
        self.out.grid(row=4, column=0, sticky="nsew", pady=(2, 0))

    def _current_quantity(self):
        return QUANTITIES[self._disp_to_key[self.q_var.get()]]

    def _on_quantity(self) -> None:
        q = self._current_quantity()
        labels = q.unit_labels()
        self.unit_combo.configure(values=labels)
        # 預設選基本單位（若有），否則第一個。
        self.unit_var.set(q.base if q.base in labels else labels[0])
        self._recompute()

    def _recompute(self) -> None:
        q = self._current_quantity()
        text = self.value_var.get().strip()
        if not text:
            theme.set_text(self.out, "(請輸入數值)")
            return
        try:
            value = parse_number(text)
        except ValueError:
            theme.set_text(self.out, "數值格式錯誤")
            return
        from_label = self.unit_var.get()
        base_value = value * q.factor_of(from_label)

        width = max(len(lbl) for lbl in q.unit_labels())
        lines = [
            f"{fmt_plain(value)} {from_label} = {fmt_plain(base_value)} {q.base}（基本單位）",
            "",
        ]
        for pfx in q.prefixes:
            label = pfx + q.base
            converted = base_value / PREFIX_FACTOR[pfx]
            mark = "  ←" if label == from_label else ""
            lines.append(f"  {label.rjust(width)} : {fmt_plain(converted)}{mark}")
        lines.append("")
        lines.append(f"  工程記號 : {format_eng(base_value, q.base)}")
        theme.set_text(self.out, "\n".join(lines))
