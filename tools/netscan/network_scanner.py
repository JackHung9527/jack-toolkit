"""網路掃描器（tkinter）。

分頁：
- IP Range Scan：IP 區段 ping sweep + 常見 port 探測
- Port Scan：單目標、全 port 範圍掃描
- Ping Monitor：對單一主機持續 ping 並記錄時間軸

純標準函式庫（tkinter + socket + subprocess + concurrent.futures）。
執行：python network_scanner.py
"""

from __future__ import annotations

import ipaddress
import os
import platform
import queue
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from tkinter import filedialog, messagebox, ttk


# Common ports shown as columns in IP scan
COMMON_PORTS = [
    ("SSH",    22),
    ("RDP",    3389),
    ("VNC",    5900),
    ("FTP",    21),
    ("Telnet", 23),
    ("Rlogin", 513),
    ("HTTP",   80),
    ("HTTPS",  443),
]

# Well-known service map for port scanner result column
SERVICE_MAP = {
    20: "FTP-Data", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 67: "DHCP-S", 68: "DHCP-C", 69: "TFTP", 80: "HTTP",
    110: "POP3", 119: "NNTP", 123: "NTP", 135: "MS-RPC", 137: "NetBIOS-NS",
    138: "NetBIOS-DGM", 139: "NetBIOS-SSN", 143: "IMAP", 161: "SNMP",
    162: "SNMP-Trap", 179: "BGP", 389: "LDAP", 443: "HTTPS", 445: "SMB",
    465: "SMTPS", 500: "ISAKMP", 502: "Modbus", 513: "Rlogin", 514: "Syslog",
    515: "LPD", 587: "SMTP-Submit", 636: "LDAPS", 853: "DNS-TLS",
    873: "rsync", 902: "VMware", 989: "FTPS-Data", 990: "FTPS",
    993: "IMAPS", 995: "POP3S", 1080: "SOCKS", 1194: "OpenVPN",
    1433: "MSSQL", 1434: "MSSQL-UDP", 1521: "Oracle", 1701: "L2TP",
    1723: "PPTP", 1883: "MQTT", 2049: "NFS", 2375: "Docker", 2376: "Docker-TLS",
    2483: "Oracle-SSL", 3000: "Dev/HTTP", 3306: "MySQL", 3389: "RDP",
    4369: "EPMD", 5000: "UPnP/Dev", 5060: "SIP", 5222: "XMPP",
    5353: "mDNS", 5432: "PostgreSQL", 5601: "Kibana", 5672: "AMQP",
    5683: "CoAP", 5900: "VNC", 5938: "TeamViewer", 5985: "WinRM",
    5986: "WinRM-S", 6379: "Redis", 6443: "K8s-API", 6667: "IRC",
    7000: "Cassandra", 7001: "WebLogic", 7077: "Spark", 8000: "HTTP-Alt",
    8008: "HTTP-Alt", 8080: "HTTP-Proxy", 8083: "MQTT-WS", 8086: "InfluxDB",
    8088: "HTTP-Alt", 8443: "HTTPS-Alt", 8883: "MQTT-TLS", 9000: "HTTP-Alt",
    9090: "Prometheus", 9092: "Kafka", 9200: "Elastic", 9300: "Elastic-TX",
    9418: "Git", 10000: "Webmin", 11211: "Memcached", 27017: "MongoDB",
    50000: "SAP",
}

IS_WIN = platform.system().lower().startswith("win")

# When launched via pythonw.exe (no parent console), every subprocess we spawn
# would otherwise pop a brand-new console window for a few ms. Suppress it.
# CREATE_NO_WINDOW = 0x08000000 (Python 3.7+ exposes subprocess.CREATE_NO_WINDOW).
_SUBPROC_FLAGS = subprocess.CREATE_NO_WINDOW if IS_WIN else 0


def tcp_probe(host: str, port: int, timeout: float = 0.4) -> bool:
    """Return True if TCP connect to host:port succeeds within timeout."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def ping_host(host: str, timeout_ms: int = 500) -> bool:
    """Send a single ICMP echo. True if reply received."""
    if IS_WIN:
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), host]
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=(timeout_ms / 1000.0) + 1.0,
            creationflags=_SUBPROC_FLAGS,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def ping_host_rtt(host: str, timeout_ms: int = 1000):
    """Send a single ICMP echo and try to parse RTT.

    Returns (ok: bool, rtt_ms: float | None).
    rtt_ms is None when ok=False or parsing failed.
    """
    if IS_WIN:
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), host]
    try:
        # On Windows, force English locale so "time=Xms" is parseable
        # regardless of system language (Chinese ping prints 時間=Xms).
        env = None
        if IS_WIN:
            env = os.environ.copy()
            env.setdefault("LANG", "C")
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=(timeout_ms / 1000.0) + 1.0,
            env=env,
            creationflags=_SUBPROC_FLAGS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return (False, None)

    if r.returncode != 0:
        return (False, None)

    try:
        out = r.stdout.decode("utf-8", errors="ignore")
    except Exception:
        out = ""

    # Match "time=12ms" / "time<1ms" / "time=12.3 ms" / Chinese "時間=12ms"
    m = re.search(r"(?:time|時間|tiempo|temps|Zeit)\s*[<=]\s*([\d.]+)\s*ms",
                  out, re.IGNORECASE)
    if m:
        try:
            return (True, float(m.group(1)))
        except ValueError:
            pass
    # Linux/macOS form: "time=12.345 ms"
    m = re.search(r"time\s*=\s*([\d.]+)\s*ms", out, re.IGNORECASE)
    if m:
        try:
            return (True, float(m.group(1)))
        except ValueError:
            pass
    return (True, None)


def resolve_hostname(host: str) -> str:
    try:
        return socket.gethostbyaddr(host)[0]
    except (socket.herror, socket.gaierror, OSError):
        return ""


# ---------------------------------------------------------------------------
# IP Range Scan tab
# ---------------------------------------------------------------------------

class IpRangeScanFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self._stop_evt = threading.Event()
        self._worker = None
        self._queue: queue.Queue = queue.Queue()
        self._row_iid = {}  # ip -> treeview iid
        self._build_ui()
        self.after(80, self._drain_queue)

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X)

        ttk.Label(top, text="IP range:").pack(side=tk.LEFT)
        self.var_o1 = tk.StringVar(value="192")
        self.var_o2 = tk.StringVar(value="168")
        self.var_o3 = tk.StringVar(value="1")
        self.var_start = tk.StringVar(value="1")
        self.var_end = tk.StringVar(value="254")
        for v, w in ((self.var_o1, 4), (self.var_o2, 4), (self.var_o3, 4)):
            e = ttk.Entry(top, textvariable=v, width=w, justify=tk.CENTER)
            e.pack(side=tk.LEFT, padx=2)
            ttk.Label(top, text=".").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.var_start, width=5,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Label(top, text="-->").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.var_end, width=5,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 8))

        ttk.Label(top, text="Timeout(ms):").pack(side=tk.LEFT)
        self.var_timeout = tk.StringVar(value="400")
        ttk.Entry(top, textvariable=self.var_timeout, width=6,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 8))

        ttk.Label(top, text="Threads:").pack(side=tk.LEFT)
        self.var_workers = tk.StringVar(value="64")
        ttk.Entry(top, textvariable=self.var_workers, width=5,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 8))

        self.btn_start = ttk.Button(top, text="Start scan",
                                    command=self.start_scan)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(top, text="Stop scan", state=tk.DISABLED,
                                   command=self.stop_scan)
        self.btn_stop.pack(side=tk.LEFT)

        cols = ("ip", "name") + tuple(name for name, _ in COMMON_PORTS) + ("other",)
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 height=20)
        headings = [("ip", "IP Address", 110), ("name", "Name", 160)]
        headings += [(n, n, 60) for n, _ in COMMON_PORTS]
        headings += [("other", "Open ports (extra)", 200)]
        for cid, txt, w in headings:
            self.tree.heading(cid, text=txt)
            anchor = tk.W if cid in ("ip", "name", "other") else tk.CENTER
            self.tree.column(cid, width=w, anchor=anchor, stretch=(cid == "other"))
        ysb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=ysb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(8, 0))
        ysb.pack(side=tk.LEFT, fill=tk.Y, pady=(8, 0))

        # Left double-click: send IP to Port Scan tab
        # Right-click: send IP to Ping Monitor tab
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)

        # Status bar
        self.var_status = tk.StringVar(value="Idle.")
        ttk.Label(self, textvariable=self.var_status,
                  anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))

    # ---- scan control ----
    def start_scan(self):
        if self._worker and self._worker.is_alive():
            return
        try:
            base = f"{self.var_o1.get()}.{self.var_o2.get()}.{self.var_o3.get()}.0"
            ipaddress.IPv4Address(base)  # validate octets 1-3
            s = int(self.var_start.get())
            e = int(self.var_end.get())
            if not (0 <= s <= 255 and 0 <= e <= 255 and s <= e):
                raise ValueError("last-octet range invalid")
            timeout = max(50, int(self.var_timeout.get()))
            workers = max(1, min(512, int(self.var_workers.get())))
        except ValueError as ex:
            messagebox.showerror("Bad input", str(ex))
            return

        # Reset table
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._row_iid.clear()

        ips = [f"{self.var_o1.get()}.{self.var_o2.get()}."
               f"{self.var_o3.get()}.{i}" for i in range(s, e + 1)]
        self._stop_evt.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.var_status.set(f"Scanning {len(ips)} hosts...")

        self._worker = threading.Thread(
            target=self._scan_worker,
            args=(ips, timeout / 1000.0, workers),
            daemon=True,
        )
        self._worker.start()

    def stop_scan(self):
        self._stop_evt.set()
        self.var_status.set("Stopping...")

    def _scan_worker(self, ips, timeout_s, workers):
        total = len(ips)
        done = 0
        ping_timeout_ms = int(timeout_s * 1000)

        def probe(ip):
            if self._stop_evt.is_set():
                return None
            alive_via_ping = ping_host(ip, ping_timeout_ms)
            open_ports = []
            if not self._stop_evt.is_set():
                with ThreadPoolExecutor(max_workers=8) as pool:
                    futs = {pool.submit(tcp_probe, ip, p, timeout_s): (name, p)
                            for name, p in COMMON_PORTS}
                    for fut in as_completed(futs):
                        name, p = futs[fut]
                        if fut.result():
                            open_ports.append((name, p))
            if not alive_via_ping and not open_ports:
                return None
            name = resolve_hostname(ip) if (alive_via_ping or open_ports) else ""
            return (ip, name, open_ports)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(probe, ip) for ip in ips]
            for fut in as_completed(futs):
                if self._stop_evt.is_set():
                    break
                res = fut.result()
                done += 1
                if res:
                    self._queue.put(("row", res))
                self._queue.put(("progress", (done, total)))

        self._queue.put(("done", None))

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "row":
                    self._add_row(*payload)
                elif kind == "progress":
                    done, total = payload
                    self.var_status.set(f"Scanning... {done}/{total}")
                elif kind == "done":
                    self.btn_start.config(state=tk.NORMAL)
                    self.btn_stop.config(state=tk.DISABLED)
                    self.var_status.set(
                        f"Done. {len(self._row_iid)} hosts responded.")
        except queue.Empty:
            pass
        self.after(80, self._drain_queue)

    def _add_row(self, ip, name, open_ports):
        opened_names = {n for n, _ in open_ports}
        cells = [ip, name]
        for n, _p in COMMON_PORTS:
            cells.append("open" if n in opened_names else "")
        # "other" column: any open we found that's not in COMMON_PORTS
        # (currently COMMON_PORTS covers all probed; left blank for future)
        cells.append("")
        iid = self.tree.insert("", tk.END, values=cells)
        self._row_iid[ip] = iid

    def _on_double_click(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        ip = self.tree.item(sel[0], "values")[0]
        nb = self.master  # the Notebook
        # Tab order: 0 = IP scan, 1 = Port scan, 2 = Ping monitor
        port_tab = nb.winfo_children()[1]
        port_tab.set_target(ip)
        nb.select(1)

    def _on_right_click(self, event):
        # Make sure the clicked row is selected first
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
        sel = self.tree.selection()
        if not sel:
            return
        ip = self.tree.item(sel[0], "values")[0]
        nb = self.master
        ping_tab = nb.winfo_children()[2]
        ping_tab.set_target(ip)
        nb.select(2)


# ---------------------------------------------------------------------------
# Port Scan tab
# ---------------------------------------------------------------------------

class PortScanFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self._stop_evt = threading.Event()
        self._worker = None
        self._queue: queue.Queue = queue.Queue()
        self._build_ui()
        self.after(80, self._drain_queue)

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Target:").pack(side=tk.LEFT)
        self.var_target = tk.StringVar(value="192.168.1.10")
        ttk.Entry(top, textvariable=self.var_target,
                  width=20).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(top, text="Port range:").pack(side=tk.LEFT)
        self.var_pstart = tk.StringVar(value="1")
        self.var_pend = tk.StringVar(value="1024")
        ttk.Entry(top, textvariable=self.var_pstart, width=6,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 2))
        ttk.Label(top, text="-->").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.var_pend, width=6,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(top, text="Timeout(ms):").pack(side=tk.LEFT)
        self.var_timeout = tk.StringVar(value="300")
        ttk.Entry(top, textvariable=self.var_timeout, width=6,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 8))

        ttk.Label(top, text="Threads:").pack(side=tk.LEFT)
        self.var_workers = tk.StringVar(value="200")
        ttk.Entry(top, textvariable=self.var_workers, width=5,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 8))

        self.btn_start = ttk.Button(top, text="Start scan",
                                    command=self.start_scan)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(top, text="Stop scan", state=tk.DISABLED,
                                   command=self.stop_scan)
        self.btn_stop.pack(side=tk.LEFT)

        cols = ("port", "proto", "service")
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 height=20)
        for cid, txt, w, anch in [
            ("port", "Port", 80, tk.CENTER),
            ("proto", "Proto", 80, tk.CENTER),
            ("service", "Service / Guess", 200, tk.W),
        ]:
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, anchor=anch,
                             stretch=(cid == "service"))
        ysb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=ysb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(8, 0))
        ysb.pack(side=tk.LEFT, fill=tk.Y, pady=(8, 0))

        self.var_status = tk.StringVar(value="Idle.")
        ttk.Label(self, textvariable=self.var_status,
                  anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))

    def set_target(self, ip: str):
        self.var_target.set(ip)

    def start_scan(self):
        if self._worker and self._worker.is_alive():
            return
        target = self.var_target.get().strip()
        try:
            # Accept hostname or IP; resolve to validate
            socket.gethostbyname(target)
        except OSError:
            messagebox.showerror("Bad target", f"Cannot resolve: {target}")
            return
        try:
            ps = int(self.var_pstart.get())
            pe = int(self.var_pend.get())
            if not (1 <= ps <= 65535 and 1 <= pe <= 65535 and ps <= pe):
                raise ValueError("port range must be 1..65535 and start<=end")
            timeout = max(50, int(self.var_timeout.get()))
            workers = max(1, min(1024, int(self.var_workers.get())))
        except ValueError as ex:
            messagebox.showerror("Bad input", str(ex))
            return

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._stop_evt.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.var_status.set(f"Scanning {target} ports {ps}-{pe}...")

        self._worker = threading.Thread(
            target=self._scan_worker,
            args=(target, ps, pe, timeout / 1000.0, workers),
            daemon=True,
        )
        self._worker.start()

    def stop_scan(self):
        self._stop_evt.set()
        self.var_status.set("Stopping...")

    def _scan_worker(self, target, ps, pe, timeout_s, workers):
        ports = list(range(ps, pe + 1))
        total = len(ports)
        done = 0

        def probe(p):
            if self._stop_evt.is_set():
                return None
            if tcp_probe(target, p, timeout_s):
                return p
            return None

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(probe, p) for p in ports]
            for fut in as_completed(futs):
                if self._stop_evt.is_set():
                    break
                p = fut.result()
                done += 1
                if p is not None:
                    self._queue.put(("row", p))
                if done % 50 == 0 or done == total:
                    self._queue.put(("progress", (done, total)))

        self._queue.put(("done", None))

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "row":
                    p = payload
                    svc = SERVICE_MAP.get(p, "")
                    self.tree.insert("", tk.END,
                                     values=(p, "TCP", svc))
                elif kind == "progress":
                    done, total = payload
                    self.var_status.set(f"Scanning... {done}/{total}")
                elif kind == "done":
                    self.btn_start.config(state=tk.NORMAL)
                    self.btn_stop.config(state=tk.DISABLED)
                    n = len(self.tree.get_children())
                    self.var_status.set(f"Done. {n} open port(s).")
        except queue.Empty:
            pass
        self.after(80, self._drain_queue)


# ---------------------------------------------------------------------------
# Ping Monitor tab
# ---------------------------------------------------------------------------

class PingMonitorFrame(ttk.Frame):
    """Continuously ping a single host and log every reply / loss with timestamp.

    Designed for "從幾點開始通 / 幾點掉了 / 掉了多久" 這類追蹤需求：
    - 每筆 ping 結果獨立一行 (Time / Status / RTT / Streak / Note)
    - 偵測 UP <-> DOWN 狀態轉變，highlight + Note 寫 "DOWN after Ns" / "UP after Ns"
    - 統計 Total / OK / Fail / Loss% / 最長連續中斷
    - 可選 auto-save 到 log file (append mode，crash safe)
    """

    LOG_LIMIT = 5000  # treeview row cap to avoid Tk slowdown

    def __init__(self, master):
        super().__init__(master, padding=8)
        self._stop_evt = threading.Event()
        self._worker = None
        self._queue: queue.Queue = queue.Queue()
        self._log_fp = None
        self._log_path = None

        # rolling state
        self._total = 0
        self._ok = 0
        self._fail = 0
        self._streak_state = None  # True=UP, False=DOWN, None=initial
        self._streak_count = 0
        self._streak_start = None  # epoch seconds when current streak began
        self._max_down_streak = 0  # longest consecutive DOWN count seen
        self._last_change_at = None  # epoch seconds of last state flip

        self._build_ui()
        self.after(120, self._drain_queue)

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Target:").pack(side=tk.LEFT)
        self.var_target = tk.StringVar(value="192.168.1.10")
        ttk.Entry(top, textvariable=self.var_target,
                  width=22).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(top, text="Interval(s):").pack(side=tk.LEFT)
        self.var_interval = tk.StringVar(value="1.0")
        # Spinbox so user can step by 0.1s without typing "." (Chinese IME
        # often turns "." into full-width "。" which is annoying).
        ttk.Spinbox(top, textvariable=self.var_interval,
                    from_=0.1, to=3600.0, increment=0.1, format="%.1f",
                    width=6, justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 8))

        ttk.Label(top, text="Timeout(ms):").pack(side=tk.LEFT)
        self.var_timeout = tk.StringVar(value="1000")
        ttk.Entry(top, textvariable=self.var_timeout, width=6,
                  justify=tk.CENTER).pack(side=tk.LEFT, padx=(2, 12))

        self.var_log_enable = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Save log",
                        variable=self.var_log_enable).pack(side=tk.LEFT)
        ttk.Button(top, text="Browse...",
                   command=self._pick_log_file).pack(side=tk.LEFT, padx=(2, 12))

        self.var_only_changes = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Only state changes",
                        variable=self.var_only_changes).pack(side=tk.LEFT,
                                                             padx=(0, 12))

        self.btn_start = ttk.Button(top, text="Start", command=self.start_mon)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(top, text="Stop", state=tk.DISABLED,
                                   command=self.stop_mon)
        self.btn_stop.pack(side=tk.LEFT)
        ttk.Button(top, text="Clear",
                   command=self._clear_log).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(top, text="Export...",
                   command=self._export_log).pack(side=tk.LEFT, padx=(4, 0))

        # Log file path display
        self.var_log_path = tk.StringVar(value="(no log file)")
        ttk.Label(self, textvariable=self.var_log_path,
                  foreground="#666").pack(fill=tk.X, pady=(4, 0))

        # Stats row
        stats = ttk.Frame(self)
        stats.pack(fill=tk.X, pady=(2, 4))
        self.var_stats = tk.StringVar(
            value="Total: 0   OK: 0   Fail: 0   Loss: 0.0%   "
                  "Max-down-streak: 0   Current: --"
        )
        ttk.Label(stats, textvariable=self.var_stats,
                  font=("Consolas", 10)).pack(side=tk.LEFT)

        # Treeview log
        cols = ("time", "status", "rtt", "streak", "note")
        self.tree = ttk.Treeview(self, columns=cols, show="headings",
                                 height=22)
        for cid, txt, w, anch, stretch in [
            ("time",   "Time",          170, tk.W,      False),
            ("status", "Status",        80,  tk.CENTER, False),
            ("rtt",    "RTT (ms)",      90,  tk.CENTER, False),
            ("streak", "Streak",        80,  tk.CENTER, False),
            ("note",   "Note",          400, tk.W,      True),
        ]:
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, anchor=anch, stretch=stretch)
        # Highlight tags
        self.tree.tag_configure("ok", foreground="#1e7e34")
        self.tree.tag_configure("fail", foreground="#c62828",
                                background="#fff0f0")
        self.tree.tag_configure("flip_down", foreground="#ffffff",
                                background="#c62828")
        self.tree.tag_configure("flip_up", foreground="#ffffff",
                                background="#1e7e34")
        ysb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=ysb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4, 0))
        ysb.pack(side=tk.LEFT, fill=tk.Y, pady=(4, 0))

        self.var_status = tk.StringVar(value="Idle.")
        ttk.Label(self, textvariable=self.var_status,
                  anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))

    # ---- helpers ----
    def set_target(self, ip: str):
        self.var_target.set(ip)

    def _pick_log_file(self):
        default = f"ping_{self.var_target.get().replace('.', '_')}_" \
                  f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        path = filedialog.asksaveasfilename(
            title="Save ping log to...",
            defaultextension=".log",
            initialfile=default,
            filetypes=[("Log file", "*.log"), ("Text file", "*.txt"),
                       ("All files", "*.*")],
        )
        if path:
            self._log_path = path
            self.var_log_path.set(f"Log file: {path}")
            self.var_log_enable.set(True)

    def _open_log_if_needed(self):
        if not self.var_log_enable.get():
            self._log_fp = None
            return
        if not self._log_path:
            # Auto pick default name in script directory
            here = os.path.dirname(os.path.abspath(__file__))
            self._log_path = os.path.join(
                here,
                f"ping_{self.var_target.get().replace('.', '_')}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            )
            self.var_log_path.set(f"Log file: {self._log_path}")
        try:
            self._log_fp = open(self._log_path, "a", encoding="utf-8",
                                buffering=1)  # line-buffered
            header = (f"# Ping log start {datetime.now().isoformat(timespec='seconds')}"
                      f"  target={self.var_target.get()}"
                      f"  interval={self.var_interval.get()}s"
                      f"  timeout={self.var_timeout.get()}ms\n")
            self._log_fp.write(header)
        except OSError as ex:
            messagebox.showerror("Log open failed", str(ex))
            self._log_fp = None
            self.var_log_enable.set(False)

    def _close_log(self):
        if self._log_fp:
            try:
                self._log_fp.write(
                    f"# Ping log stop {datetime.now().isoformat(timespec='seconds')}"
                    f"  total={self._total} ok={self._ok} fail={self._fail}\n"
                )
                self._log_fp.close()
            except OSError:
                pass
        self._log_fp = None

    # ---- control ----
    def start_mon(self):
        if self._worker and self._worker.is_alive():
            return
        target = self.var_target.get().strip()
        if not target:
            messagebox.showerror("Bad target", "Target is empty")
            return
        try:
            socket.gethostbyname(target)
        except OSError:
            messagebox.showerror("Bad target", f"Cannot resolve: {target}")
            return
        try:
            # Tolerate IME full-width "。" and locale comma as decimal point.
            raw_interval = (self.var_interval.get()
                            .replace("。", ".")
                            .replace(",", ".")
                            .strip())
            interval = float(raw_interval)
            timeout = int(self.var_timeout.get().strip())
            if interval < 0.1 or interval > 3600:
                raise ValueError("interval must be 0.1..3600 seconds")
            if timeout < 50 or timeout > 30000:
                raise ValueError("timeout must be 50..30000 ms")
        except ValueError as ex:
            messagebox.showerror("Bad input", str(ex))
            return

        self._stop_evt.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.var_status.set(f"Monitoring {target} every {interval}s ...")

        # Reset rolling stats but keep table (so user can run, stop, run again
        # without losing history). Clear only via explicit Clear button.
        self._open_log_if_needed()

        self._worker = threading.Thread(
            target=self._monitor_worker,
            args=(target, interval, timeout),
            daemon=True,
        )
        self._worker.start()

    def stop_mon(self):
        self._stop_evt.set()
        self.var_status.set("Stopping...")

    def _monitor_worker(self, target, interval_s, timeout_ms):
        # Pace using monotonic clock; ping itself can take up to ~timeout_ms.
        next_due = time.monotonic()
        while not self._stop_evt.is_set():
            ok, rtt = ping_host_rtt(target, timeout_ms)
            ts = time.time()
            self._queue.put(("sample", (ts, ok, rtt)))
            next_due += interval_s
            # If we fell behind (ping took longer than interval), skip ahead
            now = time.monotonic()
            sleep_for = next_due - now
            if sleep_for <= 0:
                next_due = now
                continue
            # Use Event.wait so Stop is responsive
            if self._stop_evt.wait(sleep_for):
                break
        self._queue.put(("done", None))

    # ---- UI updates ----
    def _drain_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "sample":
                    self._handle_sample(*payload)
                elif kind == "done":
                    self.btn_start.config(state=tk.NORMAL)
                    self.btn_stop.config(state=tk.DISABLED)
                    self.var_status.set(
                        f"Stopped. {self._total} samples, "
                        f"{self._fail} fail."
                    )
                    self._close_log()
        except queue.Empty:
            pass
        self.after(120, self._drain_queue)

    def _handle_sample(self, ts, ok, rtt):
        self._total += 1
        if ok:
            self._ok += 1
        else:
            self._fail += 1

        # Streak tracking
        flipped = False
        note = ""
        if self._streak_state is None:
            # First sample
            self._streak_state = ok
            self._streak_count = 1
            self._streak_start = ts
            self._last_change_at = ts
            note = "monitor start"
        elif ok == self._streak_state:
            self._streak_count += 1
        else:
            # State flipped
            duration = ts - (self._last_change_at or ts)
            if self._streak_state is True:
                note = f"DOWN after {self._fmt_dur(duration)} UP"
            else:
                note = f"UP after {self._fmt_dur(duration)} DOWN"
            # Update max-down-streak using the streak that just ended
            if self._streak_state is False:
                self._max_down_streak = max(self._max_down_streak,
                                            self._streak_count)
            self._streak_state = ok
            self._streak_count = 1
            self._streak_start = ts
            self._last_change_at = ts
            flipped = True

        # Update running max-down even while still in a down streak
        if self._streak_state is False:
            self._max_down_streak = max(self._max_down_streak,
                                        self._streak_count)

        # Filter: only state changes
        if self.var_only_changes.get() and not flipped \
                and self._total > 1:
            self._update_stats()
            return

        ts_text = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        status_text = "OK" if ok else "FAIL"
        rtt_text = f"{rtt:.1f}" if (ok and rtt is not None) else \
                   ("" if ok else "-")
        streak_text = f"x{self._streak_count}"

        if flipped:
            tag = "flip_up" if ok else "flip_down"
        else:
            tag = "ok" if ok else "fail"

        self.tree.insert("", tk.END,
                         values=(ts_text, status_text, rtt_text,
                                 streak_text, note),
                         tags=(tag,))
        # Auto-scroll to bottom + cap rows
        children = self.tree.get_children()
        if len(children) > self.LOG_LIMIT:
            for iid in children[: len(children) - self.LOG_LIMIT]:
                self.tree.delete(iid)
            children = self.tree.get_children()
        if children:
            self.tree.see(children[-1])

        # Write to log file
        if self._log_fp:
            try:
                self._log_fp.write(
                    f"{ts_text}\t{status_text}\t"
                    f"{rtt_text if rtt_text else '-'}\t"
                    f"{streak_text}\t{note}\n"
                )
            except OSError:
                pass

        self._update_stats()

    def _update_stats(self):
        loss = (self._fail / self._total * 100.0) if self._total else 0.0
        cur = "--"
        if self._streak_state is not None:
            label = "UP" if self._streak_state else "DOWN"
            since = (time.time() - (self._last_change_at or time.time()))
            cur = f"{label} x{self._streak_count} ({self._fmt_dur(since)})"
        self.var_stats.set(
            f"Total: {self._total}   OK: {self._ok}   Fail: {self._fail}   "
            f"Loss: {loss:.1f}%   Max-down-streak: {self._max_down_streak}   "
            f"Current: {cur}"
        )

    @staticmethod
    def _fmt_dur(seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        if seconds < 60:
            return f"{seconds:.1f}s"
        if seconds < 3600:
            m, s = divmod(int(seconds), 60)
            return f"{m}m{s:02d}s"
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h{m:02d}m{s:02d}s"

    def _clear_log(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._total = 0
        self._ok = 0
        self._fail = 0
        self._streak_state = None
        self._streak_count = 0
        self._streak_start = None
        self._max_down_streak = 0
        self._last_change_at = None
        self._update_stats()

    def _export_log(self):
        if not self.tree.get_children():
            messagebox.showinfo("Export", "No data to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export current log to...",
            defaultextension=".log",
            initialfile=f"ping_{self.var_target.get().replace('.', '_')}_"
                        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            filetypes=[("Log file", "*.log"), ("Text file", "*.txt")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(f"# Ping log export {datetime.now().isoformat(timespec='seconds')}"
                         f"  target={self.var_target.get()}\n")
                fp.write("Time\tStatus\tRTT(ms)\tStreak\tNote\n")
                for iid in self.tree.get_children():
                    vals = self.tree.item(iid, "values")
                    fp.write("\t".join(str(v) for v in vals) + "\n")
            messagebox.showinfo("Export", f"Saved to:\n{path}")
        except OSError as ex:
            messagebox.showerror("Export failed", str(ex))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _center_window(win) -> None:
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"+{x}+{y}")


def main():
    root = tk.Tk()
    root.title("Network Scanner")
    root.geometry("1080x560")
    try:
        root.iconbitmap(default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "netscan.ico"))
    except Exception:
        pass
    try:
        ttk.Style().theme_use("vista" if IS_WIN else "clam")
    except tk.TclError:
        pass

    nb = ttk.Notebook(root)
    nb.pack(fill=tk.BOTH, expand=True)
    nb.add(IpRangeScanFrame(nb), text="IP Range Scan")
    nb.add(PortScanFrame(nb), text="Port Scan")
    nb.add(PingMonitorFrame(nb), text="Ping Monitor")

    _center_window(root)
    root.mainloop()


if __name__ == "__main__":
    main()
