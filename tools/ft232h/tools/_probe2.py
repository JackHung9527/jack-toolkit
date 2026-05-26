"""diagnose: 確認 pyusb 載入的是哪個 libusb backend / DLL。"""
import os
import sys
import ctypes.util

print("python:", sys.executable)
print()

# 1. find_library 自己找到什麼？
print("[ctypes.util.find_library('usb-1.0')]:", ctypes.util.find_library("usb-1.0"))
print("[ctypes.util.find_library('libusb-1.0')]:", ctypes.util.find_library("libusb-1.0"))
print("[ctypes.util.find_library('libusb0')]:", ctypes.util.find_library("libusb0"))
print("[ctypes.util.find_library('usb0')]:", ctypes.util.find_library("usb0"))
print()

# 2. libusb-package 提供什麼
try:
    import libusb_package
    print("[libusb_package.find_library('usb-1.0')]:", libusb_package.find_library("usb-1.0"))
except Exception as ex:
    print("libusb_package error:", ex)
print()

# 3. pyusb 實際載入了哪個 backend
import usb.backend.libusb1 as b1
import usb.backend.libusb0 as b0
print("Loading libusb1 backend...")
be1 = b1.get_backend()
print("  libusb1 backend:", be1)
if be1 is not None:
    print("  libusb1 lib:", getattr(be1, "lib", None))

print("Loading libusb0 backend...")
be0 = b0.get_backend()
print("  libusb0 backend:", be0)
if be0 is not None:
    print("  libusb0 lib:", getattr(be0, "lib", None))
print()

# 4. usb.core.find 預設找哪個 backend
import usb.core
print("Calling usb.core.find(idVendor=0x0403, idProduct=0x6014, find_all=True)...")
devs = list(usb.core.find(idVendor=0x0403, idProduct=0x6014, find_all=True))
print(f"  found {len(devs)} device(s)")
for d in devs:
    print(f"    backend={type(d._ctx.backend).__module__}  bus={d.bus} addr={d.address}")

# 5. 強制 libusb1 backend
print()
print("Forcing libusb1 backend with libusb_package:")
try:
    import libusb_package
    backend = b1.get_backend(find_library=libusb_package.find_library)
    if backend is None:
        print("  failed to get libusb1 backend")
    else:
        devs2 = list(usb.core.find(idVendor=0x0403, idProduct=0x6014,
                                   find_all=True, backend=backend))
        print(f"  found {len(devs2)} device(s)")
        for d in devs2:
            try:
                lang = d.langids
                desc = usb.util.get_string(d, d.iProduct) if d.iProduct else "(no product str)"
                print(f"    sn={d.serial_number!r} desc={desc!r}")
            except Exception as ex:
                print(f"    open failed: {ex!r}")
except Exception as ex:
    import traceback
    traceback.print_exc()
