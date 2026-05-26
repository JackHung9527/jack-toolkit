"""FT232H Tester 入口。

直接執行：
    python main.py

打包後 (PyInstaller) 也由本檔當入口。
"""

from __future__ import annotations

import os
import sys


def _setup_libusb_backend() -> None:
    """套用三組 fix 讓 pyftdi 能在「系統裝過多個 FTDI 工具 + 殘留 libusb0」的
    Windows 機器上正常運作：

    Fix 1 - DLL 搜尋路徑
        libusb-package 套件帶一份 libusb-1.0.dll；把它的目錄塞進 PATH +
        os.add_dll_directory，避免 pyusb 抓到舊的 C:\\Windows\\system32\\
        libusb0.dll（libusb-win32 殘留），那顆對 WinUSB driver 不相容。

    Fix 2 - 強制 pyftdi 用 libusb_package 提供的 libusb1 backend
        pyftdi 的 UsbTools._load_backend 預設不帶 find_library，可能拿到
        錯的 DLL；這裡注入 libusb_package 提供的 backend instance。

    Fix 3 - 縮減 Ftdi.PRODUCT_IDS 只剩 232h (PID 0x6014)
        pyftdi enumerate_candidates 無視 URL 的 product 指定，會把該 vendor
        下「所有 FTDI PID」都 enumerate 並對每顆做 libusb_open。如果機器上
        有別顆 FTDI device (例如 FT232R PID 0x6001) 用 FTDIBUS driver 在跑，
        libusb_open 它會噴 NotImplementedError，整個 enumerate 流程就掛了。
        本工具只支援 FT232H，所以把 PRODUCT_IDS 縮到只剩 232h 的 alias。
    """
    try:
        import libusb_package  # type: ignore

        # --- Fix 1: DLL 路徑 ---
        lib_path = libusb_package.get_library_path()
        if lib_path is not None:
            dll_dir = os.path.dirname(os.path.abspath(str(lib_path)))
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(dll_dir)
                except (OSError, FileNotFoundError):
                    pass
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
            try:
                import ctypes
                ctypes.CDLL(str(lib_path))
            except OSError:
                pass

        # --- Fix 2: 強制 pyftdi 用 libusb_package 提供的 backend ---
        import usb.backend.libusb1 as _b1  # type: ignore
        _backend = _b1.get_backend(find_library=libusb_package.find_library)
        if _backend is not None:
            from pyftdi import usbtools as _ut  # type: ignore
            _ut.UsbTools._load_backend = classmethod(lambda cls: _backend)

        # --- Fix 3: 縮減 Ftdi.PRODUCT_IDS 到只剩 FT232H (0x6014) ---
        from pyftdi.ftdi import Ftdi  # type: ignore
        _vendor = Ftdi.FTDI_VENDOR
        _orig = Ftdi.PRODUCT_IDS.get(_vendor, {})
        _filtered = {name: pid for name, pid in _orig.items() if pid == 0x6014}
        if _filtered:
            Ftdi.PRODUCT_IDS = {_vendor: _filtered}
    except Exception:
        pass


def main() -> int:
    _setup_libusb_backend()

    # 允許從專案根目錄與打包 exe 兩種情境啟動
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    from src.ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
