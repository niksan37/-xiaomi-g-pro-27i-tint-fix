# Guide

- [How the fix works](#how-the-fix-works)
- [Verify it on your monitor](#verify-it-on-your-monitor)
- [Troubleshooting](#troubleshooting)
- [Tuning](#tuning)
- [DDC/CI findings for this monitor](#ddcci-findings-for-this-monitor)
- [What did not work](#what-did-not-work)

## How the fix works

The bug: after every resync (any moment the screen goes black) the firmware applies the selected colour gamut in a way that leaves a red tint. Loading a picture mode from the OSD applies it correctly, which is why "Standard → Energy Saver → Standard" helps.

The picture mode cannot be switched from the PC, but the colour preset can. `tintfix.pyw` does this:

1. A hidden window listens for `WM_DISPLAYCHANGE`, display power notifications (display on, resume from sleep) and monitor device arrival.
2. Events that arrive in a burst are merged. 4 seconds after the last one, the fix runs once.
3. The fix reads VCP `0x14` (colour preset), writes a different valid value (`5`, or `12` if the current one is `5`), waits 1.5 seconds, and writes the original value back.
4. Every write is confirmed by reading the value back, because this monitor drops DDC commands now and then.
5. Before switching, the original value is stored in `tintfix_state.json`. If the PC is shut down in the middle of a fix, the next run restores it.

When started with `--boot` (the autostart entry does this) the watcher also runs the fix once, 8 seconds after logon, because the screen went black before the watcher was running.

## Verify it on your monitor

You get used to the tint within seconds, so "does it look red right now?" is not a reliable question. A change is easy to see. The reliable check is therefore: apply the fix, then do the OSD trick, and watch whether the picture still changes. If it does, the fix did not work.

`tools/blind_test.py` runs exactly this, with a hidden placebo round:

1. Set the monitor gamut to sRGB (not Native) and Picture Mode to "Standard".
2. Stop the watcher (`uninstall.ps1`), otherwise it fixes the tint behind the test's back.
3. Run:

```powershell
python tools\blind_test.py
```

4. In each round the screen goes black once, then the script sends the fix or secretly nothing. You do the OSD trick and press `1` (nothing changed) or `2` (white/grey became more neutral).
5. At the end the script prints which rounds were real and whether your answers match.

Expected on an affected monitor: "nothing changed" after every real fix and "changed" after every placebo. If you get that, install the watcher again with `install.ps1`.

If the placebo rounds also show "nothing changed", the black screen did not trigger the tint on your setup, and the test says nothing either way.

## Troubleshooting

**The tint stays after a black screen.**
Press Ctrl+Alt+F10. If that fixes it, the watcher missed the event; open `%LOCALAPPDATA%\XiaomiTintFix\tintfix.log` and check whether an `event:` line exists for that moment. If not, please open an issue and describe what made the screen go black.

**The log says "colour preset not readable".**
DDC/CI is switched off in the monitor menu, or the monitor was still asleep. Enable DDC/CI. To test the connection:

```powershell
python tools\ddc.py get 14
```

**The log says "monitor not active".**
The monitor is not found under the PnP id `XMI27B2`. Run `python tools\ddc.py list` and compare the `device_id`. If your unit reports a different id, change `MONITOR_TAG` at the top of `tintfix.pyw` and install again.

**Ctrl+Alt+F10 does nothing.**
Another program owns that hotkey; the log then contains "hotkey Ctrl+Alt+F10 is taken". Use `python tintfix.pyw --once` from the install folder instead, or change the key in `watch()` (the `RegisterHotKey` call).

**The watcher no longer starts after a Python update.**
The autostart entry stores the full path to `pythonw.exe`. Run `install.ps1` again.

**The colour temperature is different after a crash or power cut.**
The fix was interrupted between "switch" and "switch back". Start the watcher or run `python tintfix.pyw --once`; it restores the stored value.

## Tuning

The constants at the top of `tintfix.pyw`:

| Constant | Default | Meaning |
|---|---|---|
| `MONITOR_TAG` | `XMI27B2` | part of the monitor's PnP device id |
| `PRESET_VALUES` | `5, 8, 11, 12` | preset values the firmware accepts |
| `DWELL` | `1.5` | seconds on the other preset |
| `DELAY` | `4.0` | seconds between the last display event and the fix |
| `BOOT_DELAY` | `8.0` | seconds after logon before the first fix (`--boot`) |

`DELAY` and `DWELL` are the values that passed the tests. Shorter values would make the tint disappear sooner but are untested. An earlier version that fixed twice per event (after 3 and 10 seconds) failed its first round in two test runs, for reasons that were never found, so the watcher fixes once per event.

## DDC/CI findings for this monitor

Unit: built 2024, firmware 1.0.0.6, MStar scaler (VCP `0xC8` reports `0x5605`), DisplayPort.

- The capabilities string cannot be read.
- Replies are unreliable when the monitor is polled quickly. A full scan returns a different set of codes each time. Pause about 60 ms before and 100 ms after every call, retry reads, and treat a value as valid only when two or three reads in a row agree. Sometimes the reply to the previous request is returned.
- Windows hands out physical-monitor handle `0` for this monitor. It is a valid handle.

| Code | Name | Behaviour |
|---|---|---|
| `0x10` | Luminance | read/write, 0–100 |
| `0x12` | Contrast | read/write, 0–100 |
| `0x14` | Colour preset | read/write; accepts only `5` (6500 K), `8` (9300 K), `11` (User 1), `12` (User 2); other values are ignored |
| `0x16`, `0x18`, `0x1A` | Red, green, blue gain | read/write, 0–100, visible effect |
| `0x6C`, `0x6E` | Red, blue black level | read/write |
| `0xDC` | Display mode | reads `0`, accepts no other value |
| `0x60` | Input source | readable |
| `0xE3`, `0xED`, `0xFA`, `0xFD`, `0xFF` | manufacturer specific | readable, meaning unknown, never written |

With HDR enabled in Windows, `0x14` reads `5` instead of the SDR value.

No readable register differs between the clean and the tinted state, so the tint cannot be detected over DDC. That is why the watcher reacts to display events instead of measuring anything.

## What did not work

- **Rewriting or nudging the RGB gains.** The picture changes, and it looked like a fix at first. With the OSD trick as referee it was clear that the correct state is never reached.
- **Nudging brightness, contrast or black level, or rewriting the preset with the same value.** Reported as "no effect" in an early test round. That round still used the unreliable "is it still red?" question and was not repeated with the referee method, so treat it as likely, not proven.
- **Switching the picture mode over DDC.** `0xDC` is not implemented.
