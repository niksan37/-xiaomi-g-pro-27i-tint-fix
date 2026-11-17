# Xiaomi G Pro 27i: Rotstich-Fix

Ein kleiner Hintergrund-Wächter für Windows, der den Rotstich des **Xiaomi Mini LED Gaming Monitor G Pro 27i** automatisch beseitigt. Damit kann der Monitor dauerhaft im sRGB-Farbraum (oder DCI-P3) bleiben.

[English version](README.md) · [Guide (englisch): Funktionsweise, Gegenprobe, Fehlersuche](docs/GUIDE.md)

## Das Problem

- Mit Firmware 1.0.0.6 bekommt das Bild einen Rotstich (sichtbar auf Weiß und Grau), sobald ein anderer Farbraum als „Nativ" gewählt ist.
- Der Stich kommt jedes Mal wieder, wenn das Bild kurz schwarz wird: Aufwachen, Einschalten, Win+P, Wechsel von Auflösung oder Bildwiederholrate.
- Bekannter Handgriff: im Monitor-Menü Picture Mode → „Energy Saver" → zurück auf „Standard". Das hält nur bis zum nächsten Schwarzbild.
- In „Nativ" bleibt der Stich weg, dafür sind sRGB-Inhalte übersättigt.
- Der Monitor hat keinen USB-Anschluss, die Firmware lässt sich nicht selbst aktualisieren.

## Die Lösung

Der Monitor nimmt per DDC/CI Umschaltungen des Farbpresets an (VCP-Code `0x14`). Schaltet man das Preset auf einen anderen Wert und zurück, lädt die Firmware ihre Farbverarbeitung neu, mit demselben Ergebnis wie der Menü-Trick.

Der Wächter wartet auf Anzeige-Ereignisse (Moduswechsel, Aufwachen, Wiederverbinden) und schaltet dann genau einmal um, etwa 4 Sekunden nachdem das Bild wieder da ist. Der Rotstich ist nach einem Schwarzbild noch rund 10 Sekunden sichtbar und verschwindet dann mit einem kurzen, leichten Farbwechsel.

## Voraussetzungen

- Windows 10 oder 11
- Python 3.8 oder neuer (Standardinstallation von python.org, keine Zusatzpakete)
- DDC/CI im Monitor-Menü eingeschaltet
- Getestet über DisplayPort; HDMI ist ungetestet

## Installation

1. Dieses Repository herunterladen (Code → Download ZIP) und entpacken, oder klonen.
2. Am Monitor den gewünschten Farbraum (sRGB) und Picture Mode „Standard" einstellen.
3. Ein normales PowerShell-Fenster (Startmenü → „PowerShell") im entpackten Ordner öffnen und ausführen:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Das kopiert `tintfix.pyw` nach `%LOCALAPPDATA%\XiaomiTintFix`, trägt den Autostart für dein Benutzerkonto ein und startet den Wächter. Adminrechte sind nicht nötig.

## Benutzung

- Nichts zu tun. Nach einem Schwarzbild verschwindet der Stich von selbst.
- **Strg+Alt+F10** löst die Korrektur sofort aus, falls der Wächter ein Schwarzbild verpasst hat.
- `tintfix.log` im Installationsordner zeigt jedes erkannte Ereignis und jede Korrektur.

## Deinstallation

```powershell
powershell -ExecutionPolicy Bypass -File uninstall.ps1
```

Am Monitor selbst wird durch Installation oder Deinstallation nichts verändert.

## Was getestet ist und was nicht

Getestet an einem Gerät (Baujahr 2024, Firmware 1.0.0.6, DisplayPort, AMD Radeon RX 7900 GRE, Windows 11, 2560×1440 bei 180 Hz). Weil sich das Auge in Sekunden an den Stich gewöhnt, wurde jedes Ergebnis mit dem Menü-Trick als Gegenprobe beurteilt: Verändert der Menü-Trick nach der Korrektur das Bild noch, ist die Korrektur durchgefallen.

| Test | Ergebnis |
|---|---|
| Preset-Umschaltung einzeln, inklusive Blindrunde ohne Befehl | 4 von 4 richtig, Leerlauf erkannt |
| Wächter, eine Korrektur pro Schwarzbild (Moduswechsel, Monitor-Standby, Moduswechsel) | 3 von 3 bestanden |
| Korrektur ohne vorheriges Schwarzbild (Fehlalarm, einmal und zweimal) | harmlos, Bild bleibt korrekt |
| RGB-Gains verstellen (`0x16`/`0x18`/`0x1A`) | verändert die Farben, erreicht aber nie den korrekten Zustand |
| Bildmodus per DDC (`0xDC`) | vom Monitor nicht unterstützt |

Nicht geprüft:

- **HDR.** Der Stich ließ sich im Test mit eingeschaltetem HDR nicht auslösen. Der Wächter läuft auch in HDR, ob er dort hilft, ist offen.
- **Kaltstart, Einschaltknopf des Monitors, echter PC-Ruhezustand.** Mit Gegenprobe geprüft sind nur Moduswechsel und Monitor-Standby.
- **Andere Geräte, Firmware-Versionen, Grafikkarten und HDMI.** Bitte den [Blindtest](docs/GUIDE.md#verify-it-on-your-monitor) laufen lassen und das Ergebnis als Issue melden.

## Haftung

Inoffizieller Workaround ohne Verbindung zu Xiaomi. Gesendet wird nur der Standard-MCCS-Befehl „Farbpreset wählen" mit Werten, die der Monitor selbst als gültig meldet; der Ausgangswert wird wiederhergestellt. Benutzung auf eigene Gefahr.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
