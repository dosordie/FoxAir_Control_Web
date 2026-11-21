# FoxAir Control Web installieren

> **Beta:** Geräte- und Verbindungsunterstützung werden noch erweitert. Zuerst Messwerte prüfen und erst anschließend bewusst Parameter ändern.

[Zurück zur Übersicht](../README.md)

## Voraussetzungen

Ein Linux-Server oder Container mit **systemd**, Git, Python 3 und Virtualenv-Unterstützung, Internetzugriff sowie sudo-/Root-Zugriff für die Einrichtung. Die CI prüft mit Python 3.12. **Node.js wird auf dem Server nicht benötigt.**

Die Skripte erwarten `/opt/foxair-web/app` als Installationspfad. Andere Pfade erfordern angepasste Dienstdateien und Hilfsskripte. Bei einer bestehenden Installation zuerst [Updates](#updates) und [Release-Migration](RELEASES.md) lesen; vorhandene Konten und Konfigurationen erhalten.

**Aktueller Entwicklungsstand:** `work` ist für die Test-VM vorgesehen, `main` bleibt Stable. Noch kein `v0.1.0` veröffentlicht. Vor Work-Updates den erfolgreichen Build auf der [Actions-Seite](https://github.com/dosordie/FoxAir_Control_Web/actions) abwarten; das passende Frontend liegt in `web-dist-work`.

## 1. Frische Linux-Testinstallation auf work

Auf Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ca-certificates curl
sudo install -d /opt/foxair-web
sudo git clone --branch work https://github.com/dosordie/FoxAir_Control_Web.git /opt/foxair-web/app
sudo python3 -m venv /opt/foxair-web/venv
cd /opt/foxair-web/app
sudo bash scripts/update-work.sh
sudo bash scripts/install_service.sh
sudo systemctl enable foxair-web.service
```

Der Work-Helfer installiert Python-Pakete in die eigene Umgebung und übernimmt das passende Frontend. Der Dienst läuft unter `foxair-web` und lauscht zunächst **nur auf `127.0.0.1:8081`**.

Kontrolle:

```bash
curl -fsS http://127.0.0.1:8081/api/health
sudo systemctl status foxair-web.service --no-pager
```

Die Gesundheitsprüfung sollte unter anderem `"ok": true` zurückgeben.

## 2. Sichere GUI-Ersteinrichtung

Der neue Dienst erhält ein eigenes privates State-Verzeichnis. Bei bestehenden Units
und deren Konfiguration wird nichts überschrieben. Frische Instanzen erzeugen einen
zufälligen einmaligen Einrichtungscode; den Code auf dem Server abrufen:

```bash
cd /opt/foxair-web/app
sudo -u foxair-web /opt/foxair-web/venv/bin/python -m backend.setup
```

Bei abweichendem `FOXAIR_STATE_DIR` dieselbe Umgebung wie der Dienst verwenden.
Code anschließend über HTTPS oder den lokalen SSH-Tunnel zusammen mit einem neuen,
mindestens zwölf Zeichen langen Passwort in der Ersteinrichtungs-GUI eingeben.
Bis dahin sind die übrigen APIs blockiert. Der Code wird danach ungültig; normal als
`admin` anmelden. Bestehende Konten und Sitzungen werden nicht zurückgesetzt.
Lokale administrative Passwort-Recovery ist ein separater bewusster Vorgang;
keine State-Dateien pauschal löschen.

## 3. Oberfläche öffnen

Für den ersten Zugriff auf dem **eigenen Computer** einen SSH-Tunnel öffnen. Vor dem Ausführen die Platzhalter `<SSH_USER>` und `<SERVER_HOST>` ersetzen:

```bash
ssh -N -L 8081:127.0.0.1:8081 <SSH_USER>@<SERVER_HOST>
```

Das Terminal geöffnet lassen und im Browser `http://127.0.0.1:8081/` aufrufen. Der lokale Loopback-Zugriff kann für die Administration verwendet werden.

Für den regulären Zugriff am iPhone einen HTTPS-Reverse-Proxy einrichten. **Die lokale Admin-Anmeldung schützt nicht sämtliche lesenden APIs.** Vor einer Internetfreigabe ist deshalb zusätzlich ein vollständiger Zugriffsschutz erforderlich, etwa Nginx mit Authelia.

Läuft der Proxy auf einem anderen Rechner, muss FoxAir an einer erreichbaren privaten LAN-Adresse lauschen. Auf dem Server, mit ersetzten Platzhaltern:

```bash
cd /opt/foxair-web/app
sudo bash scripts/set_listen_address.sh <PRIVATE_LAN_IP>
sudo bash scripts/set_trusted_proxy.sh <PRIVATE_PROXY_IP>
```

Nur die tatsächliche einzelne Proxy-IP als vertrauenswürdig eintragen. Der Proxy muss `X-Forwarded-Proto` passend setzen. Unverschlüsseltes LAN-HTTP ist nicht für die Web-Administration vorgesehen. Weitere Hinweise: [Deployment](DEPLOYMENT.md).

## 4. Verbindung einrichten

1. Oben rechts als **Administrator** anmelden.
2. **Einstellungen → Verbindungseinstellungen** öffnen.
3. Unter **Cloud-Zugang & Geräte** die Zugangsdaten hinterlegen, Geräte laden und das passende Gerät wählen. Alternativ unter **Lokaler LTE-Bus** die eigene IP-Adresse und den TCP-Port eintragen, Verbindungsdauer wählen und den Anschluss aktivieren.
4. Zur **Übersicht** wechseln, die gewünschte Verbindung auswählen und Messwerte sowie Zeitstempel kontrollieren.

Zuletzt bekannte Werte können von einer anderen Quelle stammen. Die Parameterdetails zeigen Quelle und Zeitstempel. Ohne eingerichtete Verbindung gibt es keine simulierten Livewerte.

Standard- und Display-Modbus lassen sich ebenfalls unter **Verbindungseinstellungen** einrichten. Beide sind standardmäßig deaktiviert. Display-Modbus empfängt passiv; ausschließlich die separate Spezialfunktion fordert einen Parameter-Snapshot an. Vor dem Aktivieren immer die Busbelegung klären. Details: [Lokale Modbus-Anschlüsse](LOCAL_MODBUS.md).

**iPhone:** Die HTTPS-Adresse in Safari öffnen und über das Teilen-Menü **„Zum Home-Bildschirm“** hinzufügen. Messwerte und Schreibaufträge benötigen weiterhin die Serververbindung. Nach Updates die Homescreen-App gegebenenfalls vollständig schließen und erneut öffnen.

## Updates

**Test-VM auf work:** Nach grünem Build im bestehenden Checkout als root:

```bash
cd /opt/foxair-web/app
sudo bash scripts/update-work.sh
```

Der Helfer prüft den Quell-/Frontend-SHA-Abgleich vor der Installation und aktualisiert
Code, venv und Build zusammen. Ein eigenes `git pull --ff-only origin work` bleibt
möglich, aktualisiert aber allein kein Frontend: danach denselben Helfer vor dem
Dienstneustart ausführen. Bei noch fehlendem CI-Build später erneut versuchen.
Scheitert die Installation nach dem Anhalten, Ursache beheben und den Dienst nach
erfolgreicher Wiederholung bewusst starten. Private Einstellungen bleiben erhalten.

**Bestehende produktive Installation:** Nicht einfach main in die laufende Installation
ziehen. Erst die gesicherte [Erst-Migration mit Rollback](RELEASES.md) prüfen und
freigeben. Der neue `scripts/update.sh`-Pfad verwendet nur vollständige Stable-Releases.
Die öffentlich verfügbaren Pakete und Versionsnummern stehen auf der [Release-Seite](https://github.com/dosordie/FoxAir_Control_Web/releases).

**Frische Stable-Installation:** Den freigegebenen Tag separat
bereitstellen und `scripts/install_release.py` als root mit Python 3.12 ausführen.
Der Installer legt `/opt/foxair-web/app` und die passende venv aus dem fertigen Release
an. Danach über diesen App-Pfad `scripts/install_service.sh` aufrufen und die obige
GUI-Ersteinrichtung durchführen.

Der optionale GUI-Updateknopf lässt sich nach der Release-Migration mit
`sudo bash /opt/foxair-web/app/scripts/install_web_update.sh` einrichten. Code und
venv müssen root gehören und dürfen nicht durch den Webdienst beschreibbar sein.
Auf work wird dieser Produktions-Updateknopf nicht angeboten.

## Hilfe bei Problemen

| Problem | Erste Prüfung |
| --- | --- |
| Seite öffnet sich nicht | Läuft `foxair-web.service`? Stimmen Tunnel bzw. Reverse Proxy? Standardmäßig lauscht der Dienst nur auf Loopback. |
| Anmeldung oder Speichern abgelehnt | HTTPS oder den lokalen Loopback-Tunnel verwenden; Proxy-IP und HTTPS-Header prüfen. |
| Keine Messwerte | Verbindung in der Übersicht auswählen; Cloud-Gerät bzw. LTE-Endpunkt kontrollieren. |
| LTE antwortet nicht | IP, Port, Aktivierung, Erreichbarkeit und andere Bus-Master prüfen. Diagnoseprotokoll ansehen. |

Dienstprotokoll lokal ansehen:

```bash
sudo journalctl -u foxair-web.service -n 100 --no-pager
```

Vor dem Teilen alle persönlichen Angaben, realen Netzadressen und Zugangsdaten entfernen. Fehlermeldungen lassen sich als [Issue](https://github.com/dosordie/FoxAir_Control_Web/issues) melden.

## Lokal entwickeln

Zusätzlich werden Node.js und npm benötigt; die CI verwendet Node.js 22. Im Projektverzeichnis:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
python -m backend.server --host 127.0.0.1 --port 8081
```

In einem zweiten Terminal:

```bash
cd frontend
npm ci
npm run dev
```

Die Entwicklungsversion unter `http://127.0.0.1:5173/` öffnen. Vite leitet API-Anfragen an das lokale Backend weiter.
