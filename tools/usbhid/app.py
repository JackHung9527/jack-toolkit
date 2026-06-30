"""USB-HID 測試工具主視窗（tkinter + hidapi）。

UI 風格刻意比照 tools/serial（左側 log 三分頁 ASCII/HEX/對照、右側控制面板），
讓習慣序列埠工具的人零學習成本。HID 後端用 hidapi（import hid）。

HID 概念對應：
- 一個實體裝置在 Windows 上可能拆成多個 collection（不同 usage page），
  enumerate() 會各列一筆、各有獨立 path；自製裝置要挑 vendor-defined 那筆。
  所以開啟一律用 open_path(path)，不是 open(vid, pid)。
- Output / Feature report 的第一個 byte 是 Report ID（裝置若沒用 numbered
  report 就填 0x00）。本工具把「Report ID」獨立成欄位，payload 另外填。
- Input report 由背景 thread 以 non-blocking read 輪詢，推進 queue 給 UI 顯示；
  若裝置使用 numbered report，收到資料的第一個 byte 即為 Report ID。
"""

from __future__ import annotations

import queue
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

try:
    import hid
except ImportError:
    print("缺少 hidapi。請執行: pip install hidapi", file=sys.stderr)
    raise

HISTORY_MAX = 30
POLL_INTERVAL_MS = 20      # UI 端取 queue 的頻率
READ_POLL_SEC = 0.003      # reader thread non-blocking 之間的小睡，避免 busy spin
DEFAULT_READ_LEN = 64      # 一般 full-speed HID 報告上限即 64 bytes
HERE = Path(__file__).resolve().parent
ICO_PATH = HERE / "usbhid.ico"

# 跳脫字元（CR/LF/不可列印）在 ASCII 視圖用淺藍標示，與資料中字面字元區分
ESC_TAG = "esc"
ESC_COLOR = "#1f8acc"

# 各方向各自上色，方便一眼分辨收 / 送 / feature / 系統訊息
DIR_TAGS = {
    "IN": ("dir_in", "#1b1b1b"),     # 收到的 Input report（黑）
    "OUT": ("dir_out", "#1b6b2f"),   # 送出的 Output report（綠）
    "FGET": ("dir_feat", "#9a6a00"), # Feature get（棕）
    "FSET": ("dir_feat", "#9a6a00"), # Feature set（棕）
    "INFO": ("dir_info", "#666666"), # 系統訊息（灰）
    "ERR": ("dir_err", "#a3331f"),   # 錯誤（紅）
}


@dataclass
class HidDeviceInfo:
    path: bytes
    vid: int
    pid: int
    product: str
    manufacturer: str
    serial: str
    usage_page: int
    usage: int
    interface: int

    @property
    def label(self) -> str:
        prod = self.product or "(無名稱)"
        if len(prod) > 24:
            prod = prod[:24] + "..."
        bits = [f"{self.vid:04X}:{self.pid:04X}", prod,
                f"UP {self.usage_page:04X}/{self.usage:02X}"]
        if self.serial:
            sn = self.serial if len(self.serial) <= 16 else self.serial[:16] + "..."
            bits.append(f"SN={sn}")
        if self.interface >= 0:
            bits.append(f"if{self.interface}")
        return "  ".join(bits)


class HidReader(threading.Thread):
    """背景執行緒：以 non-blocking read 輪詢 Input report，推進 queue 給 UI 取走。"""

    def __init__(self, dev: "hid.device", read_len: int, out_queue: "queue.Queue[bytes]") -> None:
        super().__init__(daemon=True)
        self.dev = dev
        self.read_len = read_len
        self.queue = out_queue
        self._running = True
        self.error: Optional[str] = None

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            try:
                data = self.dev.read(self.read_len)
            except (OSError, ValueError) as exc:
                if self._running:
                    self.error = str(exc) or "HID read 失敗（裝置可能已拔除）"
                    self.queue.put(b"")
                break
            if data:
                self.queue.put(bytes(data))
            else:
                time.sleep(READ_POLL_SEC)


class HidApp:
    """主視窗 controller。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.dev: Optional["hid.device"] = None
        self.reader: Optional[HidReader] = None
        self.rx_queue: "queue.Queue[bytes]" = queue.Queue()
        self._devices: list[HidDeviceInfo] = []
        self._open_info: Optional[HidDeviceInfo] = None
        self._read_error_shown = False
        self._hex_history: list[str] = []
        self._ascii_history: list[str] = []
        self.rx_reports = 0
        self.rx_bytes = 0
        self.tx_reports = 0
        self.tx_bytes = 0
        self._repeat_kind: Optional[str] = None
        self._repeat_after_id: Optional[str] = None

        root.title("USB-HID 測試工具")
        root.geometry("1180x760")
        root.minsize(960, 620)

        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass
        root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 11))

        self._build_menu()
        self._build_ui()
        self._refresh_devices()
        self._set_connected(False)
        self._poll_queue()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- menu ----------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="結束", command=self._on_close)
        menubar.add_cascade(label="檔案(F)", menu=file_menu, underline=3)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(label="重新掃描裝置  F5", command=self._refresh_devices)
        tools_menu.add_command(label="裝置詳細資訊  Ctrl+I", command=self._show_device_details)
        tools_menu.add_separator()
        tools_menu.add_command(label="清除記錄", command=self._clear_rx)
        menubar.add_cascade(label="工具(T)", menu=tools_menu, underline=3)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="關於", command=self._show_about)
        menubar.add_cascade(label="說明(H)", menu=help_menu, underline=3)

        self.root.config(menu=menubar)
        self.root.bind_all("<F5>", lambda _e: self._refresh_devices())
        self.root.bind_all("<Control-i>", lambda _e: self._show_device_details())
        self.root.bind_all("<Control-I>", lambda _e: self._show_device_details())

    # ---------------- UI ----------------

    def _build_ui(self) -> None:
        mono = tkfont.Font(family="Consolas", size=10)

        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned)
        paned.add(left, weight=3)
        right = ttk.Frame(paned, width=420)
        paned.add(right, weight=1)

        # ---- 左：log 工具列 ----
        rx_ctrl = ttk.Frame(left)
        rx_ctrl.pack(fill="x")
        ttk.Button(rx_ctrl, text="清除記錄", command=self._clear_rx).pack(side="left")
        self.freeze_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(rx_ctrl, text="停止顯示", variable=self.freeze_var).pack(side="left", padx=(8, 0))
        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rx_ctrl, text="自動捲動", variable=self.autoscroll_var).pack(side="left", padx=(8, 0))

        ttk.Label(rx_ctrl, text="記錄行數:").pack(side="right", padx=(0, 4))
        self.max_lines_var = tk.IntVar(value=5000)
        ttk.Spinbox(
            rx_ctrl, from_=100, to=100000, increment=500,
            textvariable=self.max_lines_var, width=8,
            command=self._on_max_lines_changed,
        ).pack(side="right")

        # ---- 左：log 三分頁 ----
        notebook = ttk.Notebook(left)
        notebook.pack(fill="both", expand=True, pady=(4, 4))
        self.rx_ascii = self._make_text_tab(notebook, "ASCII", mono)
        self.rx_hex = self._make_text_tab(notebook, "HEX", mono)
        self.rx_both = self._make_text_tab(notebook, "對照", mono)
        for w in (self.rx_ascii, self.rx_hex, self.rx_both):
            w.tag_configure(ESC_TAG, foreground=ESC_COLOR)
            for tag, color in DIR_TAGS.values():
                w.tag_configure(tag, foreground=color)

        cnt_row = ttk.Frame(left)
        cnt_row.pack(fill="x")
        self.rx_count_var = tk.StringVar(value="收: 0 report / 0 bytes")
        self.tx_count_var = tk.StringVar(value="送: 0 report / 0 bytes")
        ttk.Label(cnt_row, textvariable=self.rx_count_var).pack(side="left")
        ttk.Label(cnt_row, textvariable=self.tx_count_var).pack(side="left", padx=(20, 0))

        # ---- 右：裝置 ----
        dev_box = ttk.LabelFrame(right, text="HID 裝置", padding=6)
        dev_box.pack(fill="x", pady=(0, 6))
        dev_box.columnconfigure(0, weight=1)
        self.dev_var = tk.StringVar()
        self.dev_combo = ttk.Combobox(dev_box, textvariable=self.dev_var, state="readonly")
        self.dev_combo.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Button(dev_box, text="重新掃描", command=self._refresh_devices).grid(
            row=1, column=0, sticky="w")
        ttk.Label(dev_box, text="讀取長度:").grid(row=1, column=1, sticky="e", padx=(8, 4))
        self.read_len_var = tk.IntVar(value=DEFAULT_READ_LEN)
        ttk.Spinbox(dev_box, from_=1, to=4096, increment=1,
                    textvariable=self.read_len_var, width=7).grid(row=1, column=2, sticky="e")
        dev_box.columnconfigure(1, weight=1)

        btn_row = ttk.Frame(dev_box)
        btn_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.btn_open = ttk.Button(btn_row, text="開啟", command=self._open_device)
        self.btn_open.pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.btn_close = ttk.Button(btn_row, text="關閉", command=self._close_device)
        self.btn_close.pack(side="left", expand=True, fill="x", padx=(3, 0))

        # ---- 右：Report ID / 補零 ----
        rid_box = ttk.LabelFrame(right, text="報告共用設定", padding=6)
        rid_box.pack(fill="x", pady=(0, 6))
        ttk.Label(rid_box, text="Report ID (HEX):").pack(side="left")
        self.report_id_var = tk.StringVar(value="00")
        ttk.Entry(rid_box, textvariable=self.report_id_var, width=5, font=mono).pack(
            side="left", padx=(4, 12))
        self.pad_enable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(rid_box, text="補零至", variable=self.pad_enable_var).pack(side="left")
        self.pad_len_var = tk.IntVar(value=DEFAULT_READ_LEN)
        ttk.Spinbox(rid_box, from_=1, to=4096, increment=1,
                    textvariable=self.pad_len_var, width=7).pack(side="left", padx=(4, 0))
        ttk.Label(rid_box, text="bytes").pack(side="left", padx=(2, 0))

        # ---- 右：Output report ----
        out_box = ttk.LabelFrame(right, text="Output Report（送出）", padding=6)
        out_box.pack(fill="x", pady=(0, 6))

        ttk.Label(out_box, text="HEX payload:").pack(anchor="w")
        self.out_hex_var = tk.StringVar()
        self.out_hex_combo = ttk.Combobox(out_box, textvariable=self.out_hex_var, font=mono, values=[])
        self.out_hex_combo.pack(fill="x")
        self.out_hex_combo.bind("<Return>", lambda _e: self._send_output("hex"))
        hex_btns = ttk.Frame(out_box)
        hex_btns.pack(fill="x", pady=(3, 6))
        self.btn_repeat_hex = ttk.Button(hex_btns, text="連續傳送",
                                         command=lambda: self._toggle_repeat("hex"))
        self.btn_repeat_hex.pack(side="right", padx=(4, 0))
        self.btn_send_hex = ttk.Button(hex_btns, text="單筆傳送",
                                       command=lambda: self._send_output("hex"))
        self.btn_send_hex.pack(side="right")

        ttk.Label(out_box, text="ASCII payload:").pack(anchor="w")
        self.out_ascii_var = tk.StringVar()
        self.out_ascii_combo = ttk.Combobox(out_box, textvariable=self.out_ascii_var, font=mono, values=[])
        self.out_ascii_combo.pack(fill="x")
        self.out_ascii_combo.bind("<Return>", lambda _e: self._send_output("ascii"))
        asc_btns = ttk.Frame(out_box)
        asc_btns.pack(fill="x", pady=(3, 0))
        self.btn_repeat_ascii = ttk.Button(asc_btns, text="連續傳送",
                                           command=lambda: self._toggle_repeat("ascii"))
        self.btn_repeat_ascii.pack(side="right", padx=(4, 0))
        self.btn_send_ascii = ttk.Button(asc_btns, text="單筆傳送",
                                         command=lambda: self._send_output("ascii"))
        self.btn_send_ascii.pack(side="right")

        intv_row = ttk.Frame(out_box)
        intv_row.pack(fill="x", pady=(6, 0))
        ttk.Label(intv_row, text="連續傳送間隔 (ms):").pack(side="left")
        self.interval_var = tk.IntVar(value=1000)
        ttk.Spinbox(intv_row, from_=10, to=60000, increment=100,
                    textvariable=self.interval_var, width=8).pack(side="left", padx=(4, 0))

        # ---- 右：Feature report ----
        feat_box = ttk.LabelFrame(right, text="Feature Report", padding=6)
        feat_box.pack(fill="x", pady=(0, 6))
        feat_top = ttk.Frame(feat_box)
        feat_top.pack(fill="x")
        ttk.Label(feat_top, text="讀取長度:").pack(side="left")
        self.feat_len_var = tk.IntVar(value=DEFAULT_READ_LEN)
        ttk.Spinbox(feat_top, from_=1, to=4096, increment=1,
                    textvariable=self.feat_len_var, width=7).pack(side="left", padx=(4, 8))
        self.btn_feat_get = ttk.Button(feat_top, text="Get Feature", command=self._get_feature)
        self.btn_feat_get.pack(side="right")

        ttk.Label(feat_box, text="Set payload (HEX):").pack(anchor="w", pady=(6, 0))
        self.feat_hex_var = tk.StringVar()
        self.feat_hex_combo = ttk.Combobox(feat_box, textvariable=self.feat_hex_var, font=mono, values=[])
        self.feat_hex_combo.pack(fill="x")
        feat_btns = ttk.Frame(feat_box)
        feat_btns.pack(fill="x", pady=(3, 0))
        self.btn_feat_set = ttk.Button(feat_btns, text="Set Feature", command=self._set_feature)
        self.btn_feat_set.pack(side="right")

        self.status_var = tk.StringVar(value="未連線")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken").pack(
            side="bottom", fill="x")

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

    # ---------------- 裝置列舉 / 開關 ----------------

    def _refresh_devices(self) -> None:
        prev = self._selected_path()
        self._devices = []
        labels: list[str] = []
        try:
            entries = hid.enumerate()
        except Exception as exc:  # hidapi 後端問題：列空清單但不讓 app 死
            entries = []
            self._log_text("ERR", f"列舉 HID 裝置失敗: {exc}")
        for e in entries:
            info = HidDeviceInfo(
                path=e.get("path", b""),
                vid=int(e.get("vendor_id", 0) or 0),
                pid=int(e.get("product_id", 0) or 0),
                product=(e.get("product_string") or "").strip(),
                manufacturer=(e.get("manufacturer_string") or "").strip(),
                serial=(e.get("serial_number") or "").strip(),
                usage_page=int(e.get("usage_page", 0) or 0),
                usage=int(e.get("usage", 0) or 0),
                interface=int(e.get("interface_number", -1) if e.get("interface_number") is not None else -1),
            )
            self._devices.append(info)
            labels.append(info.label)
        if not labels:
            labels = ["（找不到任何 HID 裝置）"]
            self._devices = []
        self.dev_combo["values"] = labels
        # 盡量保留先前選取的同一個 collection
        restored = False
        if prev is not None:
            for i, info in enumerate(self._devices):
                if info.path == prev:
                    self.dev_var.set(labels[i])
                    restored = True
                    break
        if not restored:
            self.dev_var.set(labels[0])

    def _selected_device(self) -> Optional[HidDeviceInfo]:
        label = self.dev_var.get()
        for info in self._devices:
            if info.label == label:
                return info
        return None

    def _selected_path(self) -> Optional[bytes]:
        info = self._selected_device()
        return info.path if info is not None else None

    def _open_device(self) -> None:
        if self.dev is not None:
            return
        info = self._selected_device()
        if info is None or not info.path:
            messagebox.showwarning("錯誤", "請先選擇一個 HID 裝置")
            return
        try:
            read_len = max(1, int(self.read_len_var.get()))
        except (tk.TclError, ValueError):
            read_len = DEFAULT_READ_LEN
        try:
            dev = hid.device()
            dev.open_path(info.path)
            dev.set_nonblocking(1)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "開啟失敗",
                f"{exc}\n\n常見原因：裝置被其他程式佔用、權限不足，或該 collection "
                "（鍵盤/滑鼠等系統 HID）被 OS 獨佔。",
            )
            self.dev = None
            return
        self.dev = dev
        self._open_info = info
        self._read_error_shown = False
        self.reader = HidReader(dev, read_len, self.rx_queue)
        self.reader.start()
        self._set_connected(True)
        self.status_var.set(
            f"已連線 {info.vid:04X}:{info.pid:04X}  "
            f"{info.product or '(無名稱)'}  UP {info.usage_page:04X}/{info.usage:02X}"
        )
        self._log_text("INFO", f"開啟 {info.label}")

    def _close_device(self) -> None:
        if self._repeat_kind is not None:
            self._stop_repeat()
        if self.reader is not None:
            self.reader.stop()
            self.reader.join(0.8)
            self.reader = None
        if self.dev is not None:
            try:
                self.dev.close()
            except (OSError, ValueError):
                pass
            self.dev = None
            self._log_text("INFO", "已關閉裝置")
        self._open_info = None
        self._set_connected(False)
        self.status_var.set("未連線")

    def _set_connected(self, on: bool) -> None:
        self.btn_open.state(("disabled",) if on else ("!disabled",))
        self.btn_close.state(("!disabled",) if on else ("disabled",))
        # combobox 用 configure(state=) 直接設定；不要用 .state(("readonly",))，那是
        # 「疊加」語意、不會清掉先前加上的 disabled 旗標，會害關閉後選單卡在 disabled。
        self.dev_combo.configure(state="disabled" if on else "readonly")
        send_state = ("!disabled",) if on else ("disabled",)
        for btn in (self.btn_send_hex, self.btn_send_ascii, self.btn_repeat_hex,
                    self.btn_repeat_ascii, self.btn_feat_get, self.btn_feat_set):
            btn.state(send_state)

    # ---------------- 送出 ----------------

    def _parse_report_id(self) -> Optional[int]:
        text = self.report_id_var.get().strip().replace("0x", "").replace("0X", "")
        if text == "":
            return 0
        try:
            rid = int(text, 16)
        except ValueError:
            messagebox.showwarning("Report ID 錯誤", "Report ID 須為 0~FF 的 HEX 值")
            return None
        if not 0 <= rid <= 0xFF:
            messagebox.showwarning("Report ID 錯誤", "Report ID 須在 0x00 ~ 0xFF 範圍")
            return None
        return rid

    def _apply_pad(self, buf: bytes) -> bytes:
        if not self.pad_enable_var.get():
            return buf
        try:
            pad_len = int(self.pad_len_var.get())
        except (tk.TclError, ValueError):
            return buf
        if pad_len > len(buf):
            buf = buf + bytes(pad_len - len(buf))
        return buf

    def _send_output(self, kind: str) -> bool:
        if self.dev is None:
            messagebox.showwarning("錯誤", "尚未連線")
            return False
        rid = self._parse_report_id()
        if rid is None:
            return False
        if kind == "hex":
            text = self.out_hex_var.get()
            try:
                payload = parse_hex(text)
            except ValueError as exc:
                messagebox.showwarning("HEX 格式錯誤", str(exc))
                return False
        else:
            text = self.out_ascii_var.get()
            payload = text.encode("latin-1", errors="replace")
        buf = self._apply_pad(bytes([rid]) + payload)
        try:
            n = self.dev.write(buf)
        except (OSError, ValueError) as exc:
            messagebox.showerror("發送失敗", str(exc))
            self._log_text("ERR", f"Output 寫入失敗：{exc}")
            return False
        # hidapi 的 write 失敗時回傳 -1（不丟例外），務必檢查回傳值，否則會誤報成功
        if n is not None and n < 0:
            self._log_text("ERR", "Output report 寫入失敗（hid write 回傳 -1）")
            messagebox.showerror(
                "發送失敗",
                "hid write 回傳 -1。\n\n常見原因：\n"
                "  - Report ID 不對：此裝置可能用 numbered report，需填正確 ID（例如 OTA 用 F0）。\n"
                "  - 送出長度與該 Output report 宣告長度不符。\n"
                "  - 裝置已拔除。",
            )
            return False
        self.tx_reports += 1
        self.tx_bytes += len(buf)
        self.tx_count_var.set(f"送: {self.tx_reports} report / {self.tx_bytes} bytes")
        self._log_bytes("OUT", buf)
        if self._repeat_kind is None:
            self._push_history(kind, text)
        return True

    def _toggle_repeat(self, kind: str) -> None:
        if self._repeat_kind == kind:
            self._stop_repeat()
            return
        if self.dev is None:
            messagebox.showwarning("錯誤", "尚未連線")
            return
        self._stop_repeat()
        self._repeat_kind = kind
        btn = self.btn_repeat_hex if kind == "hex" else self.btn_repeat_ascii
        btn.configure(text="停止")
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
        if not self._send_output(kind):
            self._stop_repeat()
            return
        if self._repeat_kind == kind:
            self._schedule_repeat()

    # ---------------- Feature ----------------

    def _get_feature(self) -> None:
        if self.dev is None:
            messagebox.showwarning("錯誤", "尚未連線")
            return
        rid = self._parse_report_id()
        if rid is None:
            return
        try:
            length = max(1, int(self.feat_len_var.get()))
        except (tk.TclError, ValueError):
            length = DEFAULT_READ_LEN
        try:
            data = self.dev.get_feature_report(rid, length)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Get Feature 失敗", str(exc))
            return
        self._log_bytes("FGET", bytes(data))

    def _set_feature(self) -> None:
        if self.dev is None:
            messagebox.showwarning("錯誤", "尚未連線")
            return
        rid = self._parse_report_id()
        if rid is None:
            return
        text = self.feat_hex_var.get()
        try:
            payload = parse_hex(text)
        except ValueError as exc:
            messagebox.showwarning("HEX 格式錯誤", str(exc))
            return
        buf = self._apply_pad(bytes([rid]) + payload)
        try:
            n = self.dev.send_feature_report(buf)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Set Feature 失敗", str(exc))
            return
        if n is not None and n < 0:
            self._log_text("ERR", "Set Feature 失敗（send_feature_report 回傳 -1）")
            messagebox.showerror(
                "Set Feature 失敗",
                "send_feature_report 回傳 -1。\n常見原因：Report ID 不對、payload 長度與該 Feature "
                "report 宣告長度不符、或裝置已拔除。",
            )
            return
        self._log_bytes("FSET", buf)
        self._push_history("feat", text)

    # ---------------- 歷史命令 ----------------

    def _push_history(self, kind: str, text: str) -> None:
        if not text:
            return
        if kind == "hex":
            history, combo = self._hex_history, self.out_hex_combo
        elif kind == "ascii":
            history, combo = self._ascii_history, self.out_ascii_combo
        else:
            history, combo = self._hex_history, self.feat_hex_combo
        if text in history:
            history.remove(text)
        history.insert(0, text)
        del history[HISTORY_MAX:]
        combo["values"] = history

    # ---------------- log 渲染 ----------------

    def _poll_queue(self) -> None:
        rendered = False
        while True:
            try:
                data = self.rx_queue.get_nowait()
            except queue.Empty:
                break
            if data == b"" and self.reader is not None and self.reader.error:
                err = self.reader.error
                self.reader.error = None
                # reader thread 已自行停止；刻意「不關閉裝置」，讓使用者仍能嘗試送
                # Output / Feature report（read 失敗不代表 write 一定失敗）。
                self.reader = None
                self._on_read_error(err)
                break
            if not data:
                continue
            self.rx_reports += 1
            self.rx_bytes += len(data)
            self.rx_count_var.set(f"收: {self.rx_reports} report / {self.rx_bytes} bytes")
            if not self.freeze_var.get():
                self._log_bytes("IN", data, count_as_report=False)
                rendered = True
        if rendered and self.autoscroll_var.get():
            for w in (self.rx_ascii, self.rx_hex, self.rx_both):
                w.see("end")
        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    def _has_power_device_collection(self) -> bool:
        """同一顆裝置（VID:PID）是否另有 Power Device (usage page 0x84) collection。

        若有，Windows 內建電源/UPS HID 驅動會獨佔整顆裝置，使用者程式只能拿到
        query-only 把手 —— read/write 全失敗。這是自製 HID 最常見的「讀不到」原因。
        """
        info = self._open_info
        if info is None:
            return False
        return any(
            d.vid == info.vid and d.pid == info.pid and d.usage_page == 0x84
            for d in self._devices
        )

    def _on_read_error(self, err: str) -> None:
        """Input 讀取停止：不關閉裝置，記錄一次並彈出正確的診斷訊息。

        關鍵：read 失敗（Input report，中斷 IN pipe）不代表 Output / Feature 也失敗。
        HID Power Device(UPS) 的 IN pipe 會被 Windows hidbatt 接管，這是預期行為、不是故障。
        """
        is_power = self._has_power_device_collection()
        self._log_text("ERR", f"Input 讀取停止：{err}")
        if is_power:
            self.status_var.set("已連線（HID Power Device：Input 由 Windows 接管，改用 Feature/Output）")
            self._log_text("INFO", "HID Power Device(UPS)：Input report 由 Windows hidbatt 接管屬正常；改用 Get/Set Feature 與 Output（填對 Report ID）")
        else:
            self.status_var.set("已連線（Input 無法讀取，可改用 Output/Feature）")
            self._log_text("INFO", "裝置仍開啟；read 失敗不代表 write 失敗，可改用 Output / Get/Set Feature")
        if self._read_error_shown:
            return
        self._read_error_shown = True

        if is_power:
            lines = [
                "偵測到本裝置含 Power Device (usage page 0x84) collection —— 這是 HID UPS / 電源裝置。",
                "",
                "Windows 的 hidbatt 驅動會接管它的 Input report 串流（中斷 IN pipe），所以使用者程式",
                "read() 不到 Input report。這是 OS 正常行為、不是故障，也不該為了讀 Input 拿掉 UPS 功能。",
                "",
                "重點：Output report 與 Get/Set Feature（走 control pipe）仍然完全可用。",
                "請改用右側功能，並填正確的 Report ID（此類裝置用 numbered report）：",
                "  - Get Feature + Report ID = 06 / 0C → 讀 UPS 容量 / 狀態",
                "  - Get Feature + Report ID = F1（長度 64）→ OTA 狀態",
                "  - Get Feature + Report ID = F2 / F3（長度設 33）→ 版本字串",
                "  - Output report + Report ID = F0 → OTA 命令",
                "",
                "只有當你『真的需要在 user space 收非同步 Input report』時才需要動韌體（把 vendor 通道",
                "放到獨立 USB interface / 獨立 IN 端點）；一般讀值與 OTA 都靠 Feature 輪詢，不需要 Input。",
            ]
            messagebox.showinfo("Input report 由系統接管（正常）", "\n".join(lines))
        else:
            lines = [
                "無法讀取此 HID 裝置的 Input report（中斷 IN pipe）。",
                "",
                "read 失敗不代表 write / Feature 也失敗。若此裝置用 numbered report，請在右側填正確的",
                "Report ID，再用 Get/Set Feature 或 Output report。",
                "",
                "若 Output / Feature 也都失敗，才考慮：被其他程式佔用、是系統 HID（鍵盤/滑鼠，",
                "Windows 本來就獨佔輸入），或裝置已拔除。",
            ]
            messagebox.showwarning("Input 讀取停止", "\n".join(lines))

    def _log_bytes(self, direction: str, data: bytes, *, count_as_report: bool = True) -> None:
        """把一筆 report（含方向標記）寫進三個顯示分頁。"""
        tag, _ = DIR_TAGS.get(direction, DIR_TAGS["INFO"])
        prefix = f"{direction:<4} "
        n = len(data)
        suffix = f"  ({n}B)\n"
        segments = bytes_to_ascii_inline_segments(data)
        hex_str = bytes_to_hex(data)

        self.rx_ascii.insert("end", prefix, (tag,))
        for text, is_esc in segments:
            self.rx_ascii.insert("end", text, (ESC_TAG,) if is_esc else ())
        self.rx_ascii.insert("end", suffix)

        self.rx_hex.insert("end", prefix, (tag,))
        self.rx_hex.insert("end", hex_str + suffix)

        self.rx_both.insert("end", prefix, (tag,))
        for text, is_esc in segments:
            self.rx_both.insert("end", text, (ESC_TAG,) if is_esc else ())
        self.rx_both.insert("end", "  |  " + hex_str + suffix)

        self._trim_all()

    def _log_text(self, direction: str, msg: str) -> None:
        """寫一行系統訊息（非 byte 資料）到三個分頁。"""
        tag, _ = DIR_TAGS.get(direction, DIR_TAGS["INFO"])
        line = f"{direction:<4} {msg}\n"
        for w in (self.rx_ascii, self.rx_hex, self.rx_both):
            w.insert("end", line, (tag,))
        self._trim_all()
        if self.autoscroll_var.get():
            for w in (self.rx_ascii, self.rx_hex, self.rx_both):
                w.see("end")

    def _trim_all(self) -> None:
        try:
            max_lines = int(self.max_lines_var.get())
        except (tk.TclError, ValueError):
            return
        for w in (self.rx_ascii, self.rx_hex, self.rx_both):
            try:
                line_count = int(w.index("end-1c").split(".")[0])
            except (tk.TclError, ValueError):
                continue
            if line_count > max_lines:
                w.delete("1.0", f"{line_count - max_lines + 1}.0")

    def _on_max_lines_changed(self) -> None:
        self._trim_all()

    def _clear_rx(self) -> None:
        self.rx_reports = 0
        self.rx_bytes = 0
        self.tx_reports = 0
        self.tx_bytes = 0
        for w in (self.rx_ascii, self.rx_hex, self.rx_both):
            w.delete("1.0", "end")
        self.rx_count_var.set("收: 0 report / 0 bytes")
        self.tx_count_var.set("送: 0 report / 0 bytes")

    # ---------------- 對話框 ----------------

    def _show_device_details(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("HID 裝置詳細資訊")
        win.geometry("760x500")
        win.transient(self.root)
        try:
            win.iconbitmap(default=str(ICO_PATH))
        except Exception:
            pass

        bar = ttk.Frame(win, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="所有 HID collection（hidapi enumerate 欄位）").pack(side="left")

        body = ttk.Frame(win, padding=(8, 0, 8, 8))
        body.pack(fill="both", expand=True)
        txt = tk.Text(body, wrap="none", font=("Consolas", 10), bg="#ffffff",
                      relief="flat", padx=8, pady=6)
        yscroll = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        txt.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        def build_text() -> str:
            try:
                entries = hid.enumerate()
            except Exception as exc:
                return f"列舉失敗: {exc}"
            if not entries:
                return "（找不到任何 HID 裝置）"
            out = [f"共 {len(entries)} 個 HID collection"]
            for e in sorted(entries, key=lambda x: (x.get("vendor_id", 0), x.get("product_id", 0))):
                out.append("")
                out.append("─" * 60)
                vid = int(e.get("vendor_id", 0) or 0)
                pid = int(e.get("product_id", 0) or 0)
                out.append(f"  VID:PID        : {vid:04X}:{pid:04X}")
                out.append(f"  product_string : {e.get('product_string') or '-'}")
                out.append(f"  manufacturer   : {e.get('manufacturer_string') or '-'}")
                out.append(f"  serial_number  : {e.get('serial_number') or '-'}")
                up = int(e.get("usage_page", 0) or 0)
                us = int(e.get("usage", 0) or 0)
                out.append(f"  usage_page     : 0x{up:04X}")
                out.append(f"  usage          : 0x{us:04X}")
                out.append(f"  interface      : {e.get('interface_number')}")
                rel = e.get("release_number")
                if rel is not None:
                    out.append(f"  release_number : 0x{int(rel):04X}")
                path = e.get("path", b"")
                if isinstance(path, bytes):
                    path = path.decode("ascii", errors="replace")
                out.append(f"  path           : {path}")
            return "\n".join(out)

        def fill() -> None:
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", build_text())
            txt.configure(state="disabled")

        def copy() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(build_text())

        ttk.Button(bar, text="關閉", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="複製", command=copy).pack(side="right", padx=(0, 6))
        ttk.Button(bar, text="重新整理", command=fill).pack(side="right", padx=(0, 6))
        fill()
        self._center(win)

    def _show_about(self) -> None:
        messagebox.showinfo(
            "關於",
            "USB-HID 測試工具\ntkinter + hidapi\n\n"
            "列舉 HID 裝置、收 Input report、送 Output report、Get/Set Feature report，\n"
            "HEX / ASCII 雙模式收發。適合測試自製 HID 裝置（含 vendor-defined usage page）。",
        )

    def _center(self, win) -> None:
        win.update_idletasks()
        w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
        h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
        x = max(0, (win.winfo_screenwidth() - w) // 2)
        y = max(0, (win.winfo_screenheight() - h) // 2)
        win.geometry(f"+{x}+{y}")

    def _on_close(self) -> None:
        self._close_device()
        self.root.destroy()
