# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for FT232H Tester
#
# 用法：
#   pyinstaller ft232h_tester.spec
#
# 或直接用 build_exe.ps1 一鍵打包。

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# pyftdi / libusb-package 需要把 DLL 與 data 一起塞進去
datas = []
binaries = []

try:
    datas += collect_data_files("pyftdi")
except Exception:
    pass

try:
    binaries += collect_dynamic_libs("libusb_package")
    datas += collect_data_files("libusb_package")
except Exception:
    pass


a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "pyftdi",
        "pyftdi.ftdi",
        "pyftdi.gpio",
        "pyftdi.spi",
        "pyftdi.i2c",
        "usb",
        "usb.core",
        "usb.backend.libusb1",
        "libusb_package",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FT232H_Tester",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # 設 True 可看 stderr，發行時改回 False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
