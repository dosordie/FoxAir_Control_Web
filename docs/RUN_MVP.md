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
