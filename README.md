# FoxAir Control Web

Responsive Web-App / PWA für FoxAir-/PHNIX-Wärmepumpen. Ein **eigenständiges Projekt**, das das Windows-Diagnosetool [FoxAir_Control](https://github.com/dosordie/FoxAir_Control) nicht ersetzen und nicht im Dauerbetrieb benötigen soll.

## MVP 0.1

- WarmLink-inspirierte **Übersichtsseite** für iPhone und Desktop mit Wärmepumpenillustration, Betriebszustand, Temperaturen, Durchfluss und Sollwertanzeige.
- **Cloud-Autorefresh** standardmäßig alle 30 Sekunden, ausschließlich bei sichtbarer Startseite. Bestätigter `app_heartbeat=23205` vor Liveabruf, ca. 1 Sekunde Settle, kein automatischer Heartbeat bei Einzelreads.
- **Cloud-Kontoverwaltung über die Weboberfläche**: Benutzer, Passwort und Geräteauswahl mit eigenem Admin-Passwort geschützt. Nur über HTTPS/Loopback. Cloud-Geräteliste und Statusinformationen.
- Registergruppen wie H/P/T/D/E/R aus der FoxAir_Control-JSON-Datenbank, ohne separate manuelle Pflege.
- Original-Logo und Favicon aus der FoxAir_Control-FAQ übernommen.
- **Parameter / Einstellungen** per Button erreichbar: Suchfunktion nach Code/Registernummer/Name, Details, einzelne Reads.
- Letzter Transport pro Browser gespeichert.
- FoxAir_Control-Registerdatenbank als überprüfter Snapshot ohne parallele manuelle Pflege.
- **Cloud read-only**: PHNIX/Linked-Go mit serverseitig hinterlegten Zugangsdaten und gezielt freigegebenen Dashboard-Codes.
- **LTE-/Warmlink-Modbus hat als Nächstes Priorität**; vorerst noch gesperrt wegen vorhandener DTU als Bus-Master.
- Standard-Modbus ist **standardmäßig deaktiviert** und wird nicht für automatische Abfragen genutzt (etwa wenn ein anderer Dienst den Bus bereits belegt).
- FastAPI + Vue 3/TypeScript/Vite und PWA-Manifest.
- GitHub Actions prüfen Python-Backend und Frontend-Build.

**Grenze:** Cloud-Lesezugriff und Live-Herzschlag sind implementiert, der neue Live-Ablauf muss noch am realen Gerät verifiziert werden. LTE-/Display-Modbus, Live-Leases, Sollwertschreiben und alle schreibenden Parameterfunktionen sind noch nicht implementiert. Die angezeigten `—` sind echte *fehlende* Werte, keine Simulationen.

**Sicherheit:** Die erste Implementierung hat noch **keine eigene Authentifizierung**. Nicht ohne Nginx-Zugriffsschutz/MFA, Firewallbegrenzung und Abschluss der Sicherheitsprüfung ins Internet stellen.

### Installation und Updates über Git (kein Node.js auf dem Server)

GitHub Actions baut die Weboberfläche automatisch in einen separaten Branch `web-dist`. Die Aktualisierung aus einem bestehenden Checkout auf `main` erfolgt mit **einem Kommando**:

```bash
cd /opt/foxair-web/app
sudo bash scripts/update.sh
```

Beim ersten Mal zusätzlich `sudo bash scripts/install_service.sh` (Beispiel für diesen Installationspfad). Beide Anwendungen werden separat verwaltet; der Beispiel-Dienst bindet zunächst nur an `127.0.0.1:8081`. **Keinen ungeschützten Zugriff ins Internet erlauben.** Ausführlich: [RUN_MVP.md](docs/RUN_MVP.md).

### PHNIX Cloud konfigurieren (read-only)

Die ursprüngliche CLI-Konfiguration wird weiterhin unterstützt. Für die **Web-Konfiguration** zuerst einmalig lokal als root `python3 scripts/setup_web_admin.py` aufrufen und ein separates Admin-Passwort festlegen. Anschließend über HTTPS oder einen SSH-Tunnel zur App → **App-Einstellungen** → **Cloud-Zugang & Geräte**. Im gewöhnlichen unverschlüsselten LAN bleibt das Speichern absichtlich gesperrt. Der neue Webspeicher liegt außerhalb von Git und besitzt restriktive Dateiberechtigungen.



Auf dem Zielsystem mit interaktiver Konsole einmalig `sudo python3 scripts/configure_cloud.py` ausführen. Das Skript fragt Benutzername, Passwort und Gerätecode ab, speichert sie **nur lokal** in einer rootgeschützten systemd-EnvironmentFile und startet ausschließlich den FoxAir-Dienst neu. **Keine Geheimnisse im Repository hinterlegen.**

Abfragen funktionieren danach auf der Übersicht mit Transport `PHNIX Cloud` sowie per `GET /api/dashboard?transport=cloud`.

**Sicherheitsgrenze:** Der MVP hat noch keine eigene Web-Anmeldung. Cloud-Konfiguration und Messwert-API daher nicht aus ungeschützten Netzen zugänglich machen; vor Internetfreigabe Authentifizierung und Firewall einrichten.

### LAN-Zugriff auf den Testdienst

Der Dienst bindet standardmäßig an `127.0.0.1`. Für einen privaten LAN-Test kann er über `scripts/set_listen_address.sh <PRIVATE_LAN_IP>` ausschließlich an die konfigurierte LAN-Adresse gebunden werden. Diese Einstellung bleibt bei Updates erhalten. **Nur in vertrauenswürdigen Netzen verwenden**, da der MVP noch keine eigene Anmeldung hat. Details: [RUN_MVP.md](docs/RUN_MVP.md).

### Schnellstart zum lokalen Test

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8081
```

In einem zweiten Terminal:

```bash
cd frontend
npm install
npm run dev
```

Dann `http://127.0.0.1:5173/` öffnen. Ohne ser2net-Konfiguration ist die Benutzeroberfläche inklusive Registerbrowser sichtbar, aber es werden keine Livewerte vorgetäuscht.

Alle Details: [MVP-Test und Betrieb](docs/RUN_MVP.md), [Architektur](docs/ARCHITECTURE.md), [UX](docs/UX.md), [Allgemeines Deployment](docs/DEPLOYMENT.md).

## Lizenz

Vor einer Veröffentlichung/Kopplung der Quellmodule ist die widersprüchliche Lizenzangabe des Upstream-Projekts (README vs. LICENSE) zu klären. Die Quellcode-Synchronisierung erfordert einen geprüften Upstream-Commit.

## Issue #6 – Registeransicht, Livewerte und Spezialdialoge

Der Startbildschirm verwendet die generischen Cloud-Sensoren **T01/T02**
für Rücklauf/Vorlauf, nicht die separaten Klima-Zonen T40/T41. Für den
betriebsabhängigen Sollwert wird bevorzugt **2014** verwendet, wenn sein
Wert plausibel ist; ansonsten wird **R02 nur ausdrücklich als Basiswert**
angezeigt. Ein unbestätigter Offset wird nicht künstlich addiert.

Die iPhone-Parametergruppen werden innerhalb ihrer eigenen Karte horizontal
gescrollt. Die Ventilatorgrafik dreht sich nur bei frisch gemeldetem
Anlagenstatus `Ein`, niemals aufgrund einer zwischengespeicherten Altinformation.
Unter der Dashboardübersicht gibt es eine aufklappbare Register-Schnellansicht
mit den zuletzt bekannten Cloudwerten.

Die zuletzt gültigen Cloudwerte werden in einer **privaten lokalen Cachedatei**
gespeichert. Bei Ausfällen bleiben sie als **veraltet** sichtbar; die
Verbindungsanzeige bleibt offline und führt das Originaldatum weiter.
Ohne erfolgreichen Aktualisierungskontakt werden Livewerte nach **5 Minuten**
als `stale` gekennzeichnet. Schreibvorgänge und Passwortdaten sind nicht
Teil dieses Caches.

Die Spezialdialoge **Wärmepumpe, AT-Kurve, SG-Ready, Zeitprogramme,
Ruhemodus und Störungen** bieten jeweils einen gezielten Cloud-Leseaufruf,
die bestätigten Codebezeichnungen und Ablesewerte. Aktuell sind **alle
Dialoge bewusst read-only**. Eine später freizugebende Cloud-Schreibfunktion
benötigt eigene Wertvalidierung, ausdrückliche Bedienbestätigung, Quittierung,
Readback und Sperrlogik.

### Web-Git-Update (optionale Einmalinstallation)

Die Weboberfläche darf aufgrund ihrer Diensthärtung keinen Systembefehl mit
höheren Privilegien ausführen. Deshalb wird der Updateknopf durch ein
**separates systemd Path/Oneshot-Paar** realisiert: ein authentifizierter
HTTPS-Aufruf erstellt nur einen fest kodierten Trigger. Der root-eigene
Hilfsdienst ruft ausschließlich das bekannte `scripts/update.sh` auf;
der Code-/Frontend-Revisionsabgleich schützt vor nicht passenden Builds.

Einmalig im bestehenden FoxAir-Checkout als root:

~~~bash
cd /opt/foxair-web/app
bash scripts/update.sh
bash scripts/install_web_update.sh
~~~

Danach **App-Einstellungen → Cloud-Zugang & Geräte**:
Web-Administrationspasswort eingeben und unter
**App-Einstellungen → FoxAir-Web aktualisieren** Versionen prüfen und
ein Update anfordern. Der Nutzer sieht jeweils installierten Git-Commit,
aktiven Web-Build und den Stand von GitHub `main`. Da der FoxAir-Dienst
beim Update neu gestartet wird, ist ein kurzer Verbindungsabbruch normal.
Die Anforderung ist **noch keine Erfolgsmeldung**; nach erneutem Laden
des Browserfensters den aktiven Web-Build mit `main` vergleichen.

Die Einrichtung kontrolliert Besitzer/Berechtigungen des Git-Checkouts und
erlaubt ausschließlich den festgelegten Projekt-Ursprung. Sie verändert
keine anderen systemd-Dienste. Es gibt **keinen** Shell-Zugriff, frei wählbare
Kommandos oder `sudo`-Freigaben aus der Web-App.

