# FoxAir Control Web v0.1.0 · Vorabversion

Für einen Test auf einem separaten Rechner oder in einer Test-VM. Docker (Linux amd64)
und das Linux-Paket enthalten denselben Quellstand und dasselbe gebaute Frontend.
Das Linux-Paket benötigt Python 3.12 und Internetzugriff für die Python-Abhängigkeiten.
Für Docker genügt eine Docker-Installation auf einem Linux-amd64-Host.

## Dateien herunterladen und prüfen

Die Archive und `SHA256SUMS` liegen unter [Assets](https://github.com/dosordie/FoxAir_Control_Web/releases/tag/v0.1.0).
Die Befehle im Downloadverzeichnis ausführen. Einzelne Archive können separat geprüft werden.

```bash
sha256sum --ignore-missing -c SHA256SUMS
```

## Docker

```bash
docker load -i foxair-web-docker-0.1.0-amd64.tar.gz
docker run -d --name foxair-preview --init \
  --network host \
  -v foxair-preview-state:/var/lib/foxair-web \
  foxair-web:0.1.0-preview \
  python -m backend.server --host 127.0.0.1 --port 18081
docker exec foxair-preview python -m backend.setup
```

Der Container bindet im Linux-Hostnetz direkt an Loopback, damit die lokale
Admin-Ersteinrichtung funktioniert. Im Browser `http://127.0.0.1:18081` öffnen. Den angezeigten Einmalcode zusammen
mit einem neuen Admin-Passwort im Einrichtungsdialog eingeben. Mit
`docker stop foxair-preview` beenden und mit `docker start foxair-preview`
erneut starten. Das Testvolume enthält die Einstellungen.

Portainer kann das entpackte Docker-Archiv unter **Images → Import** laden.
Für einen Stack das lokale Image `foxair-web:0.1.0-preview` verwenden und ein
separates Volume nach `/var/lib/foxair-web` einbinden. Die Compose-Datei im
Linux-Archiv kann als Vorlage dienen. Für Netzwerkzugriff HTTPS konfigurieren.

## Linux ohne Docker

Als normaler Benutzer in einem neuen Verzeichnis ausführen. Für den Test bleibt
der bestehende systemd-Dienst unberührt.

```bash
mkdir foxair-preview-linux
tar -xzf foxair-web-0.1.0.tar.gz -C foxair-preview-linux
cd foxair-preview-linux
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
mkdir -m 700 state
export FOXAIR_STATE_DIR="$PWD/state"
.venv/bin/python -m backend.setup
.venv/bin/python -m backend.server --host 127.0.0.1 --port 18081
```

Im Browser dieselbe Adresse und den separat erzeugten Einmalcode verwenden.
Bei einer entfernten Test-VM einen SSH-Tunnel öffnen, beispielsweise
`ssh -N -L 18081:127.0.0.1:18081 BENUTZER@TEST-VM`. Bei einem gleichzeitigen
Docker-Test einen anderen Port wählen.

## Was prüfen?

- `curl -fsS http://127.0.0.1:18081/api/health` zeigt `ok: true`, den Kanal
  `prerelease` und `build_consistent: true`. Die Commit-SHA muss bei beiden Paketen
  mit `release-ready.json` übereinstimmen.
- Einrichten, anmelden und den Testdienst neu starten. Danach erneut anmelden
  und prüfen, ob die Einstellungen erhalten sind.
- Unter **Verbindungseinstellungen** bei Bedarf einen Testzugang einrichten.
  Zuerst Messwerte, Pumpenanzeige und Registerbrowser prüfen. Einen bereits
  belegten Modbus-Anschluss für den Test freilassen.

Die Vorabversion wird manuell installiert. Der Stable-Updater bietet sie nicht an.
