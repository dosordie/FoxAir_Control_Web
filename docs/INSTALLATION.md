# FoxAir Control Web installieren

> **Beta:** Geräte- und Verbindungsunterstützung werden noch erweitert. Zuerst Messwerte prüfen und erst anschließend bewusst Parameter ändern.

[Zurück zur Übersicht](../README.md)

## Voraussetzungen

Ein Linux-Server oder Container mit **systemd**, Git, Python 3 und Virtualenv-Unterstützung, Internetzugriff sowie sudo-/Root-Zugriff für die Einrichtung. Die CI prüft mit Python 3.12. **Node.js wird auf dem Server nicht benötigt.**

Die Skripte erwarten `/opt/foxair-web/app` als Installationspfad. Andere Pfade erfordern angepasste Dienstdateien und Hilfsskripte. Bei einer bestehenden Installation direkt zu [Updates](#updates) wechseln und das vorhandene Administratorpasswort beibehalten.

Vor dem ersten Aufruf von `update.sh` muss der Build für den aktuellen `main`-Commit auf der [Actions-Seite](https://github.com/dosordie/FoxAir_Control_Web/actions) erfolgreich abgeschlossen sein. Das fertige Frontend liegt dann im Branch `web-dist`.

## 1. Installieren

Auf Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ca-certificates curl
sudo install -d /opt/foxair-web
sudo git clone --branch main https://github.com/dosordie/FoxAir_Control_Web.git /opt/foxair-web/app
sudo python3 -m venv /opt/foxair-web/venv
cd /opt/foxair-web/app
sudo bash scripts/update.sh
sudo bash scripts/install_service.sh
sudo systemctl enable foxair-web.service
```

Das Update-Skript installiert Python-Pakete in die eigene Umgebung und übernimmt das passende Frontend. Der Dienst läuft unter `foxair-web` und lauscht zunächst **nur auf `127.0.0.1:8081`**.

Kontrolle:

```bash
curl -fsS http://127.0.0.1:8081/api/health
sudo systemctl status foxair-web.service --no-pager
```

Die Gesundheitsprüfung sollte unter anderem `"ok": true` zurückgeben.

## 2. Administratorpasswort einrichten

```bash
cd /opt/foxair-web/app
sudo /opt/foxair-web/venv/bin/python scripts/setup_web_admin.py
```

Das Skript fragt das Passwort zweimal interaktiv ab; mindestens zwölf Zeichen sind erforderlich. Es speichert den Passwort-Hash im privaten Verzeichnis `/var/lib/foxair-web` und erlaubt dem Dienst dort gezielt Schreibzugriff.

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

Den erfolgreichen Build des aktuellen `main`-Commits auf der [Actions-Seite](https://github.com/dosordie/FoxAir_Control_Web/actions) abwarten. Danach auf dem Server:

```bash
cd /opt/foxair-web/app
sudo bash scripts/update.sh
```

Das Skript gleicht Quellcode und Frontend-Commit ab und startet den laufenden FoxAir-Dienst neu. Es überschreibt keine lokalen Quellcodeänderungen. Private Einstellungen bleiben erhalten. Bei **„CI-Build … noch nicht veröffentlicht“** den fertigen Build abwarten und erneut versuchen.

Optional den Updateknopf für Administratoren in der Oberfläche einrichten:

```bash
cd /opt/foxair-web/app
sudo bash scripts/install_web_update.sh
```

Der Checkout muss dafür root gehören und darf nicht durch den Webdienst oder andere Benutzer beschreibbar sein.

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
