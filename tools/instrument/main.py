"""儀器控制台（tkinter 版）。

通用型儀器控制介面，用 PyVISA 作統一後端，一套 UI 操作四種實體介面：

- USB-TMC   USB::0xVID::0xPID::序號::INSTR
- RS232     ASRL{n}::INSTR（對應 COM{n}），可設 baud / data / parity / stop
- LAN       TCPIP::位址::INSTR (VXI-11) / ::port::SOCKET (raw) / ::hislip0::INSTR
- GPIB      GPIB{board}::{addr}::INSTR（需系統 VISA + GPIB 卡驅動）

核心功能：
- 下簡單文字命令（SCPI 等），支援 Write（只送）/ Query（送+讀）/ Read（只讀）
- 傳送結尾（write_termination）可選 無 / \\n / \\r / \\r\\n，接收結尾亦可設
- 逾時（timeout, ms）可調；後端可選 自動 / pyvisa-py / 系統 VISA
- 掃描列舉目前連著的儀器（USB / GPIB / 序列）
- 命令歷史（可下拉重送）、常用命令快捷鈕、收發 log（TX/RX/錯誤 上色）
- 所有 VISA I/O 都跑在背景 worker thread，UI 永不凍結（query 逾時也不卡）

獨立執行：python main.py
也可經 jack-toolkit launcher 啟動（本目錄含 manifest.json）。
需要第三方套件 pyvisa 與 pyvisa-py；請先跑專案根目錄的 install_requirements.bat。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# === 全域 excepthook：在所有其他 import 之前裝好 ===
# 用 pythonw.exe（雙擊 / 釘選 / launcher spawn）跑時 stderr 被吃掉，未捕捉例外會
# 「靜默死掉」毫無線索。這個 hook 把 traceback 寫到 instrument_error.log 並跳 messagebox，
# 缺 pyvisa 時再補上明確的 pip 安裝指引。
_ERROR_LOG = Path(__file__).resolve().parent / "instrument_error.log"


def _global_excepthook(exc_type, exc_value, exc_tb) -> None:
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        _ERROR_LOG.write_text(tb_text, encoding="utf-8")
    except OSError:
        pass

    hint = ""
    if isinstance(exc_value, ModuleNotFoundError) and exc_value.name in ("pyvisa", "pyvisa_py"):
        hint = ("\n\n看起來缺少 PyVISA，請先在「雙擊 .bat 用的那顆」Python 安裝：\n"
                "    python -m pip install pyvisa pyvisa-py\n"
                "或直接跑專案根目錄的 install_requirements.bat。")
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb

        _root = _tk.Tk()
        _root.withdraw()
        _mb.showerror(
            "儀器控制台啟動失敗",
            f"Traceback 已寫到:\n{_ERROR_LOG}\n\n錯誤摘要:\n{tb_text[-1500:]}{hint}",
        )
        _root.destroy()
    except Exception:
        pass


sys.excepthook = _global_excepthook

import ctypes
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Any, Callable, Optional

# pyvisa 在 import 期就可能失敗（沒裝）；交給上面的 excepthook 給指引。
# 為了讓錯誤在 launcher 的 stderr 也看得到（launcher 會抓 stderr 顯示），
# 這裡故意不 try/except——直接讓 ModuleNotFoundError 冒出去。
import pyvisa

HERE = Path(__file__).resolve().parent
ICO_PATH = HERE / "instrument.ico"

HISTORY_MAX = 40
POLL_INTERVAL_MS = 30

# 介面類型。value 是內部代碼，label 是 UI 顯示。
IFACE_USB = "usb"
IFACE_SERIAL = "serial"
IFACE_LAN = "lan"
IFACE_GPIB = "gpib"
IFACE_MANUAL = "manual"
INTERFACES = [
    (IFACE_USB, "USB-TMC"),
    (IFACE_SERIAL, "RS232 (串列)"),
    (IFACE_LAN, "LAN (乙太網路)"),
    (IFACE_GPIB, "GPIB"),
    (IFACE_MANUAL, "手動輸入 VISA 資源"),
]

# 傳送 / 接收結尾。label -> 實際字串。
TERMINATIONS = [
    ("無", ""),
    ("\\n  (LF)", "\n"),
    ("\\r  (CR)", "\r"),
    ("\\r\\n  (CRLF)", "\r\n"),
]
DEFAULT_WRITE_TERM = "\\r\\n  (CRLF)"   # 使用者常見需求：命令尾加 \r\n
DEFAULT_READ_TERM = "\\n  (LF)"         # SCPI 儀器多半以 LF 結束回應

# 後端。label -> pyvisa ResourceManager 參數（"auto" 特別處理）。
BACKENDS = [
    ("自動 (系統 VISA→pyvisa-py)", "auto"),
    ("pyvisa-py (@py，純 Python)", "@py"),
    ("系統 VISA (@ivi)", "@ivi"),
]

# LAN 子協定。
LAN_VXI11 = "vxi11"
LAN_SOCKET = "socket"
LAN_HISLIP = "hislip"
LAN_PROTOCOLS = [
    (LAN_VXI11, "VXI-11 / LXI  (::INSTR)"),
    (LAN_SOCKET, "Raw Socket  (::port::SOCKET)"),
    (LAN_HISLIP, "HiSLIP  (::hislip0::INSTR)"),
]

BAUD_RATES = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
DATA_BITS = ["5", "6", "7", "8"]
PARITIES = ["None", "Even", "Odd", "Mark", "Space"]
STOP_BITS = ["1", "1.5", "2"]

# 常用命令快捷鈕（結尾帶 ? 的視為 Query，否則 Write）。
QUICK_COMMANDS = ["*IDN?", "*RST", "*CLS", "*OPC?", "*ESR?", "*STB?", "SYST:ERR?"]

# log 上色
TAG_TX = "tx"
TAG_RX = "rx"
TAG_ERR = "err"
TAG_INFO = "info"


def _center_window(win) -> None:
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"+{x}+{y}")


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class Task:
    """丟給 worker thread 的一筆工作。"""

    op: str
    params: dict = field(default_factory=dict)


@dataclass
class Result:
    """worker thread 回報給 UI 的結果。"""

    op: str
    ok: bool
    message: str = ""
    extra: Any = None


class VisaWorker(threading.Thread):
    """背景執行緒：獨佔 pyvisa ResourceManager 與已開啟的 instrument。

    所有 VISA I/O（可能阻塞到 timeout）都在這裡跑，UI thread 只丟 Task、收 Result，
    因此 UI 永不凍結。pyvisa 物件全部只在這條 thread 上被碰，避免跨執行緒使用 VISA
    session 的未定義行為。
    """

    def __init__(self, result_queue: "queue.Queue[Result]") -> None:
        super().__init__(daemon=True)
        self.tasks: "queue.Queue[Optional[Task]]" = queue.Queue()
        self.results = result_queue
        self.rm: Optional[pyvisa.ResourceManager] = None
        self.rm_backend: Optional[str] = None
        self.inst = None
        self._running = True

    # ---- UI thread 呼叫 ----
    def submit(self, op: str, **params) -> None:
        self.tasks.put(Task(op, params))

    def shutdown(self) -> None:
        self._running = False
        self.tasks.put(None)

    # ---- worker thread 內部 ----
    def run(self) -> None:
        handlers: dict[str, Callable[[dict], Result]] = {
            "list": self._do_list,
            "connect": self._do_connect,
            "disconnect": self._do_disconnect,
            "write": self._do_write,
            "query": self._do_query,
            "read": self._do_read,
            "config": self._do_config,
        }
        while self._running:
            task = self.tasks.get()
            if task is None:
                break
            handler = handlers.get(task.op)
            if handler is None:
                self.results.put(Result(task.op, False, f"未知操作: {task.op}"))
                continue
            try:
                self.results.put(handler(task.params))
            except Exception as exc:  # noqa: BLE001 - 任何 VISA / OS 例外都要回報而非讓 thread 死掉
                self.results.put(Result(task.op, False, self._fmt_exc(exc)))
        # 收尾：關掉 instrument 與 RM
        self._safe_close_inst()
        if self.rm is not None:
            try:
                self.rm.close()
            except Exception:
                pass

    @staticmethod
    def _fmt_exc(exc: Exception) -> str:
        name = type(exc).__name__
        text = str(exc).strip()
        return f"{name}: {text}" if text else name

    def _ensure_rm(self, backend: str) -> None:
        """確保 ResourceManager 存在且符合指定後端；backend 變動時重建。"""
        if self.rm is not None and self.rm_backend == backend:
            return
        if self.rm is not None:
            try:
                self.rm.close()
            except Exception:
                pass
            self.rm = None
        if backend == "auto":
            # 先試系統 VISA（IVI），失敗就退回純 Python 後端
            try:
                self.rm = pyvisa.ResourceManager()
            except Exception:
                self.rm = pyvisa.ResourceManager("@py")
        else:
            self.rm = pyvisa.ResourceManager(backend)
        self.rm_backend = backend

    def _backend_desc(self) -> str:
        if self.rm is None:
            return "?"
        spec = getattr(getattr(self.rm, "visalib", None), "library_path", None)
        wrapper = type(getattr(self.rm, "visalib", None)).__module__
        if "pyvisa_py" in wrapper:
            return "pyvisa-py (@py)"
        return f"系統 VISA ({spec})" if spec else "系統 VISA"

    def _safe_close_inst(self) -> None:
        if self.inst is not None:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None

    def _do_list(self, p: dict) -> Result:
        self._ensure_rm(p["backend"])
        pattern = p.get("pattern", "?*::INSTR")
        resources = list(self.rm.list_resources(pattern))
        return Result("list", True, f"找到 {len(resources)} 個資源", extra=resources)

    def _do_connect(self, p: dict) -> Result:
        self._ensure_rm(p["backend"])
        self._safe_close_inst()
        resource = p["resource"]
        open_timeout = int(p.get("timeout", 5000))
        inst = self.rm.open_resource(resource, open_timeout=open_timeout)
        # 逾時（ms）
        inst.timeout = int(p.get("timeout", 5000))
        # 傳送 / 接收結尾
        inst.write_termination = p.get("write_term", "")
        inst.read_termination = p.get("read_term", "") or None
        # 串列參數（只有 ASRL 資源需要，設在非串列資源上會噴 AttributeError，故 try）
        self._apply_serial(inst, p)
        self.inst = inst
        backend = self._backend_desc()
        return Result("connect", True, f"已連線 {resource}", extra={"backend": backend, "resource": resource})

    @staticmethod
    def _apply_serial(inst, p: dict) -> None:
        if not p.get("is_serial"):
            return
        try:
            from pyvisa import constants as c

            inst.baud_rate = int(p.get("baud", 115200))
            inst.data_bits = int(p.get("data_bits", 8))
            parity_map = {
                "None": c.Parity.none, "Even": c.Parity.even, "Odd": c.Parity.odd,
                "Mark": c.Parity.mark, "Space": c.Parity.space,
            }
            inst.parity = parity_map.get(p.get("parity", "None"), c.Parity.none)
            stop_map = {"1": c.StopBits.one, "1.5": c.StopBits.one_and_a_half, "2": c.StopBits.two}
            inst.stop_bits = stop_map.get(str(p.get("stop_bits", "1")), c.StopBits.one)
        except Exception:
            # 非串列資源或後端不支援該屬性：忽略，不影響連線
            pass

    def _do_disconnect(self, p: dict) -> Result:
        self._safe_close_inst()
        return Result("disconnect", True, "已中斷連線")

    def _require_inst(self) -> None:
        if self.inst is None:
            raise RuntimeError("尚未連線")

    def _do_write(self, p: dict) -> Result:
        self._require_inst()
        text = p["text"]
        n = self.inst.write(text)
        return Result("write", True, f"已送出 {n} bytes", extra=text)

    def _do_query(self, p: dict) -> Result:
        self._require_inst()
        text = p["text"]
        t0 = time.monotonic()
        reply = self.inst.query(text)
        dt = (time.monotonic() - t0) * 1000.0
        return Result("query", True, f"{dt:.0f} ms", extra={"sent": text, "reply": reply})

    def _do_read(self, p: dict) -> Result:
        self._require_inst()
        reply = self.inst.read()
        return Result("read", True, "", extra={"reply": reply})

    def _do_config(self, p: dict) -> Result:
        """連線中即時套用逾時 / 結尾變更。"""
        self._require_inst()
        if "timeout" in p:
            self.inst.timeout = int(p["timeout"])
        if "write_term" in p:
            self.inst.write_termination = p["write_term"]
        if "read_term" in p:
            self.inst.read_termination = p["read_term"] or None
        return Result("config", True, "已套用設定")


class InstrumentApp:
    """主視窗 controller。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.result_queue: "queue.Queue[Result]" = queue.Queue()
        self.worker = VisaWorker(self.result_queue)
        self.worker.start()

        self.connected = False
        self._busy = False
        self._history: list[str] = []
        self._found: list[str] = []

        root.title("儀器控制台")
        root.geometry("1160x720")
        root.minsize(940, 600)
        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass
        root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))

        self._build_ui()
        self._rebuild_iface_fields()
        self._update_resource()
        self._set_connected(False)
        self._poll_results()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================= UI 建構 =================
    def _build_ui(self) -> None:
        mono = tkfont.Font(family="Consolas", size=10)

        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned, width=470)
        paned.add(left, weight=0)
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        self._build_connection(left, mono)
        self._build_termination(left)
        self._build_command(left, mono)
        self._build_log(right, mono)

        self.status_var = tk.StringVar(value="未連線")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken").pack(
            side="bottom", fill="x"
        )

    def _build_connection(self, parent: ttk.Widget, mono: tkfont.Font) -> None:
        box = ttk.LabelFrame(parent, text="連線設定", padding=8)
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="介面類型:").grid(row=0, column=0, sticky="w", pady=2)
        self.iface_var = tk.StringVar(value=INTERFACES[0][1])
        iface_combo = ttk.Combobox(
            box, textvariable=self.iface_var, state="readonly",
            values=[label for _, label in INTERFACES],
        )
        iface_combo.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(4, 0), pady=2)
        iface_combo.bind("<<ComboboxSelected>>", lambda _e: self._rebuild_iface_fields())

        # 各介面專屬欄位放這個容器，切換時整批重建
        self.iface_fields = ttk.Frame(box)
        self.iface_fields.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 2))
        self.iface_fields.columnconfigure(1, weight=1)

        ttk.Label(box, text="VISA 資源:").grid(row=2, column=0, sticky="w", pady=2)
        self.resource_var = tk.StringVar()
        self.resource_entry = ttk.Entry(box, textvariable=self.resource_var, font=mono)
        self.resource_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(4, 0), pady=2)

        # 掃描列舉
        scan_row = ttk.Frame(box)
        scan_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(2, 2))
        scan_row.columnconfigure(1, weight=1)
        self.btn_scan = ttk.Button(scan_row, text="掃描儀器", width=10, command=self._scan)
        self.btn_scan.grid(row=0, column=0)
        self.found_var = tk.StringVar()
        self.found_combo = ttk.Combobox(
            scan_row, textvariable=self.found_var, state="readonly", font=mono, values=[]
        )
        self.found_combo.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.found_combo.bind("<<ComboboxSelected>>", lambda _e: self._pick_found())

        # 後端 + 逾時
        opt_row = ttk.Frame(box)
        opt_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(2, 2))
        opt_row.columnconfigure(1, weight=1)
        ttk.Label(opt_row, text="後端:").grid(row=0, column=0, sticky="w")
        self.backend_var = tk.StringVar(value=BACKENDS[0][0])
        ttk.Combobox(
            opt_row, textvariable=self.backend_var, state="readonly",
            values=[label for label, _ in BACKENDS],
        ).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Label(opt_row, text="逾時(ms):").grid(row=0, column=2, sticky="w")
        self.timeout_var = tk.IntVar(value=5000)
        ttk.Spinbox(
            opt_row, from_=100, to=120000, increment=500,
            textvariable=self.timeout_var, width=8, command=self._apply_live_config,
        ).grid(row=0, column=3, sticky="w", padx=(4, 0))

        # 連線動作
        act_row = ttk.Frame(box)
        act_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.btn_connect = ttk.Button(act_row, text="連線", command=self._connect)
        self.btn_connect.pack(side="left")
        self.btn_disconnect = ttk.Button(act_row, text="中斷", command=self._disconnect)
        self.btn_disconnect.pack(side="left", padx=(6, 0))
        self.btn_idn = ttk.Button(act_row, text="*IDN? 辨識", command=lambda: self._send("*IDN?", force_query=True))
        self.btn_idn.pack(side="left", padx=(6, 0))

        # --- 各介面欄位（建立後由 _rebuild_iface_fields 決定顯示哪組）---
        self._make_iface_field_widgets(mono)

    def _make_iface_field_widgets(self, mono: tkfont.Font) -> None:
        """一次建好所有介面專屬欄位，之後靠 grid/grid_remove 切換。"""
        f = self.iface_fields

        # USB：靠掃描；只放一行提示
        self.usb_hint = ttk.Label(
            f, foreground="#666",
            text="按「掃描儀器」列出 USB-TMC 儀器，或直接在上方填 VISA 資源字串。",
            wraplength=430, justify="left",
        )

        # RS232
        self.ser_port_var = tk.StringVar(value="COM3")
        self.ser_baud_var = tk.StringVar(value="115200")
        self.ser_data_var = tk.StringVar(value="8")
        self.ser_parity_var = tk.StringVar(value="None")
        self.ser_stop_var = tk.StringVar(value="1")
        self.ser_lbl_port = ttk.Label(f, text="COM 埠:")
        self.ser_port_combo = ttk.Combobox(f, textvariable=self.ser_port_var, width=12, values=[])
        self.ser_port_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_resource())
        self.ser_port_combo.bind("<KeyRelease>", lambda _e: self._update_resource())
        self.ser_btn_scan = ttk.Button(f, text="列出 COM", width=9, command=self._scan_com)
        self.ser_lbl_baud = ttk.Label(f, text="鮑率:")
        self.ser_baud_combo = ttk.Combobox(f, textvariable=self.ser_baud_var, width=10, values=BAUD_RATES)
        self.ser_lbl_frame = ttk.Label(f, text="資料/校驗/停止:")
        self.ser_data_combo = ttk.Combobox(f, textvariable=self.ser_data_var, width=4,
                                            values=DATA_BITS, state="readonly")
        self.ser_parity_combo = ttk.Combobox(f, textvariable=self.ser_parity_var, width=7,
                                              values=PARITIES, state="readonly")
        self.ser_stop_combo = ttk.Combobox(f, textvariable=self.ser_stop_var, width=5,
                                            values=STOP_BITS, state="readonly")

        # LAN
        self.lan_proto_var = tk.StringVar(value=LAN_PROTOCOLS[0][1])
        self.lan_addr_var = tk.StringVar(value="192.168.1.100")
        self.lan_port_var = tk.StringVar(value="5025")
        self.lan_lbl_proto = ttk.Label(f, text="協定:")
        self.lan_proto_combo = ttk.Combobox(f, textvariable=self.lan_proto_var, state="readonly",
                                             values=[label for _, label in LAN_PROTOCOLS])
        self.lan_proto_combo.bind("<<ComboboxSelected>>", lambda _e: (self._sync_lan_port(), self._update_resource()))
        self.lan_lbl_addr = ttk.Label(f, text="IP 位址:")
        self.lan_addr_entry = ttk.Entry(f, textvariable=self.lan_addr_var, font=mono)
        self.lan_addr_entry.bind("<KeyRelease>", lambda _e: self._update_resource())
        self.lan_lbl_port = ttk.Label(f, text="埠號:")
        self.lan_port_entry = ttk.Entry(f, textvariable=self.lan_port_var, width=8, font=mono)
        self.lan_port_entry.bind("<KeyRelease>", lambda _e: self._update_resource())

        # GPIB
        self.gpib_board_var = tk.StringVar(value="0")
        self.gpib_addr_var = tk.StringVar(value="1")
        self.gpib_lbl_board = ttk.Label(f, text="板卡(board):")
        self.gpib_board_spin = ttk.Spinbox(f, from_=0, to=15, width=5, textvariable=self.gpib_board_var,
                                            command=self._update_resource)
        self.gpib_board_spin.bind("<KeyRelease>", lambda _e: self._update_resource())
        self.gpib_lbl_addr = ttk.Label(f, text="主位址(1-30):")
        self.gpib_addr_spin = ttk.Spinbox(f, from_=0, to=30, width=5, textvariable=self.gpib_addr_var,
                                          command=self._update_resource)
        self.gpib_addr_spin.bind("<KeyRelease>", lambda _e: self._update_resource())

        # 手動
        self.manual_hint = ttk.Label(
            f, foreground="#666",
            text="直接在上方「VISA 資源」欄輸入任意合法資源字串，例如\n"
                 "  TCPIP0::10.0.0.5::inst0::INSTR   或   USB0::0x0957::0x1798::MY::INSTR",
            wraplength=430, justify="left",
        )

    def _build_termination(self, parent: ttk.Widget) -> None:
        box = ttk.LabelFrame(parent, text="命令結尾與設定", padding=8)
        box.pack(fill="x", pady=(8, 0))
        box.columnconfigure(1, weight=1)
        box.columnconfigure(3, weight=1)

        ttk.Label(box, text="傳送結尾:").grid(row=0, column=0, sticky="w", pady=2)
        self.write_term_var = tk.StringVar(value=DEFAULT_WRITE_TERM)
        wt = ttk.Combobox(box, textvariable=self.write_term_var, state="readonly",
                          values=[label for label, _ in TERMINATIONS])
        wt.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=2)
        wt.bind("<<ComboboxSelected>>", lambda _e: self._apply_live_config())

        ttk.Label(box, text="接收結尾:").grid(row=0, column=2, sticky="w", pady=2)
        self.read_term_var = tk.StringVar(value=DEFAULT_READ_TERM)
        rt = ttk.Combobox(box, textvariable=self.read_term_var, state="readonly",
                          values=[label for label, _ in TERMINATIONS])
        rt.grid(row=0, column=3, sticky="ew", padx=(4, 0), pady=2)
        rt.bind("<<ComboboxSelected>>", lambda _e: self._apply_live_config())

        ttk.Label(
            box, foreground="#666", wraplength=430, justify="left",
            text="傳送結尾就是 write_termination：命令送出時會自動附加在尾端。\n"
                 "接收結尾是 read_termination：Query/Read 收到此字元即視為一筆回應結束\n"
                 "（Raw Socket 一定要設對，否則會等到逾時）。",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))

    def _build_command(self, parent: ttk.Widget, mono: tkfont.Font) -> None:
        box = ttk.LabelFrame(parent, text="命令", padding=8)
        box.pack(fill="x", pady=(8, 0))
        box.columnconfigure(0, weight=1)

        self.cmd_var = tk.StringVar()
        self.cmd_combo = ttk.Combobox(box, textvariable=self.cmd_var, font=mono, values=[])
        self.cmd_combo.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.cmd_combo.bind("<Return>", lambda _e: self._send_smart())

        btn_row = ttk.Frame(box)
        btn_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.btn_write = ttk.Button(btn_row, text="送出 Write", command=lambda: self._send(force_write=True))
        self.btn_write.pack(side="left")
        self.btn_query = ttk.Button(btn_row, text="查詢 Query", command=lambda: self._send(force_query=True))
        self.btn_query.pack(side="left", padx=(6, 0))
        self.btn_read = ttk.Button(btn_row, text="讀取 Read", command=self._read)
        self.btn_read.pack(side="left", padx=(6, 0))

        # 常用命令快捷鈕
        quick = ttk.Frame(box)
        quick.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Label(quick, text="常用:", foreground="#666").pack(side="left")
        for cmd in QUICK_COMMANDS:
            ttk.Button(quick, text=cmd, width=8,
                       command=lambda c=cmd: self._send(c)).pack(side="left", padx=(4, 0))

    def _build_log(self, parent: ttk.Widget, mono: tkfont.Font) -> None:
        box = ttk.LabelFrame(parent, text="收發記錄", padding=6)
        box.pack(fill="both", expand=True)
        box.rowconfigure(1, weight=1)
        box.columnconfigure(0, weight=1)

        bar = ttk.Frame(box)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="自動捲動", variable=self.autoscroll_var).pack(side="left")
        self.timestamp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="時間戳", variable=self.timestamp_var).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="複製", command=self._copy_log).pack(side="right")
        ttk.Button(bar, text="清除記錄", command=self._clear_log).pack(side="right", padx=(0, 6))

        self.log = tk.Text(box, wrap="none", font=mono, height=10, state="disabled")
        ysb = ttk.Scrollbar(box, orient="vertical", command=self.log.yview)
        xsb = ttk.Scrollbar(box, orient="horizontal", command=self.log.xview)
        self.log.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.log.grid(row=1, column=0, sticky="nsew")
        ysb.grid(row=1, column=1, sticky="ns")
        xsb.grid(row=2, column=0, sticky="ew")

        self.log.tag_configure(TAG_TX, foreground="#1b6fc4")     # 送出：藍
        self.log.tag_configure(TAG_RX, foreground="#1f8a3b")     # 收到：綠
        self.log.tag_configure(TAG_ERR, foreground="#c0392b")    # 錯誤：紅
        self.log.tag_configure(TAG_INFO, foreground="#888")      # 資訊：灰

    # ================= 介面欄位切換 =================
    def _current_iface(self) -> str:
        label = self.iface_var.get()
        for code, lab in INTERFACES:
            if lab == label:
                return code
        return IFACE_USB

    def _rebuild_iface_fields(self) -> None:
        for w in self.iface_fields.winfo_children():
            w.grid_remove()
        iface = self._current_iface()

        if iface == IFACE_USB:
            self.usb_hint.grid(row=0, column=0, columnspan=4, sticky="w")
        elif iface == IFACE_SERIAL:
            self.ser_lbl_port.grid(row=0, column=0, sticky="w", pady=1)
            self.ser_port_combo.grid(row=0, column=1, sticky="w", padx=(4, 4), pady=1)
            self.ser_btn_scan.grid(row=0, column=2, sticky="w", pady=1)
            self.ser_lbl_baud.grid(row=1, column=0, sticky="w", pady=1)
            self.ser_baud_combo.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=1)
            self.ser_lbl_frame.grid(row=2, column=0, sticky="w", pady=1)
            # data/parity/stop 擠在同一行的 column 1~3
            self.ser_data_combo.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=1)
            self.ser_parity_combo.grid(row=2, column=2, sticky="w", padx=(4, 0), pady=1)
            self.ser_stop_combo.grid(row=2, column=3, sticky="w", padx=(4, 0), pady=1)
            self._scan_com()
        elif iface == IFACE_LAN:
            self.lan_lbl_proto.grid(row=0, column=0, sticky="w", pady=1)
            self.lan_proto_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(4, 0), pady=1)
            self.lan_lbl_addr.grid(row=1, column=0, sticky="w", pady=1)
            self.lan_addr_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(4, 0), pady=1)
            self.lan_lbl_port.grid(row=2, column=0, sticky="w", pady=1)
            self.lan_port_entry.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=1)
            self._sync_lan_port()
        elif iface == IFACE_GPIB:
            self.gpib_lbl_board.grid(row=0, column=0, sticky="w", pady=1)
            self.gpib_board_spin.grid(row=0, column=1, sticky="w", padx=(4, 0), pady=1)
            self.gpib_lbl_addr.grid(row=1, column=0, sticky="w", pady=1)
            self.gpib_addr_spin.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=1)
        elif iface == IFACE_MANUAL:
            self.manual_hint.grid(row=0, column=0, columnspan=4, sticky="w")

        self._update_resource()

    def _sync_lan_port(self) -> None:
        """Raw Socket 才需要埠號欄，其餘 disable。"""
        proto = self._lan_proto()
        state = "normal" if proto == LAN_SOCKET else "disabled"
        self.lan_port_entry.configure(state=state)

    def _lan_proto(self) -> str:
        label = self.lan_proto_var.get()
        for code, lab in LAN_PROTOCOLS:
            if lab == label:
                return code
        return LAN_VXI11

    def _update_resource(self) -> None:
        """依目前介面欄位重建 VISA 資源字串（手動模式不覆寫使用者輸入）。"""
        iface = self._current_iface()
        if iface == IFACE_MANUAL:
            return
        if iface == IFACE_USB:
            # USB 靠掃描選；沒選就不動使用者可能手打的內容
            return
        if iface == IFACE_SERIAL:
            n = self._com_number(self.ser_port_var.get())
            self.resource_var.set(f"ASRL{n}::INSTR")
        elif iface == IFACE_LAN:
            addr = self.lan_addr_var.get().strip()
            proto = self._lan_proto()
            if proto == LAN_SOCKET:
                port = self.lan_port_var.get().strip() or "5025"
                self.resource_var.set(f"TCPIP0::{addr}::{port}::SOCKET")
            elif proto == LAN_HISLIP:
                self.resource_var.set(f"TCPIP0::{addr}::hislip0::INSTR")
            else:
                self.resource_var.set(f"TCPIP0::{addr}::INSTR")
        elif iface == IFACE_GPIB:
            board = self.gpib_board_var.get().strip() or "0"
            addr = self.gpib_addr_var.get().strip() or "1"
            self.resource_var.set(f"GPIB{board}::{addr}::INSTR")

    @staticmethod
    def _com_number(text: str) -> str:
        """從 'COM3' / '3' 取出數字；取不到就原樣回傳。"""
        digits = "".join(ch for ch in text if ch.isdigit())
        return digits or text.strip()

    # ================= 動作 =================
    def _backend_code(self) -> str:
        label = self.backend_var.get()
        for lab, code in BACKENDS:
            if lab == label:
                return code
        return "auto"

    def _term_value(self, var: tk.StringVar) -> str:
        label = var.get()
        for lab, val in TERMINATIONS:
            if lab == label:
                return val
        return ""

    def _scan(self) -> None:
        if self._busy:
            return
        iface = self._current_iface()
        pattern = "USB?*::INSTR" if iface == IFACE_USB else "?*::INSTR"
        self._log(f"掃描資源 ({pattern}) …", TAG_INFO)
        self._set_busy(True)
        self.worker.submit("list", backend=self._backend_code(), pattern=pattern)

    def _scan_com(self) -> None:
        """列出 COM 埠（用 pyserial，比 VISA 掃描快且不需開資源）。"""
        try:
            from serial.tools import list_ports
            ports = sorted((p.device for p in list_ports.comports()),
                           key=lambda d: self._com_number(d).rjust(3))
        except Exception:
            ports = []
        self.ser_port_combo["values"] = ports
        if ports and self.ser_port_var.get() not in ports:
            self.ser_port_var.set(ports[0])
        self._update_resource()

    def _pick_found(self) -> None:
        val = self.found_var.get()
        if val:
            self.resource_var.set(val)

    def _connect(self) -> None:
        if self._busy or self.connected:
            return
        resource = self.resource_var.get().strip()
        if not resource:
            messagebox.showwarning("錯誤", "請先填入或掃描出 VISA 資源字串")
            return
        iface = self._current_iface()
        params = dict(
            backend=self._backend_code(),
            resource=resource,
            timeout=self._safe_int(self.timeout_var, 5000),
            write_term=self._term_value(self.write_term_var),
            read_term=self._term_value(self.read_term_var),
            is_serial=(iface == IFACE_SERIAL) or resource.upper().startswith("ASRL"),
            baud=self._safe_int_str(self.ser_baud_var.get(), 115200),
            data_bits=self.ser_data_var.get(),
            parity=self.ser_parity_var.get(),
            stop_bits=self.ser_stop_var.get(),
        )
        self._log(f"連線 {resource} …", TAG_INFO)
        self._set_busy(True)
        self.worker.submit("connect", **params)

    def _disconnect(self) -> None:
        if self._busy or not self.connected:
            return
        self._set_busy(True)
        self.worker.submit("disconnect")

    def _apply_live_config(self) -> None:
        """逾時 / 結尾在連線中被改動時，即時推給 worker。"""
        if not self.connected or self._busy:
            return
        self.worker.submit(
            "config",
            timeout=self._safe_int(self.timeout_var, 5000),
            write_term=self._term_value(self.write_term_var),
            read_term=self._term_value(self.read_term_var),
        )

    def _send_smart(self) -> None:
        """Enter 鍵：結尾是 ? 就 Query，否則 Write。"""
        self._send()

    def _send(self, text: Optional[str] = None, force_write: bool = False,
              force_query: bool = False) -> None:
        if not self._ensure_ready():
            return
        cmd = (text if text is not None else self.cmd_var.get()).strip()
        if not cmd:
            return
        is_query = force_query or (not force_write and cmd.rstrip().endswith("?"))
        self._push_history(cmd)
        self._set_busy(True)
        if is_query:
            self._log(f">> {cmd}", TAG_TX)
            self.worker.submit("query", text=cmd)
        else:
            self._log(f">> {cmd}", TAG_TX)
            self.worker.submit("write", text=cmd)

    def _read(self) -> None:
        if not self._ensure_ready():
            return
        self._log("<< (讀取…)", TAG_INFO)
        self._set_busy(True)
        self.worker.submit("read")

    def _ensure_ready(self) -> bool:
        if not self.connected:
            messagebox.showwarning("錯誤", "尚未連線")
            return False
        if self._busy:
            return False
        return True

    # ================= 結果輪詢 =================
    def _poll_results(self) -> None:
        try:
            while True:
                res = self.result_queue.get_nowait()
                self._handle_result(res)
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_results)

    def _handle_result(self, res: Result) -> None:
        self._set_busy(False)
        if res.op == "list":
            if res.ok:
                self._found = list(res.extra or [])
                self.found_combo["values"] = self._found
                if self._found:
                    self.found_var.set(self._found[0])
                    self.resource_var.set(self._found[0])
                    self._log(f"{res.message}: " + " | ".join(self._found), TAG_INFO)
                else:
                    self._log("掃描完成，沒有找到任何資源。", TAG_INFO)
            else:
                self._log("掃描失敗: " + res.message, TAG_ERR)
        elif res.op == "connect":
            if res.ok:
                self._set_connected(True)
                info = res.extra or {}
                self.status_var.set(f"已連線 {info.get('resource', '')}  |  後端: {info.get('backend', '')}")
                self._log(res.message + f"  (後端: {info.get('backend', '')})", TAG_INFO)
            else:
                self._set_connected(False)
                self.status_var.set("未連線")
                self._log("連線失敗: " + res.message, TAG_ERR)
        elif res.op == "disconnect":
            self._set_connected(False)
            self.status_var.set("未連線")
            self._log(res.message, TAG_INFO)
        elif res.op == "write":
            if res.ok:
                self._log(f"   {res.message}", TAG_INFO)
            else:
                self._log("送出失敗: " + res.message, TAG_ERR)
                self._maybe_drop_on_error(res.message)
        elif res.op == "query":
            if res.ok:
                info = res.extra or {}
                self._log("<< " + self._disp(info.get("reply", "")) + f"    ({res.message})", TAG_RX)
            else:
                self._log("查詢失敗: " + res.message, TAG_ERR)
                self._maybe_drop_on_error(res.message)
        elif res.op == "read":
            if res.ok:
                info = res.extra or {}
                self._log("<< " + self._disp(info.get("reply", "")), TAG_RX)
            else:
                self._log("讀取失敗: " + res.message, TAG_ERR)
                self._maybe_drop_on_error(res.message)
        elif res.op == "config":
            if not res.ok:
                self._log("套用設定失敗: " + res.message, TAG_ERR)

    def _maybe_drop_on_error(self, message: str) -> None:
        """連線層級的致命錯誤（session 失效）就把 UI 打回未連線狀態。"""
        fatal = ("session", "not open", "InvalidSession", "VI_ERROR_INV_OBJECT", "尚未連線")
        if any(k.lower() in message.lower() for k in fatal):
            self._set_connected(False)
            self.status_var.set("未連線")

    @staticmethod
    def _disp(reply: str) -> str:
        """回應可能含控制字元，去掉尾端換行後直接顯示；空回應標註。"""
        if reply is None:
            return "(無回應)"
        text = reply.rstrip("\r\n")
        return text if text != "" else "(空字串)"

    # ================= 狀態 / log =================
    def _set_connected(self, on: bool) -> None:
        self.connected = on
        self._refresh_button_states()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_button_states()
        self.root.configure(cursor="watch" if busy else "")

    def _refresh_button_states(self) -> None:
        idle = not self._busy
        can_connect = idle and not self.connected
        can_use = idle and self.connected
        self.btn_connect.state(("!disabled",) if can_connect else ("disabled",))
        self.btn_scan.state(("!disabled",) if idle else ("disabled",))
        self.btn_disconnect.state(("!disabled",) if can_use else ("disabled",))
        for btn in (self.btn_idn, self.btn_write, self.btn_query, self.btn_read):
            btn.state(("!disabled",) if can_use else ("disabled",))

    def _push_history(self, cmd: str) -> None:
        if not cmd:
            return
        if cmd in self._history:
            self._history.remove(cmd)
        self._history.insert(0, cmd)
        del self._history[HISTORY_MAX:]
        self.cmd_combo["values"] = self._history

    def _log(self, text: str, tag: str = TAG_INFO) -> None:
        ts = ""
        if self.timestamp_var.get():
            ts = time.strftime("%H:%M:%S ")
        self.log.configure(state="normal")
        self.log.insert("end", ts, (TAG_INFO,))
        self.log.insert("end", text + "\n", (tag,))
        if self.autoscroll_var.get():
            self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _copy_log(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log.get("1.0", "end-1c"))

    @staticmethod
    def _safe_int(var: tk.IntVar, default: int) -> int:
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return default

    @staticmethod
    def _safe_int_str(text: str, default: int) -> int:
        try:
            return int(str(text).strip())
        except (ValueError, TypeError):
            return default

    def _on_close(self) -> None:
        try:
            if self.connected:
                self.worker.submit("disconnect")
            self.worker.shutdown()
            self.worker.join(1.0)
        except Exception:
            pass
        self.root.destroy()


def main() -> int:
    _enable_dpi_awareness()
    root = tk.Tk()
    try:
        root.iconbitmap(default=str(ICO_PATH))
    except Exception:
        pass
    InstrumentApp(root)
    _center_window(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
