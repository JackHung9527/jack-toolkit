"""零依賴向量圖示渲染工具（只用 zlib + struct）。

提供圓角矩形 / 圓 / 環 / 線段 / 三角形等 inside-test 原語，以 SS 超取樣做
anti-alias、premultiplied 合成，輸出多解析度 .ico（內嵌 PNG）與單張 .png。
給 make_icons.py 為 launcher 與各工具產生圖示。
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZES = [16, 24, 32, 48, 64, 128, 256]
SS = 3


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


# ===== inside-test 原語（座標皆 0..1，y 向下）=====

def rrect(x0, y0, x1, y1, r):
    def f(u, v):
        ix0, iy0, ix1, iy1 = x0 + r, y0 + r, x1 - r, y1 - r
        if ix1 < ix0:
            ix0 = ix1 = (x0 + x1) * 0.5
        if iy1 < iy0:
            iy0 = iy1 = (y0 + y1) * 0.5
        qx = u - clamp(u, ix0, ix1)
        qy = v - clamp(v, iy0, iy1)
        return (qx * qx + qy * qy) <= r * r
    return f


def rect(x0, y0, x1, y1):
    def f(u, v):
        return x0 <= u <= x1 and y0 <= v <= y1
    return f


def circle(cx, cy, rad):
    def f(u, v):
        dx, dy = u - cx, v - cy
        return dx * dx + dy * dy <= rad * rad
    return f


def ring(cx, cy, outer, inner):
    def f(u, v):
        dx, dy = u - cx, v - cy
        d2 = dx * dx + dy * dy
        return inner * inner <= d2 <= outer * outer
    return f


def segment(x0, y0, x1, y1, half):
    dx, dy = x1 - x0, y1 - y0
    ll = dx * dx + dy * dy

    def f(u, v):
        if ll == 0:
            t = 0.0
        else:
            t = clamp(((u - x0) * dx + (v - y0) * dy) / ll, 0.0, 1.0)
        px, py = x0 + t * dx, y0 + t * dy
        ex, ey = u - px, v - py
        return ex * ex + ey * ey <= half * half
    return f


def triangle(p0, p1, p2):
    def sign(ax, ay, bx, by, cx, cy):
        return (ax - cx) * (by - cy) - (bx - cx) * (ay - cy)

    def f(u, v):
        d1 = sign(u, v, p0[0], p0[1], p1[0], p1[1])
        d2 = sign(u, v, p1[0], p1[1], p2[0], p2[1])
        d3 = sign(u, v, p2[0], p2[1], p0[0], p0[1])
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)
    return f


def vgrad(top, bot, y0=0.0, y1=1.0):
    """回傳依 v 線性漸層的顏色函式。top/bot 為 (r,g,b) 0..255。"""
    def f(u, v):
        t = clamp((v - y0) / (y1 - y0) if y1 != y0 else 0.0, 0.0, 1.0)
        return (
            int(top[0] + (bot[0] - top[0]) * t),
            int(top[1] + (bot[1] - top[1]) * t),
            int(top[2] + (bot[2] - top[2]) * t),
            255,
        )
    return f


def render(size: int, layers: list) -> bytes:
    """layers: list of (inside_fn, color)。color 為 (r,g,b,a) 或 callable(u,v)->(r,g,b,a)。"""
    out = bytearray(size * size * 4)
    n = SS * SS
    for y in range(size):
        for x in range(size):
            pr = pg = pb = pa = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    u = (x + (sx + 0.5) / SS) / size
                    v = (y + (sy + 0.5) / SS) / size
                    dr = dg = db = da = 0.0
                    for fn, color in layers:
                        if not fn(u, v):
                            continue
                        if callable(color):
                            cr, cg, cb, ca = color(u, v)
                        else:
                            cr, cg, cb, ca = color
                        sa = ca / 255.0
                        sr = cr / 255.0 * sa
                        sg = cg / 255.0 * sa
                        sb = cb / 255.0 * sa
                        dr = sr + dr * (1 - sa)
                        dg = sg + dg * (1 - sa)
                        db = sb + db * (1 - sa)
                        da = sa + da * (1 - sa)
                    pr += dr
                    pg += dg
                    pb += db
                    pa += da
            pr /= n
            pg /= n
            pb /= n
            pa /= n
            if pa > 0:
                r8 = int(round(clamp(pr / pa, 0, 1) * 255))
                g8 = int(round(clamp(pg / pa, 0, 1) * 255))
                b8 = int(round(clamp(pb / pa, 0, 1) * 255))
            else:
                r8 = g8 = b8 = 0
            a8 = int(round(clamp(pa, 0, 1) * 255))
            i = (y * size + x) * 4
            out[i] = r8
            out[i + 1] = g8
            out[i + 2] = b8
            out[i + 3] = a8
    return bytes(out)


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def write_ico(path: Path, entries: list) -> None:
    n = len(entries)
    header = struct.pack("<HHH", 0, 1, n)
    dir_blob = b""
    data_blob = b""
    offset = 6 + 16 * n
    for size, png in entries:
        wb = size if size < 256 else 0
        hb = size if size < 256 else 0
        dir_blob += struct.pack("<BBBBHHII", wb & 0xFF, hb & 0xFF, 0, 0, 1, 32, len(png), offset)
        data_blob += png
        offset += len(png)
    Path(path).write_bytes(header + dir_blob + data_blob)


def build_icon(out_ico: Path, layers_for, out_png: Path | None = None, png_size: int = 64) -> None:
    """layers_for(size) -> layers list（允許依尺寸微調，多半忽略 size）。"""
    entries = []
    for size in SIZES:
        rgba = render(size, layers_for(size))
        entries.append((size, encode_png(size, size, rgba)))
    write_ico(out_ico, entries)
    if out_png is not None:
        rgba = render(png_size, layers_for(png_size))
        Path(out_png).write_bytes(encode_png(png_size, png_size, rgba))
