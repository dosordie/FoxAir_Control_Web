# UI-Konzept – Übersicht zuerst, Parameter per Button

**Grundregel:** Nach dem Öffnen landet der Nutzer **nicht im Registerbrowser**, sondern auf einer übersichtlichen, WarmLink-artigen Wärmepumpen-Startseite. Eine eigene, nicht mit App-Konfiguration verwechselte Schaltfläche führt zu den **WP-Parametern**.

## Beispiel: iPhone

```text
┌──────────────────────────────┐
│ FoxAir       GL9      ⚙ App │
│ [Cloud ▼]     ○ Verbindung  │
├──────────────────────────────┤
│ Wärmepumpe                   │
│ [Betriebszustand / Modus]    │
│ Zuletzt aktualisiert: …      │
├──────────────┬───────────────┤
│ Außentemp.   │ Vorlauf / RL  │
│    — °C      │  — / — °C     │
├──────────────┼───────────────┤
│ Warmwasser   │ Sollwert      │
│    — °C      │    — °C       │
├──────────────┴───────────────┤
│ Weitere Statuswerte / Fehler │
│      [↻ Aktualisieren]       │
│ [○ Live aus]  [Live ein]     │
│                              │
│ [  Parameter / Einstellungen]│
├──────────────────────────────┤
│ Übersicht | Parameter | Mehr │
└──────────────────────────────┘
```

`—` bedeutet hier **noch kein Messwert**. Nur vom Gerät/Transport unterstützte Werte anzeigen; keine erfundenen Werte oder unbestätigten Namen. Parameterbutton ist ohne Scrollen erreichbar, wenn Platz vorhanden.

## Beispiel: Desktop

```text
┌───────────────┬──────────────────────────────────────────┐
│ FoxAir        │ GL9    [Transport ▼] [Live] [Aktualisieren]│
│ Übersicht     ├──────────────────────────────────────────┤
│ Parameter     │ Zustand / Betriebsart / Fehlermeldungen │
│ Favoriten     ├─────────────┬──────────────┬─────────────┤
│ App-Einstellung│ Temperaturen│ Sollwerte   │ Sonst. Werte│
│               ├─────────────┴──────────────┴─────────────┤
│               │ [ Parameter / Einstellungen öffnen ]    │
└───────────────┴──────────────────────────────────────────┘
```

Desktop: Seitenmenü, Kennzahlenkarten, Statusdetails. Mobil: stapelbare Karten, große Touch-Ziele, keine überbreiten Tabellen.

## Start-/Refresh-Verhalten

- **Erster Aufruf:** Gespeicherten Transport wiederherstellen, Anzeige mit Zeitstempel des letzten Snapshots füllen und **einmalig** aktuelle Übersichtswerte abfragen.
- **Local + Live AUS:** nur während dieses Snapshots oder gezielter Einzelabfragen eine ser2net-Verbindung öffnen; nach Ruhezeit schließen.
- **Local + Live EIN:** Server hält Socket während aktiver, durch Browser-Heartbeat bestätigter Live-Sitzung offen; bei Tabwechsel/Background/Timeout schließen.
- **Cloud:** HTTP bei Refresh, Live nur bei eingeschalteter Funktion. Bei Cloud keine lokale ser2net-Verbindung.
- **Keine Verbindung:** übersichtliche Fehlermeldung; letzter bekannter Wert bleibt nur als **veraltet** mit Datum sichtbar, nicht als aktuell.
- **Transportwechsel:** bestehende Live-Sitzung freigeben, Auswahl speichern, neue Quelle einmalig abrufen, keine automatische Cloud-Fallback-Steuerung.
- **Schreibvorgänge:** nur explizit im Parameterbereich, niemals durch bloßen Transportwechsel oder den Seitenaufruf.

## Parameterseite

- Volltext-/Code-/Nummernsuche (`D14`, `E17`, `1345`).
- Filter: Favoriten, Gruppen, lesbar/beschreibbar, lokal/Cloud, Engineering (separat aktivierbar).
- Einzelansicht: Code, Nummer, Name, Erklärung/Wissensquelle, aktuelle Verbindung, Rohwert, formatierter Wert, Einheit, Zeitpunkt, Grenzen, Lese-/Schreibrecht.
- Bei Schreiben: Änderungsdialog **alt → neu**, Validierung, tatsächlichen Transport anzeigen, Bestätigung; Rücklesebericht und klarer Fehler bei unsicherem Schreibstatus.
- Nicht unterstützte Transport-Register sichtbar markieren statt irreführend bearbeiten.

## App-Einstellungen

- Aktuell ausgewählte WP/Cloud-Gerät und Transport, je Browser behalten.
- Ser2net-Ziele nur durch Backend-Admin-Konfiguration, nicht frei im Browser editierbar.
- Live-Modus pro Verbindung, Timeout-/Aktualisierungsintervalle und gegebenenfalls Anzeigeoptionen.
- Diagnoseanzeige: Socket-Status (geschlossen/verbunden/belegt/Fehler), letzter erfolgreicher Lesezeitpunkt.

## Mobile PWA

- `manifest.webmanifest`, passende Icons, `display: standalone`, `viewport-fit=cover`, Safe-Area-Abstände.
- Keine Offline-Queue für Steuereingriffe; offline ist Lesen aus gecachten Ansichten erlaubt, mit eindeutiger Stale-Warnung.
- Telefonrotation und Desktop-Fenstergrößen testen.
