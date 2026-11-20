# FoxAir Control Web v0.1.1 · Vorabversion

Für einen Test auf einem separaten Rechner oder in einer Test-VM. Docker (Linux amd64)
und das Linux-Paket enthalten denselben Quellstand und dasselbe gebaute Frontend.
Das Linux-Paket benötigt Python 3.12 und Internetzugriff für die Python-Abhängigkeiten.
Für Docker genügt eine Docker-Installation auf einem Linux-amd64-Host.

## Dateien herunterladen und prüfen

Die Archive und `SHA256SUMS` liegen unter [Assets](https://github.com/dosordie/FoxAir_Control_Web/releases/tag/v0.1.1).
Die Befehle im Downloadverzeichnis ausführen. Einzelne Archive können separat geprüft werden.

```bash
sha256sum --ignore-missing -c SHA256SUMS
```

## Docker im LAN

Die [compose.yaml](https://github.com/dosordie/FoxAir_Control_Web/releases/download/v0.1.1/compose.yaml)
in denselben Testordner wie bisher herunterladen. Compose verwendet das vorhandene
Testvolume weiter.

```bash
docker compose pull
docker compose up -d
docker compose exec foxair-web python -m backend.setup
```

Auf PC oder iPhone `http://<LAN-IP-des-Docker-Hosts>:18081` öffnen. Bei der ersten
Einrichtung den Einmalcode und ein neues Admin-Passwort eingeben. Das direkte
LAN-Setup verwendet unverschlüsseltes HTTP. Verwende es im vertrauenswürdigen
privaten IPv4-Netz. Für externen Zugriff HTTPS mit der regulären Compose-Konfiguration
verwenden.

Alternativ das Docker-Archiv mit `docker load -i foxair-web-docker-0.1.1-amd64.tar.gz`
importieren und Compose mit `FOXAIR_PREVIEW_IMAGE=foxair-web:0.1.1-preview docker compose up -d --pull never`
starten.

## Linux ohne Docker

Als normaler Benutzer in einem neuen Verzeichnis ausführen. Für den Test bleibt
der bestehende systemd-Dienst unberührt.

```bash
mkdir foxair-preview-linux
tar -xzf foxair-web-0.1.1.tar.gz -C foxair-preview-linux
cd foxair-preview-linux
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
mkdir -m 700 state
export FOXAIR_STATE_DIR="$PWD/state"
.venv/bin/python -m backend.setup
.venv/bin/python -m backend.server --host 127.0.0.1 --port 18081
```

Im Browser `http://127.0.0.1:18081` und den separat erzeugten Einmalcode verwenden.
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
