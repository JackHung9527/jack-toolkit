"""串列埠工具（tkinter 版）。

功能：
- 掃描並列出系統所有 COM port（含完整描述 / 廠商）
- HEX 傳送，輸入 `01 AB 99` 等大小寫與分隔混用格式
- ASCII 傳送，可選結尾 None / \\r / \\n / \\r\\n
- 連續傳送模式（間隔可調）
- 接收三分頁：ASCII / HEX / 對照（hex dump）
- HEX 與 ASCII 輸入框是 editable combobox，自動保留歷史命令
- 「停止顯示」勾選暫停 UI 更新，計數仍背景累加
- 「記錄行數」可調整接收區最大保留行數
- 工具選單內建程式設計師計算機（HEX/DEC/OCT/BIN + 位元運算）
- 快捷鍵：F5 重新掃描、Ctrl+K 開啟計算機

執行：python main.py
"""

from __future__ import annotations

import codecs
import queue
import re
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.hex_utils import (
    bytes_to_ascii_inline_segments,
    bytes_to_hex,
    parse_hex,
)

ESC_TAG = "esc"
ESC_COLOR = "#1f8acc"  # 淺藍色標示「跳脫字元」例如 \r \n \xNN，跟資料中字面字元區分

try:
    from serial import Serial, SerialException
    from serial.tools import list_ports
except ImportError:
    print("缺少 pyserial。請執行: pip install pyserial", file=sys.stderr)
    sys.exit(1)


HISTORY_MAX = 30
POLL_INTERVAL_MS = 20
MAX_FRAME_BYTES = 65536  # 依分隔符模式下，buffer 超過此值強制 flush 防止無限累積
# 三種模式涵蓋常見情境：
#   依閒置時間 50ms（預設）— 對 USB jitter 容錯較好，適合大多數情境
#   依閒置時間 1ms — 幾乎等同即時模式（USB scheduler 1ms 粒度，幾乎不會合併）
#   依分隔符 — 對有固定 framing 的協定 100% 可靠
#   即時 — 每個 OS read 就一個封包，0 ms 延遲，給需要看 raw read 邊界 / debug USB 的人
FRAME_MODES = ("依閒置時間", "依分隔符", "即時")
DEFAULT_FRAME_MODE = "依閒置時間"
DEFAULT_IDLE_MS = 50
MIN_IDLE_MS = 1
MAX_IDLE_MS = 2000
DEFAULT_TERMINATORS = ("\\r\\n", "\\n", "\\r", "\\x00")
# 截 USB hwid 只保留 VID:PID 段，砍掉 SER= LOCATION= 等
_VID_PID_RE = re.compile(r"USB\s+VID:PID=[0-9A-Fa-f]+:[0-9A-Fa-f]+", re.IGNORECASE)
BAUD_RATES = [
    "9600", "19200", "38400", "57600", "115200", "230400",
    "460800", "921600", "1200", "2400", "4800", "14400",
]
DATA_BITS = ["5", "6", "7", "8"]
PARITIES = [("None", "N"), ("Even", "E"), ("Odd", "O"), ("Mark", "M"), ("Space", "S")]
STOP_BITS = [("1", 1), ("1.5", 1.5), ("2", 2)]
ENDINGS = [("無", b""), ("\\r", b"\r"), ("\\n", b"\n"), ("\\r\\n", b"\r\n")]


@dataclass
class PortInfo:
    device: str
    label: str


class SerialReader(threading.Thread):
    """背景執行緒：把 serial bytes 推進 queue，由 UI 端 root.after() 取走。"""

    def __init__(self, ser: Serial, out_queue: "queue.Queue[bytes]") -> None:
        super().__init__(daemon=True)
        self.ser = ser
        self.queue = out_queue
        self._running = True
        self.error: Optional[str] = None

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            try:
                if self.ser is None or not self.ser.is_open:
                    break
                n = self.ser.in_waiting
                if n > 0:
                    data = self.ser.read(n)
                    if data:
                        self.queue.put(bytes(data))
                else:
                    threading.Event().wait(0.01)
            except (SerialException, OSError) as exc:
                if self._running:
                    self.error = str(exc)
                    self.queue.put(b"")
                break


class TextLineLimiter:
    """限制 Text widget 行數，超過時刪掉最舊的 batch 行。"""

    def __init__(self, widget: tk.Text, max_lines: int) -> None:
        self.widget = widget
        self.max_lines = max_lines

    def set_max(self, max_lines: int) -> None:
        self.max_lines = max_lines

    def trim(self) -> None:
        try:
            end_index = self.widget.index("end-1c")
            line_count = int(end_index.split(".")[0])
        except (tk.TclError, ValueError):
            return
        if line_count > self.max_lines:
            excess = line_count - self.max_lines
            self.widget.delete("1.0", f"{excess + 1}.0")


class ProgrammerCalculator(tk.Toplevel):
    """程式設計師計算機（HEX/DEC/OCT/BIN + 位元運算）。"""

    BIT_MASK = {8: 0xFF, 16: 0xFFFF, 32: 0xFFFFFFFF, 64: 0xFFFFFFFFFFFFFFFF}

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("程式設計師計算機")
        self.geometry("460x540")
        self.minsize(420, 500)

        self.value = 0
        self.pending_op: Optional[str] = None
        self.pending_value = 0
        self.input_buffer = "0"
        self.fresh_input = True
        self.base = 16
        self.bit_width = 32

        self._display_vars: dict[str, tk.StringVar] = {}
        self.digit_buttons: dict[str, ttk.Button] = {}
        self._build_ui()
        self._refresh()

    @property
    def mask(self) -> int:
        return self.BIT_MASK[self.bit_width]

    def _build_ui(self) -> None:
        mono = tkfont.Font(family="Consolas", size=11)

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)

        disp = ttk.LabelFrame(outer, text="顯示", padding=6)
        disp.pack(fill="x")
        for row, key in enumerate(("HEX", "DEC", "OCT", "BIN")):
            ttk.Label(disp, text=key, width=4).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="0")
            self._display_vars[key] = var
            entry = ttk.Entry(disp, textvariable=var, font=mono, state="readonly")
            entry.grid(row=row, column=1, sticky="ew", padx=(4, 0), pady=2)
        disp.columnconfigure(1, weight=1)

        mode = ttk.Frame(outer)
        mode.pack(fill="x", pady=(8, 4))
        ttk.Label(mode, text="輸入進位:").pack(side="left")
        self.base_var = tk.StringVar(value="HEX")
        base_combo = ttk.Combobox(
            mode,
            textvariable=self.base_var,
            values=["HEX", "DEC", "OCT", "BIN"],
            state="readonly",
            width=6,
        )
        base_combo.pack(side="left", padx=(4, 12))
        base_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_base_changed())

        ttk.Label(mode, text="位元寬度:").pack(side="left")
        self.bw_var = tk.StringVar(value="32")
        bw_combo = ttk.Combobox(
            mode,
            textvariable=self.bw_var,
            values=["8", "16", "32", "64"],
            state="readonly",
            width=5,
        )
        bw_combo.pack(side="left", padx=(4, 0))
        bw_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_bw_changed())

        grid = ttk.Frame(outer)
        grid.pack(fill="both", expand=True, pady=(8, 0))
        layout_btns = [
            [("AC", "fn"), ("CE", "fn"), ("Back", "fn"), ("+/-", "fn"), ("NOT", "fn")],
            [("AND", "op"), ("OR", "op"), ("XOR", "op"), ("<<", "op"), (">>", "op")],
            [("A", "d"), ("B", "d"), ("C", "d"), ("D", "d"), ("E", "d")],
            [("F", "d"), ("7", "d"), ("8", "d"), ("9", "d"), ("/", "op")],
            [("Mod", "op"), ("4", "d"), ("5", "d"), ("6", "d"), ("*", "op")],
            [("00", "d"), ("1", "d"), ("2", "d"), ("3", "d"), ("-", "op")],
            [("FF", "d"), ("0", "d"), ("=", "fn"), ("", "sp"), ("+", "op")],
        ]
        for r, row in enumerate(layout_btns):
            grid.rowconfigure(r, weight=1)
            for c, (label, kind) in enumerate(row):
                grid.columnconfigure(c, weight=1)
                if kind == "sp":
                    continue
                btn = ttk.Button(grid, text=label, command=lambda lab=label: self._on_button(lab))
                btn.grid(row=r, column=c, sticky="nsew", padx=2, pady=2, ipady=4)
                if kind == "d" and label in "0123456789ABCDEF":
                    self.digit_buttons[label] = btn

        self._sync_digit_enables()

    def _sync_digit_enables(self) -> None:
        allowed = {
            16: set("0123456789ABCDEF"),
            10: set("0123456789"),
            8: set("01234567"),
            2: set("01"),
        }[self.base]
        for k, btn in self.digit_buttons.items():
            state = ("!disabled",) if k in allowed else ("disabled",)
            btn.state(state)

    def _on_base_changed(self) -> None:
        self.base = {"HEX": 16, "DEC": 10, "OCT": 8, "BIN": 2}[self.base_var.get()]
        self.input_buffer = self._fmt(self.value, self.base)
        self.fresh_input = True
        self._sync_digit_enables()
        self._refresh()

    def _on_bw_changed(self) -> None:
        self.bit_width = int(self.bw_var.get())
        self.value &= self.mask
        self.pending_value &= self.mask
        self._refresh()

    def _on_button(self, label: str) -> None:
        if label in "0123456789ABCDEF":
            self._append_digit(label)
        elif label == "00":
            self._append_digit("0")
            self._append_digit("0")
        elif label == "FF":
            self._append_digit("F")
            self._append_digit("F")
        elif label == "AC":
            self.value = 0
            self.pending_op = None
            self.pending_value = 0
            self.input_buffer = "0"
            self.fresh_input = True
        elif label == "CE":
            self.input_buffer = "0"
            self.fresh_input = True
            self.value = 0
        elif label == "Back":
            if not self.fresh_input and len(self.input_buffer) > 1:
                self.input_buffer = self.input_buffer[:-1]
                try:
                    self.value = int(self.input_buffer, self.base) & self.mask
                except ValueError:
                    self.value = 0
            else:
                self.input_buffer = "0"
                self.fresh_input = True
                self.value = 0
        elif label == "+/-":
            self.value = ((~self.value) + 1) & self.mask
            self.input_buffer = self._fmt(self.value, self.base)
            self.fresh_input = True
        elif label == "NOT":
            self.value = (~self.value) & self.mask
            self.input_buffer = self._fmt(self.value, self.base)
            self.fresh_input = True
        elif label in ("+", "-", "*", "/", "Mod", "AND", "OR", "XOR", "<<", ">>"):
            self._commit_pending()
            self.pending_op = label
            self.pending_value = self.value
            self.fresh_input = True
        elif label == "=":
            self._commit_pending()
            self.pending_op = None
        self._refresh()

    def _append_digit(self, d: str) -> None:
        if self.fresh_input:
            self.input_buffer = d
            self.fresh_input = False
        elif self.input_buffer == "0":
            self.input_buffer = d
        else:
            self.input_buffer += d
        try:
            self.value = int(self.input_buffer, self.base) & self.mask
        except ValueError:
            pass

    def _commit_pending(self) -> None:
        if self.pending_op is None:
            return
        a = self.pending_value & self.mask
        b = self.value & self.mask
        op = self.pending_op
        try:
            if op == "+":
                r = (a + b) & self.mask
            elif op == "-":
                r = (a - b) & self.mask
            elif op == "*":
                r = (a * b) & self.mask
            elif op == "/":
                r = (a // b) if b else 0
            elif op == "Mod":
                r = (a % b) if b else 0
            elif op == "AND":
                r = a & b
            elif op == "OR":
                r = a | b
            elif op == "XOR":
                r = a ^ b
            elif op == "<<":
                r = (a << (b & (self.bit_width - 1))) & self.mask
            elif op == ">>":
                r = (a & self.mask) >> (b & (self.bit_width - 1))
            else:
                r = b
        except (OverflowError, ValueError):
            r = 0
        self.value = r & self.mask
        self.input_buffer = self._fmt(self.value, self.base)
        self.fresh_input = True

    @staticmethod
    def _fmt(v: int, base: int) -> str:
        if base == 16:
            return f"{v:X}"
        if base == 10:
            return str(v)
        if base == 8:
            return f"{v:o}"
        if base == 2:
            return f"{v:b}"
        return str(v)

    def _refresh(self) -> None:
        v = self.value & self.mask
        bw = self.bit_width
        self._display_vars["HEX"].set(f"{v:0{bw // 4}X}")
        self._display_vars["DEC"].set(str(v))
        self._display_vars["OCT"].set(f"{v:o}")
        bin_str = f"{v:0{bw}b}"
        self._display_vars["BIN"].set(" ".join(bin_str[i:i + 4] for i in range(0, len(bin_str), 4)))


class SerialApp:
    """主視窗 controller。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.ser: Optional[Serial] = None
        self.reader: Optional[SerialReader] = None
        self.rx_queue: "queue.Queue[bytes]" = queue.Queue()
        self.calc_dialog: Optional[ProgrammerCalculator] = None
        self.rx_total = 0
        self.tx_total = 0
        self.rx_packet_idx = 0
        self._rx_buffer = bytearray()
        self._rx_last_byte_time = 0.0
        self._ports: list[PortInfo] = []
        self._hex_history: list[str] = []
        self._ascii_history: list[str] = []
        self._repeat_kind: Optional[str] = None
        self._repeat_after_id: Optional[str] = None

        root.title("串列埠工具")
        root.geometry("1200x760")
        root.minsize(960, 600)

        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass

        self._build_menu()
        self._build_ui()
        self._refresh_ports()
        self._set_connected(False)
        self._poll_queue()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="結束", command=self._on_close)
        menubar.add_cascade(label="檔案(F)", menu=file_menu, underline=3)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(label="程式設計師計算機  Ctrl+K", command=self._open_calculator)
        tools_menu.add_command(label="重新掃描通訊埠  F5", command=self._refresh_ports)
        menubar.add_cascade(label="工具(T)", menu=tools_menu, underline=3)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="關於", command=self._show_about)
        menubar.add_cascade(label="說明(H)", menu=help_menu, underline=3)

        self.root.config(menu=menubar)
        self.root.bind_all("<F5>", lambda _e: self._refresh_ports())
        self.root.bind_all("<Control-k>", lambda _e: self._open_calculator())
        self.root.bind_all("<Control-K>", lambda _e: self._open_calculator())

    def _build_ui(self) -> None:
        mono = tkfont.Font(family="Consolas", size=10)

        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned)
        paned.add(left, weight=3)
        right = ttk.Frame(paned, width=400)
        paned.add(right, weight=1)

        rx_ctrl = ttk.Frame(left)
        rx_ctrl.pack(fill="x")
        ttk.Button(rx_ctrl, text="清空接收", command=self._clear_rx).pack(side="left")

        self.freeze_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(rx_ctrl, text="停止顯示", variable=self.freeze_var).pack(side="left", padx=(8, 0))
        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rx_ctrl, text="自動捲動", variable=self.autoscroll_var).pack(side="left", padx=(8, 0))

        ttk.Label(rx_ctrl, text="記錄行數:").pack(side="right", padx=(0, 4))
        self.max_lines_var = tk.IntVar(value=5000)
        max_spin = ttk.Spinbox(
            rx_ctrl,
            from_=100,
            to=100000,
            increment=500,
            textvariable=self.max_lines_var,
            width=8,
            command=self._on_max_lines_changed,
        )
        max_spin.pack(side="right")

        # 封包邊界控制：決定 RX buffer 怎麼切成一個個顯示用的封包
        frame_ctrl = ttk.Frame(left)
        frame_ctrl.pack(fill="x", pady=(2, 0))
        ttk.Label(frame_ctrl, text="封包邊界:").pack(side="left")
        self.frame_mode_var = tk.StringVar(value=DEFAULT_FRAME_MODE)
        mode_combo = ttk.Combobox(
            frame_ctrl,
            textvariable=self.frame_mode_var,
            values=list(FRAME_MODES),
            state="readonly",
            width=12,
        )
        mode_combo.pack(side="left", padx=(4, 12))
        mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_frame_mode_changed())

        self.frame_term_label = ttk.Label(frame_ctrl, text="分隔符:")
        self.frame_term_var = tk.StringVar(value="\\r\\n")
        self.frame_term_combo = ttk.Combobox(
            frame_ctrl,
            textvariable=self.frame_term_var,
            values=list(DEFAULT_TERMINATORS),
            width=10,
        )

        self.frame_idle_label = ttk.Label(frame_ctrl, text="閒置 (ms):")
        self.frame_idle_var = tk.IntVar(value=DEFAULT_IDLE_MS)
        self.frame_idle_spin = ttk.Spinbox(
            frame_ctrl,
            from_=MIN_IDLE_MS,
            to=MAX_IDLE_MS,
            increment=1,
            textvariable=self.frame_idle_var,
            width=6,
        )

        notebook = ttk.Notebook(left)
        notebook.pack(fill="both", expand=True, pady=(4, 4))

        self.rx_ascii = self._make_text_tab(notebook, "ASCII", mono)
        self.rx_hex = self._make_text_tab(notebook, "HEX", mono)
        self.rx_both = self._make_text_tab(notebook, "對照", mono)

        self.ascii_limiter = TextLineLimiter(self.rx_ascii, self.max_lines_var.get())
        self.hex_limiter = TextLineLimiter(self.rx_hex, self.max_lines_var.get())
        self.both_limiter = TextLineLimiter(self.rx_both, self.max_lines_var.get())

        # 替 ASCII 與 對照 兩個 widget 設「跳脫字元淺藍色」tag
        for w in (self.rx_ascii, self.rx_both):
            w.tag_configure(ESC_TAG, foreground=ESC_COLOR)

        cnt_row = ttk.Frame(left)
        cnt_row.pack(fill="x")
        self.rx_count_var = tk.StringVar(value="接收: 0 bytes")
        self.tx_count_var = tk.StringVar(value="發送: 0 bytes")
        ttk.Label(cnt_row, textvariable=self.rx_count_var).pack(side="left")
        ttk.Label(cnt_row, textvariable=self.tx_count_var).pack(side="left", padx=(20, 0))

        hex_box = ttk.LabelFrame(right, text="HEX", padding=6)
        hex_box.pack(fill="x", pady=(0, 6))
        self.hex_input_var = tk.StringVar()
        self.hex_input = ttk.Combobox(
            hex_box,
            textvariable=self.hex_input_var,
            font=mono,
            values=[],
        )
        self.hex_input.pack(fill="x")
        self.hex_input.bind("<Return>", lambda _e: self._send_once("hex"))
        hex_btn_row = ttk.Frame(hex_box)
        hex_btn_row.pack(fill="x", pady=(4, 0))
        self.btn_repeat_hex = ttk.Button(
            hex_btn_row,
            text="連續傳送",
            command=lambda: self._toggle_repeat("hex"),
        )
        self.btn_repeat_hex.pack(side="right", padx=(4, 0))
        self.btn_send_hex = ttk.Button(hex_btn_row, text="單筆傳送", command=lambda: self._send_once("hex"))
        self.btn_send_hex.pack(side="right")

        ascii_box = ttk.LabelFrame(right, text="ASCII", padding=6)
        ascii_box.pack(fill="x", pady=(0, 6))
        self.ascii_input_var = tk.StringVar()
        self.ascii_input = ttk.Combobox(
            ascii_box,
            textvariable=self.ascii_input_var,
            font=mono,
            values=[],
        )
        self.ascii_input.pack(fill="x")
        self.ascii_input.bind("<Return>", lambda _e: self._send_once("ascii"))
        end_row = ttk.Frame(ascii_box)
        end_row.pack(fill="x", pady=(4, 0))
        ttk.Label(end_row, text="結尾:").pack(side="left")
        self.end_var = tk.StringVar(value=ENDINGS[3][0])
        end_combo = ttk.Combobox(
            end_row,
            textvariable=self.end_var,
            values=[name for name, _ in ENDINGS],
            state="readonly",
            width=8,
        )
        end_combo.pack(side="left", padx=(4, 0))
        self.btn_repeat_ascii = ttk.Button(
            end_row,
            text="連續傳送",
            command=lambda: self._toggle_repeat("ascii"),
        )
        self.btn_repeat_ascii.pack(side="right", padx=(4, 0))
        self.btn_send_ascii = ttk.Button(end_row, text="單筆傳送", command=lambda: self._send_once("ascii"))
        self.btn_send_ascii.pack(side="right")

        intv_row = ttk.Frame(right)
        intv_row.pack(fill="x", pady=(0, 6))
        ttk.Label(intv_row, text="連續傳送間隔 (ms):").pack(side="left")
        self.interval_var = tk.IntVar(value=1000)
        ttk.Spinbox(
            intv_row,
            from_=10,
            to=60000,
            increment=100,
            textvariable=self.interval_var,
            width=8,
        ).pack(side="left", padx=(4, 0))

        cfg_box = ttk.LabelFrame(right, text="傳輸設定", padding=6)
        cfg_box.pack(fill="x", pady=(0, 6))
        cfg_box.columnconfigure(1, weight=1)

        ttk.Label(cfg_box, text="通訊埠:").grid(row=0, column=0, sticky="w", pady=2)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(cfg_box, textvariable=self.port_var, state="readonly", width=40)
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=(4, 4), pady=2)
        ttk.Button(cfg_box, text="重新掃描", command=self._refresh_ports, width=10).grid(row=0, column=2, pady=2)

        ttk.Label(cfg_box, text="傳輸速率:").grid(row=1, column=0, sticky="w", pady=2)
        self.baud_var = tk.StringVar(value="115200")
        self.baud_combo = ttk.Combobox(cfg_box, textvariable=self.baud_var, values=BAUD_RATES)
        self.baud_combo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(4, 0), pady=2)

        ttk.Label(cfg_box, text="資料位元:").grid(row=2, column=0, sticky="w", pady=2)
        self.data_var = tk.StringVar(value="8")
        self.data_combo = ttk.Combobox(cfg_box, textvariable=self.data_var, values=DATA_BITS, state="readonly")
        self.data_combo.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(4, 0), pady=2)

        ttk.Label(cfg_box, text="檢查位元:").grid(row=3, column=0, sticky="w", pady=2)
        self.parity_var = tk.StringVar(value=PARITIES[0][0])
        self.parity_combo = ttk.Combobox(
            cfg_box,
            textvariable=self.parity_var,
            values=[n for n, _ in PARITIES],
            state="readonly",
        )
        self.parity_combo.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(4, 0), pady=2)

        ttk.Label(cfg_box, text="停止位元:").grid(row=4, column=0, sticky="w", pady=2)
        self.stop_var = tk.StringVar(value=STOP_BITS[0][0])
        self.stop_combo = ttk.Combobox(
            cfg_box,
            textvariable=self.stop_var,
            values=[n for n, _ in STOP_BITS],
            state="readonly",
        )
        self.stop_combo.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(4, 0), pady=2)

        ttk.Button(right, text="清除記錄", command=self._clear_rx).pack(fill="x", pady=(0, 4))
        self.btn_open = ttk.Button(right, text="開啟通訊埠", command=self._open_port)
        self.btn_open.pack(fill="x", pady=(0, 4))
        self.btn_close = ttk.Button(right, text="關閉通訊埠", command=self._close_port)
        self.btn_close.pack(fill="x")

        self.status_var = tk.StringVar(value="未連線")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken").pack(side="bottom", fill="x")

        self._on_frame_mode_changed()  # 初始時根據 mode 顯示對應的參數 widget

    def _on_frame_mode_changed(self) -> None:
        mode = self.frame_mode_var.get()
        # 先全部 forget，再依 mode 把該顯示的 pack 回來
        for w in (self.frame_term_label, self.frame_term_combo,
                  self.frame_idle_label, self.frame_idle_spin):
            w.pack_forget()
        if mode == "依分隔符":
            self.frame_term_label.pack(side="left", padx=(0, 4))
            self.frame_term_combo.pack(side="left")
        elif mode == "依閒置時間":
            self.frame_idle_label.pack(side="left", padx=(0, 4))
            self.frame_idle_spin.pack(side="left")
        # 切 mode 時把舊 buffer 強制 flush 當一個 frame，避免殘留
        if self._rx_buffer:
            self._render_packet(bytes(self._rx_buffer))
            self._rx_buffer.clear()

    def _make_text_tab(self, notebook: ttk.Notebook, title: str, font: tkfont.Font) -> tk.Text:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        text = tk.Text(frame, wrap="none", font=font, height=10, state="normal")
        text.configure(undo=False)
        ysb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xsb = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        text.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return text

    def _show_about(self) -> None:
        messagebox.showinfo(
            "關於",
            "串列埠工具\ntkinter + pyserial\n支援 ASCII / HEX 雙模式收發、連續傳送、程式設計師計算機。",
        )

    def _open_calculator(self) -> None:
        if self.calc_dialog is None or not self.calc_dialog.winfo_exists():
            self.calc_dialog = ProgrammerCalculator(self.root)
        self.calc_dialog.deiconify()
        self.calc_dialog.lift()
        self.calc_dialog.focus_force()

    def _refresh_ports(self) -> None:
        prev = self._selected_device()
        ports = list(list_ports.comports())
        self._ports = []
        labels: list[str] = []
        if not ports:
            self._ports.append(PortInfo("", "（找不到任何 COM port）"))
            labels.append(self._ports[0].label)
        else:
            for p in ports:
                parts = [p.device]
                if p.description and p.description != "n/a":
                    parts.append(p.description)
                tail = []
                if p.manufacturer and p.manufacturer != "n/a" and (
                    not p.description or p.manufacturer not in p.description
                ):
                    tail.append(f"[{p.manufacturer}]")
                if p.hwid and p.hwid != "n/a":
                    m = _VID_PID_RE.search(p.hwid)
                    short = m.group(0) if m else p.hwid
                    tail.append(f"{{{short}}}")
                label = " - ".join(parts[:2])
                if tail:
                    label += "  " + "  ".join(tail)
                self._ports.append(PortInfo(p.device, label))
                labels.append(label)
        self.port_combo["values"] = labels
        if prev and any(pi.device == prev for pi in self._ports):
            for pi in self._ports:
                if pi.device == prev:
                    self.port_var.set(pi.label)
                    break
        else:
            self.port_var.set(labels[0])

    def _selected_device(self) -> Optional[str]:
        label = self.port_var.get()
        for pi in self._ports:
            if pi.label == label:
                return pi.device or None
        return None

    def _ending_bytes(self) -> bytes:
        name = self.end_var.get()
        for n, b in ENDINGS:
            if n == name:
                return b
        return b""

    def _parity_code(self) -> str:
        name = self.parity_var.get()
        for n, code in PARITIES:
            if n == name:
                return code
        return "N"

    def _stop_value(self) -> float:
        name = self.stop_var.get()
        for n, v in STOP_BITS:
            if n == name:
                return v
        return 1

    def _push_history(self, kind: str, text: str) -> None:
        if not text:
            return
        history = self._hex_history if kind == "hex" else self._ascii_history
        combo = self.hex_input if kind == "hex" else self.ascii_input
        if text in history:
            history.remove(text)
        history.insert(0, text)
        del history[HISTORY_MAX:]
        combo["values"] = history

    def _open_port(self) -> None:
        if self.ser is not None and self.ser.is_open:
            return
        device = self._selected_device()
        if not device:
            messagebox.showwarning("錯誤", "請選擇 COM port")
            return
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            messagebox.showwarning("錯誤", "Baud rate 須為整數")
            return
        try:
            data_bits = int(self.data_var.get())
        except ValueError:
            messagebox.showwarning("錯誤", "Data bits 須為整數")
            return
        parity = self._parity_code()
        stop = self._stop_value()
        try:
            self.ser = Serial(
                port=device,
                baudrate=baud,
                bytesize=data_bits,
                parity=parity,
                stopbits=stop,
                timeout=0,
                write_timeout=1,
            )
        except SerialException as exc:
            messagebox.showerror("開啟失敗", str(exc))
            self.ser = None
            return
        self.reader = SerialReader(self.ser, self.rx_queue)
        self.reader.start()
        self._set_connected(True)
        self.status_var.set(f"已連線 {device}  {baud}-{data_bits}{parity}{stop}")

    def _close_port(self) -> None:
        if self._repeat_kind is not None:
            self._stop_repeat()
        if self.reader is not None:
            self.reader.stop()
            self.reader.join(0.8)
            self.reader = None
        if self.ser is not None:
            try:
                self.ser.close()
            except (SerialException, OSError):
                pass
            self.ser = None
        # 關閉時把 buffer 殘餘 flush 成最後一個 frame（避免下次 open 時看到舊資料）
        if self._rx_buffer:
            self._render_packet(bytes(self._rx_buffer))
            self._rx_buffer.clear()
        self._set_connected(False)
        self.status_var.set("未連線")

    def _set_connected(self, on: bool) -> None:
        state_cfg = ("disabled",) if on else ("!disabled",)
        state_send = ("!disabled",) if on else ("disabled",)
        self.btn_open.state(("disabled",) if on else ("!disabled",))
        self.btn_close.state(("!disabled",) if on else ("disabled",))
        for combo in (self.port_combo, self.baud_combo, self.data_combo, self.parity_combo, self.stop_combo):
            combo.state(state_cfg)
        for btn in (self.btn_send_hex, self.btn_send_ascii, self.btn_repeat_hex, self.btn_repeat_ascii):
            btn.state(state_send)

    def _send_once(self, kind: str) -> None:
        if self.ser is None or not self.ser.is_open:
            messagebox.showwarning("錯誤", "尚未連線")
            return
        text = self.hex_input_var.get() if kind == "hex" else self.ascii_input_var.get()
        try:
            if kind == "hex":
                data = parse_hex(text)
                if not data:
                    return
            else:
                data = text.encode("latin-1", errors="replace") + self._ending_bytes()
        except ValueError as exc:
            messagebox.showwarning("HEX 格式錯誤", str(exc))
            return
        try:
            self.ser.write(data)
        except SerialException as exc:
            messagebox.showerror("發送失敗", str(exc))
            self._close_port()
            return
        self.tx_total += len(data)
        self.tx_count_var.set(f"發送: {self.tx_total} bytes")
        if self._repeat_kind is None:
            self._push_history(kind, text)

    def _toggle_repeat(self, kind: str) -> None:
        if self._repeat_kind == kind:
            self._stop_repeat()
            return
        if self.ser is None or not self.ser.is_open:
            messagebox.showwarning("錯誤", "尚未連線")
            return
        self._stop_repeat()
        self._repeat_kind = kind
        if kind == "hex":
            self.btn_repeat_hex.configure(text="停止")
        else:
            self.btn_repeat_ascii.configure(text="停止")
        self._schedule_repeat()

    def _stop_repeat(self) -> None:
        if self._repeat_after_id is not None:
            try:
                self.root.after_cancel(self._repeat_after_id)
            except tk.TclError:
                pass
            self._repeat_after_id = None
        self._repeat_kind = None
        self.btn_repeat_hex.configure(text="連續傳送")
        self.btn_repeat_ascii.configure(text="連續傳送")

    def _schedule_repeat(self) -> None:
        if self._repeat_kind is None:
            return
        try:
            interval = max(10, int(self.interval_var.get()))
        except (tk.TclError, ValueError):
            interval = 1000
        self._repeat_after_id = self.root.after(interval, self._repeat_tick)

    def _repeat_tick(self) -> None:
        if self._repeat_kind is None:
            return
        kind = self._repeat_kind
        self._send_once(kind)
        if self._repeat_kind == kind:
            self._schedule_repeat()

    def _poll_queue(self) -> None:
        rendered_any = False
        # Step 1: 把 queue 裡的 raw bytes 吃進 buffer，更新 byte 計數
        while True:
            try:
                data = self.rx_queue.get_nowait()
            except queue.Empty:
                break
            if data == b"" and self.reader is not None and self.reader.error:
                err = self.reader.error
                self.reader.error = None
                self._close_port()
                messagebox.showwarning("Serial 錯誤", err)
                self._rx_buffer.clear()
                break
            if not data:
                continue
            self.rx_total += len(data)
            self.rx_count_var.set(f"接收: {self.rx_total} bytes")
            self._rx_buffer.extend(data)
            self._rx_last_byte_time = time.monotonic()

        # Step 2: 根據封包邊界模式從 buffer 切 frame
        if not self.freeze_var.get():
            for pkt in self._extract_frames():
                self._render_packet(pkt)
                rendered_any = True

        if rendered_any and self.autoscroll_var.get():
            for w in (self.rx_ascii, self.rx_hex, self.rx_both):
                w.see("end")

        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _extract_frames(self) -> list[bytes]:
        """依目前 mode 從 self._rx_buffer 切出可顯示的 frame list（已從 buffer 移除）。"""
        if not self._rx_buffer:
            return []
        mode = self.frame_mode_var.get()
        frames: list[bytes] = []

        if mode == "即時":
            # 每個 poll tick 把 buffer 整包 flush，相當於「OS 給多少就一筆」
            frames.append(bytes(self._rx_buffer))
            self._rx_buffer.clear()
        elif mode == "依分隔符":
            term = self._parse_terminator(self.frame_term_var.get())
            if not term:
                # 分隔符無效，全部 flush 當一個 frame
                frames.append(bytes(self._rx_buffer))
                self._rx_buffer.clear()
            else:
                buf = bytes(self._rx_buffer)
                while True:
                    idx = buf.find(term)
                    if idx < 0:
                        break
                    frames.append(buf[: idx + len(term)])
                    buf = buf[idx + len(term):]
                self._rx_buffer = bytearray(buf)
                # 保險絲：buffer 太大強制 flush 避免無限累積（一直沒收到分隔符）
                if len(self._rx_buffer) >= MAX_FRAME_BYTES:
                    frames.append(bytes(self._rx_buffer))
                    self._rx_buffer.clear()
        else:
            # 依閒置時間（也是 fallback）
            try:
                idle_ms = max(MIN_IDLE_MS, int(self.frame_idle_var.get()))
            except (tk.TclError, ValueError):
                idle_ms = DEFAULT_IDLE_MS
            idle_sec = idle_ms / 1000.0
            if (time.monotonic() - self._rx_last_byte_time) >= idle_sec:
                frames.append(bytes(self._rx_buffer))
                self._rx_buffer.clear()
        return frames

    def _parse_terminator(self, text: str) -> bytes:
        """把使用者輸入的 `\\r\\n` / `\\x0A` 之類字串轉成實際 bytes。"""
        text = text.strip()
        if not text:
            return b""
        try:
            return codecs.decode(text, "unicode_escape").encode("latin-1", errors="replace")
        except (UnicodeDecodeError, ValueError):
            return b""

    def _render_packet(self, data: bytes) -> None:
        """把一個 frame 寫進三個顯示分頁。"""
        if not data:
            return
        n = len(data)
        self.rx_packet_idx += 1
        segments = bytes_to_ascii_inline_segments(data)
        hex_str = bytes_to_hex(data)
        suffix = f" (R{n}, #{self.rx_packet_idx})\n"

        for text, is_esc in segments:
            self.rx_ascii.insert("end", text, (ESC_TAG,) if is_esc else ())
        self.rx_ascii.insert("end", suffix)

        self.rx_hex.insert("end", hex_str + suffix)

        for text, is_esc in segments:
            self.rx_both.insert("end", text, (ESC_TAG,) if is_esc else ())
        self.rx_both.insert("end", "  |  " + hex_str + suffix)

        self.ascii_limiter.trim()
        self.hex_limiter.trim()
        self.both_limiter.trim()

    def _clear_rx(self) -> None:
        self.rx_total = 0
        self.rx_packet_idx = 0
        self._rx_buffer.clear()
        for w in (self.rx_ascii, self.rx_hex, self.rx_both):
            w.delete("1.0", "end")
        self.rx_count_var.set("接收: 0 bytes")

    def _on_max_lines_changed(self) -> None:
        try:
            v = int(self.max_lines_var.get())
        except (tk.TclError, ValueError):
            return
        for limiter in (self.ascii_limiter, self.hex_limiter, self.both_limiter):
            limiter.set_max(v)
            limiter.trim()

    def _on_close(self) -> None:
        self._close_port()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    SerialApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
