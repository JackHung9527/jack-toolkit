"""PMBus 分頁 — OPERATION / ON_OFF_CONFIG / STATUS_WORD / 版本資訊。

韌體 SCPI 端對應命令：
    PMBUS:OP? <addr>            → 讀 0x01 OPERATION
    PMBUS:OP  <addr> <byte>     → 寫 0x01 OPERATION
    PMBUS:ONOFF? <addr>         → 讀 0x02 ON_OFF_CONFIG
    PMBUS:ONOFF  <addr> <byte>  → 寫 0x02 ON_OFF_CONFIG
    PMBUS:STATUS? <addr>        → 讀 0x79 STATUS_WORD (16-bit)
    PMBUS:REV? <addr>           → 讀 0x98 PMBUS_REVISION
    PMBUS:MFRREV? <addr>        → 讀 0x9B MFR_REVISION (block read)

bit-level 解碼來源：PMBus Specification Part II, Rev 1.3 §§11.1, 12.1, 12.2
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

import re

from ..core.scpi_client import ScpiClient, ScpiError


# ====== PMBus 命令碼（給 _show_write_result 顯示用）======
PMBUS_CMD_OP    = 0x01
PMBUS_CMD_ONOFF = 0x02


# ====== 韌體錯誤訊息翻譯 ======
# 韌體會回 `ERR HAL=N bus_idle=M`、`ERR PEC mismatch ...`、`ERR usage: ...` 等
# 把這些 raw text 翻成人話、給 UI 顯示

def humanize_pmbus_error(text: str) -> dict:
    """Parse 韌體 ERR 訊息成結構化資訊。

    回傳 {kind, title, detail, advice, raw}:
      - kind  : 'nack' / 'busy' / 'timeout' / 'pec' / 'usage' / 'unknown'
      - title : 一行標題（給 Decoded 區頂端紅字）
      - detail: 補充說明
      - advice: 建議下一步動作（可空）
      - raw   : 原始韌體 text
    """
    result = {
        "kind": "unknown",
        "title": "✗ 錯誤",
        "detail": text,
        "advice": "",
        "raw": text,
    }
    u = text.upper()

    if "HAL=" in u:
        hal_m = re.search(r"HAL=(\d+)", text)
        bi_m = re.search(r"bus_idle=(\d+)", text)
        hal = int(hal_m.group(1)) if hal_m else -1
        bi = int(bi_m.group(1)) if bi_m else -1

        if hal == 1:
            result["kind"] = "nack"
            if bi == 1:
                result["title"] = "✗ NACK — slave 沒有 ACK，但 bus 仍 idle"
                result["detail"] = (
                    "I2C 主機送出 START + 位址 + R/W bit，但 slave 沒有 ACK 回應。\n"
                    "常見原因：\n"
                    "  (1) Slave 位址錯（你設的 0x__ 跟 DUT 實際位址不同）\n"
                    "  (2) DUT 沒上電 / 沒接好 SCL / SDA / GND\n"
                    "  (3) PMBus device 不支援這個 command code\n"
                    "  (4) 沒接 4.7k pull-up 或上拉電壓不夠")
                result["advice"] = "先確認 slave addr 與 DUT 接線；可以按 I2C 分頁的 Scan 看看實際抓到哪些位址"
            else:
                result["title"] = "✗ NACK + bus 卡 low — slave 異常"
                result["detail"] = (
                    "Slave 沒 ACK，並且 SCL 或 SDA 還被拉 low（bus 沒回到 idle）。\n"
                    "可能 slave clock-stretch 過久卡住、或硬體問題。")
                result["advice"] = "按 I2C 分頁的 Recover bus 救一次，再試"
        elif hal == 2:
            result["kind"] = "busy"
            result["title"] = "✗ I2C peripheral BUSY"
            result["detail"] = "STM32 端的 I2C 周邊還在前一個操作中；通常 ms 內會自己清掉"
            result["advice"] = "稍候再按一次按鈕"
        elif hal == 3:
            result["kind"] = "timeout"
            result["title"] = "✗ TIMEOUT — slave 沒在時限內完成"
            if bi == 1:
                result["detail"] = "Slave 太慢或 clock-stretch 過久；bus 仍 idle"
            else:
                result["detail"] = "Slave 太慢且把 bus 拉 low 卡住"
                result["advice"] = "Recover bus 後再試"
        else:
            result["title"] = f"✗ HAL 錯誤 (code={hal})"
    elif "PEC MISMATCH" in u:
        result["kind"] = "pec"
        result["title"] = "✗ PEC 對不上 — CRC-8 驗證失敗"
        # 從原 text 抽 data/rx/calc
        m = re.search(r"data=0x(\w+).*rx=0x(\w+).*calc=0x(\w+)", text, re.I)
        if m:
            result["detail"] = (
                f"slave 回傳 data=0x{m.group(1).upper()}、PEC byte=0x{m.group(2).upper()}\n"
                f"但我們算出來應該是 0x{m.group(3).upper()}")
        else:
            result["detail"] = text
        result["advice"] = "chip 端 PEC 沒開、或我們的 CRC8 計算跟 chip 不一致；先試試關掉 PEC 看 data 對不對"
    elif "USAGE:" in u:
        result["kind"] = "usage"
        result["title"] = "✗ 命令格式錯"
        result["detail"] = text
    elif "PORT NOT OPEN" in u:
        result["kind"] = "noport"
        result["title"] = "✗ COM port 未開"
        result["detail"] = "host 跟韌體之間的 serial 連線斷了；按主視窗 Open 重連"

    return result


# ====== PMBus STATUS_WORD bit names (16-bit) ======
# Reference: PMBus Spec Part II Rev 1.3 §11.1
STATUS_WORD_BITS = [
    # (bit, name, desc)
    (15, "VOUT",            "Output voltage fault/warning"),
    (14, "IOUT/POUT",       "Output current/power fault/warning"),
    (13, "INPUT",           "Input V/I/P fault/warning"),
    (12, "MFR_SPECIFIC",    "Manufacturer-specific fault"),
    (11, "POWER_GOOD#",     "POWER_GOOD asserted negated (i.e. NOT good)"),
    (10, "FANS",            "Fan fault/warning"),
    ( 9, "OTHER",           "Some other fault (see STATUS_OTHER)"),
    ( 8, "UNKNOWN",         "Unknown fault (STATUS_BYTE bit 7)"),
    ( 7, "BUSY",            "Device busy, command rejected"),
    ( 6, "OFF",             "Unit is not providing power"),
    ( 5, "VOUT_OV",         "VOUT overvoltage fault"),
    ( 4, "IOUT_OC",         "IOUT overcurrent fault"),
    ( 3, "VIN_UV",          "VIN undervoltage fault"),
    ( 2, "TEMPERATURE",     "Temperature fault/warning"),
    ( 1, "CML",             "Comm/Memory/Logic fault"),
    ( 0, "NONE_OF_ABOVE",   "Some unknown condition"),
]


# ====== OPERATION (0x01) bit fields ======
# Reference: PMBus Spec Part II Rev 1.3 §12.1
def decode_operation(b: int) -> list[tuple[str, str]]:
    """回傳 [(field_name, value_text), ...]，給 UI 顯示。"""
    on_off = (b >> 7) & 0x01
    margin = (b >> 4) & 0x07
    trans  = (b >> 2) & 0x03

    margin_text = {
        0b000: "0 = no margin",
        0b001: "1 = margin LOW (ignore fault)",
        0b010: "2 = margin LOW (act on fault)",
        0b101: "5 = margin HIGH (ignore fault)",
        0b110: "6 = margin HIGH (act on fault)",
    }.get(margin, f"{margin} = reserved")

    trans_text = {
        0b00: "0 = use programmed TOFF_FALL/TON_RISE",
        0b01: "1 = TOFF_FALL ignored, fast turn-off",
    }.get(trans, f"{trans} = reserved")

    return [
        ("bit 7  ON",                "1 = ON" if on_off else "0 = OFF"),
        ("bits 6:4  MARGIN",         margin_text),
        ("bits 3:2  TRANSITION",     trans_text),
        ("bits 1:0  reserved",       f"{b & 0x03:02b}"),
    ]


# ====== ON_OFF_CONFIG (0x02) bit fields ======
# Reference: PMBus Spec Part II Rev 1.3 §12.2
def decode_on_off_config(b: int) -> list[tuple[str, str]]:
    return [
        ("bit 4  PowerUp",
         "1 = use OPERATION+CONTROL (PMBus mode)"
         if (b >> 4) & 1 else
         "0 = always on at power-up (legacy)"),
        ("bit 3  CmdResponse",
         "1 = obey OPERATION command"
         if (b >> 3) & 1 else
         "0 = ignore OPERATION command"),
        ("bit 2  CtrlPin",
         "1 = use CONTROL pin"
         if (b >> 2) & 1 else
         "0 = ignore CONTROL pin"),
        ("bit 1  CtrlPolarity",
         "1 = active high"
         if (b >> 1) & 1 else
         "0 = active low"),
        ("bit 0  CtrlAction",
         "1 = CONTROL OFF = TOFF_FALL ignored"
         if b & 1 else
         "0 = CONTROL OFF = use TOFF_FALL"),
    ]


class PmbusTab(ttk.Frame):
    def __init__(self, master: tk.Misc, client: ScpiClient,
                 log: Callable[[str, str], None]) -> None:
        super().__init__(master)
        self._client = client
        self._log = log
        self._busy = False
        self._build()
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        state = "normal" if connected else "disabled"
        for btn in self._action_buttons:
            btn.configure(state=state)
        self._pec_check.configure(state=state)
        # 顯眼地告訴使用者目前連線狀態 — 沒連線時所有按鈕都是 disabled，
        # ttk Vista theme 的 disabled 視覺差異很細微，需要這個 badge 補強
        if connected:
            self._conn_badge.configure(text=" ● 已連線 ", background="#1a7f37",
                                      foreground="white")
        else:
            self._conn_badge.configure(text=" ● 未連線 (請先按主視窗 Open) ",
                                      background="#c00000", foreground="white")
        # 不再做 firmware PEC state sync — checkbox 純為 UI 設定，
        # 每個 PMBus 命令送出時把 checkbox 狀態當作 PEC arg 帶過去

    # ---------------- build ----------------

    def _build(self) -> None:
        # === 連線狀態徽章（明顯紅/綠塊；ttk theme 對 disabled 按鈕不夠明顯）===
        self._conn_badge = tk.Label(self, text=" ● 未連線 ", font=("Segoe UI", 10, "bold"),
                                    background="#c00000", foreground="white",
                                    padx=8, pady=4)
        self._conn_badge.pack(side="top", anchor="w", padx=8, pady=(8, 0))

        # === 位址列 + PEC 開關 ===
        addr_row = ttk.LabelFrame(self, text="PMBus device")
        addr_row.pack(side="top", fill="x", padx=8, pady=(4, 4))
        ttk.Label(addr_row, text="Slave addr (7-bit hex):").pack(side="left", padx=(8, 4), pady=6)
        self._addr_var = tk.StringVar(value="0x40")
        ttk.Entry(addr_row, textvariable=self._addr_var, width=10,
                  font=("Consolas", 10)).pack(side="left")

        # PEC checkbox — 純 UI 設定，按下命令時即時帶到 SCPI 命令尾巴
        # 不再對韌體做 set/get；每個命令自帶 PEC bit，沒有全域狀態同步問題
        self._pec_var = tk.BooleanVar(value=True)
        self._pec_check = ttk.Checkbutton(
            addr_row, text="使用 PEC (SMBus CRC-8)", variable=self._pec_var)
        self._pec_check.pack(side="left", padx=(20, 4))

        ttk.Label(addr_row,
                  text="位址常見 0x10-0x4F；勾選與否會在下次命令送出時即時生效",
                  foreground="#888").pack(side="left", padx=8)

        # === 動作鈕區 ===
        self._action_buttons: list[ttk.Button] = []
        act = ttk.LabelFrame(self, text="Quick read")
        act.pack(side="top", fill="x", padx=8, pady=4)

        btn_specs = [
            ("Read OPERATION (0x01)",      self._on_read_op),
            ("Read ON_OFF_CONFIG (0x02)",  self._on_read_onoff),
            ("Read STATUS_WORD (0x79)",    self._on_read_status),
            ("Read PMBUS_REVISION (0x98)", self._on_read_rev),
            ("Read MFR_REVISION (0x9B)",   self._on_read_mfrrev),
        ]
        for i, (label, cb) in enumerate(btn_specs):
            b = ttk.Button(act, text=label, command=cb, width=28)
            b.grid(row=i // 2, column=i % 2, padx=4, pady=3, sticky="w")
            self._action_buttons.append(b)

        # === 寫入區 (OP / ON_OFF) ===
        wr = ttk.LabelFrame(self, text="Write")
        wr.pack(side="top", fill="x", padx=8, pady=4)

        ttk.Label(wr, text="OPERATION byte:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        self._op_write_var = tk.StringVar(value="0x80")
        ttk.Entry(wr, textvariable=self._op_write_var, width=10,
                  font=("Consolas", 10)).grid(row=0, column=1, sticky="w")
        btn_w_op = ttk.Button(wr, text="Write OP", width=12, command=self._on_write_op)
        btn_w_op.grid(row=0, column=2, padx=8)
        self._action_buttons.append(btn_w_op)
        ttk.Label(wr, text="(0x80 = ON, 0x00 = OFF)",
                  foreground="#888").grid(row=0, column=3, sticky="w", padx=8)

        ttk.Label(wr, text="ON_OFF_CONFIG byte:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        self._onoff_write_var = tk.StringVar(value="0x1E")
        ttk.Entry(wr, textvariable=self._onoff_write_var, width=10,
                  font=("Consolas", 10)).grid(row=1, column=1, sticky="w")
        btn_w_onoff = ttk.Button(wr, text="Write ON_OFF", width=12, command=self._on_write_onoff)
        btn_w_onoff.grid(row=1, column=2, padx=8)
        self._action_buttons.append(btn_w_onoff)
        ttk.Label(wr, text="(0x1E = OP+CTRL 都聽，active high；實際預設見 chip datasheet)",
                  foreground="#888").grid(row=1, column=3, sticky="w", padx=8)

        # === 解碼結果 ===
        res = ttk.LabelFrame(self, text="Decoded")
        res.pack(side="top", fill="both", expand=True, padx=8, pady=4)
        self._result_text = tk.Text(res, font=("Consolas", 10), bg="#fafafa",
                                    state="disabled", wrap="none")
        self._result_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb = ttk.Scrollbar(res, orient="vertical", command=self._result_text.yview)
        sb.pack(side="right", fill="y")
        self._result_text.configure(yscrollcommand=sb.set)

        self._result_text.tag_configure("head", font=("Consolas", 10, "bold"),
                                        foreground="#0d4488")
        self._result_text.tag_configure("ok",   foreground="#1a7f37")
        self._result_text.tag_configure("warn", foreground="#bf8700")
        self._result_text.tag_configure("err",  foreground="#c00000")
        self._result_text.tag_configure("dim",  foreground="#888")

    # ---------------- helpers ----------------

    def _parse_addr(self) -> Optional[int]:
        s = self._addr_var.get().strip()
        try:
            v = int(s, 0)
        except ValueError:
            self._log(f"addr 不是合法數字: {s!r}", "ERR")
            return None
        if not (0x08 <= v <= 0x77):
            self._log(f"addr 0x{v:02X} 超出 0x08-0x77", "ERR")
            return None
        return v

    def _parse_byte(self, var: tk.StringVar, what: str) -> Optional[int]:
        s = var.get().strip()
        try:
            v = int(s, 0)
        except ValueError:
            self._log(f"{what} 不是合法數字: {s!r}", "ERR")
            return None
        if not (0 <= v <= 0xFF):
            self._log(f"{what} 超出 0-255", "ERR")
            return None
        return v

    def _pec(self) -> bool:
        """目前 UI checkbox 狀態（每個命令送出前讀一次，作為 PEC arg）"""
        return bool(self._pec_var.get())

    def _run_bg(self, fn) -> None:
        if self._busy:
            self._log("PMBus 命令進行中，請稍候", "WARN")
            return
        self._busy = True

        def _worker():
            try:
                fn()
            finally:
                self._busy = False

        threading.Thread(target=_worker, daemon=True).start()

    def _clear_result(self) -> None:
        self._result_text.configure(state="normal")
        self._result_text.delete("1.0", "end")
        self._result_text.configure(state="disabled")

    def _append(self, text: str, tag: str = "") -> None:
        self._result_text.configure(state="normal")
        if tag:
            self._result_text.insert("end", text, tag)
        else:
            self._result_text.insert("end", text)
        self._result_text.see("end")
        self._result_text.configure(state="disabled")

    def _show_result_lines(self, lines: list[tuple[str, str]]) -> None:
        """`lines` 是 [(text, tag), ...]，依序印到結果框。"""
        self._clear_result()
        for text, tag in lines:
            self._append(text + "\n", tag)

    # ---------------- handlers ----------------

    def _on_read_op(self) -> None:
        self._log("[btn] Read OPERATION pressed", "INFO")
        addr = self._parse_addr()
        if addr is None: return
        pec_now = self._pec()

        def do():
            cmd = f"PMBUS:OP? 0x{addr:02X} {1 if pec_now else 0}"
            self._log(cmd, "TX")
            try:
                b = self._client.pmbus_op_read(addr, pec=pec_now)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._show_err(
                    str(exc), prefix="OPERATION (0x01) 讀取失敗"))
                return
            self._log(f"OPERATION = 0x{b:02X}", "RX")

            fields = decode_operation(b)
            out: list[tuple[str, str]] = [
                (f"OPERATION (0x01) = 0x{b:02X}  (binary {b:08b})", "head"),
                ("", ""),
            ]
            for name, val in fields:
                out.append((f"  {name:30s}  {val}", ""))
            on = (b >> 7) & 1
            out.extend([
                ("", ""),
                ("結論：" + ("輸出 ON" if on else "輸出 OFF"),
                 "ok" if on else "warn"),
            ])
            self.after(0, lambda: self._show_result_lines(out))

        self._run_bg(do)

    def _on_read_onoff(self) -> None:
        self._log("[btn] Read ON_OFF_CONFIG pressed", "INFO")
        addr = self._parse_addr()
        if addr is None: return
        pec_now = self._pec()

        def do():
            cmd = f"PMBUS:ONOFF? 0x{addr:02X} {1 if pec_now else 0}"
            self._log(cmd, "TX")
            try:
                b = self._client.pmbus_onoff_read(addr, pec=pec_now)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._show_err(
                    str(exc), prefix="ON_OFF_CONFIG (0x02) 讀取失敗"))
                return
            self._log(f"ON_OFF_CONFIG = 0x{b:02X}", "RX")

            fields = decode_on_off_config(b)
            out: list[tuple[str, str]] = [
                (f"ON_OFF_CONFIG (0x02) = 0x{b:02X}  (binary {b:08b})", "head"),
                ("", ""),
            ]
            for name, val in fields:
                out.append((f"  {name:25s}  {val}", ""))
            self.after(0, lambda: self._show_result_lines(out))

        self._run_bg(do)

    def _on_read_status(self) -> None:
        self._log("[btn] Read STATUS_WORD pressed", "INFO")
        addr = self._parse_addr()
        if addr is None: return
        pec_now = self._pec()

        def do():
            cmd = f"PMBUS:STATUS? 0x{addr:02X} {1 if pec_now else 0}"
            self._log(cmd, "TX")
            try:
                w = self._client.pmbus_status_word(addr, pec=pec_now)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._show_err(
                    str(exc), prefix="STATUS_WORD (0x79) 讀取失敗"))
                return
            self._log(f"STATUS_WORD = 0x{w:04X}", "RX")

            out: list[tuple[str, str]] = [
                (f"STATUS_WORD (0x79) = 0x{w:04X}  (binary {w:016b})", "head"),
                ("", ""),
            ]
            any_fault = False
            for bit, name, desc in STATUS_WORD_BITS:
                on = (w >> bit) & 1
                marker = "■" if on else "·"
                tag = "err" if on else "dim"
                out.append((f"  [{bit:2d}] {marker} {name:14s}  {desc}", tag))
                if on:
                    any_fault = True
            out.extend([
                ("", ""),
                ("結論：" + ("有 fault/warning 旗標升起 (上面 ■ 標記)"
                              if any_fault else "全 clear，無 fault"),
                 "err" if any_fault else "ok"),
            ])
            self.after(0, lambda: self._show_result_lines(out))

        self._run_bg(do)

    def _on_read_rev(self) -> None:
        self._log("[btn] Read PMBUS_REVISION pressed", "INFO")
        addr = self._parse_addr()
        if addr is None: return
        pec_now = self._pec()

        def do():
            cmd = f"PMBUS:REV? 0x{addr:02X} {1 if pec_now else 0}"
            self._log(cmd, "TX")
            try:
                raw, part1, part2 = self._client.pmbus_revision(addr, pec=pec_now)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._show_err(
                    str(exc), prefix="PMBUS_REVISION (0x98) 讀取失敗"))
                return
            self._log(f"PMBUS_REVISION = 0x{raw:02X}", "RX")

            out: list[tuple[str, str]] = [
                (f"PMBUS_REVISION (0x98) = 0x{raw:02X}", "head"),
                ("", ""),
                (f"  Part I  (spec)  rev 1.{part1}", ""),
                (f"  Part II (cmd)   rev 1.{part2}", ""),
                ("", ""),
                ("這是 PMBus spec 版本，不是 chip 韌體版本。",
                 "dim"),
                ("Chip 自家的 firmware revision 用 MFR_REVISION (0x9B)。",
                 "dim"),
            ]
            self.after(0, lambda: self._show_result_lines(out))

        self._run_bg(do)

    def _on_read_mfrrev(self) -> None:
        self._log("[btn] Read MFR_REVISION pressed", "INFO")
        addr = self._parse_addr()
        if addr is None: return
        pec_now = self._pec()

        def do():
            cmd = f"PMBUS:MFRREV? 0x{addr:02X} {1 if pec_now else 0}"
            self._log(cmd, "TX")
            try:
                data = self._client.pmbus_mfr_revision(addr, pec=pec_now)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._show_err(
                    str(exc), prefix="MFR_REVISION (0x9B) 讀取失敗"))
                return

            ascii_repr = "".join(
                chr(b) if 0x20 <= b < 0x7F else f"\\x{b:02X}"
                for b in data
            )
            hex_repr = " ".join(f"{b:02X}" for b in data)
            self._log(f"MFR_REVISION = '{ascii_repr}' ({len(data)} bytes)", "RX")

            out: list[tuple[str, str]] = [
                (f"MFR_REVISION (0x9B)  byte count = {len(data)}", "head"),
                ("", ""),
                (f"  ASCII : \"{ascii_repr}\"", "ok" if data else "warn"),
                (f"  Hex   : {hex_repr or '(none)'}", ""),
            ]
            if not data:
                out.append(
                    ("Chip 回 0 byte — 不支援 MFR_REVISION 或沒設定", "warn"))
            self.after(0, lambda: self._show_result_lines(out))

        self._run_bg(do)

    def _on_write_op(self) -> None:
        self._log("[btn] Write OP pressed", "INFO")
        addr = self._parse_addr()
        if addr is None: return
        b = self._parse_byte(self._op_write_var, "OPERATION byte")
        if b is None: return
        pec_now = self._pec()

        def do():
            cmd = f"PMBUS:OP 0x{addr:02X} 0x{b:02X} {1 if pec_now else 0}"
            self._log(cmd, "TX")
            try:
                self._client.pmbus_op_write(addr, b, pec=pec_now)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._show_write_result(
                    "OPERATION", PMBUS_CMD_OP, b, None, error=str(exc)))
                return
            self._log(f"OPERATION ← 0x{b:02X}  寫入 OK", "OK")

            # inline read-back（同一個 worker thread，不再 _run_bg 避免被 busy 擋）
            try:
                rb = self._client.pmbus_op_read(addr, pec=pec_now)
            except ScpiError as exc:
                self._log(f"OPERATION read-back 失敗: {exc}", "WARN")
                self.after(0, lambda: self._show_write_result(
                    "OPERATION", PMBUS_CMD_OP, b, None, error=f"read-back: {exc}"))
                return
            match = (rb == b)
            self._log(f"OPERATION read-back = 0x{rb:02X}  ({'MATCH' if match else 'MISMATCH'})",
                      "OK" if match else "WARN")
            self.after(0, lambda: self._show_write_result(
                "OPERATION", PMBUS_CMD_OP, b, rb, fields=decode_operation(rb)))

        self._run_bg(do)

    def _on_write_onoff(self) -> None:
        self._log("[btn] Write ON_OFF pressed", "INFO")
        addr = self._parse_addr()
        if addr is None: return
        b = self._parse_byte(self._onoff_write_var, "ON_OFF_CONFIG byte")
        if b is None: return
        pec_now = self._pec()

        def do():
            cmd = f"PMBUS:ONOFF 0x{addr:02X} 0x{b:02X} {1 if pec_now else 0}"
            self._log(cmd, "TX")
            try:
                self._client.pmbus_onoff_write(addr, b, pec=pec_now)
            except ScpiError as exc:
                self._log(str(exc), "ERR")
                self.after(0, lambda: self._show_write_result(
                    "ON_OFF_CONFIG", PMBUS_CMD_ONOFF, b, None, error=str(exc)))
                return
            self._log(f"ON_OFF_CONFIG ← 0x{b:02X}  寫入 OK", "OK")

            try:
                rb = self._client.pmbus_onoff_read(addr, pec=pec_now)
            except ScpiError as exc:
                self._log(f"ON_OFF_CONFIG read-back 失敗: {exc}", "WARN")
                self.after(0, lambda: self._show_write_result(
                    "ON_OFF_CONFIG", PMBUS_CMD_ONOFF, b, None, error=f"read-back: {exc}"))
                return
            match = (rb == b)
            self._log(f"ON_OFF_CONFIG read-back = 0x{rb:02X}  ({'MATCH' if match else 'MISMATCH'})",
                      "OK" if match else "WARN")
            self.after(0, lambda: self._show_write_result(
                "ON_OFF_CONFIG", PMBUS_CMD_ONOFF, b, rb, fields=decode_on_off_config(rb)))

        self._run_bg(do)

    def _show_err(self, msg: str, *, prefix: str = "") -> None:
        """顯示錯誤到 Decoded 區。先嘗試 humanize，無法解析就 raw print。"""
        info = humanize_pmbus_error(msg)
        out: list[tuple[str, str]] = []
        if prefix:
            out.append((prefix, "head"))
            out.append(("", ""))
        out.append((info["title"], "err"))
        out.append(("", ""))
        for line in info["detail"].split("\n"):
            out.append((f"  {line}", "warn"))
        if info["advice"]:
            out.append(("", ""))
            out.append((f"建議：{info['advice']}", "warn"))
        out.append(("", ""))
        out.append((f"原始韌體訊息：{info['raw']}", "dim"))
        self._show_result_lines(out)

    def _show_write_result(self, name: str, cmd_code: int, written: int,
                           read_back: Optional[int],
                           fields: Optional[list[tuple[str, str]]] = None,
                           error: Optional[str] = None) -> None:
        """寫入操作的結果顯示，給 Decoded 區用 — 比起只在 log 印一行 OK，這個能讓
        使用者「立刻看到 write 有沒有真的被 chip 接受」。
        """
        out: list[tuple[str, str]] = [
            (f"{name} (0x{cmd_code:02X}) 寫入操作", "head"),
            ("", ""),
            (f"  寫入值      : 0x{written:02X}  (binary {written:08b})", ""),
        ]
        if error is not None:
            info = humanize_pmbus_error(error)
            out.append(("", ""))
            out.append((info["title"], "err"))
            out.append(("", ""))
            for line in info["detail"].split("\n"):
                out.append((f"  {line}", "warn"))
            if info["advice"]:
                out.append(("", ""))
                out.append((f"建議：{info['advice']}", "warn"))
            out.append(("", ""))
            out.append((f"原始韌體訊息：{info['raw']}", "dim"))
        elif read_back is None:
            out.append((f"  狀態        : ⚠ 寫入 OK 但無法 read-back 驗證", "warn"))
        else:
            match = (read_back == written)
            out.append((f"  read-back   : 0x{read_back:02X}  (binary {read_back:08b})",
                        "ok" if match else "warn"))
            out.append(("", ""))
            if match:
                out.append(("✓ 寫入成功且 chip 套用了新值（寫入值 == read-back）", "ok"))
            else:
                out.append(("⚠ 寫入後 read-back 不同！chip 可能拒絕、或某些 bit 被遮罩 / 唯讀",
                            "warn"))
            # 若有 bit-level decoded 資訊就一起顯示，方便看 chip 實際生效的狀態
            if fields:
                out.append(("", ""))
                out.append((f"read-back 解碼：", "head"))
                for fname, fval in fields:
                    out.append((f"  {fname:30s}  {fval}", ""))
        self._show_result_lines(out)
