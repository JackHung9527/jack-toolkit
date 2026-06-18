"""電路計算引擎：純函式，與 UI 完全解耦。

所有輸入輸出皆為基本 SI 單位（Ω / V / A / W）。所有 public 函式遇到不合法輸入
丟 ValueError，由 UI 端攔截顯示，不在這裡碰 tkinter。
"""

from __future__ import annotations

import math

# E 系列標準電阻基準值（一個十進位內）。
E_SERIES = {
    "E12": [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2],
    "E24": [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
            3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1],
    "E96": [1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30,
            1.33, 1.37, 1.40, 1.43, 1.47, 1.50, 1.54, 1.58, 1.62, 1.65, 1.69, 1.74,
            1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
            2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09,
            3.16, 3.24, 3.32, 3.40, 3.48, 3.57, 3.65, 3.74, 3.83, 3.92, 4.02, 4.12,
            4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
            5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32,
            7.50, 7.68, 7.87, 8.06, 8.25, 8.45, 8.66, 8.87, 9.09, 9.31, 9.53, 9.76],
}


def nearest_e_series(value: float, series: str = "E24") -> float:
    """回傳最接近 value 的標準電阻值（在對數空間取最近）。value 須 > 0。"""
    if value <= 0:
        raise ValueError("電阻值需為正")
    base = E_SERIES[series]
    decade = math.floor(math.log10(value))
    best = None
    best_err = math.inf
    # 跨相鄰十進位都試，避免邊界（例如 9.8k 應落到 10k 而非 9.1k）。
    for d in (decade - 1, decade, decade + 1):
        scale = 10.0 ** d
        for b in base:
            cand = b * scale
            err = abs(math.log10(cand) - math.log10(value))
            if err < best_err:
                best_err = err
                best = cand
    return best


# ===================== 分壓電阻 =====================
# 電路：Vin --[R1]-- Vout --[R2]-- GND，Vout 取在 R2 上端。

def divider_forward(vin: float, r1: float, r2: float) -> dict:
    """已知 Vin / R1 / R2，算 Vout 與電流、各電阻壓降與功耗。"""
    total = r1 + r2
    if total <= 0:
        raise ValueError("R1 + R2 必須大於 0")
    current = vin / total
    vout = vin * r2 / total
    v_r1 = vin * r1 / total
    return {
        "vout": vout,
        "v_r1": v_r1,
        "ratio": r2 / total,
        "current": current,
        "total_r": total,
        "p_r1": current * current * r1,
        "p_r2": current * current * r2,
        "p_total": vin * current,
    }


def divider_solve_r2(vin: float, vout: float, r1: float) -> float:
    """已知 Vin / 目標 Vout / R1，反推 R2。需 0 < Vout < Vin（同號）。"""
    if r1 < 0:
        raise ValueError("R1 不可為負")
    if vin == 0:
        raise ValueError("Vin 不可為 0")
    frac = vout / vin
    if not (0.0 < frac < 1.0):
        raise ValueError("需滿足 0 < Vout < Vin（且同號）")
    # Vout = Vin * R2 / (R1 + R2)  =>  R2 = R1 * Vout / (Vin - Vout)
    return r1 * vout / (vin - vout)


def divider_solve_r1(vin: float, vout: float, r2: float) -> float:
    """已知 Vin / 目標 Vout / R2，反推 R1。需 0 < Vout < Vin（同號）。"""
    if r2 < 0:
        raise ValueError("R2 不可為負")
    if vout == 0:
        raise ValueError("Vout 不可為 0")
    frac = vout / vin if vin else 0.0
    if not (0.0 < frac < 1.0):
        raise ValueError("需滿足 0 < Vout < Vin（且同號）")
    # R1 = R2 * (Vin - Vout) / Vout
    return r2 * (vin - vout) / vout


# ===================== OPA 放大器 =====================

def noninverting_gain(rf: float, rg: float) -> float:
    """非反相放大增益 = 1 + Rf/Rg。Rg <= 0 視為非法（Rg 為回授到地的電阻）。"""
    if rg <= 0:
        raise ValueError("Rg 必須大於 0")
    if rf < 0:
        raise ValueError("Rf 不可為負")
    return 1.0 + rf / rg


def inverting_gain(rf: float, rin: float) -> float:
    """反相放大增益 = -Rf/Rin。Rin <= 0 視為非法。"""
    if rin <= 0:
        raise ValueError("Rin 必須大於 0")
    if rf < 0:
        raise ValueError("Rf 不可為負")
    return -rf / rin


def gain_db(gain: float) -> float:
    """電壓增益轉 dB = 20*log10(|gain|)。gain 為 0 回 -inf。"""
    g = abs(gain)
    if g == 0:
        return float("-inf")
    return 20.0 * math.log10(g)


def clamp_to_rails(vout_ideal: float, v_pos: float, v_neg: float) -> tuple[float, bool]:
    """把理想輸出夾在電源軌之間。回傳 (實際輸出, 是否飽和)。"""
    lo, hi = (v_neg, v_pos) if v_neg <= v_pos else (v_pos, v_neg)
    clamped = max(lo, min(hi, vout_ideal))
    return clamped, (clamped != vout_ideal)


# ===================== 歐姆定律 / 功率 =====================

def ohms_law(v=None, i=None, r=None, p=None) -> dict:
    """已知 V / I / R / P 之中「恰兩個」，解出其餘兩個。回傳四者皆有的 dict。"""
    have = [name for name, val in (("v", v), ("i", i), ("r", r), ("p", p)) if val is not None]
    if len(have) != 2:
        raise ValueError("請剛好輸入兩個量（V / I / R / P 任兩個）")
    if v is not None and i is not None:
        if i == 0:
            raise ValueError("I 不可為 0")
        r = v / i
        p = v * i
    elif v is not None and r is not None:
        if r <= 0:
            raise ValueError("R 必須大於 0")
        i = v / r
        p = v * v / r
    elif v is not None and p is not None:
        if v == 0:
            raise ValueError("V 不可為 0")
        i = p / v
        r = v * v / p if p != 0 else math.inf
    elif i is not None and r is not None:
        if r < 0:
            raise ValueError("R 不可為負")
        v = i * r
        p = i * i * r
    elif i is not None and p is not None:
        if i == 0:
            raise ValueError("I 不可為 0")
        v = p / i
        r = p / (i * i)
    else:  # r, p
        if r <= 0:
            raise ValueError("R 必須大於 0")
        if p < 0:
            raise ValueError("P 不可為負")
        i = math.sqrt(p / r)
        v = math.sqrt(p * r)
    return {"v": v, "i": i, "r": r, "p": p}


# ===================== 串 / 並聯電阻 =====================

def series_resistance(values: list[float]) -> float:
    if not values:
        raise ValueError("至少輸入一個電阻值")
    return sum(values)


def parallel_resistance(values: list[float]) -> float:
    if not values:
        raise ValueError("至少輸入一個電阻值")
    if any(v <= 0 for v in values):
        raise ValueError("並聯電阻值必須皆大於 0")
    return 1.0 / sum(1.0 / v for v in values)


# ===================== LED 限流電阻 =====================

def led_resistor(vsupply: float, vf: float, i_f: float) -> dict:
    """給電源電壓 / LED 順向壓降 / 目標順向電流，算限流電阻與其功耗。"""
    if i_f <= 0:
        raise ValueError("順向電流 If 必須大於 0")
    if vsupply <= vf:
        raise ValueError("Vsupply 必須大於 LED 順向壓降 Vf")
    r = (vsupply - vf) / i_f
    return {"r": r, "p_r": (vsupply - vf) * i_f, "p_led": vf * i_f}


# ===================== STM32 Timer / PWM =====================

def timer_psc_arr(f_clk: float, f_target: float, max_count: int = 65536) -> dict:
    """由計時器時脈與目標頻率，算 16-bit timer 的 PSC / ARR（盡量保留解析度）。

    關係：f_target = f_clk / ((PSC+1) * (ARR+1))。
    策略：PSC+1 取剛好讓 ARR+1 落在 max_count 以內的最小值，使 ARR 最大、解析度最高。
    """
    if f_clk <= 0 or f_target <= 0:
        raise ValueError("時脈與目標頻率必須大於 0")
    total = f_clk / f_target
    if total < 1.0:
        raise ValueError("目標頻率高於計時器時脈，無法達成")
    psc_plus1 = max(1, math.ceil(total / max_count))
    arr_plus1 = max(1, round(total / psc_plus1))
    actual = f_clk / (psc_plus1 * arr_plus1)
    return {
        "psc": psc_plus1 - 1,
        "arr": arr_plus1 - 1,
        "arr_plus1": arr_plus1,
        "actual": actual,
        "error": (actual - f_target) / f_target,
        "resolution_bits": math.log2(arr_plus1) if arr_plus1 > 1 else 0.0,
    }


def pwm_ccr(arr_plus1: int, duty: float) -> dict:
    """給 ARR+1 與占空比（0~100 %），算 CCR 與量化後的實際占空比。"""
    if not (0.0 <= duty <= 100.0):
        raise ValueError("占空比需在 0 ~ 100 %")
    ccr = round(duty / 100.0 * arr_plus1)
    ccr = max(0, min(arr_plus1, ccr))
    return {"ccr": ccr, "actual_duty": ccr / arr_plus1 * 100.0}


# ===================== UART baud rate =====================

def uart_baud(f_ck: float, baud: float, over8: bool = False) -> dict:
    """USART 過取樣分頻（OVER16 預設）。算分頻值、實際 baud 與誤差。"""
    if f_ck <= 0 or baud <= 0:
        raise ValueError("時脈與 baud 必須大於 0")
    osr = 8 if over8 else 16
    div = round(f_ck / baud)
    if div < 1:
        raise ValueError("時脈太低或 baud 太高，分頻值 < 1")
    actual = f_ck / div
    return {
        "div": div,
        "usartdiv": f_ck / baud,
        "actual": actual,
        "error": (actual - baud) / baud,
        "osr": osr,
    }


# ===================== ADC 解析度 =====================

def adc_lsb(vref: float, bits: int) -> float:
    if vref <= 0:
        raise ValueError("Vref 必須大於 0")
    if bits <= 0:
        raise ValueError("位元數必須大於 0")
    return vref / (2 ** bits)


def adc_raw_to_volt(raw: float, vref: float, bits: int) -> float:
    return raw * adc_lsb(vref, bits)


def adc_volt_to_raw(volt: float, vref: float, bits: int) -> int:
    lsb = adc_lsb(vref, bits)
    return max(0, min(2 ** bits - 1, round(volt / lsb)))


# ===================== 穩壓器回授分壓 =====================
# 典型：Vout --[R1]--◆ FB(=Vref) --[R2]-- GND，Vout = Vref*(1 + R1/R2)。

def reg_feedback_vout(vref: float, r1: float, r2: float) -> float:
    if r2 <= 0:
        raise ValueError("R2 必須大於 0")
    if r1 < 0:
        raise ValueError("R1 不可為負")
    return vref * (1.0 + r1 / r2)


def reg_feedback_solve_r1(vref: float, vout: float, r2: float) -> float:
    if vref <= 0:
        raise ValueError("Vref 必須大於 0")
    if vout <= vref:
        raise ValueError("Vout 必須大於 Vref")
    return r2 * (vout / vref - 1.0)


def reg_feedback_solve_r2(vref: float, vout: float, r1: float) -> float:
    if vref <= 0:
        raise ValueError("Vref 必須大於 0")
    if vout <= vref:
        raise ValueError("Vout 必須大於 Vref")
    return r1 / (vout / vref - 1.0)


# ===================== LDO 功耗 / 散熱 =====================

def ldo_analysis(vin: float, vout: float, iout: float, theta_ja: float | None = None,
                 t_amb: float = 25.0, iq: float = 0.0) -> dict:
    """LDO 壓差功耗與接面溫度。theta_ja 為 None 時不算溫度。"""
    if vin < vout:
        raise ValueError("Vin 必須 ≥ Vout")
    if iout < 0:
        raise ValueError("Iout 不可為負")
    p_pass = (vin - vout) * iout
    p_q = vin * iq
    p_total = p_pass + p_q
    p_out = vout * iout
    p_in = vin * (iout + iq)
    res = {
        "p_pass": p_pass,
        "p_total": p_total,
        "efficiency": (p_out / p_in) if p_in > 0 else 0.0,
        "t_junction": None,
    }
    if theta_ja is not None:
        res["t_junction"] = t_amb + p_total * theta_ja
    return res


# ===================== 電池續航 =====================

def battery_life(capacity_ah: float, load_a: float, usable: float = 1.0) -> dict:
    """容量(Ah) / 負載(A) -> 運行時間(小時)。usable 為可用比例（如 0.8）。"""
    if capacity_ah <= 0:
        raise ValueError("容量必須大於 0")
    if load_a <= 0:
        raise ValueError("負載電流必須大於 0")
    hours = capacity_ah / load_a
    return {"hours": hours, "usable_hours": hours * usable}


# ===================== RC / RL / LC =====================

def rc_cutoff(r: float, c: float) -> float:
    if r <= 0 or c <= 0:
        raise ValueError("R 與 C 必須大於 0")
    return 1.0 / (2.0 * math.pi * r * c)


def rl_cutoff(r: float, l: float) -> float:
    if r <= 0 or l <= 0:
        raise ValueError("R 與 L 必須大於 0")
    return r / (2.0 * math.pi * l)


def lc_resonance(l: float, c: float) -> float:
    if l <= 0 or c <= 0:
        raise ValueError("L 與 C 必須大於 0")
    return 1.0 / (2.0 * math.pi * math.sqrt(l * c))


# ===================== 分流電阻電流量測（shunt -> CSA -> ADC）=====================
# 訊號鏈：I 流過 Rshunt -> Vshunt = I*Rshunt -> 放大 Vout = G*Vshunt + Voffset -> ADC。

def current_sense(rshunt: float, gain: float, vref: float, bits: int,
                  voffset: float = 0.0) -> dict:
    """回傳電流量測鏈的靜態特性（靈敏度、滿量程、解析度）。"""
    if rshunt <= 0:
        raise ValueError("Rshunt 必須大於 0")
    if gain <= 0:
        raise ValueError("增益 G 必須大於 0")
    if vref <= 0:
        raise ValueError("Vref 必須大於 0")
    if bits <= 0:
        raise ValueError("ADC 位元數必須大於 0")
    lsb = vref / (2 ** bits)
    sens_v = gain * rshunt          # 每安培輸出電壓 (V/A)
    return {
        "lsb": lsb,
        "sens_v": sens_v,                       # V/A
        "counts_per_a": sens_v / lsb,           # ADC 碼 / A
        "per_lsb": lsb / sens_v,                # 每 LSB 對應電流 (A)
        "i_fs_pos": (vref - voffset) / sens_v,  # 驅動 Vout 至 Vref 的正向電流
        "i_fs_neg": (0.0 - voffset) / sens_v,   # 驅動 Vout 至 0 的（負向）電流
        "full_count": 2 ** bits,
    }


def current_sense_at(i: float, rshunt: float, gain: float, vref: float, bits: int,
                     voffset: float = 0.0) -> dict:
    """給定量測電流 I，回傳該點的 Vshunt / Vout / ADC 碼 / 功耗 / 飽和旗標。"""
    base = current_sense(rshunt, gain, vref, bits, voffset)
    vshunt = i * rshunt
    vout = gain * vshunt + voffset
    raw = vout / base["lsb"]
    code = max(0, min(base["full_count"] - 1, round(raw)))
    return {
        "vshunt": vshunt,
        "vout": vout,
        "code": code,
        "saturated": (vout > vref) or (vout < 0.0),
        "p_shunt": i * i * rshunt,
        "frac": vout / vref,
    }


def current_sense_code_to_current(code: float, rshunt: float, gain: float, vref: float,
                                  bits: int, voffset: float = 0.0) -> float:
    """ADC 碼反推回量測電流。"""
    base = current_sense(rshunt, gain, vref, bits, voffset)
    vout = code * base["lsb"]
    return (vout - voffset) / base["sens_v"]


# ===================== 555 astable =====================

def timer555_astable(r1: float, r2: float, c: float) -> dict:
    """555 無穩態（astable）：標準 R1(上)-R2-C 接法。"""
    if r1 <= 0 or r2 <= 0 or c <= 0:
        raise ValueError("R1 / R2 / C 必須皆大於 0")
    ln2 = math.log(2.0)  # 0.6931
    t_high = ln2 * (r1 + r2) * c
    t_low = ln2 * r2 * c
    period = t_high + t_low
    return {
        "t_high": t_high,
        "t_low": t_low,
        "period": period,
        "freq": 1.0 / period,
        "duty": t_high / period,
    }
