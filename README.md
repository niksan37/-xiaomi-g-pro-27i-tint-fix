# Xiaomi G Pro 27i red-tint fix

A small background watcher for Windows that removes the red tint of the **Xiaomi Mini LED Gaming Monitor G Pro 27i** automatically, so you can keep the monitor in its sRGB (or DCI-P3) gamut.

[Deutsche Fassung](README.de.md) · [Guide: how it works, how to verify, troubleshooting](docs/GUIDE.md)

## The problem

- With firmware 1.0.0.6 the picture gets a red tint (visible on white and grey) whenever a colour gamut other than "Native" is selected.
- The tint comes back every time the screen goes black for a moment: wake-up, power-on, Win+P, a resolution or refresh-rate change.
- The known manual workaround is the OSD trick: Picture Mode → "Energy Saver" → back to "Standard". It only lasts until the next black screen.
- In "Native" the tint stays away, but sRGB content is oversaturated.
- The monitor has no USB port, so the firmware cannot be updated by the user.

## The fix

The monitor accepts colour-preset changes over DDC/CI (VCP code `0x14`). Switching the preset to another value and back makes the firmware reload its colour pipeline, with the same result as the OSD trick.

The watcher waits for display events (mode change, wake-up, monitor reconnect) and then does that switch exactly once, about 4 seconds after the screen is back. Expect the tint to be visible for roughly 10 seconds after a black screen, then it disappears with a short, slight colour shift.

## Requirements

- Windows 10 or 11
- Python 3.8 or newer (standard install from python.org, no extra packages)
- DDC/CI enabled in the monitor menu
- Tested over DisplayPort; HDMI is untested

## Install

1. Download this repository (Code → Download ZIP) and unpack it, or clone it.
2. Set the monitor to the gamut you want (sRGB) and Picture Mode "Standard".
3. Open a normal PowerShell window (Start menu → "PowerShell") in the unpacked folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

This copies `tintfix.pyw` to `%LOCALAPPDATA%\XiaomiTintFix`, adds an autostart entry for your user account and starts the watcher. No admin rights are needed.

## Use

- Nothing to do. After a black screen the tint goes away on its own.
- **Ctrl+Alt+F10** applies the fix immediately, in case the watcher missed a black screen.
- `tintfix.log` in the install folder shows every event the watcher saw and every fix it applied.

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File uninstall.ps1
```

The monitor itself is not changed by installing or uninstalling.

## What is tested and what is not

Tested on one unit (built 2024, firmware 1.0.0.6, DisplayPort, AMD Radeon RX 7900 GRE, Windows 11, 2560×1440 at 180 Hz). Because the eye adapts to the tint within seconds, every result was judged with the OSD trick as referee: if the OSD trick still changes the picture after the fix, the fix failed.

| Test | Result |
|---|---|
| Preset switch alone, including a blind round where nothing was sent | 4 of 4 correct, placebo detected |
| Watcher, one fix per black screen (mode change, monitor standby, mode change) | 3 of 3 passed |
| Fix without a preceding black screen (false alarm, once and twice) | harmless, picture stays correct |
| Nudging the RGB gains (`0x16`/`0x18`/`0x1A`) | changes the colours but never reaches the correct state |
| Display mode over DDC (`0xDC`) | not supported by the monitor |

Not verified:

- **HDR.** The tint could not be reproduced with HDR on during testing. The watcher runs in HDR too, but whether it helps there is unknown.
- **Cold boot, the monitor's power button, real PC sleep.** Only mode changes and monitor standby were checked with the referee method.
- **Other units, firmware versions, GPUs and HDMI.** Please run the [blind test](docs/GUIDE.md#verify-it-on-your-monitor) and open an issue with your result.

## Files

| File | Purpose |
|---|---|
| `tintfix.pyw` | the watcher (single file, standard library only) |
| `install.ps1`, `uninstall.ps1` | per-user install and removal |
| `tools/ddc.py` | minimal DDC/CI command line tool (list, scan, get, set) |
| `tools/blind_test.py` | blind test with the OSD trick as referee |

## Disclaimer

This is an unofficial workaround and not affiliated with Xiaomi. It only sends the standard MCCS command "select colour preset" with values the monitor reports as valid, and restores the original value. Use at your own risk.

## License

MIT, see [LICENSE](LICENSE).
