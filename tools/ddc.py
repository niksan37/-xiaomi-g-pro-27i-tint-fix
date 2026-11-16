"""Minimal DDC/CI tool (Windows, dxva2) -- no external dependencies.

Usage:
  python ddc.py list
  python ddc.py caps  [--mon XMI27B2]
  python ddc.py scan  [--mon XMI27B2]
  python ddc.py get  <code_hex> [--mon XMI27B2]
  python ddc.py set  <code_hex> <value> [--mon XMI27B2]
"""
import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
dxva2 = ctypes.windll.dxva2


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [("hPhysicalMonitor", wintypes.HANDLE),
                ("szPhysicalMonitorDescription", wintypes.WCHAR * 128)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
    wintypes.HANDLE, wintypes.BYTE, ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
dxva2.GetCapabilitiesStringLength.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
dxva2.CapabilitiesRequestAndCapabilitiesReply.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]


def monitors():
    """Return list of dicts: device, device_id, desc, handle."""
    out = []

    def cb(hmon, hdc, rect, lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(mi)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(dd)
        dev_id = ""
        if user32.EnumDisplayDevicesW(mi.szDevice, 0, ctypes.byref(dd), 0):
            dev_id = dd.DeviceID
        n = wintypes.DWORD()
        if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) and n.value:
            arr = (PHYSICAL_MONITOR * n.value)()
            if dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
                for pm in arr:
                    out.append({"device": mi.szDevice, "device_id": dev_id,
                                "desc": pm.szPhysicalMonitorDescription,
                                "handle": pm.hPhysicalMonitor,
                                "primary": bool(mi.dwFlags & 1)})
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return out


def find(tag):
    for m in monitors():
        if tag.lower() in m["device_id"].lower():
            return m
    raise SystemExit(f"Monitor '{tag}' not found")


def get_vcp(h, code, retries=6):
    # This monitor answers unreliably when polled quickly: pace and retry.
    for _ in range(retries):
        time.sleep(0.06)
        t = wintypes.DWORD()
        cur = wintypes.DWORD()
        mx = wintypes.DWORD()
        if dxva2.GetVCPFeatureAndVCPFeatureReply(h, code, ctypes.byref(t), ctypes.byref(cur), ctypes.byref(mx)):
            return t.value, cur.value, mx.value
        time.sleep(0.1)
    return None


def set_vcp(h, code, value):
    time.sleep(0.06)
    ok = bool(dxva2.SetVCPFeature(h, code, value))
    time.sleep(0.12)
    return ok


def caps(h):
    ln = wintypes.DWORD()
    for _ in range(3):
        if dxva2.GetCapabilitiesStringLength(h, ctypes.byref(ln)) and ln.value:
            buf = ctypes.create_string_buffer(ln.value)
            if dxva2.CapabilitiesRequestAndCapabilitiesReply(h, buf, ln.value):
                return buf.value.decode("ascii", "replace")
        time.sleep(0.2)
    return None


def main():
    args = sys.argv[1:]
    tag = "XMI27B2"
    if "--mon" in args:
        i = args.index("--mon")
        tag = args[i + 1]
        del args[i:i + 2]
    cmd = args[0] if args else "list"
    if cmd == "list":
        for m in monitors():
            print(m)
        return
    m = find(tag)
    h = m["handle"]
    if cmd == "caps":
        print(caps(h))
    elif cmd == "scan":
        for code in range(256):
            r = get_vcp(h, code, retries=4)
            if r:
                print(f"0x{code:02X}: type={r[0]} cur={r[1]} (0x{r[1]:04X}) max={r[2]} (0x{r[2]:04X})")
    elif cmd == "get":
        for c in args[1:]:
            code = int(c, 16)
            r = get_vcp(h, code)
            print(f"0x{code:02X}:", "FAIL" if r is None else f"type={r[0]} cur={r[1]} (0x{r[1]:04X}) max={r[2]} (0x{r[2]:04X})")
    elif cmd == "set":
        code = int(args[1], 16)
        val = int(args[2], 0)
        print("set", hex(code), val, "->", set_vcp(h, code, val))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
