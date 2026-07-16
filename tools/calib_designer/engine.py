"""校正設計工具 — 演算法核心（純 Python，無 UI 依賴）。

把一條密集取樣的參考曲線 (x 原始 -> y 目標) 用「N 段折線」逼近，並回答兩個問題：
  1. 給定節點數 N，節點該放哪裡才最準？（minimax：最小化最大誤差）
  2. 給定可容許最大誤差 E，最少要幾個節點？

提供三種配點法：
  - greedy_place : Douglas-Peucker 式貪婪細分，每次把節點插到目前誤差最大的樣本上，
                   近似最佳、速度快，適合互動即時預覽。
  - dp_optimal   : 動態規劃，對給定 N 求「證明上最佳」的 minimax 配置（較慢）。
  - uniform_place: 均勻分點（沿 x 等距取最近樣本），當作「手動均分」的對照基準。

誤差量度 (metric)：
  - "abs" 絕對誤差    : |yhat - y|
  - "rel" 相對誤差(%) : |yhat - y| / max(|y|, eps) * 100

所有配點法的「節點」都限制落在輸入樣本點上，且頭尾兩端必為節點，
因此 DP 為精確最佳解。誤差一律拿節點折線跟「全部原始樣本」比對的真實值，
不依賴二階導數公式（避免雜訊放大）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# DP 成本表為 O(n^2) 對、建表為 O(n^3)；超過此樣本數時 DP 會拒絕並建議改用貪婪。
DP_REF_LIMIT = 600


@dataclass
class Curve:
    """密集參考曲線：xs 嚴格遞增，ys 對應。"""

    xs: list[float]
    ys: list[float]

    @property
    def n(self) -> int:
        return len(self.xs)


@dataclass
class EvalResult:
    """一組節點配置的評估結果。"""

    nodes: list[int]          # 節點在 curve 中的索引（已排序，含頭尾）
    yhat: list[float]         # 折線在每個原始 x 上的內插值
    errors: list[float]       # 每個原始樣本的誤差（依 metric）
    max_err: float
    rms_err: float

    @property
    def node_count(self) -> int:
        return len(self.nodes)


def make_curve(points) -> tuple[Curve, int]:
    """把 (x, y) 點集整理成 Curve。

    依 x 排序；相同 x 的點以 y 平均合併（回傳被合併掉的點數，供 UI 提示）。
    """
    pts = sorted(((float(x), float(y)) for x, y in points), key=lambda p: p[0])
    if len(pts) < 2:
        raise ValueError("至少需要 2 個資料點")

    xs: list[float] = []
    ys: list[float] = []
    collapsed = 0
    i = 0
    while i < len(pts):
        x = pts[i][0]
        group = [pts[i][1]]
        j = i + 1
        while j < len(pts) and pts[j][0] == x:
            group.append(pts[j][1])
            j += 1
        if len(group) > 1:
            collapsed += len(group) - 1
        xs.append(x)
        ys.append(sum(group) / len(group))
        i = j

    if len(xs) < 2:
        raise ValueError("去除重複 x 後不足 2 點")
    return Curve(xs, ys), collapsed


def _rel_scale(ys: list[float]) -> float:
    """相對誤差的分母下限，避免接近零的 y 把相對誤差炸到無限大。"""
    peak = max((abs(v) for v in ys), default=1.0) or 1.0
    return max(1e-12, 1e-6 * peak)


def is_excluded(y: float) -> bool:
    """判斷該點是否應排除於配點與誤差評估之外。

    目標值 y 恰為 0 的點：相對誤差以目標值為分母會除以近零、誤差無意義，
    絕對誤差雖不會除零但使用者要求一律不將此點納入校正，故兩種量度都排除。
    """
    return y == 0.0


def _filter_calc(curve: Curve) -> tuple[Curve, list[int]]:
    """回傳「排除目標值為 0 後的計算用曲線」與「索引對照表」。

    keep[k] 為精簡曲線第 k 點在原始 curve 中的索引；配點演算法一律跑在精簡曲線上，
    回傳的節點索引再透過 keep 映射回原始 curve，確保目標值為 0 的點不會被選為節點。
    """
    keep = [i for i, y in enumerate(curve.ys) if not is_excluded(y)]
    if len(keep) < 2:
        raise ValueError("排除目標值為 0 的點後不足 2 點，無法配置查表節點。")
    return Curve([curve.xs[i] for i in keep], [curve.ys[i] for i in keep]), keep


def _interp_on_nodes(curve: Curve, nodes: list[int]) -> list[float]:
    """以節點折線在每個原始 x 上求值，完全對齊韌體 linearInterpolationFromLUT：

    表內線性內插；低於表頭由原點 (0,0) 外插；高於表尾沿最後一段外插；單段結果負值箝位為 0。
    節點「不必」含頭尾——使用者手動取消頭尾時，落在節點範圍外的點即以上述外插評估，
    這樣工具報的誤差才跟現場韌體一致。
    """
    nodes = sorted(nodes)
    xs, ys = curve.xs, curve.ys
    n = len(xs)
    if len(nodes) < 2:
        return [0.0] * n

    if nodes[0] == 0 and nodes[-1] == n - 1:
        # 快速路徑：頭尾齊全，免外插（仍套負值箝位以對齊韌體）
        yhat = [0.0] * n
        for seg in range(len(nodes) - 1):
            a, b = nodes[seg], nodes[seg + 1]
            xa, ya, xb, yb = xs[a], ys[a], xs[b], ys[b]
            dx = xb - xa
            for k in range(a, b + 1):
                v = ya if dx == 0.0 else ya + (xs[k] - xa) / dx * (yb - ya)
                yhat[k] = v if v > 0.0 else 0.0
        return yhat

    # 一般路徑（頭尾可能被取消）：逐點比照韌體查表（含原點外插、末段外插、負值箝位）
    ov_x = [xs[i] for i in nodes]
    tv_y = [ys[i] for i in nodes]
    return [firmware_interp_single(x, ov_x, tv_y) for x in xs]


def _errors(curve: Curve, yhat: list[float], metric: str) -> list[float]:
    """逐點誤差；目標值為 0 的點回傳 NaN 代表「不列入評估」。

    NaN 在後續彙總（max/rms/最差點）一律以 not-a-number 過濾掉，
    繪圖時 matplotlib 也會自動在該點斷線，避免相對誤差除以近零把圖炸掉。
    """
    ys = curve.ys
    nan = float("nan")
    if metric == "rel":
        eps = _rel_scale(ys)
        return [nan if is_excluded(y) else abs(yh - y) / max(abs(y), eps) * 100.0
                for y, yh in zip(ys, yhat)]
    return [nan if is_excluded(y) else abs(yh - y) for y, yh in zip(ys, yhat)]


def _agg(errs: list[float]) -> tuple[float, float]:
    """由逐點誤差算 (max, rms)，自動略過 NaN（目標值為 0 的排除點）。"""
    valid = [e for e in errs if e == e]  # NaN != NaN，藉此濾掉排除點
    if not valid:
        return 0.0, 0.0
    max_err = max(valid)
    rms = math.sqrt(sum(e * e for e in valid) / len(valid))
    return max_err, rms


def evaluate(curve: Curve, nodes: list[int], metric: str) -> EvalResult:
    """評估一組節點配置的內插誤差。"""
    nodes = sorted(nodes)
    yhat = _interp_on_nodes(curve, nodes)
    errs = _errors(curve, yhat, metric)
    max_err, rms = _agg(errs)
    return EvalResult(nodes, yhat, errs, max_err, rms)


# === 線性回歸（單一直線 gain/offset 校正） ===

@dataclass
class RegResult:
    """最小平方線性回歸結果：y ≈ a*x + b。"""

    a: float                  # gain（斜率）
    b: float                  # offset（截距）
    yhat: list[float]
    errors: list[float]
    max_err: float
    rms_err: float


def linear_regression(curve: Curve, metric: str = "abs",
                      fit_indices: list[int] | None = None) -> tuple[RegResult, int]:
    """對 (x, y) 做最小平方線性回歸（OLS），回傳 (RegResult, 實際擬合點數)。

    fit_indices：只用這些樣本點來擬合直線（None = 全部）；不足 2 點時退回全部。
    無論用幾點擬合，誤差一律對「全部樣本」評估，這樣才能看出該直線在每一點的表現。
    OLS 最小化的是「絕對殘差平方和」；metric 只影響誤差「怎麼回報」（絕對 / 相對%）。
    """
    # 擬合資料一律排除目標值為 0 的點（與 LUT 配點一致，不納入校正）
    included = [i for i in range(curve.n) if not is_excluded(curve.ys[i])]
    if fit_indices is None:
        idx = included
    else:
        idx = sorted(set(i for i in fit_indices
                         if 0 <= i < curve.n and not is_excluded(curve.ys[i])))
    if len(idx) < 2:
        idx = included if len(included) >= 2 else list(range(curve.n))
    fx = [curve.xs[i] for i in idx]
    fy = [curve.ys[i] for i in idx]
    m = len(fx)
    sx = sum(fx)
    sy = sum(fy)
    sxx = sum(x * x for x in fx)
    sxy = sum(x * y for x, y in zip(fx, fy))
    denom = m * sxx - sx * sx
    if denom == 0.0:
        a = 0.0
        b = sy / m if m else 0.0
    else:
        a = (m * sxy - sx * sy) / denom
        b = (sy - a * sx) / m
    yhat = [a * x + b for x in curve.xs]  # 對全部樣本評估
    errs = _errors(curve, yhat, metric)
    max_err, rms = _agg(errs)
    return RegResult(a, b, yhat, errs, max_err, rms), m


# === 貪婪配點 (Douglas-Peucker 式) ===

def greedy_place(curve: Curve, n_nodes: int | None = None,
                 target_err: float | None = None, metric: str = "abs") -> list[int]:
    """貪婪配點對外介面：先排除目標值為 0 的點，回傳原始曲線上的節點索引。"""
    sub, keep = _filter_calc(curve)
    return [keep[k] for k in _greedy_impl(sub, n_nodes, target_err, metric)]


def _greedy_impl(curve: Curve, n_nodes: int | None = None,
                 target_err: float | None = None, metric: str = "abs") -> list[int]:
    """從頭尾兩點開始，反覆把節點插到誤差最大的樣本上（假設 curve 已排除排除點）。

    n_nodes 與 target_err 至少給一個：
      - 給 n_nodes：插到節點數達到 n_nodes 為止。
      - 給 target_err：插到最大誤差 <= target_err 為止（或節點用盡）。
    兩者同時給時，任一條件先滿足即停止。
    """
    n = curve.n
    if n < 2:
        return list(range(n))
    if n_nodes is None and target_err is None:
        raise ValueError("greedy_place 需要 n_nodes 或 target_err 至少一個")

    nodes = [0, n - 1]
    node_set = {0, n - 1}
    cap = min(n_nodes, n) if n_nodes is not None else n

    while True:
        ev = evaluate(curve, nodes, metric)
        if len(nodes) >= cap:
            break
        if target_err is not None and ev.max_err <= target_err:
            break
        if len(nodes) >= n:
            break

        worst_k, worst_e = -1, -1.0
        for k in range(n):
            if k in node_set:
                continue
            if ev.errors[k] > worst_e:
                worst_e, worst_k = ev.errors[k], k
        if worst_k < 0:
            break
        nodes.append(worst_k)
        node_set.add(worst_k)
        nodes.sort()

    return sorted(nodes)


# === 動態規劃最佳配點 (minimax) ===

def _build_cost(curve: Curve, metric: str) -> list[list[float]]:
    """cost[i][j] = 用單一直線接 (i)->(j) 時，區段內樣本的最大誤差。"""
    n = curve.n
    if n > DP_REF_LIMIT:
        raise ValueError(
            f"演算法 2（全域最佳）需建 O(n^2) 成本表，樣本數 {n} 超過上限 {DP_REF_LIMIT}；"
            "請改用演算法 1，或先精簡參考資料點數。"
        )
    xs, ys = curve.xs, curve.ys
    use_rel = metric == "rel"
    eps = _rel_scale(ys) if use_rel else 0.0

    cost = [[0.0] * n for _ in range(n)]
    for i in range(n):
        xa, ya = xs[i], ys[i]
        for j in range(i + 2, n):  # j == i+1 時區段內無中間點，成本 0
            xb, yb = xs[j], ys[j]
            dx = xb - xa
            worst = 0.0
            for k in range(i + 1, j):
                t = 0.0 if dx == 0.0 else (xs[k] - xa) / dx
                yh = ya + t * (yb - ya)
                if use_rel:
                    e = abs(yh - ys[k]) / max(abs(ys[k]), eps) * 100.0
                else:
                    e = abs(yh - ys[k])
                if e > worst:
                    worst = e
            cost[i][j] = worst
    return cost


def _dp_from_cost(cost: list[list[float]], n_nodes: int, n: int) -> list[int]:
    """以預先建好的成本表跑 minimax DP，回傳最佳節點索引。"""
    if n_nodes >= n:
        return list(range(n))
    if n_nodes < 2:
        raise ValueError("節點數至少為 2")

    segments = n_nodes - 1
    inf = float("inf")
    # f[s][j]：用 s 段、最後一個節點落在 j，所能達到的最小「最大誤差」。
    f = [[inf] * n for _ in range(segments + 1)]
    par = [[-1] * n for _ in range(segments + 1)]
    f[0][0] = 0.0

    for s in range(1, segments + 1):
        for j in range(s, n):
            best, bi = inf, -1
            for i in range(s - 1, j):
                prev = f[s - 1][i]
                if prev == inf:
                    continue
                val = prev if prev > cost[i][j] else cost[i][j]
                if val < best:
                    best, bi = val, i
            f[s][j] = best
            par[s][j] = bi

    nodes = [n - 1]
    s, j = segments, n - 1
    while s > 0:
        i = par[s][j]
        nodes.append(i)
        j, s = i, s - 1
    nodes.reverse()
    return nodes


def dp_optimal(curve: Curve, n_nodes: int, metric: str = "abs") -> list[int]:
    """DP 最佳配點對外介面：先排除目標值為 0 的點，回傳原始曲線上的節點索引。"""
    sub, keep = _filter_calc(curve)
    return [keep[k] for k in _dp_optimal_impl(sub, n_nodes, metric)]


def _dp_optimal_impl(curve: Curve, n_nodes: int, metric: str = "abs") -> list[int]:
    """對給定節點數求 minimax 最佳配置（節點限制落在樣本點上，故為精確最佳）。"""
    n = curve.n
    if n_nodes >= n:
        return list(range(n))
    cost = _build_cost(curve, metric)
    return _dp_from_cost(cost, n_nodes, n)


# === 均勻分點（對照基準） ===

def uniform_place(curve: Curve, n_nodes: int) -> list[int]:
    """均勻配點對外介面：先排除目標值為 0 的點，回傳原始曲線上的節點索引。"""
    sub, keep = _filter_calc(curve)
    return [keep[k] for k in _uniform_impl(sub, n_nodes)]


def _uniform_impl(curve: Curve, n_nodes: int) -> list[int]:
    """沿 x 等距取最近樣本當節點（手動均分的代表）。頭尾固定。"""
    n = curve.n
    k = min(max(n_nodes, 2), n)
    if k <= 2 or n <= 2:
        return list(range(n)) if n <= 2 else [0, n - 1]

    xs = curve.xs
    x0, x1 = xs[0], xs[-1]
    nodes: set[int] = set()
    for idx in range(k):
        tx = x0 + (x1 - x0) * idx / (k - 1)
        best_i = min(range(n), key=lambda q: abs(xs[q] - tx))
        nodes.add(best_i)
    nodes.add(0)
    nodes.add(n - 1)
    return sorted(nodes)


# === 「給目標誤差求最少節點」 ===

def min_nodes_for_target(curve: Curve, target_err: float,
                         metric: str = "abs", method: str = "greedy") -> list[int]:
    """求最少節點對外介面：先排除目標值為 0 的點，回傳原始曲線上的節點索引。"""
    sub, keep = _filter_calc(curve)
    return [keep[k] for k in _min_nodes_impl(sub, target_err, metric, method)]


def _min_nodes_impl(curve: Curve, target_err: float,
                    metric: str = "abs", method: str = "greedy") -> list[int]:
    """回傳使最大誤差 <= target_err 的（近似）最少節點配置。

    method == "greedy"：直接貪婪細分到達標。
    method == "dp"    ：對節點數二分搜尋，每次用 DP 求最佳並檢查是否達標
                        （成本表只建一次重複使用）。
    """
    n = curve.n
    if method == "greedy":
        return _greedy_impl(curve, target_err=target_err, metric=metric)

    cost = _build_cost(curve, metric)
    lo, hi = 2, n
    best = list(range(n))
    while lo <= hi:
        mid = (lo + hi) // 2
        nodes = _dp_from_cost(cost, mid, n)
        ev = evaluate(curve, nodes, metric)
        if ev.max_err <= target_err:
            best = nodes
            hi = mid - 1
        else:
            lo = mid + 1
    return best


# === 匯出 ===

def firmware_interp_single(ov: float, ov_x: list[float], tv_y: list[float]) -> float:
    """完全比照韌體 linearInterpolationFromLUT 的單組查表邏輯（Python 鏡像）。

    與韌體一致：表內線性掃描找區段；低於表頭由原點 (0,0) 外插；
    高於表尾沿最後一段外插；每次內插結果負值箝位為 0。
    工具可用此函式驗證匯出表格在任意輸入下會算出什麼，與 MCU 端逐位元對齊。
    """
    n = len(ov_x)
    if n < 2:
        return 0.0
    for i in range(n - 1):
        if ov >= ov_x[i] and ov < ov_x[i + 1]:
            return _fw_lerp(ov_x[i], ov_x[i + 1], tv_y[i], tv_y[i + 1], ov)
    if ov < ov_x[0]:
        return _fw_lerp(0.0, ov_x[0], 0.0, tv_y[0], ov)
    return _fw_lerp(ov_x[n - 2], ov_x[n - 1], tv_y[n - 2], tv_y[n - 1], ov)


def _fw_lerp(o1: float, o2: float, t1: float, t2: float, ov: float) -> float:
    """韌體 linearInterpolation 核心：單段線性內插 + 負值箝位為 0。"""
    if o2 == o1:
        return t1
    res = t1 + (t2 - t1) * (ov - o1) / (o2 - o1)
    return res if res > 0.0 else 0.0


def _c_float(v: float) -> str:
    """格式化為 C float 常數（小數點 + f 後綴）。

    必須確保字串含小數點或指數，否則 'f' 後綴會接到整數上（如 0f / 100f）
    產生非法的 C 浮點常數。
    """
    s = f"{v:.7g}"
    if ("." not in s) and ("e" not in s) and ("E" not in s):
        s += ".0"
    return s + "f"


def _sanitize_ident(name: str) -> str:
    """把使用者輸入的組名整理成合法 C 識別字片段。

    只汰換非法字元；組名永遠接在 cal_ / CAL_ 之後，不會成為識別字開頭，
    故開頭是數字（如 12V_curr）是允許的，不另加前導底線。
    """
    out = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name.strip())
    return out or "lut"


def export_c_table(curve: Curve, nodes: list[int], metric: str,
                   group_name: str = "lut") -> str:
    """產生單組查表 C 程式碼，比照使用者韌體 linearInterpolationFromLUT 邏輯。

    含 linearInterpolation 核心（負值箝位為 0）+ 單組查表函式
    （表內線性掃描；低於表頭由原點外插；高於表尾沿最後一段外插）。
    命名慣例：cal_<組名>_OV_X / cal_<組名>_TV_Y / CAL_<組名>_POINT_NUM。
    """
    nodes = sorted(nodes)
    ev = evaluate(curve, nodes, metric)
    xs = [curve.xs[i] for i in nodes]
    ys = [curve.ys[i] for i in nodes]
    length = len(nodes)
    metric_txt = "相對誤差(%)" if metric == "rel" else "絕對誤差"

    g = _sanitize_ident(group_name)
    arr_x = f"cal_{g}_OV_X"
    arr_y = f"cal_{g}_TV_Y"
    num = f"CAL_{g.upper()}_POINT_NUM"

    def fmt_block(values: list[float]) -> str:
        lines = []
        per_line = 6
        for start in range(0, len(values), per_line):
            chunk = values[start:start + per_line]
            lines.append("    " + ", ".join(_c_float(v) for v in chunk) + ",")
        return "\n".join(lines)

    out = []
    out.append("/*")
    out.append(" * @brief  單組線性內插查表 (single-group LUT)。")
    out.append(" *         由「校正設計工具」自動產生。")
    out.append(" *         說明：")
    out.append(f" *           - 節點數    : {num} = {length}")
    out.append(f" *           - 量度     : {metric_txt}")
    out.append(f" *           - 最大誤差  : {ev.max_err:.6g}")
    out.append(f" *           - RMS 誤差  : {ev.rms_err:.6g}")
    out.append(" *           - 查表邏輯  : 表內線性掃描；低於表頭由原點(0,0)外插；")
    out.append(" *                       高於表尾沿最後一段外插；單段結果負值箝位為 0")
    out.append(" */")
    out.append(f"#define {num}  ({length}U)")
    out.append("")
    out.append(f"static const float {arr_x}[{num}] =")
    out.append("{")
    out.append(fmt_block(xs))
    out.append("};")
    out.append("")
    out.append(f"static const float {arr_y}[{num}] =")
    out.append("{")
    out.append(fmt_block(ys))
    out.append("};")
    out.append("")
    out.append("static inline float linearInterpolation(float OV1, float OV2, float TV1, float TV2, float targetOV)")
    out.append("{")
    out.append("    float")
    out.append("        denom   = OV2 - OV1,")
    out.append("        res     = 0.0f;")
    out.append("")
    out.append("    if (OV2 == OV1)")
    out.append("    {")
    out.append("        return TV1;")
    out.append("    }")
    out.append("    res = TV1 + ((TV2 - TV1) * (targetOV - OV1)) / denom;")
    out.append("    return (res > 0.0f) ? res : 0.0f;")
    out.append("}")
    out.append("")
    out.append("float linearInterpolationFromLUT(float OV)")
    out.append("{")
    out.append("    uint32_t i = 0U;")
    out.append("")
    out.append(f"    if ({num} < 2U)")
    out.append("    {")
    out.append("        return 0.0f;")
    out.append("    }")
    out.append("")
    out.append("    // 先在表內找到所在區段")
    out.append(f"    for (i = 0U; i < ({num} - 1U); i++)")
    out.append("    {")
    out.append(f"        if ((OV >= {arr_x}[i]) && (OV < {arr_x}[i + 1U]))")
    out.append("        {")
    out.append(f"            return linearInterpolation({arr_x}[i], {arr_x}[i + 1U],")
    out.append(f"                                       {arr_y}[i], {arr_y}[i + 1U], OV);")
    out.append("        }")
    out.append("    }")
    out.append("")
    out.append("    // 低於表頭：以原點 (0,0) 到第一點外插")
    out.append(f"    if (OV < {arr_x}[0])")
    out.append("    {")
    out.append(f"        return linearInterpolation(0.0f, {arr_x}[0],")
    out.append(f"                                   0.0f, {arr_y}[0], OV);")
    out.append("    }")
    out.append("")
    out.append("    // 高於表尾：沿最後一段外插")
    out.append(f"    return linearInterpolation({arr_x}[{num} - 2U], {arr_x}[{num} - 1U],")
    out.append(f"                               {arr_y}[{num} - 2U], {arr_y}[{num} - 1U], OV);")
    out.append("}")
    return "\n".join(out)


def export_c_regression(reg: RegResult, metric: str, group_name: str = "lut") -> str:
    """產生線性回歸校正的 C 程式碼（gain/offset + 單行函式，負值箝位為 0）。"""
    g = _sanitize_ident(group_name)
    gain = f"CAL_{g.upper()}_GAIN"
    offset = f"CAL_{g.upper()}_OFFSET"
    metric_txt = "相對誤差(%)" if metric == "rel" else "絕對誤差"

    out = []
    out.append("/*")
    out.append(" * @brief  線性回歸校正 (single-line gain/offset)。")
    out.append(" *         由「校正設計工具」自動產生。")
    out.append(" *         說明：")
    out.append(" *           - 公式     : y = GAIN * x + OFFSET，結果負值箝位為 0")
    out.append(f" *           - 量度     : {metric_txt}")
    out.append(f" *           - 最大誤差  : {reg.max_err:.6g}")
    out.append(f" *           - RMS 誤差  : {reg.rms_err:.6g}")
    out.append(" */")
    out.append(f"#define {gain}    ({_c_float(reg.a)})")
    out.append(f"#define {offset}  ({_c_float(reg.b)})")
    out.append("")
    out.append("float linearCalFromReg(float OV)")
    out.append("{")
    out.append(f"    float res = {gain} * OV + {offset};")
    out.append("    return (res > 0.0f) ? res : 0.0f;")
    out.append("}")
    return "\n".join(out)


def comparison_table(curve: Curve, lut_yhat: list[float], uni_yhat: list[float],
                     reg_yhat: list[float]) -> list[dict]:
    """逐點比較 原始 / 內插(演算法配點) / 內插(均勻撒點) / 線性回歸，標出表現最好者。

    每列 dict：load, x, y, raw_err, lut_calc/err, uni_calc/err, reg_calc/err, best, excluded
      - raw_err = y - x（校正前）
      - *_err = y - *_calc（皆帶正負號）
      - best ∈ {"原始", "內插", "均勻", "回歸"}：|誤差| 最小者
        （平手依 內插 > 均勻 > 回歸 > 原始 優先；目標值為 0 的排除點 best = "—"）
    """
    rows = []
    for i in range(curve.n):
        x, y = curve.xs[i], curve.ys[i]
        excluded = is_excluded(y)
        re = y - x
        le = y - lut_yhat[i]
        ue = y - uni_yhat[i]
        ge = y - reg_yhat[i]
        if excluded:
            best = "—"                               # 目標值為 0：不參與最佳排名
        else:
            # 平手優先序：內插、均勻、回歸、原始
            cand = [("內插", abs(le)), ("均勻", abs(ue)), ("回歸", abs(ge)), ("原始", abs(re))]
            best = min(cand, key=lambda t: t[1])[0]
        rows.append({"load": i + 1, "x": x, "y": y, "raw_err": re,
                     "lut_calc": lut_yhat[i], "lut_err": le,
                     "uni_calc": uni_yhat[i], "uni_err": ue,
                     "reg_calc": reg_yhat[i], "reg_err": ge,
                     "best": best, "excluded": excluded})
    return rows


def export_comparison_csv_rows(curve: Curve, lut_yhat: list[float], uni_yhat: list[float],
                               reg_yhat: list[float]) -> list[list[str]]:
    """四方逐點比較的 CSV 內容（全精度）。"""
    def num(v: float) -> str:
        return f"{v:.9g}"

    header = ["load", "raw_original", "target", "raw_err",
              "lut_calc", "lut_err", "uni_calc", "uni_err",
              "reg_calc", "reg_err", "best"]
    out = [header]
    for r in comparison_table(curve, lut_yhat, uni_yhat, reg_yhat):
        out.append([str(r["load"]), num(r["x"]), num(r["y"]), num(r["raw_err"]),
                    num(r["lut_calc"]), num(r["lut_err"]),
                    num(r["uni_calc"]), num(r["uni_err"]),
                    num(r["reg_calc"]), num(r["reg_err"]), r["best"]])
    return out


def export_csv_rows(curve: Curve, nodes: list[int], metric: str) -> list[list[str]]:
    """產生節點表 CSV 內容（含每段最大誤差）。回傳含表頭的列陣列。"""
    nodes = sorted(nodes)
    use_rel = metric == "rel"
    eps = _rel_scale(curve.ys) if use_rel else 0.0
    err_col = "seg_max_err_pct" if use_rel else "seg_max_err"
    rows: list[list[str]] = [["index", "node_no", "x", "y", err_col]]

    for seg_no in range(len(nodes)):
        idx = nodes[seg_no]
        # 計算「以此節點為左端、到下一節點」這段的最大誤差（最後一個節點留白）
        seg_err = ""
        if seg_no < len(nodes) - 1:
            a, b = nodes[seg_no], nodes[seg_no + 1]
            xa, ya = curve.xs[a], curve.ys[a]
            xb, yb = curve.xs[b], curve.ys[b]
            dx = xb - xa
            worst = 0.0
            for k in range(a + 1, b):
                if is_excluded(curve.ys[k]):
                    continue                         # 目標值為 0 的點不列入誤差
                t = 0.0 if dx == 0.0 else (curve.xs[k] - xa) / dx
                yh = ya + t * (yb - ya)
                if use_rel:
                    e = abs(yh - curve.ys[k]) / max(abs(curve.ys[k]), eps) * 100.0
                else:
                    e = abs(yh - curve.ys[k])
                if e > worst:
                    worst = e
            seg_err = f"{worst:.6g}"
        rows.append([str(idx), str(seg_no), f"{curve.xs[idx]:.9g}",
                     f"{curve.ys[idx]:.9g}", seg_err])
    return rows
