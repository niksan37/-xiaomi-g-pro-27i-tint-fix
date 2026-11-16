"""Xiaomi G Pro 27i red-tint fix (firmware 1.0.0.6).

The monitor shows a red tint after every resync (wake-up, power-on, mode change)
while a colour gamut other than "Native" is active. Switching the colour preset
over DDC/CI (VCP 0x14) to another value and back makes the firmware reload its
colour pipeline -- verified in a blind test to be equivalent to the OSD trick
"Standard -> Energy Saver -> Standard". (Nudging the RGB gains is NOT equivalent.)
This script waits in the background until the screen has gone black (mode change,
wake-up, monitor reconnect) and then does that toggle EXACTLY ONCE per black screen.
(An earlier version that toggled twice per event failed some test rounds.)

  pythonw tintfix.pyw          background watcher (single instance)
  pythonw tintfix.pyw --boot   same, plus one fix after logon (autostart: the screen was black before)
  python  tintfix.pyw --once   apply the fix once and exit

Manual trigger while the watcher runs: Ctrl+Alt+F10
"""
import ctypes
import json
import logging
import os
import sys
import threading
import time
from ctypes import wintypes
from logging.handlers import RotatingFileHandler

MONITOR_TAG = "XMI27B2"            # PnP id of the G Pro 27i
PRESET = 0x14                      # VCP: select colour preset
PRESET_VALUES = (5, 8, 11, 12)     # values this firmware accepts (6500K, 9300K, User1, User2)
DWELL = 1.5                        # seconds on the other preset (as tested)
DELAY = 4.0                        # seconds after the LAST display event of a burst (as tested)
BOOT_DELAY = 8.0                   # seconds after logon when started with --boot
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "tintfix_state.json")

log = logging.getLogger("tintfix")
log.setLevel(logging.INFO)
_h = RotatingFileHandler(os.path.join(HERE, "tintfix.log"), maxBytes=200_000, backupCount=1, encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
log.addHandler(_h)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dxva2 = ctypes.WinDLL("dxva2", use_last_error=True)

# ---------------------------------------------------------------- DDC/CI


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [("handle", wintypes.HANDLE), ("desc", wintypes.WCHAR * 128)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32), ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD), ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.DestroyPhysicalMonitor.argtypes = [wintypes.HANDLE]
dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [wintypes.HANDLE, wintypes.BYTE, ctypes.POINTER(wintypes.DWORD),
                                                  ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]


def open_monitor():
    """Return (present, target_handle, all_handles) for the Xiaomi."""
    found, handles = [], []

    def cb(hmon, hdc, rect, lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(mi)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return True
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(dd)
        dev_id = dd.DeviceID if user32.EnumDisplayDevicesW(mi.szDevice, 0, ctypes.byref(dd), 0) else ""
        n = wintypes.DWORD()
        if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) and n.value:
            arr = (PHYSICAL_MONITOR * n.value)()
            if dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
                for pm in arr:
                    handles.append(pm.handle)
                    if MONITOR_TAG.lower() in dev_id.lower():
                        found.append(pm.handle)
        return True

    proc = MONITORENUMPROC(cb)
    user32.EnumDisplayMonitors(None, None, proc, 0)
    # Note: Windows hands out physical-monitor handle 0 (ctypes: None) as a valid handle,
    # so "not found" is reported separately instead of via the handle value.
    return bool(found), (found[0] if found else None), handles


def close_monitors(handles):
    for h in handles:
        dxva2.DestroyPhysicalMonitor(h)


def get_vcp(h, code, retries=6):
    # The monitor answers unreliably when polled quickly: pace and retry.
    for _ in range(retries):
        time.sleep(0.06)
        t, cur, mx = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
        if dxva2.GetVCPFeatureAndVCPFeatureReply(h, code, ctypes.byref(t), ctypes.byref(cur), ctypes.byref(mx)):
            return cur.value, mx.value
        time.sleep(0.1)
    return None


def set_vcp(h, code, value, n=2):
    for _ in range(n):
        time.sleep(0.06)
        dxva2.SetVCPFeature(h, code, value)
        time.sleep(0.12)


def set_confirmed(h, code, value, tries=5):
    """Write and read back until the monitor really reports the new value (writes get lost sometimes)."""
    for _ in range(tries):
        set_vcp(h, code, value)
        r = get_vcp(h, code, retries=4)
        if r is not None and r[0] == value:
            return True
    return False


def read_preset(h):
    """Three identical, valid reads in a row (the bus occasionally returns a stale reply)."""
    streak, last = 0, None
    for _ in range(12):
        r = get_vcp(h, PRESET)
        if r is None or r[0] not in PRESET_VALUES:
            streak, last = 0, None
            continue
        streak = streak + 1 if r[0] == last else 1
        last = r[0]
        if streak >= 3:
            return last
    return None


# ---------------------------------------------------------------- the fix

_fix_lock = threading.Lock()
_known = None                      # preset verified by the last successful run


def _load_pending():
    try:
        with open(STATE, encoding="utf-8") as f:
            v = int(json.load(f)["restore_preset"])
            return v if v in PRESET_VALUES else None
    except Exception:
        return None


def _save_pending(v):
    try:
        if v is not None:
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump({"restore_preset": v}, f)
        elif os.path.exists(STATE):
            os.remove(STATE)
    except Exception as e:
        log.warning("state file: %s", e)


def apply_fix(reason=""):
    global _known
    with _fix_lock:
        t0 = time.monotonic()
        present, h, handles = open_monitor()
        try:
            if not present:
                log.info("fix(%s): monitor not active, nothing to do", reason)
                return False
            # A previous run was interrupted between "switch" and "switch back": that value wins.
            v = _load_pending()
            if v is None and _known is not None:
                r = get_vcp(h, PRESET, retries=3)      # fast path: one read matching the last verified value
                if r is not None and r[0] == _known:
                    v = _known
            if v is None:
                v = read_preset(h)
            if v is None:
                log.info("fix(%s): colour preset not readable (monitor asleep?), skipped", reason)
                return False
            other = 5 if v != 5 else 12
            _save_pending(v)
            switched = set_confirmed(h, PRESET, other)
            time.sleep(DWELL)
            set_confirmed(h, PRESET, v)
            t_done = time.monotonic()
            ok = False
            for _ in range(3):
                if read_preset(h) == v:
                    ok = True
                    break
                set_vcp(h, PRESET, v)
            if ok:
                _save_pending(None)
                _known = v
            else:
                _known = None
            log.info("fix(%s): colour preset %s->%s->%s (%.1f s), switch %s, read-back %s", reason, v, other, v,
                     t_done - t0, "confirmed" if switched else "NOT CONFIRMED", "ok" if ok else "MISMATCH")
            return ok and switched
        except Exception:
            log.exception("fix(%s) failed", reason)
            return False
        finally:
            close_monitors(handles)


# ---------------------------------------------------------------- event watcher

WM_DESTROY, WM_DISPLAYCHANGE, WM_POWERBROADCAST, WM_DEVICECHANGE, WM_HOTKEY = 0x0002, 0x007E, 0x0218, 0x0219, 0x0312
PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC, PBT_POWERSETTINGCHANGE = 0x0007, 0x0012, 0x8013
DBT_DEVICEARRIVAL = 0x8000


class GUID(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    def __init__(self, s=None):
        super().__init__()
        if s:
            p = s.strip("{}").split("-")
            self.d1, self.d2, self.d3 = int(p[0], 16), int(p[1], 16), int(p[2], 16)
            tail = bytes.fromhex(p[3] + p[4])
            for i, b in enumerate(tail):
                self.d4[i] = b

    def __eq__(self, o):
        return bytes(self) == bytes(o)


GUID_CONSOLE_DISPLAY_STATE = GUID("6fe69556-704a-47a0-8f24-c28d936fda47")
GUID_MONITOR_POWER_ON = GUID("02731015-4510-4526-99e6-e5a17ebd1aea")
GUID_DEVINTERFACE_MONITOR = GUID("e6f07b5f-ee97-4a90-b076-33f57bf4eaa7")


class POWERBROADCAST_SETTING(ctypes.Structure):
    _fields_ = [("PowerSetting", GUID), ("DataLength", wintypes.DWORD), ("Data", ctypes.c_ubyte * 4)]


class DEV_BROADCAST_DEVICEINTERFACE_W(ctypes.Structure):
    _fields_ = [("dbcc_size", wintypes.DWORD), ("dbcc_devicetype", wintypes.DWORD), ("dbcc_reserved", wintypes.DWORD),
                ("dbcc_classguid", GUID), ("dbcc_name", wintypes.WCHAR * 1)]


LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterPowerSettingNotification.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), wintypes.DWORD]
user32.RegisterPowerSettingNotification.restype = wintypes.HANDLE
user32.RegisterDeviceNotificationW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
user32.RegisterDeviceNotificationW.restype = wintypes.HANDLE
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE


class Scheduler(threading.Thread):
    """Runs the fix once, DELAY seconds after the last display event of a burst."""

    def __init__(self):
        super().__init__(daemon=True)
        self._cv = threading.Condition()
        self._due = None
        self._reason = ""

    def trigger(self, reason, delay=DELAY):
        with self._cv:
            if self._due is None:
                log.info("event: %s", reason)
            self._due = time.monotonic() + delay
            self._reason = reason
            self._cv.notify()

    def run(self):
        while True:
            with self._cv:
                while self._due is None:
                    self._cv.wait()
                wait = self._due - time.monotonic()
                if wait > 0:
                    self._cv.wait(wait)
                    continue
                self._due = None
                reason = self._reason
            apply_fix(reason)


def watch():
    mutex = kernel32.CreateMutexW(None, False, "Local\\XiaomiTintFixWatcher")
    if ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
        return
    sched = Scheduler()
    sched.start()
    started = time.monotonic()

    def wndproc(hwnd, msg, wparam, lparam):
        try:
            if msg == WM_DISPLAYCHANGE:
                sched.trigger("display mode change")
            elif msg == WM_POWERBROADCAST:
                if wparam in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
                    sched.trigger("resume")
                elif wparam == PBT_POWERSETTINGCHANGE and lparam:
                    s = ctypes.cast(lparam, ctypes.POINTER(POWERBROADCAST_SETTING)).contents
                    # Windows reports the current state once right after registering: not a black screen.
                    if (time.monotonic() - started > 3.0 and s.Data[0] == 1
                            and (s.PowerSetting == GUID_CONSOLE_DISPLAY_STATE
                                 or s.PowerSetting == GUID_MONITOR_POWER_ON)):
                        sched.trigger("display on")
            elif msg == WM_DEVICECHANGE and wparam == DBT_DEVICEARRIVAL:
                sched.trigger("monitor connected")
            elif msg == WM_HOTKEY:
                sched.trigger("hotkey", delay=0.0)
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
        except Exception:
            log.exception("wndproc")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    proc = WNDPROC(wndproc)
    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = hinst
    wc.lpszClassName = "XiaomiTintFixWindow"
    user32.RegisterClassW(ctypes.byref(wc))
    # hidden top-level window (message-only windows do not receive broadcasts)
    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "XiaomiTintFix", 0, 0, 0, 0, 0, None, None, hinst, None)
    if not hwnd:
        log.error("could not create the hidden window: %s", ctypes.get_last_error())
        return
    user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(GUID_CONSOLE_DISPLAY_STATE), 0)
    user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(GUID_MONITOR_POWER_ON), 0)
    flt = DEV_BROADCAST_DEVICEINTERFACE_W()
    flt.dbcc_size = ctypes.sizeof(flt)
    flt.dbcc_devicetype = 5                # DBT_DEVTYP_DEVICEINTERFACE
    flt.dbcc_classguid = GUID_DEVINTERFACE_MONITOR
    user32.RegisterDeviceNotificationW(hwnd, ctypes.byref(flt), 0)
    if not user32.RegisterHotKey(hwnd, 1, 0x0001 | 0x0002 | 0x4000, 0x79):   # Ctrl+Alt+F10, no repeat
        log.warning("hotkey Ctrl+Alt+F10 is taken and was not registered")
    log.info("watcher started (pid %s)", os.getpid())
    if "--boot" in sys.argv:
        sched.trigger("logon", delay=BOOT_DELAY)

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    del mutex


if __name__ == "__main__":
    if "--once" in sys.argv:
        ok = apply_fix("manual")
        if sys.stdout:
            print("ok" if ok else "failed (see tintfix.log)")
    else:
        watch()
