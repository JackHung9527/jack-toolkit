"""網路優先權設定工具。

列出所有網路介面與其 IPv4 interface metric（數字越小優先權越高），
可調整指定介面的 metric、一鍵降到最低、或改回自動。讀取免權限；
套用變更需要系統管理員權限，會跳 UAC 提權執行（變更可逆）。

持久化：套用時除了用 Set-NetIPInterface 讓設定當下生效，也直接把
InterfaceMetric 寫進該介面 GUID 的登錄檔機碼（Tcpip / Tcpip6），
等同 Windows「網路內容→IPv4→進階→取消自動計量值」的做法，
重開機後仍保留（純跑 Set-NetIPInterface 只進 ActiveStore，重開機會被沖掉）。

對應原本的 fix_network_priority.bat 之 GUI 版。
獨立執行：
    python main.py
也可經 jack-toolkit launcher 啟動（本目錄含 manifest.json）。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# === 全域 excepthook：在其他 import 之前裝好（pythonw 下錯誤可見）===
_ERROR_LOG = Path(__file__).resolve().parent / "netpriority_error.log"


def _global_excepthook(exc_type, exc_value, exc_tb) -> None:
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        _ERROR_LOG.write_text(tb_text, encoding="utf-8")
    except OSError:
        pass
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb

        _root = _tk.Tk()
        _root.withdraw()
        _mb.showerror("網路優先權工具啟動失敗",
                      f"Traceback 已寫到:\n{_ERROR_LOG}\n\n{tb_text[-1500:]}")
        _root.destroy()
    except Exception:
        pass


sys.excepthook = _global_excepthook

import ctypes
import json
import os
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

HERE = Path(__file__).resolve().parent
ICO_PATH = HERE / "netpriority.ico"
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW：別讓 powershell 跳黑窗


def _run_ps(script: str) -> tuple[int, str, str]:
    """執行一段 PowerShell（強制 UTF-8 輸出），回傳 (returncode, stdout, stderr)。"""
    full = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", full],
            capture_output=True, encoding="utf-8", errors="replace",
            creationflags=_NO_WINDOW,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except FileNotFoundError:
        return 1, "", "找不到 powershell.exe"


def _as_list(data):
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


class NetPriorityApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.rows: list[dict] = []
        self._busy = False

        root.title("網路優先權設定")
        root.geometry("760x520")
        root.minsize(640, 440)
        try:
            root.iconbitmap(default=str(ICO_PATH))
        except Exception:
            pass

        self._build()
        self.reload()

    # ---- UI ----
    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        head = ttk.Frame(self.root, padding=(12, 10, 12, 4))
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="網路介面優先權", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(head, foreground="#555",
                  text="優先權 = IPv4 interface metric，數字越小優先權越高。"
                       "套用變更需要系統管理員權限（會跳 UAC），"
                       "設定會寫入登錄檔，重開機後保留。").pack(anchor="w")

        # 表格
        table_box = ttk.Frame(self.root, padding=(12, 4))
        table_box.grid(row=2, column=0, sticky="nsew")
        table_box.columnconfigure(0, weight=1)
        table_box.rowconfigure(0, weight=1)

        cols = ("alias", "desc", "state", "metric", "mode", "idx")
        self.tree = ttk.Treeview(table_box, columns=cols, show="headings", selectmode="browse")
        headings = {
            "alias": ("介面", 130), "desc": ("描述", 240), "state": ("狀態", 70),
            "metric": ("優先權", 70), "mode": ("模式", 70), "idx": ("ifIndex", 60),
        }
        for c, (txt, w) in headings.items():
            self.tree.heading(c, text=txt)
            anchor = "center" if c in ("state", "metric", "mode", "idx") else "w"
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "desc"))
        ysb = ttk.Scrollbar(table_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("up", foreground="#0a7d28")
        self.tree.tag_configure("down", foreground="#999999")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())

        # 控制列
        ctrl = ttk.LabelFrame(self.root, text="調整選定介面的優先權", padding=10)
        ctrl.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 4))
        ctrl.columnconfigure(6, weight=1)

        ttk.Label(ctrl, text="優先權(metric):").grid(row=0, column=0, sticky="w")
        self.metric_var = tk.StringVar(value="10")
        self.metric_spin = ttk.Spinbox(ctrl, from_=1, to=9999, width=8, textvariable=self.metric_var)
        self.metric_spin.grid(row=0, column=1, sticky="w", padx=(4, 10))
        self.ipv6_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="同時套用 IPv6", variable=self.ipv6_var).grid(row=0, column=2, sticky="w")

        self.btn_apply = ttk.Button(ctrl, text="套用優先權", command=self._apply_metric)
        self.btn_apply.grid(row=0, column=3, padx=(12, 4))
        self.btn_low = ttk.Button(ctrl, text="降到最低 (9000)", command=self._apply_lowest)
        self.btn_low.grid(row=0, column=4, padx=4)
        self.btn_auto = ttk.Button(ctrl, text="改回自動", command=self._apply_auto)
        self.btn_auto.grid(row=0, column=5, padx=4)
        ttk.Button(ctrl, text="重新整理", command=self.reload).grid(row=0, column=7, sticky="e")

        self._action_btns = [self.btn_apply, self.btn_low, self.btn_auto]

        self.status = tk.StringVar(value="")
        bar = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        bar.grid(row=4, column=0, sticky="ew")
        ttk.Label(bar, textvariable=self.status, foreground="#555").pack(side="left")

        self._set_action_state("disabled")

    def _set_action_state(self, state: str) -> None:
        for b in self._action_btns:
            b.configure(state=state)

    def _on_select(self) -> None:
        row = self._selected_row()
        if row is None:
            self._set_action_state("disabled")
            return
        self._set_action_state("normal" if not self._busy else "disabled")
        if row.get("metric") is not None:
            self.metric_var.set(str(row["metric"]))

    def _selected_row(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        idx = int(sel[0])
        return next((r for r in self.rows if r["idx"] == idx), None)

    # ---- 讀取 ----
    def reload(self) -> None:
        if self._busy:
            return
        self.status.set("讀取網路介面中…")
        self._busy = True
        self._set_action_state("disabled")
        threading.Thread(target=self._reload_worker, daemon=True).start()

    def _reload_worker(self) -> None:
        rc, out, err = _run_ps(
            "Get-NetIPInterface -AddressFamily IPv4 | "
            "Select-Object ifIndex,InterfaceAlias,InterfaceMetric,AutomaticMetric,ConnectionState | "
            "ConvertTo-Json -Compress"
        )
        rc2, out2, _ = _run_ps(
            "Get-NetAdapter | Select-Object ifIndex,InterfaceDescription,Status | ConvertTo-Json -Compress"
        )
        rows: list[dict] = []
        error = ""
        try:
            ipdata = _as_list(json.loads(out)) if out.strip() else []
            adata = _as_list(json.loads(out2)) if out2.strip() else []
            desc_by_idx = {a.get("ifIndex"): a for a in adata}
            for it in ipdata:
                alias = it.get("InterfaceAlias") or ""
                if "Loopback" in alias:
                    continue
                idx = it.get("ifIndex")
                a = desc_by_idx.get(idx, {})
                rows.append({
                    "idx": idx,
                    "alias": alias,
                    "desc": a.get("InterfaceDescription") or "",
                    "connected": it.get("ConnectionState") == 1,
                    "metric": it.get("InterfaceMetric"),
                    "auto": it.get("AutomaticMetric") == 1,
                })
            rows.sort(key=lambda r: (r["metric"] is None, r["metric"] if r["metric"] is not None else 0))
        except (ValueError, TypeError) as exc:
            error = f"解析失敗: {exc}\n{err}"
        self.root.after(0, lambda: self._reload_done(rows, error))

    def _reload_done(self, rows: list[dict], error: str) -> None:
        self._busy = False
        self.rows = rows
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            tag = "up" if r["connected"] else "down"
            self.tree.insert("", "end", iid=str(r["idx"]), tags=(tag,), values=(
                r["alias"],
                r["desc"],
                "連線中" if r["connected"] else "已斷線",
                "-" if r["metric"] is None else r["metric"],
                "自動" if r["auto"] else "手動",
                r["idx"],
            ))
        if error:
            self.status.set(error.splitlines()[0])
        else:
            self.status.set(f"共 {len(rows)} 個介面。數字越小優先權越高。")

    # ---- 套用（提權）----
    def _apply_metric(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        try:
            metric = int(self.metric_var.get())
        except ValueError:
            messagebox.showwarning("優先權無效", "請輸入 1~9999 的整數")
            return
        if not (1 <= metric <= 9999):
            messagebox.showwarning("優先權無效", "請輸入 1~9999 的整數")
            return
        self._do_set(row, _metric_script(row["idx"], metric, self.ipv6_var.get()),
                     f"已將「{row['alias']}」優先權(metric)設為 {metric}（已寫入登錄檔，重開機後保留）")

    def _apply_lowest(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        if not messagebox.askyesno("降到最低",
                                   f"將「{row['alias']}」的 metric 設為 9000（降到最低優先權）？"):
            return
        self._do_set(row, _metric_script(row["idx"], 9000, self.ipv6_var.get()),
                     f"已將「{row['alias']}」降到最低優先權 (metric 9000，重開機後保留)")

    def _apply_auto(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self._do_set(row, _auto_script(row["idx"], self.ipv6_var.get()),
                     f"已將「{row['alias']}」改回自動 metric（已移除登錄檔設定）")

    def _do_set(self, row: dict, inner: str, success_msg: str) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_action_state("disabled")
        self.status.set("套用中…請在 UAC 視窗按「是」")
        threading.Thread(target=self._set_worker, args=(inner, success_msg), daemon=True).start()

    def _set_worker(self, inner: str, success_msg: str) -> None:
        # 提權子程序的詳細錯誤寫到這個 temp log（-Verb RunAs 不能用 -Redirect*，只能靠檔案傳回）
        log = Path(os.environ.get("TEMP", os.environ.get("TMP", "."))) / "netpriority_apply.log"
        try:
            log.unlink()  # 先清掉，避免讀到上一輪的殘留
        except OSError:
            pass

        quoted = "'" + inner.replace("'", "''") + "'"
        # -PassThru 取回提權子程序物件，再 exit 它的 ExitCode，否則 inner 失敗也會被當成成功
        outer = (
            "$ErrorActionPreference='Stop';"
            "$p=Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList "
            "@('-NoProfile','-WindowStyle','Hidden','-Command'," + quoted + ");"
            "exit $p.ExitCode"
        )
        rc, _out, err = _run_ps(outer)
        detail = ""
        if rc != 0:
            try:
                if log.exists():
                    detail = log.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                pass
        self.root.after(0, lambda: self._set_done(rc, err, detail, success_msg))

    def _set_done(self, rc: int, err: str, detail: str, success_msg: str) -> None:
        self._busy = False
        if rc == 0:
            self.status.set(success_msg)
            self.reload()
        else:
            low = (err + " " + detail).lower()
            if "cancel" in low or "取消" in err or "取消" in detail or "by the user" in low:
                self.status.set("已取消（未提權）")
            else:
                msg = detail.strip() or err.strip() or "未知錯誤"
                self.status.set("套用失敗：" + msg.splitlines()[0])
            self._set_action_state("normal")


def _elevated_script(idx: int, body: str) -> str:
    """組出在提權 powershell 內執行的腳本。

    先由 ifIndex 解析出介面 GUID，算出 Tcpip / Tcpip6 兩個登錄檔機碼路徑（$reg4 / $reg6），
    再執行傳入的 body（寫入或移除 InterfaceMetric），最後把成功/失敗用 exit code 回傳，
    失敗時把 traceback 寫到 %TEMP%\\netpriority_apply.log 供 host 端顯示。
    body 可使用 $idx / $reg4 / $reg6 三個變數。
    """
    return (
        "$ErrorActionPreference='Stop';"
        "$log=Join-Path $env:TEMP 'netpriority_apply.log';"
        "try{"
        f"$idx={idx};"
        "$guid=(Get-NetAdapter -InterfaceIndex $idx -ErrorAction Stop).InterfaceGuid;"
        "if([string]::IsNullOrEmpty($guid)){throw ('ifIndex '+$idx+' has no InterfaceGuid')};"
        "$reg4='HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\'+$guid;"
        "$reg6='HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip6\\Parameters\\Interfaces\\'+$guid;"
        + body +
        "Remove-Item $log -Force -ErrorAction SilentlyContinue;"
        "exit 0"
        "}catch{"
        "$_|Out-String|Set-Content -LiteralPath $log -Encoding UTF8;"
        "exit 1"
        "}"
    )


def _metric_script(idx: int, metric: int, ipv6: bool) -> str:
    # 登錄檔寫入 = 持久（重開機保留）；Set-NetIPInterface = 當下立即生效（不必等重開機）
    body = (
        f"if(Test-Path $reg4){{Set-ItemProperty -LiteralPath $reg4 -Name InterfaceMetric -Type DWord -Value {metric}}};"
        f"Set-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4 -InterfaceMetric {metric} -ErrorAction SilentlyContinue;"
    )
    if ipv6:
        body += (
            f"if(Test-Path $reg6){{Set-ItemProperty -LiteralPath $reg6 -Name InterfaceMetric -Type DWord -Value {metric}}};"
            f"Set-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv6 -InterfaceMetric {metric} -ErrorAction SilentlyContinue;"
        )
    return _elevated_script(idx, body)


def _auto_script(idx: int, ipv6: bool) -> str:
    # 移除登錄檔值 = 重開機後恢復自動；Set-NetIPInterface -AutomaticMetric Enabled = 當下立即恢復自動
    body = (
        "if(Test-Path $reg4){Remove-ItemProperty -LiteralPath $reg4 -Name InterfaceMetric -ErrorAction SilentlyContinue};"
        "Set-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4 -AutomaticMetric Enabled -ErrorAction SilentlyContinue;"
    )
    if ipv6:
        body += (
            "if(Test-Path $reg6){Remove-ItemProperty -LiteralPath $reg6 -Name InterfaceMetric -ErrorAction SilentlyContinue};"
            "Set-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv6 -AutomaticMetric Enabled -ErrorAction SilentlyContinue;"
        )
    return _elevated_script(idx, body)


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _center_window(win) -> None:
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"+{x}+{y}")


def main() -> int:
    _enable_dpi_awareness()
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    NetPriorityApp(root)
    _center_window(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
