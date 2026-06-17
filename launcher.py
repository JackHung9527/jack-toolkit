"""jack-toolkit launcher.

tkinter dashboard：自動掃描 tools/*/manifest.json，
每個子工具一張卡片，按下「啟動」就 spawn 一個獨立 process。
Launcher 自己不會關閉，可重複啟動或同時開多個工具。
右側列出目前還活著的子程序，可單獨終止。

PyInstaller frozen 模式：
    本檔同時是 launcher 又是 tool dispatcher。
    `launcher.exe --tool <name>` 會把該 tool 的 entry 當入口執行；
    launcher 自身按下「啟動」時若偵測到 frozen，就 spawn 自己加 --tool 旗標。
    這樣整套打包成單一 exe 也能跑（前提是 PyInstaller spec 要 hidden-import 各 tool 的依賴）。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# === 全域 excepthook：在所有其他 import 之前裝好 ===
# 用 pythonw.exe 跑時 stderr 被吃掉，任何未捕捉例外都會「靜默死掉」沒線索。
# 這個 hook 把 traceback 寫到 launcher_error.log，並嘗試跳一個 tkinter messagebox
# 顯示前 1500 字元。這樣 .bat 用 pythonw 啟動失敗時使用者也能看到原因。
_ERROR_LOG = Path(__file__).resolve().parent / "launcher_error.log"


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
        _mb.showerror(
            "jack-toolkit launcher 啟動失敗",
            f"Traceback 已寫到:\n{_ERROR_LOG}\n\n錯誤摘要:\n{tb_text[-1500:]}",
        )
        _root.destroy()
    except Exception:
        pass


sys.excepthook = _global_excepthook

import ctypes
import json
import runpy
import subprocess
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent
TOOLS_DIR = ROOT / "tools"
LAUNCHER_ICO = ROOT / "launcher.ico"
POLL_INTERVAL_MS = 500
IS_FROZEN = bool(getattr(sys, "frozen", False))


_WHEEL_TARGETS: "list[tk.Canvas]" = []


def _register_wheel_target(canvas: tk.Canvas) -> None:
    """登記一個 canvas 為「游標飄到上面時要被滾輪捲動」的目標。

    所有 canvas 共用一個全域 <MouseWheel> binding；分派時靠 winfo_containing()
    判斷游標下是哪個 canvas（或其子 widget），找到了就 yview_scroll 它。
    這套作法不會被「游標進到 canvas 內某個 child widget 觸發 Leave」搞混。
    """
    _WHEEL_TARGETS.append(canvas)


def _bind_mousewheel(canvas: tk.Canvas, _inner: tk.Misc) -> None:
    """API 保留給呼叫端，內部委派給 _register_wheel_target。"""
    _register_wheel_target(canvas)


def _install_global_wheel(root: tk.Tk) -> None:
    """裝一次全域滑鼠滾輪 handler，依游標位置 dispatch 到對應 canvas。"""
    def _on_wheel(event: tk.Event) -> str:
        if hasattr(event, "delta") and event.delta:
            step = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            return ""
        # 找游標底下哪個 widget 屬於哪個 scroll canvas
        try:
            w = root.winfo_containing(event.x_root, event.y_root)
        except KeyError:
            w = None
        target: tk.Canvas | None = None
        while w is not None:
            if w in _WHEEL_TARGETS:
                target = w  # type: ignore[assignment]
                break
            try:
                w = w.master
            except AttributeError:
                break
        if target is None:
            return ""
        bbox = target.bbox("all")
        if bbox is None or bbox[3] - bbox[1] <= target.winfo_height():
            return "break"
        target.yview_scroll(step, "units")
        return "break"

    root.bind_all("<MouseWheel>", _on_wheel)
    root.bind_all("<Button-4>", _on_wheel)
    root.bind_all("<Button-5>", _on_wheel)


def _center_window(win) -> None:
    """把視窗置中於螢幕（在 mainloop 前呼叫，視窗一出現就在中央）。"""
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"+{x}+{y}")


@dataclass
class Tool:
    name: str
    display_name: str
    description: str
    entry: Path
    framework: str
    cwd: Path
    icon: Path | None

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> "Tool":
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        cwd = manifest_path.parent
        icon_png = cwd / "icon.png"
        return cls(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            description=data.get("description", ""),
            entry=cwd / data["entry"],
            framework=data.get("framework", "?"),
            cwd=cwd,
            icon=icon_png if icon_png.is_file() else None,
        )


def discover_tools() -> list[Tool]:
    tools: list[Tool] = []
    if not TOOLS_DIR.is_dir():
        return tools
    for manifest in sorted(TOOLS_DIR.glob("*/manifest.json")):
        try:
            tools.append(Tool.from_manifest(manifest))
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            print(f"[launcher] 略過 {manifest}: {exc}", file=sys.stderr)
    return tools


def dispatch_tool(name: str) -> int:
    """以 module entry 方式直接執行指定工具（給 frozen 模式重入用）。"""
    tools = discover_tools()
    target = next((t for t in tools if t.name == name), None)
    if target is None:
        print(f"[launcher] 找不到工具: {name}", file=sys.stderr)
        return 2
    if not target.entry.is_file():
        print(f"[launcher] entry 不存在: {target.entry}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(target.cwd))
    runpy.run_path(str(target.entry), run_name="__main__")
    return 0


def _spawn_command(tool: Tool) -> tuple[list[str], dict]:
    """回傳 (cmd, popen_kwargs) — frozen 與 source 模式分流。"""
    if IS_FROZEN:
        # 重新 spawn 自己，靠 --tool dispatch 進入該工具
        return ([sys.executable, "--tool", tool.name], {"cwd": str(tool.cwd)})
    return ([sys.executable, str(tool.entry)], {"cwd": str(tool.cwd)})


class LauncherApp:
    def __init__(self, root: tk.Tk, tools: list[Tool]) -> None:
        self.root = root
        self.tools = tools
        self.processes: list[tuple[Tool, subprocess.Popen[bytes], ttk.Frame]] = []
        self.empty_label: tk.Widget | None = None
        self._card_images: list[tk.PhotoImage] = []  # 保留參照避免被 GC

        root.title("jack-toolkit launcher")
        root.geometry("900x520")
        root.minsize(720, 420)
        try:
            root.iconbitmap(default=str(LAUNCHER_ICO))
        except Exception:
            pass

        self._build_ui()
        _center_window(root)
        _install_global_wheel(root)
        self._poll_processes()

    def _build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(1, weight=1)

        header = ttk.Label(
            outer,
            text="jack-toolkit",
            font=("Segoe UI", 18, "bold"),
        )
        header.grid(row=0, column=0, sticky="w", pady=(0, 8))
        sub = ttk.Label(
            outer,
            text="個人工具集合 — 每個子工具皆為獨立程序",
            foreground="#666",
        )
        sub.grid(row=0, column=1, sticky="w", pady=(0, 8))

        # ===== 左側：可用工具（含垂直滑桿，工具多時可捲動）=====
        cards_box = ttk.LabelFrame(outer, text="可用工具", padding=4)
        cards_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        cards_box.columnconfigure(0, weight=1)
        cards_box.rowconfigure(0, weight=1)

        cards_canvas = tk.Canvas(cards_box, borderwidth=0, highlightthickness=0)
        cards_scroll = ttk.Scrollbar(cards_box, orient="vertical", command=cards_canvas.yview)
        cards = ttk.Frame(cards_canvas)
        cards.columnconfigure(0, weight=1)

        cards_window = cards_canvas.create_window((0, 0), window=cards, anchor="nw")

        def _on_cards_inner_configure(_event: tk.Event) -> None:
            cards_canvas.configure(scrollregion=cards_canvas.bbox("all"))

        def _on_cards_canvas_configure(event: tk.Event) -> None:
            # 內層 frame 寬度跟著 canvas 視窗寬度走，避免卡片被壓在左邊
            cards_canvas.itemconfigure(cards_window, width=event.width)

        cards.bind("<Configure>", _on_cards_inner_configure)
        cards_canvas.bind("<Configure>", _on_cards_canvas_configure)
        cards_canvas.configure(yscrollcommand=cards_scroll.set)
        cards_canvas.grid(row=0, column=0, sticky="nsew")
        cards_scroll.grid(row=0, column=1, sticky="ns")

        if not self.tools:
            ttk.Label(
                cards,
                text="找不到任何工具。\n請確認 tools/<name>/manifest.json 是否存在。",
                foreground="#a33",
                justify="left",
            ).pack(padx=8, pady=8, anchor="w")
        else:
            for idx, tool in enumerate(self.tools):
                self._make_card(cards, tool, idx)

        _bind_mousewheel(cards_canvas, cards)

        # ===== 右側：執行中（也支援滑鼠滾輪）=====
        running = ttk.LabelFrame(outer, text="執行中", padding=8)
        running.grid(row=1, column=1, sticky="nsew")
        running.columnconfigure(0, weight=1)
        running.rowconfigure(0, weight=1)

        canvas = tk.Canvas(running, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(running, orient="vertical", command=canvas.yview)
        self.running_box = ttk.Frame(canvas)
        self.running_box.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.running_box, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        _bind_mousewheel(canvas, self.running_box)

        self.empty_label = ttk.Label(
            self.running_box,
            text="(尚未啟動任何工具)",
            foreground="#888",
        )
        self.empty_label.pack(anchor="w", padx=4, pady=4)

        bar = ttk.Frame(outer)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        runtime_label = "frozen exe" if IS_FROZEN else f"Python: {sys.executable}"
        ttk.Label(bar, text=runtime_label, foreground="#888").pack(side="left")
        ttk.Button(bar, text="關閉 launcher", command=self.root.destroy).pack(side="right")

    def _make_card(self, parent: ttk.Widget, tool: Tool, idx: int) -> None:
        card = ttk.Frame(parent, padding=10, relief="groove", borderwidth=1)
        card.grid(row=idx, column=0, sticky="ew", pady=4)
        card.columnconfigure(1, weight=1)

        # 工具圖示（icon.png 存在才顯示）
        if tool.icon is not None:
            try:
                img = tk.PhotoImage(file=str(tool.icon))
                self._card_images.append(img)
                ttk.Label(card, image=img).grid(row=0, column=0, rowspan=3,
                                                sticky="n", padx=(0, 10))
            except Exception:
                pass

        title = ttk.Label(card, text=tool.display_name, font=("Segoe UI", 11, "bold"))
        title.grid(row=0, column=1, sticky="w")

        tag = ttk.Label(card, text=f"[{tool.framework}]", foreground="#369")
        tag.grid(row=0, column=2, sticky="e", padx=(8, 0))

        desc = ttk.Label(card, text=tool.description, foreground="#444", wraplength=420)
        desc.grid(row=1, column=1, columnspan=2, sticky="w", pady=(2, 6))

        path = ttk.Label(
            card,
            text=str(tool.entry.relative_to(ROOT)),
            foreground="#888",
            font=("Consolas", 9),
        )
        path.grid(row=2, column=1, sticky="w")

        btn = ttk.Button(card, text="啟動", command=lambda t=tool: self._launch(t))
        btn.grid(row=2, column=2, sticky="e")

    def _launch(self, tool: Tool) -> None:
        if not IS_FROZEN and not tool.entry.is_file():
            messagebox.showerror(
                "啟動失敗",
                f"找不到 entry 檔案:\n{tool.entry}",
            )
            return
        cmd, kwargs = _spawn_command(tool)
        # 抓子程序 stderr 才能在啟動失敗時顯示原因
        kwargs.setdefault("stderr", subprocess.PIPE)
        kwargs.setdefault("stdout", subprocess.DEVNULL)
        kwargs.setdefault("text", True)
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except OSError as exc:
            messagebox.showerror("啟動失敗", f"{tool.display_name}\n{exc}")
            return
        self._add_running(tool, proc)

    def _add_running(self, tool: Tool, proc: subprocess.Popen[bytes]) -> None:
        if self.empty_label is not None:
            self.empty_label.destroy()
            self.empty_label = None

        row = ttk.Frame(self.running_box, padding=(4, 3))
        row.pack(fill="x", anchor="w")
        row.columnconfigure(0, weight=1)

        label = ttk.Label(row, text=f"{tool.display_name}  PID={proc.pid}")
        label.grid(row=0, column=0, sticky="w")

        kill_btn = ttk.Button(
            row,
            text="終止",
            width=6,
            command=lambda p=proc: self._terminate(p),
        )
        kill_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self.processes.append((tool, proc, row))

    def _terminate(self, proc: subprocess.Popen[bytes]) -> None:
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _poll_processes(self) -> None:
        survivors = []
        crashed: list[tuple[Tool, int, str]] = []
        for tool, proc, row in self.processes:
            if proc.poll() is None:
                survivors.append((tool, proc, row))
                continue
            # 子程序已退出：若 returncode != 0 就視為崩潰，抓 stderr 給使用者看
            stderr_data = ""
            if proc.stderr is not None:
                try:
                    stderr_data = proc.stderr.read() or ""
                except (OSError, ValueError):
                    pass
                finally:
                    try:
                        proc.stderr.close()
                    except OSError:
                        pass
            rc = proc.returncode if proc.returncode is not None else -1
            if rc != 0:
                crashed.append((tool, rc, stderr_data))
            row.destroy()
        self.processes = survivors

        if not self.processes and self.empty_label is None:
            self.empty_label = ttk.Label(
                self.running_box,
                text="(尚未啟動任何工具)",
                foreground="#888",
            )
            self.empty_label.pack(anchor="w", padx=4, pady=4)

        # 用 after(0) 把錯誤訊息排到事件迴圈後面顯示，避免阻塞 polling
        for tool, rc, err in crashed:
            self.root.after(0, lambda t=tool, r=rc, e=err: self._show_child_error(t, r, e))

        self.root.after(POLL_INTERVAL_MS, self._poll_processes)

    def _show_child_error(self, tool: Tool, rc: int, stderr_data: str) -> None:
        body = stderr_data.strip() or "(子程序 stderr 沒有輸出)"
        if len(body) > 2000:
            body = body[-2000:]
        # 偵測 ModuleNotFoundError 直接給出對的 pip 指令
        hint = ""
        if "ModuleNotFoundError" in stderr_data or "No module named" in stderr_data:
            hint = (
                "\n\n看起來缺少 Python 套件，請用「Launcher 同一個 Python」執行："
                f'\n  "{sys.executable}" -m pip install -r "{ROOT / "requirements.txt"}"'
                "\n或雙擊根目錄的 install_requirements.bat"
            )
        messagebox.showerror(
            f"{tool.display_name} 啟動失敗",
            f"exit code: {rc}\n\n{body}{hint}",
        )


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> int:
    # --tool <name>：dispatch 模式（給 frozen exe 重入用，source 模式也可直接呼叫）
    if len(sys.argv) >= 3 and sys.argv[1] == "--tool":
        return dispatch_tool(sys.argv[2])

    _enable_dpi_awareness()
    tools = discover_tools()
    root = tk.Tk()
    LauncherApp(root, tools)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
