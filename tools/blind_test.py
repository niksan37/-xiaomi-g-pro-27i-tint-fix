"""Blind test: does the DDC colour-preset toggle really replace the OSD trick on YOUR monitor?

Why blind: you get used to the tint within seconds, so "is it red right now?" is not a
reliable question. What you can judge reliably is a CHANGE. So the OSD trick is the referee:

  1. the screen goes black once (refresh-rate switch) -> the tint is back
  2. the script either sends the DDC fix or secretly does nothing (placebo)
  3. you do the OSD trick: Picture Mode -> Energy Saver -> back to Standard
  4. you answer: did the OSD trick still change the picture?

Expected if the fix works: "nothing changed" after a real fix, "changed" after the placebo.
The order is random and only revealed at the end.

Before you start: monitor gamut = sRGB (or DCI-P3), NOT Native. Stop the background watcher
(uninstall.ps1 or Task Manager), otherwise it fixes the tint behind the test's back.

  python tools/blind_test.py [--rounds 4] [--mon XMI27B2]

Keys: 1 / 2 to answer, Esc to abort.
"""
import ctypes
import random
import sys
import time
import tkinter as tk
from ctypes import wintypes

import ddc

user32 = ctypes.windll.user32
PRESET = 0x14


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
        ("dmPositionX", wintypes.LONG), ("dmPositionY", wintypes.LONG),
        ("dmDisplayOrientation", wintypes.DWORD), ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short), ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD)]


DM_DISPLAYFREQUENCY = 0x400000
user32.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODEW)]
user32.ChangeDisplaySettingsExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(DEVMODEW), wintypes.HWND,
                                            wintypes.DWORD, wintypes.LPVOID]


def current_mode(dev):
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    user32.EnumDisplaySettingsW(dev, -1, ctypes.byref(dm))      # ENUM_CURRENT_SETTINGS
    return dm


def available_rates(dev, w, h):
    rates, i = set(), 0
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    while user32.EnumDisplaySettingsW(dev, i, ctypes.byref(dm)):
        if dm.dmPelsWidth == w and dm.dmPelsHeight == h:
            rates.add(dm.dmDisplayFrequency)
        i += 1
    return sorted(rates)


def set_rate(dev, rate):
    dm = current_mode(dev)
    dm.dmDisplayFrequency = rate
    dm.dmFields = DM_DISPLAYFREQUENCY
    return user32.ChangeDisplaySettingsExW(dev, ctypes.byref(dm), None, 0, None)


def blackout(dev):
    """Make the monitor resync (short black screen) by switching the refresh rate and back."""
    dm = current_mode(dev)
    orig = dm.dmDisplayFrequency
    others = [r for r in available_rates(dev, dm.dmPelsWidth, dm.dmPelsHeight) if r != orig and r >= 60]
    if not others:
        raise SystemExit("No second refresh rate available to force a black screen.")
    set_rate(dev, min(others, key=lambda r: abs(r - 120)))
    time.sleep(2.5)
    set_rate(dev, orig)
    time.sleep(3.0)


def main():
    args = sys.argv[1:]
    tag, rounds = "XMI27B2", 4
    if "--mon" in args:
        tag = args[args.index("--mon") + 1]
    if "--rounds" in args:
        rounds = max(2, int(args[args.index("--rounds") + 1]))

    mon = ddc.find(tag)
    handle, dev = mon["handle"], mon["device"]

    def read_preset():
        last = None
        for _ in range(8):
            r = ddc.get_vcp(handle, PRESET)
            v = None if r is None else r[1]
            if v is not None and v == last:
                return v
            last = v
        return last

    def write(value):
        for _ in range(2):
            ddc.set_vcp(handle, PRESET, value)

    preset = read_preset()
    if preset is None:
        raise SystemExit("Could not read VCP 0x14. Is DDC/CI enabled in the monitor menu?")

    def fix():
        write(5 if preset != 5 else 12)
        time.sleep(1.5)
        write(preset)
        time.sleep(0.5)

    def placebo():
        time.sleep(3.0)

    n_placebo = max(1, rounds // 3)
    plan = ["fix"] * (rounds - n_placebo) + ["placebo"] * n_placebo
    random.shuffle(plan)
    results = []

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    w, h = root.winfo_screenwidth(), root.winfo_screenheight()
    canvas = tk.Canvas(root, width=w, height=h, highlightthickness=0, bg="white")
    canvas.pack(fill="both", expand=True)
    canvas.create_rectangle(w // 2, 0, w, h, fill="#808080", outline="")
    title = canvas.create_text(60, 60, anchor="nw", font=("Segoe UI", 28, "bold"), fill="black", width=w // 2 - 120)
    body = canvas.create_text(60, 200, anchor="nw", font=("Segoe UI", 20), fill="black", width=w // 2 - 120)
    hint = canvas.create_text(60, h - 150, anchor="nw", font=("Segoe UI", 19, "bold"), fill="#004488", width=w // 2 - 120)
    answer = tk.StringVar(value="")

    def on_key(ev):
        k = ev.keysym.lower()
        if k in ("1", "2"):
            answer.set(k)
        elif k == "escape":
            answer.set("esc")

    root.bind("<Key>", on_key)

    def show(t, b, hi=""):
        canvas.itemconfigure(title, text=t)
        canvas.itemconfigure(body, text=b)
        canvas.itemconfigure(hint, text=hi)
        root.update()

    def ask(t, b, hi):
        root.attributes("-topmost", True)
        root.focus_force()
        answer.set("")
        show(t, b, hi)
        root.wait_variable(answer)
        if answer.get() == "esc":
            raise KeyboardInterrupt
        return answer.get()

    def run():
        try:
            ask("Blind test", f"{rounds} rounds. In at least one of them nothing is sent.\n\n"
                "Do the OSD trick ONCE NOW (Picture Mode -> Energy Saver -> Standard) so the test "
                "starts from a clean picture, then press 1.", "1 = done, start      Esc = abort")
            for i, kind in enumerate(plan, 1):
                t = f"Round {i} of {rounds}"
                show(t, "The screen goes black for a moment ...")
                blackout(dev)
                root.attributes("-topmost", True)
                show(t, "Please wait ...")
                time.sleep(1.5)
                (fix if kind == "fix" else placebo)()
                time.sleep(1.5)
                a = ask(t, "Do the OSD trick NOW:\nPicture Mode -> Energy Saver -> back to Standard.\n\n"
                        "Compare Standard before with Standard after.\n\nWhat did the OSD trick change?",
                        "1 = nothing, it was already fine      2 = white/grey became more neutral (tint was there)")
                results.append((kind, a == "2"))
        except KeyboardInterrupt:
            pass
        finally:
            if read_preset() != preset:
                write(preset)
            root.destroy()

    root.after(300, run)
    root.mainloop()

    print("round  sent     OSD trick changed the picture   verdict")
    good = 0
    for i, (kind, changed) in enumerate(results, 1):
        expected = (kind == "placebo")
        ok = changed == expected
        good += ok
        print(f"{i:>5}  {kind:<8} {'yes' if changed else 'no':<31} {'as expected' if ok else 'UNEXPECTED'}")
    if results:
        print(f"\n{good} of {len(results)} rounds as expected.")
        print("All as expected -> the DDC toggle replaces the OSD trick on your monitor.")


if __name__ == "__main__":
    main()
