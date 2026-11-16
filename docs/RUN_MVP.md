# Erste lauffähige Version (MVP 0.1)

**Stand:** Vorab-Implementierung; nicht für produktive Steuerung freigegeben.
Die Smartphone-Startseite ist am *Layoutprinzip* von WarmLink orientiert: orangefarbene Wärmepumpenansicht, Messwerte, Sollwertbereich und Schnellzugriffe. Keine kopierten Markenbilder oder App-Assets.

## Was bereits funktioniert

- Responsive Dashboard auf iPhone und Desktop inkl. installierbarem PWA-Manifest
- Navigieren zu Parameterbrowser und App-Einstellungen
- Persistente Transportwahl **pro Browser** (localStorage)
- Haupt- und Displayregisterdefinitionen sowie Knowledge aus geprüftem FoxAir_Control-Snapshot
- Suche nach Parameter-Code, Nummer oder Name, inklusive Registerdetails
- PHNIX-Cloud: *read-only* über Linked-Go Cloud-API nach manueller serverseitiger Konfiguration
- Standard-Modbus: standardmäßig **deaktiviert**; nur bei ausdrücklicher administrativer Freigabe über FOXAIR_ENABLE_STANDARD_MODBUS=1; falls aktiviert, on demand über ser2net
- Mehrere gleichzeitige Requests zum selben ser2net-Endpunkt sind im Backend serialisiert
- Keine simulierten Livewerte. Nicht unterstützte Transportwege liefern einen klaren Status statt erfundener Messwerte

## Was ausdrücklich noch nicht fertig ist

- PHNIX-Cloud: Schreibzugriffe, Geräteauswahl-UI und weitergehende Registerauflösung; gezielter **Lesezugriff** ist bereits implementiert
- LTE-DTU-/Warmlink-Modbus-Protokollanbindung (nächste Priorität) und Display-Modbus (später)
- Live-Lease-Manager / zyklische Abfrage
- Schreibfunktionen für beliebige Register, Sollwert +/−, Betriebsarten oder SG-Ready
- Verteilte Authentifizierung/MFA, vollständige Härtung für öffentliche Zugriffe
- Änderungshistorie, Mehrbenutzerbetrieb und automatisches Cloud-Mapping-Sync

In der Oberfläche sind diese Funktionen entsprechend deaktiviert oder als „noch nicht verfügbar“ gekennzeichnet.

## Lokal testen (Entwicklungsumgebung)

Benötigt: Python 3.11+, Node.js 20+, npm.

Terminal 1:
~~~bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8081
~~~

Terminal 2:
~~~bash
cd frontend
npm install
npm run dev
~~~

Browser: \`http://127.0.0.1:5173/\`. Vite leitet \`/api\` lokal an \`127.0.0.1:8081\` weiter.

**Für den Live-Displaytest ohne Geräteverbindung:** Alle dynamischen Werte bleiben \`—\` und die App erklärt, warum. Der Registerbrowser funktioniert ohne Hardware.

## Cloud-Livewerte, Gruppen und geschützte Web-Einstellungen

Die Anzeige aktualisiert bei ausgewählter Cloudverbindung automatisch alle **30 Sekunden**, aber nur solange die Übersichtsseite sichtbar ist. Beim Livepoll wird gemäß [FoxAir_Control Reverse-Engineering](https://github.com/dosordie/FoxAir_Control/blob/main/docs/warmlink_polling_and_readback.md) einmal `app_heartbeat=23205` über `app/device/control` ausgelöst, nach Erfolg ca. 1 Sekunde gewartet und anschließend `getDataByCode` für die Dashboard-Codes abgefragt. Beim ersten Snapshot und Einzelread wird **kein Heartbeat** ausgelöst. Der Server begrenzt Heartbeats zusätzlich auf mindestens 25 Sekunden Abstand. Das Intervall ist in **App-Einstellungen** zwischen 10 und 3600 Sekunden einstellbar. Keine automatischen Standard-Modbus-Abfragen.

**Wichtig:** Das neue Cloud-Liveverhalten ist aus FoxAir_Control abgeleitet und per Unit-Tests zu prüfen; es wurde für diese Web-App noch nicht an der realen Hardware verifiziert. Ein Heartbeat ist ein definiertes Cloud-Steuerkommando, das einen Telemetrie-Snapshot auslösen soll, kein allgemeiner Register-Schreibzugriff.

Die Parameterauswahl gruppiert Hauptregister aus `data/foxair_phnix_registers.json` nach `block` und gegebenenfalls bestätigtem Code-Präfix (H/P/T/D/E/R …). Für unzugeordnete Register bleiben getrennte Gruppen STATUS/DIAG/OTHER. Die Gruppennamen werden **nicht** frei aus Cloud-T-Codes erschlossen.

### Erstmalige Admin-Freigabe für Cloud-Webeinstellungen

Die bisherigen Cloud-Zugangsdaten können aus dem systemd-EnvironmentFile weiterverwendet werden. Um zusätzliche Einstellungen über die Weboberfläche zu verwalten, muss einmalig ein separates Admin-Passwort auf dem Server eingerichtet werden:

~~~bash
cd /opt/foxair-web/app
sudo python3 scripts/setup_web_admin.py
~~~

Das Skript fragt interaktiv nach einem **neuen, mindestens 12-stelligen Admin-Passwort**. Es legt nur für FoxAir eine lokale, zugriffsgeschützte Passwort-Hash-Datei an. Bereits konfigurierte Cloud-Zugangsdaten werden dadurch nicht geändert.

**Administration nur bei HTTPS oder Loopback:** Im Web-UI werden Benutzername, neues Passwort und die Gerätekennung nur über HTTPS oder einen per SSH auf localhost getunnelten Zugriff gespeichert. Ein unverschlüsselter LAN-Aufruf kann die Dashboardwerte lesen, aber weder Cloud-Einstellungen ändern noch die komplette Geräteliste abrufen. Für die spätere Verwendung des Reverse-Proxys müssen dessen HTTPS-Forwarded-Header **nur von der vertrauenswürdigen Proxy-Adresse** akzeptiert werden. Nicht unkontrolliert `--forwarded-allow-ips=*` verwenden.

- `GET /api/cloud/config` zeigt nur Boolean-Statusfelder, keine Zugangsdaten.
- `POST /api/cloud/config` ist mit Admin-Passwort gesichert; leere Felder behalten vorhandene Werte. Cloud-Passwort bleibt serverseitig.
- `POST /api/cloud/devices` fragt die Geräteliste des Accounts ab und liefert nach Administratorprüfung ausgewählte Geräte-/DTU-Metadaten. Gerätedaten inklusive Kennungen nur in dieser Admin-Antwort.
- `POST /api/cloud/device-status` fragt den Status des gespeicherten Geräts ab und gibt nur bekannte, nicht geheime Statusfelder zurück.

Die Webdaten werden im privaten Dienst-State als `cloud.json` (0600, Besitzer FoxAir-Dienstbenutzer) gespeichert, **nicht** im Git-Checkout. Ein Neustart ist beim Speichern nicht nötig; die nächste Cloud-Abfrage verwendet die neue Konfiguration.

### Branding

`frontend/public/foxye-logo.png` und `frontend/public/favicon.png` stammen unverändert aus `dosordie/FoxAir_Control/docs/FAQ/assets` (der offiziellen FoxAir_Control-FAQ-Seite).

## Git-basierte Installation ohne manuelles ZIP

Die GitHub-Actions-Pipeline führt Python-Tests und den Vue/Vite-Build aus. Nach erfolgreicher Prüfung veröffentlicht sie die fertig gebaute PWA automatisch in den **Git-Branch `web-dist`**. Dessen Datei `.build-source-sha` dokumentiert den passenden `main`-Commit.

Auf dem Zielsystem genügt danach:

~~~bash
cd /opt/foxair-web/app
sudo bash scripts/update.sh
~~~

Das Skript macht `git pull --ff-only origin main`, lädt den generierten Git-Branch, prüft dass Build und Quellcode **exakt denselben Commit** verwenden, packt die statischen Dateien ohne Node.js/ZIP in `frontend/dist` aus und aktualisiert Python-Pakete **nur bei geänderter requirements-Datei** in der eigenen FoxAir-venv. Wenn ein FoxAir-Dienst bereits läuft, startet es **ausschließlich diesen** neu.

Ein passender Build kann direkt nach einem Push noch fehlen. Dann beendet sich das Skript ohne Frontend-Austausch oder Dienstneustart mit einem Hinweis auf die noch laufende CI. Den Befehl nach erfolgreichem [Main-Build](https://github.com/dosordie/FoxAir_Control_Web/actions/workflows/ci.yml) erneut ausführen.

Erstinstallation des eigenen Beispieldienstes (nur bei der dokumentierten Beispiel-Pfadstruktur):

~~~bash
sudo bash scripts/install_service.sh
~~~

Der Dienst wird zunächst **nur lokal** auf `127.0.0.1:8081` gebunden. Für einen Windows-Browser kann man einen SSH-Tunnel zum lokalen Port einrichten. HTTP-Endpunkte dieser MVP-Version haben noch keine eigene Benutzer-Authentifizierung; kein offener LAN-/Internet-Port ohne zusätzlichen Zugriffsschutz.

Es ist nicht nötig, eine GitHub-Actions-ZIP-Datei manuell herunterzuladen oder Node/npm im produktiven Container zu installieren. Bestehende Dienste werden nicht verändert.

## Optional: Zugriff aus einem privaten LAN

Standardmäßig startet der Beispieldienst nur auf `127.0.0.1:8081`.
Für einen LAN-Test kann der Bind-Host mit einem **isolierten systemd-Drop-in** angepasst werden, ohne fremde Dienste oder den Repository-Code zu ändern:

~~~bash
cd /opt/foxair-web/app
sudo bash scripts/set_listen_address.sh <IP_DES_LINUX_SERVERS_IM_PRIVATEN_LAN>
~~~

Das Skript akzeptiert ausschließlich eine auf dem Server vorhandene IPv4-Adresse aus privaten RFC1918-Bereichen und startet nur den FoxAir-Dienst neu. Die Adresse wird ausschließlich lokal unter systemd konfiguriert und nicht ins Repository übernommen. Das Drop-in bleibt bei `git pull` und `scripts/update.sh` erhalten.

Zurück auf ausschließlich lokalen Zugriff:

~~~bash
sudo bash scripts/set_listen_address.sh --local
~~~

**Achtung:** Der MVP hat noch **keine eigene Anmeldung** und enthält Parameter- und Messwertinformationen. Ohne weitere Authentifizierung darf der Port nur aus einem vertrauenswürdigen, ausdrücklich freigegebenen Netzwerksegment erreichbar sein. Eine IP-Bindung ist **keine Firewall**. Zugriff durch Router/Firewall auf das benötigte LAN bzw. Administrationsnetz begrenzen; **keine WAN-Portfreigabe** einrichten.

## Cloud-Vollscan, aktuelle Parameterwerte und Logs

Die Web-App enthält einen **aus FoxAir_Control generierten Cloud-Katalog** mit aktuell 535 bekannten Cloud-Abfragecodes. Die Quellen werden im GitHub-Build von einem festgelegten Upstream-Commit übernommen, nicht auf dem Produktivserver live ausgeführt. `frontend/dist/cloud_catalog.json` wird zusammen mit der gebauten PWA installiert. Bei Änderungen an FoxAir_Control muss der gepinnte Quellcommit bewusst angepasst und geprüft werden.

- Nach dem ersten erfolgreichen Cloud-Dashboardabruf beginnt einmalig ein **asynchroner Vollscan**. Er liest in Batches von bis zu 50 Codes; explizit unzulässige/unsupported Codes werden eingegrenzt, echte HTTP-/Loginfehler stoppen den Scan ohne massenhaftes Wiederholen.
- Der Scan speichert nur Werte mit gültiger Antwort in einem pro Cloud-Konto getrennten **RAM-Cache**, keine Werte oder Gerätekennungen im Git. Nicht unterstützte Codes werden als ohne Wert gekennzeichnet.
- Spätere Dashboard-Livepolls lesen nur den bekannten, unterstützten Liveanteil und die Kernanzeigen. Statik-/Konfigurationscodes werden nicht im 30-Sekunden-Rhythmus erneut gelesen.
- Unter **Parameter → Modbus-Register** werden bestätigte Cloudwerte direkt in der Parameterliste mit Zeitstempel angezeigt; unter **Alle Cloud-Codes** stehen zusätzlich Cloud-only-Codes ohne behauptete Modbus-Zuordnung.
- Unter **App-Einstellungen → Cloud-Protokoll** erscheinen maximal 150 jüngste Prozessereignisse mit Zeitpunkt, Kategorie und Ergebnismengen. Keine Zugangsdaten, IDs, Tokens oder Cloud-Rohfehlermeldungen.
- Der Cache und das Log werden durch Neustart des FoxAir-Dienstes zurückgesetzt; dies ist noch **kein historisches Datenarchiv**.

### Vorhandene Cloud-E-Mail und Gerätekennung anzeigen

Die gespeicherte E-Mail und `deviceCode` werden **nicht** durch ungeschützte GET-Endpunkte ausgeliefert. In den App-Einstellungen zuerst das separate Administrationspasswort eingeben und **Aktuelle E-Mail und Gerätekennung anzeigen** auswählen. Danach werden beide Werte in den Bearbeitungsfeldern angezeigt, während das Cloud-Passwort verborgen bleibt. Die aktuelle Geräteübersicht kombiniert `deviceList` mit House-/Room-Ergebnissen analog zu FoxAir_Control.

### HTTPS-Reverse-Proxy für die Admin-Funktionen freigeben

Die Admin-API hat im Reverse-Proxy-Betrieb einen anderen TLS-Kontext als der Browser. Sie akzeptiert `X-Forwarded-Proto: https` **nur von einem explizit erlaubten Proxy-Endpunkt**. Andernfalls ist das Bearbeiten über einen HTTPS-Reverse-Proxy korrekt aus Sicherheitsgründen gesperrt.

Den internen **privaten IPv4-Absender des Reverse-Proxys** einmalig *nur auf dem Zielsystem* konfigurieren:

~~~bash
cd /opt/foxair-web/app
sudo bash scripts/set_trusted_proxy.sh <PRIVATER_PROXY_IPV4>
~~~

Die IP wird in einer **lokalen FoxAir-systemd-Drop-in-Datei** gespeichert und nicht in GitHub übertragen. Das Skript startet ausschließlich `foxair-web.service` neu.

Der Reverse Proxy muss mindestens den tatsächlichen Host und das externe Schema weitergeben:

~~~nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
~~~

Bei nicht-standardmäßigen HTTPS-Ports auch die richtige Host-/Port-Kombination weitergeben. Nicht sämtliche Absender vertrauen (`--forwarded-allow-ips='*'` vermeiden). HTTP-LAN-Clients dürfen die Header nicht fälschen und dadurch Admin-Zugriff erhalten.

**Hinweis:** Die Anwendung besitzt weiterhin keine vollständige Web-Benutzer-Authentifizierung. Der Adminschutz gilt nur für Kontokonfiguration und Geräteübersicht; reine Cloud-Telemetrie ist im freigegebenen Netz lesbar. Vor Zugriff aus dem Internet zusätzlichen Authentifizierungs-/Firewall-Schutz einrichten.

## PHNIX-Cloud als erste Live-Datenquelle

Die Web-App übernimmt für die erste Cloud-Lesestufe das bestätigte Protokoll aus FoxAir_Control: Login über `app/user/login`, anschließend `app/device/getDataByCode`. Es werden **ausschließlich** die bestätigten Dashboard-Codes `Power`, `ModeState`, `T04`, `T08`, `T39`, `T40`, `T41` und `R02` angefordert. Keine Cloud-Schreibbefehle.

**Einmalige Konfiguration (interaktive Konsole, kein Eintrag in Git):**

~~~bash
cd /opt/foxair-web/app
sudo python3 scripts/configure_cloud.py
~~~

Das Script fragt nach Benutzername, Passwort (verdeckt) und `deviceCode`. Es schreibt die Daten in eine **lokale** EnvironmentFile mit Berechtigung 0600 und fügt ausschließlich für den FoxAir-Dienst ein systemd-Drop-in hinzu. Keine Daten oder lokalen Hostnamen werden in GitHub gespeichert.

Nach dem Start der Anwendung:

~~~bash
curl -fsS "http://127.0.0.1:8081/api/transports"
curl -fsS "http://127.0.0.1:8081/api/dashboard?transport=cloud"
~~~

Die erste Ausgabe soll bei `cloud` ein `configured:true` zeigen. Bei der Dashboard-Abfrage enthält `metrics` echte Werte oder `null` für ununterstützte Cloud-Codes. **Nicht** aus `null` einen Messwert ableiten; bei Fehlermeldung Token/Anmeldedaten und Gerätestatus prüfen.

**Hinweis zur Cloud-Skalierung:** Angezeigte Cloud-Werte werden zunächst so übernommen, wie die API sie liefert; sie werden **nicht nochmals wie lokale Modbus-Rohwerte** durch 10 geteilt. Reale Gerätewerte vor Freigabe weiterer Berechnungen oder Schreibfunktionen prüfen.

### LTE-/Warmlink-Modbus danach

Beim LTE-Bus existiert bereits ein aktiver Master (DTU). Die bestehende FoxAir_Control-Dokumentation bestätigt Modbus RTU (am untersuchten Gerät 9600 8N1) und erfolgreiche aktive Einzelzugriffe, weist aber ausdrücklich auf fehlende Bus-Arbitrierung und Kollisionsrisiken hin. Deshalb **kein automatisches Aktivieren des generischen Standard-Modbus-Adapters** auf diesem Bus. Umsetzung zunächst mit passiver Beobachtung, dann begrenzten gezielten Abfragen mit Timeout-/Ruhephasen und exklusiver Queue.

## Optionaler erster Standard-Modbus-Test

Nur wenn ein dedizierter, bereits bestätigter Standard-Modbus-ser2net-Endpunkt existiert – **keine** LTE-/Display-Multi-Master-Schnittstelle dafür verwenden.

Die Gateway-Adresse ist **nur** in der Serverkonfiguration, niemals im Browser:

~~~bash
export FOXAIR_STANDARD_HOST="<MODBUS_HOST>"
export FOXAIR_STANDARD_PORT="4001"
export FOXAIR_STANDARD_SLAVE="99"
export FOXAIR_ENABLE_STANDARD_MODBUS="1"
uvicorn backend.main:app --host 127.0.0.1 --port 8081
~~~

Dann im Browser „Standard-Modbus“ auswählen. Beim Öffnen der Übersicht werden die bekannten Blöcke einzeln per FC03 gelesen. Bei jeder Aktion wird der TCP-Socket nur vorübergehend geöffnet und wieder geschlossen; noch **kein** dauerhaftes Live-Polling. IP, Port und Slave-ID sind zunächst individuell zu prüfen.

Die erste Implementierung ist absichtlich **read-only**: Kein HTTP-Endpunkt akzeptiert Registerschreibbefehle.

## Deployment

Die Anwendung kann neben vorhandenen Linux-Diensten betrieben werden, wenn Prozesse, Paketumgebungen, Konfiguration, Logs und Updates getrennt bleiben.

Generische Vorgaben: [DEPLOYMENT.md](DEPLOYMENT.md). Private Installationspfade, Netzwerkadressen, Host-/Containerinformationen und konkrete Ressourcenmessungen sind **nicht** Bestandteil dieses öffentlichen Projekts.

**Sicherheit:** Der erste MVP enthält noch keine eigene Benutzer-Authentifizierung. Vor Internetzugriff sind vorgeschaltete Authentifizierung, Zugriffsbeschränkung und Sicherheitsprüfung erforderlich. Das Frontend nach Möglichkeit außerhalb des Produktivsystems bauen.

## Registerpflege

Daten werden aus dem öffentlichen Quellrepo \`dosordie/FoxAir_Control\` zum geprüften Commit kopiert. Für spätere Aktualisierung:

~~~bash
python scripts/sync_registers.py --ref <40-Zeichen-Upstream-SHA>
git diff -- data/
~~~

**Erst nach Review committen.** Cloud-Mapping-Synchronisierung erfolgt in einer gesonderten Etappe; der Upstream-Katalog ist in \`data/upstream.json\` dokumentiert.

## Tests

~~~bash
python -m unittest discover -s backend/tests -v
cd frontend && npm install && npm run build
~~~

## Issue #6: Korrigierte Sensoren und Web-Update

Die Startseite verwendet Cloud **T01 (MAIN 2045)** als Wasser-Einlass/Rücklauf
und **T02 (MAIN 2046)** als Auslass/Vorlauf. Die bisher für diesen Zweck
fälschlich verwendeten **T40/T41** bleiben separat als Klimakreis-Codes
im Registerkatalog. Der betriebsabhängige Temperaturwert **2014** wird
bei plausibler Cloudantwort vor `R02` dargestellt; der R02-Basiswert bleibt
separat angezeigt. Ohne 2014 behauptet die Anzeige keine berechnete Korrektur.

Beim Offline-Fall werden bisherige Cloudwerte **nicht** als frisch markiert.
Es wird stattdessen ein zeitgestempelter Altwert angezeigt. Livewerte gelten
nach 300 Sekunden als `stale`; der private Persistenzcache wird nur
höchstens einmal pro Minute geschrieben. Neue Zugangsdaten werden in
einem anderen, zugriffsgeschützten lokalen Dateispeicher aufbewahrt.

### Nachrüstbarer Updateknopf

Nach dem gewöhnlichen `bash scripts/update.sh` einmal als root:

~~~bash
bash scripts/install_web_update.sh
~~~

Damit werden nur `foxair-web-update.path` und
`foxair-web-update.service` angelegt; andere Dienstkonfigurationen
werden nicht angefasst. Die Web-App löst nach erfolgreicher
Admin-Passwortprüfung über HTTPS nur einen lokalen, fest benannten
Dateitrigger aus. Das Update wird separat als systemd-Oneshot ausgeführt
und kann dessen Erfolg/Fehlschlag unter **Update-Status** anzeigen.

`systemctl status foxair-web-update.service` und
`journalctl -u foxair-web-update.service -n 50 --no-pager`
geben im Bedarfsfall die konkreten Updatefehler aus.

**Sicherheitsgrenze:** Keine Freigabe für beliebige Shellbefehle.
Der Update-Dienst prüft beim Installieren root-eigene, nicht gruppen-
oder weltweit beschreibbare Dateien im Quellcheckout und eine erlaubte
Git-Quelle. Der unprivilegierte Webdienst darf das ausführbare
`update.sh` nicht verändern. Der Git-Build muss weiterhin zur
jeweiligen `main`-Revision passen.

### Spezialdialoge (zunächst nur Anzeige)

Über **Schnellzugriff** erscheinen Wärmepumpe, AT-Kurve,
SG-Ready, M-/WP-Timer, Silent-Timer und Störungsübersicht.
Bekannte Cloudcodes werden aus dem im CI erzeugten Katalog übernommen.
Gezielte Read-Requests sind auf diese Codes und ein Mindestintervall
begrenzt. Die allgemeine Cloud-Abfrage und die reine Diagnose bleiben
weiterhin read-only. Schreibfunktionen benötigen eine separate
Security-/Readback-Implementierung.

