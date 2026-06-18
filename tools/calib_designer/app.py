"""校正設計工具 — 主視窗 UI（tkinter + 嵌入式 matplotlib）。

左側控制面板：資料輸入、模式（給點數 / 給目標誤差）、誤差量度（絕對 / 相對）、
演算法（貪婪 / DP 最佳）、對照開關、結果摘要、三種匯出。
右側：上半 XY 疊圖（原始散點 + 最佳化折線 + 均勻折線），下半 誤差 vs x 圖。
"""

from __future__ import annotations

import csv
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib

# 中文標籤需要 CJK 字型，否則 matplotlib 會畫成豆腐方塊。
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft JhengHei", "Microsoft YaHei", "SimHei", "Segoe UI", "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)

import theme
import engine


def _example_points() -> list[tuple[float, float]]:
    """範例資料：電流校正（x=原始讀值, y=目標），與 電流校正範例.csv 同一組。"""
    return [
        (0.960, 1.008), (1.883, 2.013), (2.821, 3.035), (3.722, 4.025),
        (4.703, 5.090), (5.604, 6.080), (6.462, 7.012), (7.429, 8.064),
        (8.330, 9.056), (9.231, 10.044), (10.161, 11.083), (11.070, 12.091),
        (12.000, 13.156), (12.799, 14.086), (13.648, 15.121), (14.418, 16.111),
        (15.143, 17.101), (15.824, 18.106), (16.454, 19.126), (17.004, 20.116),
        (17.524, 21.149), (17.963, 22.139),
    ]


def _parse_text(raw: str) -> tuple[list[tuple[float, float]], list[str]]:
    """把多行 'x, y' 文字解析成點集。回傳 (points, warnings)。"""
    points: list[tuple[float, float]] = []
    warnings: list[str] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = [p for p in s.replace(",", " ").replace("\t", " ").split() if p]
        if len(parts) < 2:
            warnings.append(f"第 {lineno} 行欄位不足，已略過：{s!r}")
            continue
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            # 可能是表頭，靜默略過（只在不是第一行時才提醒）
            if lineno != 1:
                warnings.append(f"第 {lineno} 行非數值，已略過：{s!r}")
            continue
        points.append((x, y))
    return points, warnings


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.curve: engine.Curve | None = None
        self._recompute_job: str | None = None
        self._last: dict | None = None  # 最近一次結果，供匯出使用

        root.title("校正設計工具")
        root.configure(bg=theme.BG)
        root.geometry("1180x850")
        root.minsize(980, 680)

        # 控制變數
        self.method_kind = tk.StringVar(value="lut")      # lut / reg（校正方式）
        self.mode_var = tk.StringVar(value="count")       # count / target
        self.metric_var = tk.StringVar(value="abs")       # abs / rel
        self.method_var = tk.StringVar(value="greedy")    # greedy / dp
        self.manual_mode = tk.BooleanVar(value=False)     # 手動插點模式
        self.n_var = tk.IntVar(value=6)
        self.target_var = tk.StringVar(value="1.0")
        self.reg_n_var = tk.IntVar(value=6)               # 回歸取樣點數
        self.group_var = tk.StringVar(value="lut")        # C 匯出的組名
        self._algo_count = 2                              # 手動模式的節點數上限
        # 圖表比較項目（可同時疊多條）
        self.show_algo1 = tk.BooleanVar(value=True)       # 線性內插：演算法 1
        self.show_algo2 = tk.BooleanVar(value=False)      # 線性內插：演算法 2
        self.show_reg = tk.BooleanVar(value=False)        # 線性回歸
        self.show_uniform = tk.BooleanVar(value=True)     # 均勻
        self.show_raw = tk.BooleanVar(value=False)        # 原始（校正前）

        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self._build_controls(root)
        self._build_chart(root)
        self._update_target_unit()
        self._update_kind_hint()
        self._sync_overlay_locks()   # 鎖定主方法的勾選項（一律顯示）

        # 啟動載入範例資料
        self._set_rows(_example_points(), initial=True)

    # === 左側控制面板 ===

    def _build_controls(self, root: tk.Tk) -> None:
        style = ttk.Style(root)
        style.configure("Treeview", rowheight=22, font=(theme.MONO, 10))
        style.configure("Treeview.Heading", font=(theme.UI, 9, "bold"))

        # 左側面板做成可捲動容器（內容高於視窗時用滾輪或捲軸）
        holder = tk.Frame(root, bg=theme.BG, width=378)
        holder.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        holder.grid_propagate(False)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        pcanvas = tk.Canvas(holder, bg=theme.BG, highlightthickness=0)
        psb = ttk.Scrollbar(holder, orient="vertical", command=pcanvas.yview)
        pcanvas.configure(yscrollcommand=psb.set)
        pcanvas.grid(row=0, column=0, sticky="nsew")
        psb.grid(row=0, column=1, sticky="ns")
        self._panel_canvas = pcanvas

        panel = tk.Frame(pcanvas, bg=theme.BG)
        pwin = pcanvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", lambda _e: pcanvas.configure(scrollregion=pcanvas.bbox("all")))
        pcanvas.bind("<Configure>", lambda e: pcanvas.itemconfigure(pwin, width=e.width))
        root.bind_all("<MouseWheel>", self._on_global_wheel, add="+")

        # --- 資料輸入（datagrid，雙擊儲存格編輯） ---
        g_data = theme.group(panel, "資料輸入")
        g_data.pack(fill="x", pady=(0, 8))
        tk.Label(g_data, text="雙擊儲存格編輯 x / y；手動模式下點「節點」欄選節點",
                 bg=theme.BG, fg=theme.TEXT_MUTED, font=(theme.UI, 8)).pack(anchor="w")
        tree_wrap = tk.Frame(g_data, bg=theme.BG)
        tree_wrap.pack(fill="x")
        self.tree = ttk.Treeview(tree_wrap, columns=("idx", "x", "y", "node"),
                                 show="headings", height=6, selectmode="extended")
        self.tree.heading("idx", text="#")
        self.tree.heading("x", text="x 原始")
        self.tree.heading("y", text="y 目標")
        self.tree.heading("node", text="節點")
        self.tree.column("idx", width=30, anchor="center", stretch=False)
        self.tree.column("x", width=98, anchor="e")
        self.tree.column("y", width=98, anchor="e")
        self.tree.column("node", width=44, anchor="center", stretch=False)
        vs = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="x", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.tag_configure("nodecol", background="#dce8f6")
        self.tree.bind("<Double-1>", self._on_cell_edit)
        self.tree.bind("<Button-1>", self._on_tree_click)

        btns1 = tk.Frame(g_data, bg=theme.BG)
        btns1.pack(fill="x", pady=(6, 0))
        theme.make_button(btns1, "新增列", self._row_add).pack(side="left")
        theme.make_button(btns1, "刪除選取", self._row_del).pack(side="left", padx=4)
        theme.make_button(btns1, "清除", self._clear_data).pack(side="left")
        btns2 = tk.Frame(g_data, bg=theme.BG)
        btns2.pack(fill="x", pady=(4, 0))
        theme.make_button(btns2, "匯入 CSV", self._import_csv).pack(side="left")
        theme.make_button(btns2, "空白 CSV", self._new_blank_csv).pack(side="left", padx=4)
        theme.make_button(btns2, "範例", self._load_example).pack(side="left")

        # --- 校正方式 ---
        g_kind = theme.group(panel, "校正方式")
        g_kind.pack(fill="x", pady=(0, 8))
        row_kind = tk.Frame(g_kind, bg=theme.BG)
        row_kind.pack(fill="x")
        for txt, val in (("分段線性查表 (LUT)", "lut"), ("線性回歸", "reg")):
            tk.Radiobutton(row_kind, text=txt, variable=self.method_kind, value=val,
                           bg=theme.BG, fg=theme.TEXT_PRIMARY, activebackground=theme.BG,
                           selectcolor=theme.GROUP_BG, font=(theme.UI, 10),
                           command=self._on_kind_change).pack(side="left", padx=(0, 10))
        theme.make_button(row_kind, "公式", self._show_formulas).pack(side="left", padx=(4, 0))
        self.kind_hint = tk.Label(g_kind, text="", bg=theme.BG, fg=theme.TEXT_MUTED,
                                  font=(theme.UI, 8), justify="left")
        self.kind_hint.pack(anchor="w", pady=(2, 0))
        # 回歸取樣點數滑桿（只在回歸模式顯示）
        self.reg_n_row = tk.Frame(g_kind, bg=theme.BG)
        tk.Label(self.reg_n_row, text="回歸取樣點數", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        self.reg_n_scale = tk.Scale(self.reg_n_row, from_=2, to=20, orient="horizontal",
                                    variable=self.reg_n_var, bg=theme.BG, troughcolor=theme.PANEL,
                                    highlightthickness=0, length=140, command=self._on_reg_n_change)
        self.reg_n_scale.pack(side="left", padx=(6, 0))

        # --- 模式（LUT 節點數）---
        g_mode = theme.group(panel, "LUT 節點選法")
        g_mode.pack(fill="x", pady=(0, 8))
        tk.Radiobutton(g_mode, text="給點數，找最佳位置", variable=self.mode_var,
                       value="count", bg=theme.BG, fg=theme.TEXT_PRIMARY,
                       activebackground=theme.BG, selectcolor=theme.GROUP_BG,
                       font=(theme.UI, 10), command=self._on_mode_change).pack(anchor="w")
        row_n = tk.Frame(g_mode, bg=theme.BG)
        row_n.pack(fill="x", padx=(20, 0))
        tk.Label(row_n, text="節點數 N", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        self.n_scale = tk.Scale(row_n, from_=2, to=20, orient="horizontal",
                                variable=self.n_var, bg=theme.BG, troughcolor=theme.PANEL,
                                highlightthickness=0, length=150,
                                command=lambda _v: self._schedule_recompute())
        self.n_scale.pack(side="left", padx=(6, 0))

        tk.Radiobutton(g_mode, text="給目標最大誤差，找最少點數", variable=self.mode_var,
                       value="target", bg=theme.BG, fg=theme.TEXT_PRIMARY,
                       activebackground=theme.BG, selectcolor=theme.GROUP_BG,
                       font=(theme.UI, 10), command=self._on_mode_change).pack(anchor="w", pady=(4, 0))
        row_e = tk.Frame(g_mode, bg=theme.BG)
        row_e.pack(fill="x", padx=(20, 0))
        tk.Label(row_e, text="目標誤差 E", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        self.target_entry = theme.make_entry(row_e, self.target_var, width=8)
        self.target_entry.pack(side="left", padx=(6, 0))
        self.target_entry.bind("<Return>", lambda _e: self._schedule_recompute())
        self.target_entry.bind("<FocusOut>", lambda _e: self._schedule_recompute())
        # 單位標示：跟著「誤差量度」切換（相對 → 「% 以內」；絕對 → 「（絕對值）」）
        self.target_unit = tk.Label(row_e, text="", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                                    font=(theme.UI, 10))
        self.target_unit.pack(side="left", padx=(4, 0))

        # --- 誤差量度 ---
        g_metric = theme.group(panel, "誤差量度")
        g_metric.pack(fill="x", pady=(0, 8))
        for txt, val in (("絕對誤差 |Δy|", "abs"), ("相對誤差 % 讀值", "rel")):
            tk.Radiobutton(g_metric, text=txt, variable=self.metric_var, value=val,
                           bg=theme.BG, fg=theme.TEXT_PRIMARY, activebackground=theme.BG,
                           selectcolor=theme.GROUP_BG, font=(theme.UI, 10),
                           command=self._on_metric_change).pack(side="left", padx=(0, 10))

        # --- 演算法 ---
        g_algo = theme.group(panel, "配點演算法")
        g_algo.pack(fill="x", pady=(0, 8))
        row_algo = tk.Frame(g_algo, bg=theme.BG)
        row_algo.pack(fill="x")
        for txt, val in (("演算法 1", "greedy"), ("演算法 2", "dp")):
            tk.Radiobutton(row_algo, text=txt, variable=self.method_var, value=val,
                           bg=theme.BG, fg=theme.TEXT_PRIMARY, activebackground=theme.BG,
                           selectcolor=theme.GROUP_BG, font=(theme.UI, 10),
                           command=self._on_algo_change).pack(side="left", padx=(0, 10))
        theme.make_button(row_algo, "說明", self._show_algo_info).pack(side="left", padx=(6, 0))
        self.manual_chk = tk.Checkbutton(
            g_algo, text="手動插點模式（自己選節點，點數=演算法）",
            variable=self.manual_mode, bg=theme.BG, fg=theme.TEXT_PRIMARY,
            activebackground=theme.BG, selectcolor=theme.GROUP_BG, font=(theme.UI, 10),
            command=self._on_manual_toggle)
        self.manual_chk.pack(anchor="w", pady=(4, 0))

        # --- 圖表比較項目（可同時疊多條，主方法一律顯示） ---
        g_cmp = theme.group(panel, "圖表比較項目")
        g_cmp.pack(fill="x", pady=(0, 8))
        cmp_row1 = tk.Frame(g_cmp, bg=theme.BG)
        cmp_row1.pack(fill="x")
        cmp_row2 = tk.Frame(g_cmp, bg=theme.BG)
        cmp_row2.pack(fill="x")

        def _mk_chk(parent, text, var):
            return tk.Checkbutton(parent, text=text, variable=var, bg=theme.BG,
                                  fg=theme.TEXT_PRIMARY, activebackground=theme.BG,
                                  selectcolor=theme.GROUP_BG, font=(theme.UI, 10),
                                  command=self._schedule_recompute)

        tk.Label(cmp_row1, text="內插：", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        self.chk_algo1 = _mk_chk(cmp_row1, "演算法1", self.show_algo1)
        self.chk_algo1.pack(side="left", padx=(0, 6))
        self.chk_algo2 = _mk_chk(cmp_row1, "演算法2", self.show_algo2)
        self.chk_algo2.pack(side="left", padx=(0, 6))
        self.chk_reg = _mk_chk(cmp_row2, "線性回歸", self.show_reg)
        self.chk_reg.pack(side="left", padx=(0, 8))
        _mk_chk(cmp_row2, "均勻", self.show_uniform).pack(side="left", padx=(0, 8))
        _mk_chk(cmp_row2, "原始(校正前)", self.show_raw).pack(side="left")

        # --- 結果摘要 ---
        g_sum = theme.group(panel, "結果摘要")
        g_sum.pack(fill="x", pady=(0, 8))
        self.summary = tk.Text(g_sum, height=6, font=(theme.MONO, 10), bg=theme.GROUP_BG,
                               fg=theme.TEXT_PRIMARY, relief="flat", wrap="word",
                               highlightthickness=0, padx=6, pady=4)
        self.summary.pack(fill="x")
        self.summary.configure(state="disabled")
        theme.make_button(g_sum, "逐點比較數據表", self._show_data_table).pack(anchor="w", pady=(4, 0))

        # --- 匯出 ---
        g_exp = theme.group(panel, "匯出")
        g_exp.pack(fill="x")
        row_g = tk.Frame(g_exp, bg=theme.BG)
        row_g.pack(fill="x", pady=(0, 4))
        tk.Label(row_g, text="C 組名", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        theme.make_entry(row_g, self.group_var, width=14).pack(side="left", padx=(6, 0))
        tk.Label(row_g, text="(cal_<組名>_OV_X)", bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=(theme.UI, 8)).pack(side="left", padx=(6, 0))
        row_b = tk.Frame(g_exp, bg=theme.BG)
        row_b.pack(fill="x")
        theme.make_button(row_b, "C 查表陣列", self._export_c).pack(side="left")
        theme.make_button(row_b, "CSV 節點表", self._export_csv).pack(side="left", padx=4)
        theme.make_button(row_b, "PNG 圖", self._export_png).pack(side="left")

    # === 右側圖表 ===

    def _build_chart(self, root: tk.Tk) -> None:
        right = tk.Frame(root, bg=theme.BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

        self.fig = Figure(figsize=(7.2, 6.4), dpi=100)
        self.fig.subplots_adjust(left=0.10, right=0.97, top=0.95, bottom=0.08, hspace=0.28)
        gs = self.fig.add_gridspec(4, 1)
        self.ax_top = self.fig.add_subplot(gs[0:3, 0])
        self.ax_err = self.fig.add_subplot(gs[3, 0], sharex=self.ax_top)

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas, right, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill="x")

    def _on_global_wheel(self, event: tk.Event) -> str:
        """滑鼠滾輪：游標在左側控制面板上才捲動它，否則放行給圖表（縮放）。"""
        try:
            w = self.root.winfo_containing(event.x_root, event.y_root)
        except KeyError:
            w = None
        node = w
        while node is not None:
            if node is self._panel_canvas:
                bbox = self._panel_canvas.bbox("all")
                if bbox and (bbox[3] - bbox[1]) > self._panel_canvas.winfo_height():
                    step = -1 if event.delta > 0 else 1
                    self._panel_canvas.yview_scroll(step, "units")
                return "break"
            node = getattr(node, "master", None)
        return ""

    # === 資料 datagrid ===

    def _collect_points(self) -> list[tuple[float, float]]:
        """從 datagrid 讀出所有有效 (x, y)。非數值列略過。"""
        pts = []
        for iid in self.tree.get_children():
            sx = self.tree.set(iid, "x")
            sy = self.tree.set(iid, "y")
            try:
                pts.append((float(sx), float(sy)))
            except ValueError:
                continue
        return pts

    def _renumber(self) -> None:
        for n, iid in enumerate(self.tree.get_children(), start=1):
            self.tree.set(iid, "idx", str(n))

    def _set_rows(self, points, initial: bool = False) -> None:
        """以指定點集重建 datagrid（依 x 排序），並重算。"""
        self.tree.delete(*self.tree.get_children())
        for x, y in sorted(points, key=lambda p: p[0]):
            self.tree.insert("", "end", values=("", f"{x:g}", f"{y:g}"))
        self._renumber()
        self._rebuild_curve(initial=initial)

    def _rebuild_curve(self, initial: bool = False) -> None:
        """由目前 datagrid 內容建立 Curve 並重算；資料不足則清空圖表。"""
        pts = self._collect_points()
        if len(pts) < 2:
            self.curve = None
            self._last = None
            self.ax_top.clear()
            self.ax_err.clear()
            self.canvas.draw_idle()
            self._set_summary("（資料不足，至少需要 2 點）")
            return
        try:
            curve, _collapsed = engine.make_curve(pts)
        except ValueError as e:
            self._set_summary(str(e))
            return
        self.curve = curve
        self.n_scale.configure(to=max(2, curve.n))
        self.reg_n_scale.configure(to=max(2, curve.n))
        if self.n_var.get() > curve.n:
            self.n_var.set(curve.n)
        if self.reg_n_var.get() > curve.n:
            self.reg_n_var.set(curve.n)
        self._recompute()

    # --- datagrid 互動 ---

    def _on_cell_edit(self, event: tk.Event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        col = self.tree.identify_column(event.x)
        iid = self.tree.identify_row(event.y)
        if not iid or col not in ("#2", "#3"):
            return
        self._begin_edit(iid, "x" if col == "#2" else "y")

    def _begin_edit(self, iid: str, colname: str) -> None:
        colid = "#2" if colname == "x" else "#3"
        bbox = self.tree.bbox(iid, colid)
        if not bbox:
            return
        x, y, w, h = bbox
        ent = tk.Entry(self.tree, justify="right", font=(theme.MONO, 10),
                       relief="solid", bd=1, bg=theme.ENTRY_BG, fg=theme.TEXT_PRIMARY)
        theme.bind_numpad_decimal_fix(ent)  # 修數字鍵盤小數點被當 Delete、打不進去
        ent.place(x=x, y=y, width=w, height=h)
        ent.insert(0, self.tree.set(iid, colname))
        ent.focus_set()
        ent.select_range(0, "end")

        def commit(_e=None) -> None:
            val = ent.get().strip()
            ent.destroy()
            try:
                float(val)
            except ValueError:
                return  # 非數值不寫入
            self.tree.set(iid, colname, val)
            self._schedule_recompute()

        ent.bind("<Return>", commit)
        ent.bind("<FocusOut>", commit)
        ent.bind("<Escape>", lambda _e: ent.destroy())

    def _row_add(self) -> None:
        iid = self.tree.insert("", "end", values=("", "0", "0"))
        self._renumber()
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self.tree.update_idletasks()
        self._begin_edit(iid, "x")  # 立即編輯新列的 x

    def _row_del(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        for iid in sel:
            self.tree.delete(iid)
        self._renumber()
        self._schedule_recompute()

    def _new_blank_csv(self) -> None:
        """產生只含表頭的空白 CSV，給使用者自行填資料（第一欄 x=原始、第二欄 y=目標）。"""
        path = filedialog.asksaveasfilename(
            title="產生空白 CSV（只含表頭，自行填入資料）",
            defaultextension=".csv", initialfile="interp_data.csv",
            filetypes=[("CSV", "*.csv"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write("x_raw,y_target\n")
        except OSError as e:
            messagebox.showerror("存檔失敗", str(e))
            return
        messagebox.showinfo("已產生空白 CSV",
                            f"已建立：\n{path}\n\n第一欄填原始值(x)、第二欄填目標(y)，"
                            "每列一筆，填好後用「匯入 CSV」載入。")

    def _import_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="匯入 CSV（兩欄 x, y）",
            filetypes=[("CSV / 文字檔", "*.csv *.txt"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                content = f.read()
        except OSError as e:
            messagebox.showerror("讀檔失敗", str(e))
            return
        points, _warn = _parse_text(content)
        if len(points) < 2:
            messagebox.showwarning("匯入失敗", "檔案沒有有效的 x, y 資料。")
            return
        self._set_rows(points)

    def _load_example(self) -> None:
        self._set_rows(_example_points())

    def _clear_data(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.curve = None
        self._last = None
        self.ax_top.clear()
        self.ax_err.clear()
        self.canvas.draw_idle()
        self._set_summary("（尚無資料）")

    # === 重新計算（去抖動） ===

    def _on_mode_change(self) -> None:
        is_count = self.mode_var.get() == "count"
        self.n_scale.configure(state="normal" if is_count else "disabled")
        self.target_entry.configure(state="normal" if is_count is False else "disabled")
        self._schedule_recompute()

    def _on_metric_change(self) -> None:
        self._update_target_unit()
        self._schedule_recompute()

    def _update_target_unit(self) -> None:
        """目標誤差 E 的單位標示，跟著「誤差量度」切換。"""
        if self.metric_var.get() == "rel":
            self.target_unit.configure(text="% 以內")
        else:
            self.target_unit.configure(text="（絕對值，與 y 同單位）")

    _ALGO_INFO = (
        "兩種演算法都在做同一件事：從你的資料挑出 N 個節點，讓折線內插盡量貼近\n"
        "原始曲線。差別只在「怎麼挑」。\n\n"
        "【演算法 1】逐步插點\n"
        "  從頭尾兩點開始，每一步把節點插在「目前誤差最大」的那一點，插完不回頭。\n"
        "  速度快、結果接近最佳。\n\n"
        "【演算法 2】全域最佳\n"
        "  考慮所有可能的節點組合，找出在給定點數下「最大誤差」最小的擺法，是數學上\n"
        "  可證明的最佳解。資料點數很多（數百點以上）時計算量會明顯變大、變慢。\n\n"
        "怎麼選：\n"
        "  - 看「最大誤差」：演算法 2 一定 <= 演算法 1（它就是專門壓最大誤差的）。\n"
        "  - 看「RMS（整體平均）」：不一定。演算法 1 有時整體更平均、某些區段更貼，\n"
        "    所以你會發現「有時演算法 1 看起來比較好」——那通常是 RMS 或視覺上的差異，\n"
        "    不是最大誤差。兩者最佳化的目標本來就不完全一樣。\n"
        "  - 看速度：對幾十～一兩百點的資料，兩者都幾乎瞬間，感覺不出差別；資料到\n"
        "    數百點時演算法 2 才會慢下來（時間隨點數約三次方成長）。\n\n"
        "建議：點數不多就用演算法 2（又快又最準）；點數很多、或想即時拖曳節點數時，\n"
        "改用演算法 1。"
    )

    def _show_algo_info(self) -> None:
        top = tk.Toplevel(self.root)
        top.title("配點演算法說明")
        top.configure(bg=theme.BG)
        top.geometry("600x500")
        txt = tk.Text(top, font=(theme.UI, 10), bg=theme.ENTRY_BG, fg=theme.TEXT_PRIMARY,
                      relief="flat", wrap="word", padx=12, pady=10, highlightthickness=0)
        txt.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        txt.insert("1.0", self._ALGO_INFO)
        txt.configure(state="disabled")
        theme.make_button(top, "關閉", top.destroy).pack(anchor="e", padx=10, pady=(0, 10))
        return top

    _FORMULAS = (
        "【線性內插 Linear Interpolation】\n"
        "\n"
        "  在相鄰兩點 (x0, y0) 與 (x1, y1) 之間，對 x0 <= x <= x1：\n"
        "\n"
        "        y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)\n"
        "\n"
        "  斜率 m = (y1 - y0) / (x1 - x0)\n"
        "  分段查表 (LUT)：先找出 x 落在哪一段 [xi, xi+1]，再套上式。\n"
        "\n"
        "\n"
        "【線性回歸 Linear Regression（最小平方 OLS）】\n"
        "\n"
        "  擬合直線 y = a*x + b，使殘差平方和 Σ(yi - (a*xi + b))^2 最小：\n"
        "\n"
        "              n * Σ(xi*yi)  -  Σxi * Σyi\n"
        "        a = ----------------------------------\n"
        "                 n * Σ(xi^2)  -  (Σxi)^2\n"
        "\n"
        "        b = ( Σyi - a * Σxi ) / n  =  ȳ - a * x̄\n"
        "\n"
        "  其中 n 為擬合所用的點數，Σ 為對這些點求和，x̄ / ȳ 為平均值。\n"
        "  a 為增益 (gain)、b 為截距 (offset)。\n"
    )

    def _show_formulas(self) -> None:
        top = tk.Toplevel(self.root)
        top.title("標準公式")
        top.configure(bg=theme.BG)
        top.geometry("560x470")
        txt = tk.Text(top, font=(theme.MONO, 10), bg=theme.ENTRY_BG, fg=theme.TEXT_PRIMARY,
                      relief="flat", wrap="word", padx=12, pady=10, highlightthickness=0)
        txt.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        txt.insert("1.0", self._FORMULAS)
        txt.configure(state="disabled")
        theme.make_button(top, "關閉", top.destroy).pack(anchor="e", padx=10, pady=(0, 10))
        return top

    def _schedule_recompute(self) -> None:
        if self._recompute_job is not None:
            self.root.after_cancel(self._recompute_job)
        self._recompute_job = self.root.after(120, self._recompute)

    # --- 校正方式 / 節點欄 互動 ---

    def _update_kind_hint(self) -> None:
        if self.method_kind.get() == "reg":
            self.kind_hint.configure(text="點「節點」欄選回歸要用的點（預設全選，可不等於 LUT 點數）")
        else:
            self.kind_hint.configure(text="「節點」欄顯示 LUT 斷點；手動模式可自己點選")

    def _sync_overlay_locks(self) -> None:
        """主方法對應的勾選項鎖定為「開」（一律顯示），其餘可自由勾。"""
        for c in (self.chk_algo1, self.chk_algo2, self.chk_reg):
            c.configure(state="normal")
        if self.method_kind.get() == "reg":
            self.show_reg.set(True)
            self.chk_reg.configure(state="disabled")
        elif not self.manual_mode.get():
            if self.method_var.get() == "dp":
                self.show_algo2.set(True)
                self.chk_algo2.configure(state="disabled")
            else:
                self.show_algo1.set(True)
                self.chk_algo1.configure(state="disabled")
        # 手動模式：手動為主方法（一律顯示），演算法 1/2 皆可自由勾來對照

    def _on_kind_change(self) -> None:
        self._update_kind_hint()
        is_reg = self.method_kind.get() == "reg"
        self.manual_chk.configure(state="disabled" if is_reg else "normal")
        self._sync_overlay_locks()
        if is_reg:
            self.reg_n_row.pack(fill="x", pady=(2, 0))           # 顯示回歸取樣滑桿
            if self.curve is not None:
                self.reg_n_var.set(max(2, min(self._algo_count, self.curve.n)))
                self._set_node_column(engine.uniform_place(self.curve, self.reg_n_var.get()))
        else:
            self.reg_n_row.pack_forget()                         # 隱藏回歸取樣滑桿
            if self.manual_mode.get() and self._last and self._last.get("algo_nodes"):
                self._set_node_column(self._last["algo_nodes"])
        self._recompute()

    def _on_algo_change(self) -> None:
        self._sync_overlay_locks()
        self._recompute()

    def _on_manual_toggle(self) -> None:
        self._sync_overlay_locks()
        if self.manual_mode.get() and self._last and self._last.get("algo_nodes"):
            self._set_node_column(self._last["algo_nodes"])      # 手動起點 = 演算法
        self._recompute()

    def _on_reg_n_change(self, _v=None) -> None:
        if self.method_kind.get() == "reg" and self.curve is not None:
            k = max(2, min(int(self.reg_n_var.get()), self.curve.n))
            self._set_node_column(engine.uniform_place(self.curve, k))  # 均勻撒點
        self._schedule_recompute()

    def _marked_node_positions(self) -> list[int]:
        n = self.curve.n if self.curve else len(self.tree.get_children())
        return [i for i, r in enumerate(self.tree.get_children())
                if self.tree.set(r, "node") == "●" and i < n]

    def _set_node_column(self, indices) -> None:
        s = set(indices)
        for i, r in enumerate(self.tree.get_children()):
            self.tree.set(r, "node", "●" if i in s else "")

    def _manual_nodes(self) -> list[int]:
        # 頭尾不強制：韌體查表支援表外外插（低於表頭由原點、高於表尾沿末段），可自由取消頭尾
        return sorted(set(self._marked_node_positions()))

    def _on_tree_click(self, event: tk.Event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return None
        if self.tree.identify_column(event.x) != "#4":
            return None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        kind = self.method_kind.get()
        if kind == "reg":
            self._toggle_reg_point(iid)
            return "break"
        if kind == "lut" and self.manual_mode.get():
            self._toggle_manual_node(iid)
            return "break"
        return None

    def _toggle_manual_node(self, iid: str) -> None:
        rows = self.tree.get_children()
        n_now = sum(1 for r in rows if self.tree.set(r, "node") == "●")
        if self.tree.set(iid, "node") == "●":
            if n_now <= 2:
                self.root.bell()                                 # 至少留 2 點才能形成查表
                return
            self.tree.set(iid, "node", "")                       # 頭尾也可取消（韌體會外插）
        else:
            if n_now >= self._algo_count:
                self.root.bell()                                 # 已達演算法點數上限
                return
            self.tree.set(iid, "node", "●")
        self._schedule_recompute()

    def _toggle_reg_point(self, iid: str) -> None:
        rows = self.tree.get_children()
        if self.tree.set(iid, "node") == "●":
            n_now = sum(1 for r in rows if self.tree.set(r, "node") == "●")
            if n_now <= 2:
                self.root.bell()                                 # 至少留 2 點才能擬合
                return
            self.tree.set(iid, "node", "")
        else:
            self.tree.set(iid, "node", "●")
        self._schedule_recompute()

    # --- 計算 ---

    def _algo_label(self) -> str:
        return "演算法 2" if self.method_var.get() == "dp" else "演算法 1"

    def _algo_nodes(self, curve, metric: str, method: str) -> list[int]:
        if self.mode_var.get() == "count":
            n_nodes = max(2, min(int(self.n_var.get()), curve.n))
            if method == "dp":
                return engine.dp_optimal(curve, n_nodes, metric)
            return engine.greedy_place(curve, n_nodes=n_nodes, metric=metric)
        try:
            target = float(self.target_var.get())
        except ValueError:
            raise ValueError("目標誤差 E 不是有效數字。")
        if target <= 0:
            raise ValueError("目標誤差 E 必須大於 0。")
        return engine.min_nodes_for_target(curve, target, metric, method)

    def _lut_view(self, curve, metric: str, nodes, label: str, ckey: str) -> dict:
        ev = engine.evaluate(curve, nodes, metric)
        return {"kind": "lut", "ckey": ckey, "label": label, "yhat": ev.yhat,
                "errors": ev.errors, "max": ev.max_err, "rms": ev.rms_err,
                "node_count": ev.node_count, "nodes": ev.nodes, "desc": f"{ev.node_count} 點"}

    def _reg_view(self, reg, fit_m: int) -> dict:
        return {"kind": "reg", "ckey": "reg", "label": "線性回歸", "yhat": reg.yhat,
                "errors": reg.errors, "max": reg.max_err, "rms": reg.rms_err,
                "node_count": 2, "a": reg.a, "b": reg.b, "nodes": None,
                "desc": f"擬合 {fit_m} 點"}

    def _raw_view(self, curve, metric: str) -> dict:
        """原始（校正前）：計算值 = 原始讀值 x，誤差 = y - x。"""
        yhat = list(curve.xs)
        errs = engine._errors(curve, yhat, metric)
        mx = max(errs) if errs else 0.0
        rms = (sum(e * e for e in errs) / len(errs)) ** 0.5 if errs else 0.0
        return {"kind": "raw", "ckey": "raw", "label": "原始", "yhat": yhat, "errors": errs,
                "max": mx, "rms": rms, "node_count": 0, "nodes": None,
                "a": None, "b": None, "desc": "校正前"}

    def _recompute(self) -> None:
        self._recompute_job = None
        if self.curve is None:
            self._set_summary("（尚無資料）")
            return
        curve = self.curve
        metric = self.metric_var.get()
        sel = self.method_var.get()       # greedy / dp（主方法用）
        kind = self.method_kind.get()

        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            primary_algo_nodes = self._algo_nodes(curve, metric, sel)
        except ValueError as e:
            self.root.configure(cursor="")
            self._set_summary(str(e))
            return
        self.root.configure(cursor="")
        self._algo_count = len(primary_algo_nodes)

        # 演算法 1（greedy）檢視：主方法是它或被勾選才算
        if sel == "greedy":
            algo1_view = self._lut_view(curve, metric, primary_algo_nodes, "演算法 1", "algo1")
        elif self.show_algo1.get():
            algo1_view = self._lut_view(curve, metric,
                                        self._algo_nodes(curve, metric, "greedy"), "演算法 1", "algo1")
        else:
            algo1_view = None

        # 演算法 2（DP）檢視：DP 可能因點數過多被拒，捕捉後停用該疊圖
        if sel == "dp":
            algo2_view = self._lut_view(curve, metric, primary_algo_nodes, "演算法 2", "algo2")
        elif self.show_algo2.get():
            try:
                algo2_view = self._lut_view(curve, metric,
                                            self._algo_nodes(curve, metric, "dp"), "演算法 2", "algo2")
            except ValueError:
                algo2_view = None
                self.show_algo2.set(False)
        else:
            algo2_view = None

        uni_view = self._lut_view(curve, metric,
                                  engine.uniform_place(curve, len(primary_algo_nodes)), "均勻", "uniform")
        raw_view = self._raw_view(curve, metric)

        # LUT 主方法：手動 or 選定演算法
        manual_view = None
        if kind == "lut" and self.manual_mode.get():
            if not self._marked_node_positions():
                self._set_node_column(primary_algo_nodes)        # 手動起點 = 演算法
            manual_view = self._lut_view(curve, metric, self._manual_nodes(), "手動", "manual")
        elif kind == "lut":
            self._set_node_column(primary_algo_nodes)            # 顯示演算法選的節點

        # 線性回歸（reg 模式用節點欄選的擬合點；否則全資料擬合，供疊圖/比較）
        if kind == "reg":
            marked = self._marked_node_positions()
            if not marked:
                k = max(2, min(self.reg_n_var.get(), curve.n))
                self._set_node_column(engine.uniform_place(curve, k))
                marked = self._marked_node_positions()
            reg, fit_m = engine.linear_regression(curve, metric, marked)
        else:
            reg, fit_m = engine.linear_regression(curve, metric, None)
        reg_view = self._reg_view(reg, fit_m)

        sel_lut = algo2_view if sel == "dp" else algo1_view      # 選定演算法的 LUT 檢視
        lut_view = manual_view if manual_view is not None else sel_lut
        primary = reg_view if kind == "reg" else lut_view
        self._last = {
            "metric": metric, "kind": kind, "primary": primary, "lut": lut_view,
            "algo1": algo1_view, "algo2": algo2_view, "reg": reg_view,
            "uniform": uni_view, "raw": raw_view,
            "algo_nodes": primary_algo_nodes, "reg_obj": reg,
        }
        self._draw()
        self._update_summary()

    # === 繪圖 ===

    def _unit(self, metric: str) -> str:
        return "相對誤差 (%)" if metric == "rel" else "絕對誤差"

    CMP_COLORS = {"algo1": "#005fb8", "algo2": "#7a4fb5", "manual": "#c0398b",
                  "reg": "#2f9e5f", "uniform": "#d08a1f", "raw": "#c0504d"}

    def _chart_views(self) -> list:
        """回傳要畫的 (view, color, is_primary)。主方法一律畫；其餘看勾選且非主方法。"""
        d = self._last
        primary = d["primary"]
        out = [(primary, self.CMP_COLORS[primary["ckey"]], True)]
        for key, var in (("algo1", self.show_algo1), ("algo2", self.show_algo2),
                         ("reg", self.show_reg), ("uniform", self.show_uniform),
                         ("raw", self.show_raw)):
            v = d.get(key)
            if v is not None and var.get() and v is not primary:
                out.append((v, self.CMP_COLORS[v["ckey"]], False))
        return out

    def _plot_view(self, ax, view: dict, color: str, dashed: bool, zorder: int) -> None:
        curve = self.curve
        if view["kind"] == "reg":
            xs = [curve.xs[0], curve.xs[-1]]
            ys = [view["a"] * x + view["b"] for x in xs]
            ax.plot(xs, ys, "--" if dashed else "-", color=color, lw=1.8, zorder=zorder,
                    label=f"{view['label']} (a={view['a']:.4g}, b={view['b']:.4g})")
        elif view["kind"] == "lut":
            # 線：完整查表評估值（含表外外插尾段，與韌體一致）；點：選定的節點
            ax.plot(curve.xs, view["yhat"], "--" if dashed else "-", color=color,
                    lw=1.4 if dashed else 1.8, zorder=zorder,
                    label=f"{view['label']} {view['node_count']} 點")
            nodes = view["nodes"]
            ax.plot([curve.xs[i] for i in nodes], [curve.ys[i] for i in nodes],
                    "o", color=color, ms=4 if dashed else 5, zorder=zorder)
        else:  # raw（校正前）：計算值 = x，即 y=x 線
            ax.plot(curve.xs, view["yhat"], "--" if dashed else "-", color=color,
                    lw=1.3, zorder=zorder, label=view["label"])

    def _draw(self) -> None:
        d = self._last
        curve = self.curve
        if d is None or curve is None:
            return
        metric = d["metric"]
        views = self._chart_views()

        ax, axe = self.ax_top, self.ax_err
        ax.clear()
        axe.clear()

        ax.scatter(curve.xs, curve.ys, s=14, color=theme.PLOT_RAW,
                   alpha=0.55, zorder=1, label="原始資料")
        for view, color, prim in views:
            self._plot_view(ax, view, color, not prim, 3 if prim else 2)
        ax.set_ylabel("y 目標")
        ax.set_title("校正方法比較")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8, loc="best")

        for view, color, prim in views:
            axe.plot(curve.xs, view["errors"], "-" if prim else "--", color=color,
                     lw=1.4 if prim else 1.1, label=view["label"])
        if d["kind"] == "lut" and self.mode_var.get() == "target":
            try:
                e = float(self.target_var.get())
                axe.axhline(e, color=theme.PLOT_TARGET, lw=1.0, ls=":", label=f"目標 {e:g}")
            except ValueError:
                pass
        axe.set_xlabel("x 原始")
        axe.set_ylabel(self._unit(metric))
        axe.grid(True, alpha=0.25)
        axe.legend(fontsize=8, loc="best")

        self.canvas.draw_idle()

    # === 摘要 ===

    def _set_summary(self, text: str) -> None:
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text)
        self.summary.configure(state="disabled")

    def _update_summary(self) -> None:
        d = self._last
        if d is None:
            return
        unit = "%" if d["metric"] == "rel" else ""
        views = [v for v, _, _ in self._chart_views()]
        lines = [f"樣本 {self.curve.n} 點　主方法：{d['primary']['label']}"]
        for v in views:
            mark = "★" if v is d["primary"] else "  "
            lines.append(f"{mark}{v['label']}（{v['desc']}）max {v['max']:.4g}{unit}  RMS {v['rms']:.4g}{unit}")
        self._set_summary("\n".join(lines))

    # === 匯出 ===

    def _primary_lut_nodes(self):
        """目前 LUT 方法的節點（reg 模式則為演算法 LUT 節點）。"""
        return self._last["lut"]["nodes"]

    def _export_c(self) -> None:
        if self._last is None or self.curve is None:
            messagebox.showinfo("無資料", "請先套用資料並計算。")
            return
        d = self._last
        if d["kind"] == "reg" and d["reg_obj"] is not None:
            code = engine.export_c_regression(d["reg_obj"], d["metric"], self.group_var.get())
            self._show_code_popup("C 線性回歸校正（gain/offset）", code)
        else:
            code = engine.export_c_table(self.curve, self._primary_lut_nodes(),
                                         d["metric"], self.group_var.get())
            self._show_code_popup("C 查表陣列（單組，比照韌體）", code)

    def _show_code_popup(self, title: str, code: str) -> None:
        top = tk.Toplevel(self.root)
        top.title(title)
        top.configure(bg=theme.BG)
        top.geometry("680x560")
        txt = tk.Text(top, font=(theme.MONO, 10), bg=theme.ENTRY_BG, fg=theme.TEXT_PRIMARY,
                      relief="flat", wrap="none", padx=8, pady=6)
        txt.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        txt.insert("1.0", code)
        bar = tk.Frame(top, bg=theme.BG)
        bar.pack(fill="x", padx=8, pady=(0, 8))

        def copy_clip() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(code)

        def save_file() -> None:
            path = filedialog.asksaveasfilename(
                title="儲存 C 程式碼", defaultextension=".c",
                filetypes=[("C 原始檔", "*.c *.h"), ("所有檔案", "*.*")],
            )
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(code)
                except OSError as e:
                    messagebox.showerror("存檔失敗", str(e))

        theme.make_button(bar, "複製到剪貼簿", copy_clip).pack(side="left")
        theme.make_button(bar, "存檔", save_file).pack(side="left", padx=4)

    def _export_csv(self) -> None:
        if self._last is None or self.curve is None:
            messagebox.showinfo("無資料", "請先套用資料並計算。")
            return
        path = filedialog.asksaveasfilename(
            title="儲存節點表 CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        rows = engine.export_csv_rows(self.curve, self._primary_lut_nodes(), self._last["metric"])
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(rows)
        except OSError as e:
            messagebox.showerror("存檔失敗", str(e))

    def _export_png(self) -> None:
        if self._last is None:
            messagebox.showinfo("無資料", "請先套用資料並計算。")
            return
        path = filedialog.asksaveasfilename(
            title="儲存圖檔", defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            self.fig.savefig(path, dpi=150, bbox_inches="tight")
        except Exception as e:  # matplotlib 後端例外型別多樣
            messagebox.showerror("存檔失敗", str(e))

    # === 前後比較數據表 ===

    @staticmethod
    def _auto_decimals(values) -> int:
        """依數值量級決定顯示小數位（約 5 位有效數字），夾在 0~6。

        例：峰值 ~22（電流 A）→ 3 位小數，與常見校正表一致；峰值 ~1000 → 1 位。
        """
        peak = max((abs(v) for v in values if v != 0.0), default=1.0)
        if peak <= 0:
            return 3
        dec = 4 - int(math.floor(math.log10(peak)))
        return max(0, min(6, dec))

    _BEST_BG = {"原始": "#f6dcdc", "內插": "#dce8f6", "回歸": "#d8f0e0"}

    def _show_data_table(self) -> None:
        if self._last is None or self.curve is None:
            messagebox.showinfo("無資料", "請先套用資料並計算。")
            return
        d = self._last
        unit = "%" if d["metric"] == "rel" else ""
        raw_v, lut_v, reg_v = d["raw"], d["lut"], d["reg"]
        rows = engine.three_way_table(self.curve, lut_v["yhat"], reg_v["yhat"])
        dec = self._auto_decimals(list(self.curve.xs) + list(self.curve.ys))

        top = tk.Toplevel(self.root)
        top.title("逐點比較：原始 / 線性內插 / 線性回歸")
        top.configure(bg=theme.BG)
        top.geometry("780x600")

        win = {"原始": 0, "內插": 0, "回歸": 0}
        for r in rows:
            win[r["best"]] += 1
        summary = (
            f"原始（校正前）   max {raw_v['max']:.4g}{unit}  RMS {raw_v['rms']:.4g}{unit}  ｜ 最佳 {win['原始']} 點\n"
            f"線性內插（{lut_v['desc']}）max {lut_v['max']:.4g}{unit}  RMS {lut_v['rms']:.4g}{unit}  ｜ 最佳 {win['內插']} 點\n"
            f"線性回歸（{reg_v['desc']}）max {reg_v['max']:.4g}{unit}  RMS {reg_v['rms']:.4g}{unit}  ｜ 最佳 {win['回歸']} 點"
        )
        tk.Label(top, text=summary, bg=theme.BG, fg=theme.TEXT_PRIMARY,
                 font=(theme.MONO, 10), justify="left").pack(anchor="w", padx=10, pady=(8, 4))

        # 可捲動的儲存格表（用 Label grid 才能只給「最佳」欄上色）
        wrap = tk.Frame(top, bg=theme.BG)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        cv = tk.Canvas(wrap, bg="#ffffff", highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        grid = tk.Frame(cv, bg="#ffffff")
        cv.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda _e: cv.configure(scrollregion=cv.bbox("all")))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _wheel(e):
            cv.yview_scroll(-1 if e.delta > 0 else 1, "units")
        cv.bind("<MouseWheel>", _wheel)
        grid.bind("<MouseWheel>", _wheel)

        heads = ["#", "原始(MCU)", "目標", "原始誤差", "內插計算值", "內插誤差",
                 "回歸計算值", "回歸誤差", "最佳"]
        widths = [4, 11, 10, 10, 11, 10, 11, 10, 6]

        def cell(rr, cc, text, bg="#ffffff", anchor="e", bold=False):
            tk.Label(grid, text=text, bg=bg, fg=theme.TEXT_PRIMARY,
                     font=(theme.MONO, 9, "bold" if bold else "normal"),
                     width=widths[cc], anchor=anchor, padx=3, pady=1,
                     borderwidth=1, relief="solid").grid(row=rr, column=cc, sticky="nsew")

        for cc, h in enumerate(heads):
            cell(0, cc, h, bg="#e8edf2", anchor="center", bold=True)

        def fv(v):
            return f"{v:.{dec}f}"

        def fe(e):
            return f"{e:+.{dec}f}"

        for i, r in enumerate(rows, start=1):
            cell(i, 0, str(r["load"]), anchor="center")
            cell(i, 1, fv(r["x"]))
            cell(i, 2, fv(r["y"]))
            cell(i, 3, fe(r["raw_err"]))
            cell(i, 4, fv(r["lut_calc"]))
            cell(i, 5, fe(r["lut_err"]))
            cell(i, 6, fv(r["reg_calc"]))
            cell(i, 7, fe(r["reg_err"]))
            cell(i, 8, r["best"], bg=self._BEST_BG.get(r["best"], "#ffffff"),
                 anchor="center", bold=True)

        bar = tk.Frame(top, bg=theme.BG)
        bar.pack(fill="x", padx=10, pady=(0, 8))
        tk.Label(bar, text="（誤差為帶號 目標-計算值；只有「最佳」欄上色：紅=原始 藍=內插 綠=回歸）",
                 bg=theme.BG, fg=theme.TEXT_MUTED, font=(theme.UI, 8)).pack(side="left")
        theme.make_button(bar, "匯出 CSV", self._export_comparison_csv).pack(side="right")
        return top

    def _export_comparison_csv(self) -> None:
        if self._last is None or self.curve is None:
            return
        path = filedialog.asksaveasfilename(
            title="儲存逐點比較表 CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        d = self._last
        rows = engine.export_three_way_csv_rows(self.curve, d["lut"]["yhat"], d["reg"]["yhat"])
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(rows)
        except OSError as e:
            messagebox.showerror("存檔失敗", str(e))
