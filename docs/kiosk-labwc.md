# Kiosk-Konfiguration (labwc)

Hintergrundwissen zur labwc-Kiosk-Konfiguration auf dem Raspberry Pi (Desktop-Umgebung: labwc, Wayland-Compositor, Openbox-3.6-kompatibel). Kiosk-Anwendung: Chromium im App-Modus auf `http://planer:3000` (Yuvomi-Frontend).

## labwc_config statt openbox_config

Die Raspberry-Pi-OS-GUI-Einstellungstools (z. B. "Einstellungen -> Tastatur und Maus") ueberschreiben `~/.config/labwc/rc.xml` bei jedem Speichern komplett und schreiben dabei den alten Openbox-Dialekt `<openbox_config>` statt des fuer native labwc-Features (z. B. `windowRules`) benoetigten `<labwc_config>`-Root-Elements. Beide Root-Elemente duerfen nicht gleichzeitig in einer Datei stehen - das verursacht XML-Fehler.

**Konsequenz:** GUI-Einstellungstools an diesem Geraet meiden; Aenderungen nur noch haendisch in `rc.xml` vornehmen.

Funktionierende Struktur (`~/.config/labwc/rc.xml`):

```xml
<?xml version="1.0"?>
<labwc_config>
  <theme>
    <font place="ActiveWindow">
      <name>Nunito Sans</name>
      <size>12</size>
      <weight>Light</weight>
      <slant>Normal</slant>
    </font>
    <name>PiXonyx</name>
  </theme>
  <windowRules>
    <windowRule identifier="*" serverDecoration="no" />
  </windowRules>
</labwc_config>
```

`windowRules` mit `serverDecoration="no"` entfernt Fensterrahmen/Titelleiste bei allen Fenstern.

## Automatische Wiederherstellung der rc.xml beim Systemstart

1. Master-Kopie unter `~/.config/kiosk-backup/rc.xml.master`:
   ```bash
   mkdir -p ~/.config/kiosk-backup
   cp ~/.config/labwc/rc.xml ~/.config/kiosk-backup/rc.xml.master
   ```
2. In `~/.config/labwc/autostart` als allererste Zeile:
   ```bash
   cp ~/.config/kiosk-backup/rc.xml.master ~/.config/labwc/rc.xml
   ```

**Einschraenkung:** Wirkt erst beim naechsten Neustart. **Wartung:** Bei jeder bewussten Aenderung an `rc.xml` die Master-Kopie manuell nachziehen, sonst wird sie beim naechsten Boot ueberschrieben.

## Taskleiste (wf-panel-pi)

Komplett deaktivieren per drei Kill-Befehlen in `~/.config/labwc/autostart`:
```bash
pkill wf-panel-pi
pkill -9 lwrespawn
pkill -9 wf-panel-pi
```

Alternative (Autohide statt komplett entfernen):
```ini
[panel]
autohide=true
autohide_duration=300
edge_offset=20
```
in `~/.config/wf-panel-pi.ini`, dazu die drei `pkill`-Zeilen auskommentieren.

**Wichtig:** Aenderungen wirken erst nach `sudo systemctl reboot`.
