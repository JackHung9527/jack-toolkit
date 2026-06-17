"""CRC 計算分頁 UI（支援自訂 poly 等參數）。"""

from __future__ import annotations

import tkinter as tk

import theme
import crc_defs

CUSTOM = "自訂 (custom)"


class CrcFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=theme.BG)
        self.mode = tk.StringVar(value="text")          # text / hex
        self.model_name = tk.StringVar(value=crc_defs.MODELS[0].name)
        self.input_var = tk.StringVar(value="123456789")
        self.result_var = tk.StringVar(value="")
        self.note_var = tk.StringVar(value="")
        # 自訂參數
        self.width_var = tk.StringVar(value="8")
        self.poly_var = tk.StringVar(value="07")
        self.init_var = tk.StringVar(value="00")
        self.xorout_var = tk.StringVar(value="00")
        self.refin_var = tk.BooleanVar(value=False)
        self.refout_var = tk.BooleanVar(value=False)
        self._custom_widgets: list = []
        self._build()
        self._on_preset()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        pad = tk.Frame(self, bg=theme.BG)
        pad.grid(row=0, column=0, sticky="nsew", padx=12, pady=10)
        pad.columnconfigure(0, weight=1)

        tk.Label(pad, text="CRC 計算", bg=theme.BG, fg=theme.TEXT_PRIMARY,
                 font=(theme.UI, 16, "bold")).grid(row=0, column=0, sticky="w")

        # 輸入模式
        mrow = tk.Frame(pad, bg=theme.BG)
        mrow.grid(row=1, column=0, sticky="w", pady=(10, 2))
        tk.Label(mrow, text="輸入格式：", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        for val, label in (("text", "文字"), ("hex", "HEX 位元組")):
            tk.Radiobutton(mrow, text=label, value=val, variable=self.mode, command=self._compute,
                           bg=theme.BG, fg=theme.TEXT_PRIMARY, selectcolor=theme.SELECT_BG,
                           activebackground=theme.BG, activeforeground=theme.TEXT_PRIMARY,
                           font=(theme.UI, 10), highlightthickness=0, bd=0).pack(side="left", padx=4)

        # 資料輸入欄
        ent = tk.Entry(pad, textvariable=self.input_var, bg=theme.ENTRY_BG, fg=theme.ENTRY_FG,
                       insertbackground=theme.ENTRY_FG, relief="flat", font=(theme.MONO, 13))
        ent.grid(row=2, column=0, sticky="ew", ipady=6, pady=(2, 8))
        self.focus_widget = ent
        theme.bind_numpad_decimal_fix(ent)
        self.input_var.trace_add("write", lambda *_: self._compute())

        # 預設選擇
        prow = tk.Frame(pad, bg=theme.BG)
        prow.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        tk.Label(prow, text="預設：", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        names = [m.name for m in crc_defs.MODELS] + [CUSTOM]
        opt = tk.OptionMenu(prow, self.model_name, *names, command=lambda _v: self._on_preset())
        opt.configure(bg=theme.FN_BG, fg=theme.FN_FG, activebackground=theme.FN_HOVER,
                      activeforeground=theme.FN_FG, relief="flat", font=(theme.UI, 10),
                      highlightthickness=0, bd=0)
        opt["menu"].configure(bg=theme.ENTRY_BG, fg=theme.TEXT_PRIMARY)
        opt.pack(side="left", padx=4)

        # 參數面板（選預設時唯讀顯示，選自訂時可編輯）
        cf = tk.Frame(pad, bg=theme.PANEL)
        cf.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        for c in (1, 3, 5):
            cf.columnconfigure(c, weight=1)

        def lbl(text, r, c):
            tk.Label(cf, text=text, bg=theme.PANEL, fg=theme.TEXT_SECONDARY,
                     font=(theme.UI, 9)).grid(row=r, column=c, sticky="w", padx=(8, 2), pady=3)

        def hexent(var, r, c):
            e = tk.Entry(cf, textvariable=var, width=10, bg=theme.ENTRY_BG, fg=theme.ENTRY_FG,
                         insertbackground=theme.ENTRY_FG, relief="flat", font=(theme.MONO, 10))
            e.grid(row=r, column=c, sticky="ew", padx=(0, 8), pady=3)
            var.trace_add("write", lambda *_: self._compute())
            self._custom_widgets.append(e)
            return e

        # 位寬
        lbl("位寬", 0, 0)
        wopt = tk.OptionMenu(cf, self.width_var, "8", "16", "32", command=lambda _v: self._compute())
        wopt.configure(bg=theme.FN_BG, fg=theme.FN_FG, activebackground=theme.FN_HOVER,
                       activeforeground=theme.FN_FG, relief="flat", font=(theme.UI, 9),
                       highlightthickness=0, bd=0, width=4)
        wopt["menu"].configure(bg=theme.ENTRY_BG, fg=theme.TEXT_PRIMARY)
        wopt.grid(row=0, column=1, sticky="w", pady=3)
        self._custom_widgets.append(wopt)
        # 反射
        cb_in = tk.Checkbutton(cf, text="反射輸入", variable=self.refin_var, command=self._compute,
                               bg=theme.PANEL, fg=theme.TEXT_PRIMARY, selectcolor=theme.SELECT_BG,
                               activebackground=theme.PANEL, activeforeground=theme.TEXT_PRIMARY,
                               font=(theme.UI, 9), highlightthickness=0, bd=0)
        cb_in.grid(row=0, column=2, columnspan=2, sticky="w", padx=8)
        cb_out = tk.Checkbutton(cf, text="反射輸出", variable=self.refout_var, command=self._compute,
                                bg=theme.PANEL, fg=theme.TEXT_PRIMARY, selectcolor=theme.SELECT_BG,
                                activebackground=theme.PANEL, activeforeground=theme.TEXT_PRIMARY,
                                font=(theme.UI, 9), highlightthickness=0, bd=0)
        cb_out.grid(row=0, column=4, columnspan=2, sticky="w", padx=8)
        self._custom_widgets += [cb_in, cb_out]
        # Poly / Init / XorOut
        lbl("Poly 0x", 1, 0); hexent(self.poly_var, 1, 1)
        lbl("Init 0x", 1, 2); hexent(self.init_var, 1, 3)
        lbl("XorOut 0x", 1, 4); hexent(self.xorout_var, 1, 5)

        # 結果
        tk.Label(pad, text="CRC 結果", bg=theme.BG, fg=theme.TEXT_MUTED, font=(theme.UI, 9)).grid(
            row=5, column=0, sticky="w")
        tk.Label(pad, textvariable=self.result_var, bg=theme.BG, fg=theme.ACCENT,
                 font=(theme.MONO, 22, "bold"), anchor="w").grid(row=6, column=0, sticky="ew")
        tk.Label(pad, textvariable=self.note_var, bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=(theme.UI, 9), anchor="w", justify="left").grid(row=7, column=0, sticky="w", pady=(6, 0))

    # ---- 預設 / 自訂切換 ----
    def _on_preset(self) -> None:
        name = self.model_name.get()
        if name == CUSTOM:
            self._set_custom_state(True)
        else:
            try:
                m = crc_defs.find_model(name)
            except KeyError:
                return
            self.width_var.set(str(m.width))
            self.poly_var.set(format(m.poly, "X"))
            self.init_var.set(format(m.init, "X"))
            self.xorout_var.set(format(m.xorout, "X"))
            self.refin_var.set(m.refin)
            self.refout_var.set(m.refout)
            self._set_custom_state(False)
        self._compute()

    def _set_custom_state(self, editable: bool) -> None:
        state = "normal" if editable else "disabled"
        for w in self._custom_widgets:
            try:
                w.configure(state=state)
            except tk.TclError:
                pass

    # ---- 計算 ----
    def _build_model(self):
        name = self.model_name.get()
        if name != CUSTOM:
            return crc_defs.find_model(name)
        width = int(self.width_var.get())
        poly = int(self.poly_var.get() or "0", 16)
        init = int(self.init_var.get() or "0", 16)
        xorout = int(self.xorout_var.get() or "0", 16)
        mask = (1 << width) - 1
        return crc_defs.CrcModel("自訂", width, poly & mask, init & mask,
                                 self.refin_var.get(), self.refout_var.get(),
                                 xorout & mask, "使用者自訂參數")

    def _compute(self) -> None:
        try:
            model = self._build_model()
        except (KeyError, ValueError):
            self.result_var.set("參數錯誤")
            self.note_var.set("Poly / Init / XorOut 需為十六進位，位寬需為 8/16/32")
            return
        try:
            data = crc_defs.parse_input(self.input_var.get(), self.mode.get() == "hex")
        except ValueError as exc:
            self.result_var.set("輸入錯誤")
            self.note_var.set(str(exc))
            return
        value = crc_defs.crc_compute(model, data)
        digits = model.width // 4
        self.result_var.set("0x" + format(value, "0{}X".format(digits)) + "   (" + str(value) + ")")
        self.note_var.set(
            f"{model.name}：width={model.width}  poly=0x{model.poly:X}  init=0x{model.init:X}  "
            f"refin={model.refin}  refout={model.refout}  xorout=0x{model.xorout:X}\n"
            f"位元組數：{len(data)}"
        )

    def on_key(self, keysym: str, char: str) -> None:
        return
