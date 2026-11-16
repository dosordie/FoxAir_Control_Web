# Technische Spezifikation – FoxAir Control Web (v0-Plan)

**Status:** Entwurf zur Implementierung, noch keine produktive Hardwareanbindung.  
**Quellprojekt:** [dosordie/FoxAir_Control](https://github.com/dosordie/FoxAir_Control).  
**Zielplattform:** Linux-System oder Container mit eigenständigem Backend-Dienst hinter HTTPS-Reverse-Proxy. Allgemeine Hinweise: [DEPLOYMENT.md](DEPLOYMENT.md). Private Betriebsdaten werden nicht öffentlich dokumentiert.

## Ziel und Abgrenzung

Eine *eigenständige*, mobil- und desktopfähige PWA zur schnellen Kontrolle und Parametrierung der FoxAir/PHNIX-Wärmepumpe. Das Windows-Tool FoxAir_Control wird **weder zum Webdienst umgebaut noch für den Betrieb benötigt**. Stattdessen werden wiederverwendbare, GUI-freie Protokoll-/Registerteile aus FoxAir_Control übernommen oder als gemeinsam genutzte Core-Bibliothek extrahiert.

Die Startseite ist eine **WarmLink-artige Übersicht**, nicht der Registerbrowser. Von dort führt ein klarer Button zu **Parametern/Einstellungen**. Die App läuft für den privaten Eigengebrauch, die Architektur soll eine spätere Mehrbenutzervariante nicht verbauen.

## Architektur

```text
Safari PWA / Desktop Browser
    | HTTPS
    v
HTTPS-Reverse-Proxy mit Zugriffsschutz
    | internes HTTP (nur Nginx-LAN)
    v
FoxAir_Web (eigenständiger Backend-Dienst)
  - FastAPI: API, Auth/Sitzungen, Berechtigungen, Parametrierung
  - Vue 3/TypeScript: responsive Übersicht, Parameter, App-Einstellungen
  - Adapter Cloud (PHNIX/Linked-Go HTTPS)
  - Adapter local standard_modbus
  - Adapter local display_modbus
  - Adapter local warmlink_raw
  - Register-Resolver + Knowledge + Cloud-Mapping
  - ConnectionManager (pro ser2net-Endpunkt genau ein Besitzer)
    |                    |
    v                    v
PHNIX Cloud          TCP-zu-RS485 (ser2net)
```

Lokale Transportadapter sprechen **Modbus-RTU-Framing mit CRC über einen rohen TCP-Bytekanal** zu ser2net; dies ist **nicht** automatisch Modbus-TCP/MBAP. Die Core-Implementierung in FoxAir_Control kennt `WarmlinkSocketClient`, `ModbusSerialClient`, RTU-Parser und Frame-Builder. Ob sämtliche GUI-gekoppelten ReaderWorker ohne Änderungen nutzbar sind, wird getrennt geprüft.

## Vier logische Verbindungsarten

| Schlüssel | Bezeichnung | Besonderheit |
|---|---|---|
| `cloud` | PHNIX-Cloud | Credentials/Tokens nur serverseitig; separate Cloud-Code-Mappings |
| `standard_modbus` | Standard-Modbus | Direkte Mainboard-Register via ser2net |
| `display_modbus` | Display-Modbus | Am untersuchten Gerät 4800 8N1; Teilnehmer/Blockpakete beachten |
| `warmlink_raw` | Warmlink-/LTE-DTU-Modbus | Am untersuchten Gerät 9600 8N1; bestehender DTU-Master |

Die Parameter für IP/Port und serielle Eigenschaften werden im Backend konfiguriert, **nicht** als freie Socket-Ziele aus HTTP-Requests übernommen (SSRF-/Netzwerkschutz). Bei anderen Gerätemodellen können andere Parameter gelten. Gleichzeitige Web-Requests desselben Busendpunkts werden serialisiert. Kollisionen mit fremden Bus-Mastern sind dadurch **nicht** ausgeschlossen; Warmlink-/Displaybus besonders schonend bedienen.

## UI-/Navigationsvertrag

1. **Übersicht als Rootroute `/`:** Betriebszustand (an/aus/Modus), wichtige Temperaturen, relevante Leistungs-/Statuswerte, aktuelle Meldungen; nur **verifizierte, vorhandene** Register/Werte zeigen. Werte tragen Erfassungszeit und Quellenangabe; bei fehlender Verbindung `—`/„nicht verfügbar“ statt Demo-Daten.
2. Klarer Button **„Parameter / Einstellungen“** führt zu `/parameters`: Suche nach Code, Registeradresse und Namen; Gruppen; Favoriten; Wert, Einheit, min/max, Beschreibung, RO/RW, Quelle; Lese- und Schreibfunktion mit Bestätigung.
3. Separate **„App-Einstellungen“** `/settings`: lokale ser2net-Ziele, Cloud-Geräteauswahl, Live-Modus, Pollintervall, Sicherheits- und Anzeigefunktionen. Parametrierung der Wärmepumpe und App-Konfiguration nicht verwechseln.
4. **Transportwahl** jederzeit erkennbar und bedienbar; je nach Transport nicht verfügbare Register klar kennzeichnen.
5. Responsive Breakpoints: iPhone einspaltige Karten, gut bedienbare Buttons und kompakte Bottom-Navigation; Desktop nutzt mehrspaltige Kennzahlen, Seitenmenü und Tabellen/Detailansicht.
6. Startbildschirm über Safari/Home-Screen installierbar (Manifest, Icons, Service Worker nur für statische Assets; **keine Offline-Writes**).

## Letzte Verbindung merken

- Pro Browser/Endgerät und ausgewählter Wärmepumpe den letzten **Transporttyp** speichern (`localStorage`, z. B. `foxair.selectedTransport:<deviceKey>`).
- Beim erneuten Öffnen die Auswahl vorauswählen. **Nicht** blind lokale TCP-Sockets öffnen und **keine** Schreibaktion wiederholen.
- Favoriten/Anzeigekonfiguration können zunächst ebenfalls lokal im Browser gespeichert werden; spätere serverseitige Nutzerprofile sind möglich.
- Verbindungstyp und Zustand sind getrennt: `selected` ≠ `connected`. Beim Neustart beginnt lokale Verbindung grundsätzlich als `disconnected`, bis eine echte Anfrage oder ein aktiver Livemodus sie benötigt.
- Cloud-Credentials/Token **niemals** in localStorage/Frontend oder PWA-Cache.

## Ser2net-Verbindungslebenszyklus

**Betriebsarten je Verbindung:** `on_demand` (Default) und `live` (explizit eingeschaltet).

### On-Demand (keine Livewerte)

1. Beim Öffnen der Übersicht wird bei ausgewähltem Transport **einmalig ein aktueller Snapshot angefragt** (sofort hilfreiche Startseite). Danach kein stilles zyklisches Polling. Falls nicht erreichbar, bleibt ein vorhandener Cache sichtbar, mit Zeitstempel und Stale-Kennzeichnung.
2. Bei „Aktualisieren“, gezieltem Registerread oder bestätigtem Write nimmt das Backend ein exklusives Bus-Lease.
3. Ser2net-TCP öffnen, nur die benötigten Telegramme senden/empfangen, Timeout-/CRC-/Antwortzuordnung beachten.
4. Operation abschließen, Wert ggf. rücklesen; nach kurzer konfigurierbarer Ruhezeit (Vorschlag: 3–5 s) TCP schließen; bei Abbruch/Fehler immer freigeben.
5. Kein automatisches Write-Retry; bei unsicherem Ausgang explizit „Schreibstatus unbekannt – bitte rücklesen“.

### Live-Modus (Dashboard sichtbar + Live ausdrücklich aktiviert)

1. Backend hält **eine** Verbindung je tatsächlichem Bus-Endpunkt; alle Browser-Clients teilen sie und verwenden eine gemeinsame Queue.
2. Browser meldet regelmäßige Heartbeats / Live-Leases (z. B. alle 10 s), nur solange Ansicht sichtbar und Live aktiviert.
3. Nach `visibilitychange` hidden, explizitem Live-Aus, Tab-/Transportwechsel: Live-Lease freigeben; **kein Verlassen auf `beforeunload` allein**.
4. Wenn Heartbeats ausbleiben, verfallen Leases serverseitig (z. B. 25–30 s). Ohne Lease und ohne ausstehenden Auftrag Socket schließen.
5. Serverneustart verliert nur Socket-/Lease-Zustand; gespeicherte Transportpräferenz bleibt erhalten.
6. Polls priorisieren/fairness gegenüber manuellen Lese- und vor allem Schreibvorgängen; keine unkontrolliert schnellen Busanfragen.
7. **Display-/LTE-Bus:** passiv mitgehörte Frames wenn möglich als Livequelle nutzen, gezielte aktive Requests nur soweit nach bestehendem FoxAir_Control-Protokoll bestätigt und konfiguriert.
8. Wird der Socket von ser2net exklusiv verwaltet, Status „Bus belegt“ statt konkurrierenden Master zu erzwingen.

**Cloud:** HTTP-Requests bei Bedarf; kein ser2net-Socket. Optional periodische Cloudwerte nur bei aktivem Live-Modus; bekannte Heartbeat-/Pollingsemantik aus FoxAir_Control beachten.

## Register-Single-Source-of-Truth

Aus FoxAir_Control übernehmen (separate, reproduzierbar synchronisierte lokale Snapshots):

- `data/foxair_phnix_registers.json` (Hauptregister)
- `data/foxair_phnix_display_registers.json` (Display-spezifisch)
- `data/foxair_phnix_knowledge.json` (Zusatzwissen)
- bestätigte Cloud-Codes, Schreibfreigaben, Zuordnungs-/Wertkonvertierungslogik aus `cloud/...`.

**Keine unabhängige manuelle Registerliste in FoxAir_Control_Web.** Empfohlen: GitHub Action erkennt Upstream-Änderungen und erstellt nach JSON-/Mapping-Validierung einen **Review-PR** mit Versions-/SHA-Provenienz. Deployment nutzt geprüften Snapshot, lädt zur Laufzeit nicht ungesichert immer `main` herunter. In einer zweiten Phase ist ein geteilter, GUI-unabhängiger Python-Core möglich.

Ein Register hat je Transport **getrennte** Capability: lokal read/write nach Definition/Protokoll, Cloud nur nach geprüftem Cloud-Code-Mapping/Write-Allow. Kein automatisches Mapping aus bloß ähnlichen Namen, keine unbekannten/virtuellen T-Codes als Cloud-Query.

## Sicherheits- und Write-Regeln

- Zugriff ausschließlich über HTTPS-Reverse-Proxy mit belastbarer Nutzer-Authentifizierung (vorzugsweise MFA). Backend nicht direkt im WAN exponieren.
- Zugangsdaten/Tokens ausschließlich im Backend (Dateiberechtigungen/Secret-Storage); nicht loggen, nicht in Cache oder browserseitige Speicherung.
- Für lokale ser2net-Gateways feste Allowlist/Serverkonfiguration; API darf keine beliebigen Zielhosts oder Ports akzeptieren.
- Reads nur für zulässige registrierte Geräte/Bustypen, sichere Timeouts/Request-Limits.
- Writes: transportabhängige Berechtigung, Wertebereich, Skalierung und Typ prüfen; alter und neuer Wert anzeigen; vor Senden bestätigen; wenn möglich nachlesen und Ergebnis transparent kennzeichnen.
- Spezial-/Engineering-Register standardmäßig ausgeblendet, separater Warn-/Freigabemodus; keine pauschale Freigabe nur aufgrund 1xxx/2xxx.
- Kein stiller Wechsel zu Cloud, wenn lokaler Transport nicht erreichbar ist.
- Kollisionsrisiko auf RS485 mit aktivem DTU/Display explizit dokumentieren und tatsächliche Hardware vor Write-Freigabe testen.

## Minimaler Backend-Vertrag (Entwurf)

```text
GET     /api/health
GET     /api/transports
GET     /api/devices
GET     /api/dashboard?device=...&transport=...
GET     /api/registers?query=...&transport=...
POST    /api/registers/read          {device, transport, registers:[...]}
POST    /api/registers/write         {device, transport, register, value, confirm:true}
POST    /api/live/leases             {device, transport}
POST    /api/live/leases/{id}/ping
DELETE  /api/live/leases/{id}
```

Antworten enthalten `source`, `timestamp`, `quality` (`fresh`/`stale`/`unavailable`), `raw_value`, `formatted_value`, `unit`, `read_allowed`, `write_allowed` und gegebenenfalls Fehlermeldung. Weder Werte noch Feature-Verfügbarkeit erfinden.

## Akzeptanzkriterien für den ersten funktionsfähigen Stand

- iPhone und Desktop öffnen dieselbe, responsive Übersicht; „Parameter / Einstellungen“ funktioniert.
- Transportwechsel wird nach Neuladen pro Browser wiederhergestellt.
- Ohne Live-Modus und ohne Lese-/Schreibauftrag bleibt **kein** TCP-Socket zu ser2net offen.
- Ein einzelner Read öffnet Socket bedarfsgesteuert und schließt ihn danach zuverlässig.
- Live einschalten hält erforderliche Verbindung offen; abschalten und verlorener Browser-Heartbeat führen nach kurzer Frist zum Schließen.
- Zwei parallele Browser können keine konkurrierenden Modbus-Aufträge zum selben Bus absenden.
- Werte sind als Live/veraltet/nicht verfügbar erkennbar; keine erfundenen Beispielwerte im Produktivmodus.
- Registerdaten werden aus FoxAir_Control reproduzierbar synchronisiert; Cloud-Write nur bei bestätigtem Mapping.
- Unit-Tests für ConnectionManager, Lease-Timeout, Ser2net-Lock, Auswahlpersistenz und Schreibfreigaben; Hardwaretests getrennt/markiert.

## Nicht Teil des ersten Releases

Firmwareupdate, Raw-Capture, permanenter Logger, vollständige Replik des Windows-Diagnosetools, öffentlicher Multi-Tenant-Betrieb.

## Ergänzung: Cloud-Live-Web-App

- Default Cloud-Livepoll **30 s** bei sichtbarer Übersichtsseite; 10–3600 s konfigurierbar, gespeicherter Wert im jeweiligen Browser.
- Heartbeat-Auslösung ausschließlich beim Livepoll, nicht beim ersten Abruf oder einem einzelnen Registerread. Payload `app_heartbeat=23205` ohne `appId`, nach bestätigtem Erfolg ca. 1 s Ruhezeit; serverseitig auf min. 25 s begrenzt.
- Ohne sichtbare Webseite **keine zyklischen Polls**. Source-Transportwechsel verwirft die laufende Timerplanung.
- Web-Konfiguration mit eigenem Admin-Passwort, Transport nur über HTTPS/Loopback, nur selektierte Geräteinformationen. Backend-Passwörter nie über GET oder im Frontend abfragen.
- Parametergruppen aus dem Hauptregisterkatalog `block`, bei fehlendem Block aus einem überprüfbaren Code-Präfix. Status-/Diagnosegruppen bleiben eigenständig.
- Logo und Favicon aus der FoxAir_Control-FAQ als lokale statische Assets eingebunden.
