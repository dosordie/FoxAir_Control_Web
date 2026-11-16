# Erste lauffähige Version (MVP 0.1)

**Stand:** Vorab-Implementierung; nicht für produktive Steuerung freigegeben.
Die Smartphone-Startseite ist am *Layoutprinzip* von WarmLink orientiert: orangefarbene Wärmepumpenansicht, Messwerte, Sollwertbereich und Schnellzugriffe. Keine kopierten Markenbilder oder App-Assets.

## Was bereits funktioniert

- Responsive Dashboard auf iPhone und Desktop inkl. installierbarem PWA-Manifest
- Navigieren zu Parameterbrowser und App-Einstellungen
- Persistente Transportwahl **pro Browser** (localStorage)
- Haupt- und Displayregisterdefinitionen sowie Knowledge aus geprüftem FoxAir_Control-Snapshot
- Suche nach Parameter-Code, Nummer oder Name, inklusive Registerdetails
- Standard-Modbus: *read-only*, **on demand** via konfiguriertem ser2net (rohes RTU mit CRC über TCP), Socket wird nach Request geschlossen
- Mehrere gleichzeitige Requests zum selben ser2net-Endpunkt sind im Backend serialisiert
- Keine simulierten Livewerte. Nicht unterstützte Transportwege liefern einen klaren Status statt erfundener Messwerte

## Was ausdrücklich noch nicht fertig ist

- PHNIX-Cloud Login/Livewerte/Schreiben
- Display- und LTE-DTU-/Warmlink-Modbus-Protokollanbindung (Multi-Master)
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

## Optionaler erster Standard-Modbus-Test

Nur wenn ein dedizierter, bereits bestätigter Standard-Modbus-ser2net-Endpunkt existiert – **keine** LTE-/Display-Multi-Master-Schnittstelle dafür verwenden.

Die Gateway-Adresse ist **nur** in der Serverkonfiguration, niemals im Browser:

~~~bash
export FOXAIR_STANDARD_HOST="<MODBUS_HOST>"
export FOXAIR_STANDARD_PORT="4001"
export FOXAIR_STANDARD_SLAVE="99"
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
