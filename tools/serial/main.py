"""Serial Port Tool - Qt6 + Python GUI.

Layout 參考使用者提供的 "串口測試" 圖：左右分割、右側為控制區。

需求：
- 掃描並列出系統所有 COM port（含完整描述 / 廠商）
- HEX 傳送，輸入 "01 AB 99" 等大小寫與分隔混用格式
- ASCII 傳送，可選結尾 None / \\r / \\n / \\r\\n
- 連續傳送模式（間隔可調）
- 接收三分頁：ASCII / HEX / 對照（hex dump）
- 程式設計師計算機（HEX/DEC/OCT/BIN，含位元運算）

執行：python main.py
"""

import re
import sys
from typing import Optional

try:
    from PySide6.QtCore import Qt, QTimer, QThread, Signal
    from PySide6.QtGui import QAction, QFont, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QComboBox, QPushButton, QLineEdit, QPlainTextEdit, QSpinBox,
        QTabWidget, QGroupBox, QCheckBox, QSplitter, QMessageBox, QDialog,
        QStatusBar,
    )
except ImportError:
    print("缺少 PySide6。請執行: pip install PySide6", file=sys.stderr)
    sys.exit(1)

try:
    from serial import Serial, SerialException
    from serial.tools import list_ports
except ImportError:
    print("缺少 pyserial。請執行: pip install pyserial", file=sys.stderr)
    sys.exit(1)


def parse_hex_input(text: str) -> bytes:
    cleaned = re.sub(r"[\s,\-_:]", "", text)
    if not cleaned:
        return b""
    if not re.fullmatch(r"[0-9A-Fa-f]+", cleaned):
        raise ValueError("含非 HEX 字元（合法字元 0-9 A-F a-f 與分隔）")
    if len(cleaned) % 2 != 0:
        raise ValueError("HEX 字元數須為偶數（每個 byte 兩個 hex 字元）")
    return bytes.fromhex(cleaned)


def bytes_to_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def bytes_to_ascii(data: bytes) -> str:
    out = []
    for b in data:
        if b == 0x0D:
            out.append("\\r")
        elif b == 0x0A:
            out.append("\\n\n")
        elif b == 0x09:
            out.append("\\t")
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\x{b:02X}")
    return "".join(out)


def make_hex_dump_line(offset: int, chunk: bytes, bytes_per_line: int = 16) -> str:
    hex_part = " ".join(f"{b:02X}" for b in chunk).ljust(bytes_per_line * 3 - 1)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    return f"{offset:08X}  {hex_part}  |{ascii_part}|"


class SerialReader(QThread):
    data_received = Signal(bytes)
    error_occurred = Signal(str)

    def __init__(self, ser: Serial, parent=None):
        super().__init__(parent)
        self.ser = ser
        self._running = True

    def stop(self):
        self._running = False
        self.wait(800)

    def run(self):
        while self._running:
            try:
                if self.ser is None or not self.ser.is_open:
                    break
                n = self.ser.in_waiting
                if n > 0:
                    data = self.ser.read(n)
                    if data:
                        self.data_received.emit(bytes(data))
                else:
                    self.msleep(10)
            except (SerialException, OSError) as e:
                if self._running:
                    self.error_occurred.emit(str(e))
                break


class HexDumpView:
    BPL = 16

    def __init__(self, hex_edit: QPlainTextEdit, dump_edit: QPlainTextEdit):
        self.hex_edit = hex_edit
        self.dump_edit = dump_edit
        self.pending = bytearray()
        self.offset = 0
        self.has_partial = False

    def reset(self):
        self.pending.clear()
        self.offset = 0
        self.has_partial = False

    def append(self, data: bytes):
        self._clear_partial()
        self.pending.extend(data)
        while len(self.pending) >= self.BPL:
            chunk = bytes(self.pending[:self.BPL])
            del self.pending[:self.BPL]
            self._write_full_line(chunk)
            self.offset += self.BPL
        if self.pending:
            self._write_partial(bytes(self.pending))

    def _write_full_line(self, chunk: bytes):
        hex_line = bytes_to_hex(chunk)
        dump_line = make_hex_dump_line(self.offset, chunk, self.BPL)
        cur = self.hex_edit.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText(hex_line + "\n")
        cur2 = self.dump_edit.textCursor()
        cur2.movePosition(QTextCursor.End)
        cur2.insertText(dump_line + "\n")

    def _write_partial(self, chunk: bytes):
        hex_line = bytes_to_hex(chunk)
        dump_line = make_hex_dump_line(self.offset, chunk, self.BPL)
        cur = self.hex_edit.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText(hex_line)
        cur2 = self.dump_edit.textCursor()
        cur2.movePosition(QTextCursor.End)
        cur2.insertText(dump_line)
        self.has_partial = True

    def _clear_partial(self):
        if not self.has_partial:
            return
        for edit in (self.hex_edit, self.dump_edit):
            cur = edit.textCursor()
            cur.movePosition(QTextCursor.End)
            cur.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
            cur.removeSelectedText()
        self.has_partial = False


class ProgrammerCalculator(QDialog):
    BIT_MASK = {8: 0xFF, 16: 0xFFFF, 32: 0xFFFFFFFF, 64: 0xFFFFFFFFFFFFFFFF}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("程式設計師計算機")
        self.resize(440, 540)
        self.value = 0
        self.pending_op: Optional[str] = None
        self.pending_value = 0
        self.input_buffer = "0"
        self.fresh_input = True
        self.base = 16
        self.bit_width = 32
        self._build_ui()
        self._refresh()

    @property
    def mask(self) -> int:
        return self.BIT_MASK[self.bit_width]

    def _build_ui(self):
        layout = QVBoxLayout(self)
        disp = QGroupBox("顯示")
        gl = QGridLayout(disp)
        font = QFont("Consolas", 11)
        self.hex_d = QLineEdit("0"); self.hex_d.setFont(font); self.hex_d.setReadOnly(True)
        self.dec_d = QLineEdit("0"); self.dec_d.setFont(font); self.dec_d.setReadOnly(True)
        self.oct_d = QLineEdit("0"); self.oct_d.setFont(font); self.oct_d.setReadOnly(True)
        self.bin_d = QLineEdit("0"); self.bin_d.setFont(font); self.bin_d.setReadOnly(True)
        gl.addWidget(QLabel("HEX"), 0, 0); gl.addWidget(self.hex_d, 0, 1)
        gl.addWidget(QLabel("DEC"), 1, 0); gl.addWidget(self.dec_d, 1, 1)
        gl.addWidget(QLabel("OCT"), 2, 0); gl.addWidget(self.oct_d, 2, 1)
        gl.addWidget(QLabel("BIN"), 3, 0); gl.addWidget(self.bin_d, 3, 1)
        layout.addWidget(disp)

        mode = QHBoxLayout()
        mode.addWidget(QLabel("輸入進位:"))
        self.base_combo = QComboBox()
        self.base_combo.addItems(["HEX", "DEC", "OCT", "BIN"])
        self.base_combo.currentIndexChanged.connect(self._on_base_changed)
        mode.addWidget(self.base_combo)
        mode.addWidget(QLabel("位元寬度:"))
        self.bw_combo = QComboBox()
        self.bw_combo.addItems(["8", "16", "32", "64"])
        self.bw_combo.setCurrentText("32")
        self.bw_combo.currentTextChanged.connect(self._on_bw_changed)
        mode.addWidget(self.bw_combo)
        mode.addStretch()
        layout.addLayout(mode)

        grid = QGridLayout()
        layout_btns = [
            [("AC", "fn"), ("CE", "fn"), ("Back", "fn"), ("+/-", "fn"), ("NOT", "fn")],
            [("AND", "op"), ("OR", "op"), ("XOR", "op"), ("<<", "op"), (">>", "op")],
            [("A", "d"), ("B", "d"), ("C", "d"), ("D", "d"), ("E", "d")],
            [("F", "d"), ("7", "d"), ("8", "d"), ("9", "d"), ("/", "op")],
            [("Mod", "op"), ("4", "d"), ("5", "d"), ("6", "d"), ("*", "op")],
            [("00", "d"), ("1", "d"), ("2", "d"), ("3", "d"), ("-", "op")],
            [("FF", "d"), ("0", "d"), ("=", "fn"), ("",  "sp"), ("+", "op")],
        ]
        self.digit_buttons = {}
        for r, row in enumerate(layout_btns):
            for c, (label, kind) in enumerate(row):
                if kind == "sp":
                    continue
                btn = QPushButton(label)
                btn.setMinimumHeight(36)
                btn.clicked.connect(lambda _, x=label: self._on_button(x))
                grid.addWidget(btn, r, c)
                if kind == "d" and label in "0123456789ABCDEF":
                    self.digit_buttons[label] = btn
        layout.addLayout(grid)
        self._sync_digit_enables()

    def _sync_digit_enables(self):
        allowed = {
            16: set("0123456789ABCDEF"),
            10: set("0123456789"),
            8:  set("01234567"),
            2:  set("01"),
        }[self.base]
        for k, btn in self.digit_buttons.items():
            btn.setEnabled(k in allowed)

    def _on_base_changed(self, idx):
        self.base = [16, 10, 8, 2][idx]
        self.input_buffer = self._fmt(self.value, self.base)
        self.fresh_input = True
        self._sync_digit_enables()
        self._refresh()

    def _on_bw_changed(self, txt):
        self.bit_width = int(txt)
        self.value &= self.mask
        self.pending_value &= self.mask
        self._refresh()

    def _on_button(self, label: str):
        if label in "0123456789ABCDEF":
            self._append_digit(label)
        elif label == "00":
            self._append_digit("0"); self._append_digit("0")
        elif label == "FF":
            self._append_digit("F"); self._append_digit("F")
        elif label == "AC":
            self.value = 0; self.pending_op = None; self.pending_value = 0
            self.input_buffer = "0"; self.fresh_input = True
        elif label == "CE":
            self.input_buffer = "0"; self.fresh_input = True
            self.value = 0
        elif label == "Back":
            if not self.fresh_input and len(self.input_buffer) > 1:
                self.input_buffer = self.input_buffer[:-1]
                try:
                    self.value = int(self.input_buffer, self.base) & self.mask
                except ValueError:
                    self.value = 0
            else:
                self.input_buffer = "0"; self.fresh_input = True; self.value = 0
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

    def _append_digit(self, d: str):
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

    def _commit_pending(self):
        if self.pending_op is None:
            return
        a = self.pending_value & self.mask
        b = self.value & self.mask
        op = self.pending_op
        try:
            if   op == "+":   r = (a + b) & self.mask
            elif op == "-":   r = (a - b) & self.mask
            elif op == "*":   r = (a * b) & self.mask
            elif op == "/":   r = (a // b) if b else 0
            elif op == "Mod": r = (a % b) if b else 0
            elif op == "AND": r = a & b
            elif op == "OR":  r = a | b
            elif op == "XOR": r = a ^ b
            elif op == "<<":  r = (a << (b & (self.bit_width - 1))) & self.mask
            elif op == ">>":  r = (a & self.mask) >> (b & (self.bit_width - 1))
            else:             r = b
        except Exception:
            r = 0
        self.value = r & self.mask
        self.input_buffer = self._fmt(self.value, self.base)
        self.fresh_input = True

    @staticmethod
    def _fmt(v: int, base: int) -> str:
        if base == 16: return f"{v:X}"
        if base == 10: return str(v)
        if base == 8:  return f"{v:o}"
        if base == 2:  return f"{v:b}"
        return str(v)

    def _refresh(self):
        v = self.value & self.mask
        bw = self.bit_width
        self.hex_d.setText(f"{v:0{bw // 4}X}")
        self.dec_d.setText(str(v))
        self.oct_d.setText(f"{v:o}")
        bin_str = f"{v:0{bw}b}"
        self.bin_d.setText(" ".join(bin_str[i:i+4] for i in range(0, len(bin_str), 4)))


class MainWindow(QMainWindow):
    BAUD_RATES = [
        "9600", "19200", "38400", "57600", "115200", "230400",
        "460800", "921600", "1200", "2400", "4800", "14400",
    ]
    DATA_BITS = ["5", "6", "7", "8"]
    PARITIES = [("None", "N"), ("Even", "E"), ("Odd", "O"), ("Mark", "M"), ("Space", "S")]
    STOP_BITS = [("1", 1), ("1.5", 1.5), ("2", 2)]
    HISTORY_MAX = 30

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Serial Port Tool - Qt6")
        self.resize(1200, 760)
        self.ser: Optional[Serial] = None
        self.reader: Optional[SerialReader] = None
        self.calc_dialog: Optional[ProgrammerCalculator] = None
        self._repeat_kind: Optional[str] = None
        self.rx_total = 0
        self.tx_total = 0
        self._build_ui()
        self._build_menu()
        self.dump_view = HexDumpView(self.rx_hex, self.rx_both)
        self.tx_timer = QTimer(self)
        self.tx_timer.timeout.connect(self._on_repeat_tick)
        self._refresh_ports()
        self._set_connected(False)

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("檔案(&F)")
        act_quit = QAction("結束", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)
        tools_menu = menubar.addMenu("工具(&T)")
        act_calc = QAction("程式設計師計算機", self)
        act_calc.setShortcut("Ctrl+K")
        act_calc.triggered.connect(self._open_calculator)
        tools_menu.addAction(act_calc)
        act_rescan = QAction("重新掃描通訊埠", self)
        act_rescan.setShortcut("F5")
        act_rescan.triggered.connect(self._refresh_ports)
        tools_menu.addAction(act_rescan)
        help_menu = menubar.addMenu("說明(&H)")
        act_about = QAction("關於", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _open_calculator(self):
        if self.calc_dialog is None:
            self.calc_dialog = ProgrammerCalculator(self)
        self.calc_dialog.show()
        self.calc_dialog.raise_()
        self.calc_dialog.activateWindow()

    def _show_about(self):
        QMessageBox.information(
            self, "關於",
            "Serial Port Tool\nQt6 (PySide6) + pyserial\n"
            "支援 ASCII / HEX 雙模式收發、連續傳送、程式設計師計算機。",
        )

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(2, 2, 2, 2)
        rx_ctrl = QHBoxLayout()
        btn_clear_rx_l = QPushButton("清空接收")
        btn_clear_rx_l.clicked.connect(self._clear_rx)
        rx_ctrl.addWidget(btn_clear_rx_l)
        self.chk_freeze = QCheckBox("停止顯示")
        self.chk_freeze.setToolTip("勾選後接收區暫停更新（資料仍在背景累積計數）")
        rx_ctrl.addWidget(self.chk_freeze)
        self.chk_autoscroll = QCheckBox("自動捲動")
        self.chk_autoscroll.setChecked(True)
        rx_ctrl.addWidget(self.chk_autoscroll)
        rx_ctrl.addStretch()
        rx_ctrl.addWidget(QLabel("記錄行數:"))
        self.spin_max_lines = QSpinBox()
        self.spin_max_lines.setRange(100, 100000)
        self.spin_max_lines.setValue(5000)
        self.spin_max_lines.setSingleStep(500)
        self.spin_max_lines.valueChanged.connect(self._on_max_lines_changed)
        rx_ctrl.addWidget(self.spin_max_lines)
        ll.addLayout(rx_ctrl)

        self.tab_rx = QTabWidget()
        mono = QFont("Consolas", 10)
        self.rx_ascii = QPlainTextEdit(); self.rx_ascii.setReadOnly(True); self.rx_ascii.setFont(mono)
        self.rx_hex   = QPlainTextEdit(); self.rx_hex.setReadOnly(True);   self.rx_hex.setFont(mono)
        self.rx_both  = QPlainTextEdit(); self.rx_both.setReadOnly(True);  self.rx_both.setFont(mono)
        for w in (self.rx_ascii, self.rx_hex, self.rx_both):
            w.setMaximumBlockCount(self.spin_max_lines.value())
        self.tab_rx.addTab(self.rx_ascii, "ASCII")
        self.tab_rx.addTab(self.rx_hex, "HEX")
        self.tab_rx.addTab(self.rx_both, "對照")
        ll.addWidget(self.tab_rx, stretch=1)

        cnt_row = QHBoxLayout()
        self.lbl_rx_count = QLabel("接收: 0 bytes")
        self.lbl_tx_count = QLabel("發送: 0 bytes")
        cnt_row.addWidget(self.lbl_rx_count)
        cnt_row.addSpacing(20)
        cnt_row.addWidget(self.lbl_tx_count)
        cnt_row.addStretch()
        ll.addLayout(cnt_row)
        splitter.addWidget(left)

        right = QWidget()
        right.setMinimumWidth(380)
        right.setMaximumWidth(440)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(2, 2, 2, 2)

        hex_box = QGroupBox("HEX")
        hexl = QVBoxLayout(hex_box)
        self.hex_input = QComboBox()
        self.hex_input.setEditable(True)
        self.hex_input.setFont(mono)
        self.hex_input.setInsertPolicy(QComboBox.NoInsert)
        self.hex_input.lineEdit().setPlaceholderText("AA 55 1A 00 00 19  （大小寫均可）")
        self.hex_input.lineEdit().returnPressed.connect(lambda: self._send_once("hex"))
        hexl.addWidget(self.hex_input)
        hex_btn_row = QHBoxLayout()
        hex_btn_row.addStretch()
        self.btn_repeat_hex = QPushButton("連續傳送")
        self.btn_repeat_hex.setCheckable(True)
        self.btn_repeat_hex.toggled.connect(lambda on: self._toggle_repeat("hex", on))
        hex_btn_row.addWidget(self.btn_repeat_hex)
        self.btn_send_hex = QPushButton("單筆傳送")
        self.btn_send_hex.clicked.connect(lambda: self._send_once("hex"))
        hex_btn_row.addWidget(self.btn_send_hex)
        hexl.addLayout(hex_btn_row)
        rl.addWidget(hex_box)

        ascii_box = QGroupBox("ASCII")
        asciil = QVBoxLayout(ascii_box)
        self.ascii_input = QComboBox()
        self.ascii_input.setEditable(True)
        self.ascii_input.setFont(mono)
        self.ascii_input.setInsertPolicy(QComboBox.NoInsert)
        self.ascii_input.lineEdit().setPlaceholderText("輸入要傳送的 ASCII 字串")
        self.ascii_input.lineEdit().returnPressed.connect(lambda: self._send_once("ascii"))
        asciil.addWidget(self.ascii_input)
        end_row = QHBoxLayout()
        end_row.addWidget(QLabel("結尾:"))
        self.end_combo = QComboBox()
        self.end_combo.addItem("無", b"")
        self.end_combo.addItem("\\r", b"\r")
        self.end_combo.addItem("\\n", b"\n")
        self.end_combo.addItem("\\r\\n", b"\r\n")
        self.end_combo.setCurrentIndex(3)
        self.end_combo.setMinimumWidth(70)
        end_row.addWidget(self.end_combo)
        end_row.addStretch()
        self.btn_repeat_ascii = QPushButton("連續傳送")
        self.btn_repeat_ascii.setCheckable(True)
        self.btn_repeat_ascii.toggled.connect(lambda on: self._toggle_repeat("ascii", on))
        end_row.addWidget(self.btn_repeat_ascii)
        self.btn_send_ascii = QPushButton("單筆傳送")
        self.btn_send_ascii.clicked.connect(lambda: self._send_once("ascii"))
        end_row.addWidget(self.btn_send_ascii)
        asciil.addLayout(end_row)
        rl.addWidget(ascii_box)

        intv_row = QHBoxLayout()
        intv_row.addWidget(QLabel("連續傳送間隔 (ms):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 60000)
        self.interval_spin.setValue(1000)
        self.interval_spin.setSingleStep(100)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        intv_row.addWidget(self.interval_spin)
        intv_row.addStretch()
        rl.addLayout(intv_row)

        cfg_box = QGroupBox("傳輸設定")
        cfgl = QGridLayout(cfg_box)
        cfgl.addWidget(QLabel("通訊埠:"), 0, 0)
        self.port_combo = QComboBox()
        cfgl.addWidget(self.port_combo, 0, 1, 1, 2)
        btn_rescan = QPushButton("重新掃描")
        btn_rescan.clicked.connect(self._refresh_ports)
        cfgl.addWidget(btn_rescan, 0, 3)
        cfgl.addWidget(QLabel("傳輸速率:"), 1, 0)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(self.BAUD_RATES)
        self.baud_combo.setCurrentText("115200")
        self.baud_combo.setEditable(True)
        cfgl.addWidget(self.baud_combo, 1, 1, 1, 3)
        cfgl.addWidget(QLabel("資料位元:"), 2, 0)
        self.data_combo = QComboBox()
        self.data_combo.addItems(self.DATA_BITS)
        self.data_combo.setCurrentText("8")
        cfgl.addWidget(self.data_combo, 2, 1, 1, 3)
        cfgl.addWidget(QLabel("檢查位元:"), 3, 0)
        self.parity_combo = QComboBox()
        for n, _ in self.PARITIES:
            self.parity_combo.addItem(n)
        cfgl.addWidget(self.parity_combo, 3, 1, 1, 3)
        cfgl.addWidget(QLabel("停止位元:"), 4, 0)
        self.stop_combo = QComboBox()
        for n, _ in self.STOP_BITS:
            self.stop_combo.addItem(n)
        cfgl.addWidget(self.stop_combo, 4, 1, 1, 3)
        rl.addWidget(cfg_box)

        self.btn_clear_rec = QPushButton("清除記錄")
        self.btn_clear_rec.clicked.connect(self._clear_rx)
        rl.addWidget(self.btn_clear_rec)
        self.btn_open = QPushButton("開啟通訊埠")
        self.btn_open.clicked.connect(self._open_port)
        rl.addWidget(self.btn_open)
        self.btn_close = QPushButton("關閉通訊埠")
        self.btn_close.clicked.connect(self._close_port)
        rl.addWidget(self.btn_close)
        rl.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([820, 380])

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("未連線")

    def _refresh_ports(self):
        prev = self.port_combo.currentData()
        self.port_combo.clear()
        ports = list(list_ports.comports())
        if not ports:
            self.port_combo.addItem("（找不到任何 COM port）", None)
            return
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
                tail.append(f"{{{p.hwid}}}")
            label = " - ".join(parts[:2])
            if tail:
                label += "  " + "  ".join(tail)
            self.port_combo.addItem(label, p.device)
            self.port_combo.setItemData(self.port_combo.count() - 1, label, Qt.ToolTipRole)
        if prev:
            for i in range(self.port_combo.count()):
                if self.port_combo.itemData(i) == prev:
                    self.port_combo.setCurrentIndex(i)
                    break

    def _open_port(self):
        if self.ser is not None and self.ser.is_open:
            return
        device = self.port_combo.currentData()
        if not device:
            QMessageBox.warning(self, "錯誤", "請選擇 COM port")
            return
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            QMessageBox.warning(self, "錯誤", "Baud rate 須為整數")
            return
        data_bits = int(self.data_combo.currentText())
        parity = self.PARITIES[self.parity_combo.currentIndex()][1]
        stop = self.STOP_BITS[self.stop_combo.currentIndex()][1]
        try:
            self.ser = Serial(
                port=device, baudrate=baud, bytesize=data_bits,
                parity=parity, stopbits=stop, timeout=0, write_timeout=1,
            )
        except SerialException as e:
            QMessageBox.critical(self, "開啟失敗", str(e))
            self.ser = None
            return
        self.reader = SerialReader(self.ser)
        self.reader.data_received.connect(self._on_data)
        self.reader.error_occurred.connect(self._on_reader_error)
        self.reader.start()
        self._set_connected(True)
        self.statusBar().showMessage(f"已連線 {device}  {baud}-{data_bits}{parity}{stop}")

    def _close_port(self):
        if self.btn_repeat_hex.isChecked():
            self.btn_repeat_hex.setChecked(False)
        if self.btn_repeat_ascii.isChecked():
            self.btn_repeat_ascii.setChecked(False)
        if self.reader is not None:
            self.reader.stop()
            self.reader = None
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        self._set_connected(False)
        self.statusBar().showMessage("未連線")

    def _set_connected(self, on: bool):
        self.btn_open.setEnabled(not on)
        self.btn_close.setEnabled(on)
        for w in (self.port_combo, self.baud_combo, self.data_combo,
                  self.parity_combo, self.stop_combo):
            w.setEnabled(not on)
        for w in (self.btn_send_hex, self.btn_send_ascii,
                  self.btn_repeat_hex, self.btn_repeat_ascii):
            w.setEnabled(on)

    def _ending_bytes(self) -> bytes:
        data = self.end_combo.currentData()
        return data if isinstance(data, (bytes, bytearray)) else b""

    def _push_history(self, combo: QComboBox, text: str):
        if not text:
            return
        idx = combo.findText(text)
        if idx >= 0:
            combo.removeItem(idx)
        combo.insertItem(0, text)
        combo.setCurrentIndex(0)
        while combo.count() > self.HISTORY_MAX:
            combo.removeItem(combo.count() - 1)

    def _send_once(self, kind: str):
        if self.ser is None or not self.ser.is_open:
            QMessageBox.warning(self, "錯誤", "尚未連線")
            return
        try:
            if kind == "hex":
                text = self.hex_input.currentText()
                data = parse_hex_input(text)
                if not data:
                    return
            else:
                text = self.ascii_input.currentText()
                data = text.encode("latin-1", errors="replace") + self._ending_bytes()
        except ValueError as e:
            QMessageBox.warning(self, "HEX 格式錯誤", str(e))
            return
        try:
            self.ser.write(data)
        except SerialException as e:
            QMessageBox.critical(self, "發送失敗", str(e))
            self._close_port()
            return
        self.tx_total += len(data)
        self.lbl_tx_count.setText(f"發送: {self.tx_total} bytes")
        if not self.tx_timer.isActive():
            if kind == "hex":
                self._push_history(self.hex_input, text)
            else:
                self._push_history(self.ascii_input, text)

    def _toggle_repeat(self, kind: str, on: bool):
        sender = self.btn_repeat_hex if kind == "hex" else self.btn_repeat_ascii
        if on:
            if self.ser is None or not self.ser.is_open:
                QMessageBox.warning(self, "錯誤", "尚未連線")
                sender.blockSignals(True); sender.setChecked(False); sender.blockSignals(False)
                return
            other = self.btn_repeat_ascii if kind == "hex" else self.btn_repeat_hex
            if other.isChecked():
                other.setChecked(False)
            self._repeat_kind = kind
            self.tx_timer.start(self.interval_spin.value())
            sender.setText("停止")
        else:
            self.tx_timer.stop()
            self._repeat_kind = None
            self.btn_repeat_hex.setText("連續傳送")
            self.btn_repeat_ascii.setText("連續傳送")

    def _on_repeat_tick(self):
        if self._repeat_kind is not None:
            self._send_once(self._repeat_kind)

    def _on_interval_changed(self, v: int):
        if self.tx_timer.isActive():
            self.tx_timer.setInterval(v)

    def _on_data(self, data: bytes):
        self.rx_total += len(data)
        self.lbl_rx_count.setText(f"接收: {self.rx_total} bytes")
        if self.chk_freeze.isChecked():
            return
        self.rx_ascii.moveCursor(QTextCursor.End)
        self.rx_ascii.insertPlainText(bytes_to_ascii(data))
        self.dump_view.append(data)
        if self.chk_autoscroll.isChecked():
            for w in (self.rx_ascii, self.rx_hex, self.rx_both):
                sb = w.verticalScrollBar()
                sb.setValue(sb.maximum())

    def _on_reader_error(self, msg: str):
        QMessageBox.warning(self, "Serial 錯誤", msg)
        self._close_port()

    def _clear_rx(self):
        self.rx_total = 0
        self.rx_ascii.clear()
        self.rx_hex.clear()
        self.rx_both.clear()
        self.dump_view.reset()
        self.lbl_rx_count.setText("接收: 0 bytes")

    def _on_max_lines_changed(self, v: int):
        for w in (self.rx_ascii, self.rx_hex, self.rx_both):
            w.setMaximumBlockCount(v)

    def closeEvent(self, ev):
        self._close_port()
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
