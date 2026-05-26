"""只跑 backend.enumerate_devices 一次（沒 warm-up），看 open 會不會成功。"""
import os, sys

proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, proj_root)

from main import _setup_libusb_backend
_setup_libusb_backend()

import usb.core
import usb.backend.libusb1 as b1
import libusb_package

backend = b1.get_backend(find_library=libusb_package.find_library)

# 純 enumerate 一次（同 pyftdi 流程）
print("[only enumerate, no warm-up]")
devs = []
for raw_dev in backend.enumerate_devices():
    d = usb.core.Device(raw_dev, backend)
    if d.idVendor == 0x0403 and d.idProduct == 0x6014:
        devs.append(d)
print(f"  found {len(devs)} matching device(s)")
for d in devs:
    try:
        sn = d.serial_number
        print(f"  OK sn={sn!r}")
    except Exception as ex:
        print(f"  FAIL {ex!r}")
