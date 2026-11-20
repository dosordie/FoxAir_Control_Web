# Docker / Portainer – vorbereitete Installation

> **Status:** Docker-Unterstützung liegt zunächst im Vorbereitungs-PR zu Issue #9.
> Bis CI-Smoketest und Review erfolgreich sind und ein GHCR-Paket veröffentlicht wurde,
> existiert das Image `ghcr.io/dosordie/foxair-control-web:latest` möglicherweise **noch nicht**.
> Die bestehende Linux-/systemd-Installation bleibt unverändert.

## Architektur

Ein Container enthält das Python-Backend (FastAPI/Uvicorn) und die von Node.js
gebauten Vue-Dateien. Node.js wird nur beim Image-Build verwendet. Es ist **kein**
zweiter Nginx-Container erforderlich. Dieselbe WebApp besitzt im Container ihre
eigenen Cloud-/LTE-/Modbus-Verbindungen; es besteht **keine** Verbindung zur
geplanten Windows-Desktop-Bridge (Issue #8).

- Containerprozess: Python 3.12, Port 8081, UID/GID 10001, kein Root
- Zustand: `/var/lib/foxair-web` (`FOXAIR_STATE_DIR`), benanntes Docker-Volume
- Health: `GET /api/health`
- Standard-Portfreigabe: nur `127.0.0.1:8081` auf dem Docker-Host
- Start: `python -m backend.server --host 0.0.0.0 --port 8081` innerhalb des Containers
- Keine Docker-Socket-Mounts und kein privilegierter Container

## Installation über GHCR und Compose

Sobald das öffentliche Image aus einem GitHub-Release verfügbar ist:

1. `compose.yaml` und optional `.env.example` als `.env` auf den Docker-Host kopieren.
2. Ggf. feste Image-Version in `FOXAIR_IMAGE=ghcr.io/dosordie/foxair-control-web:<VERSION>` setzen.
3. `docker compose pull && docker compose up -d` ausführen.
4. Auf dem Docker-Host `curl -fsS http://127.0.0.1:8081/api/health` prüfen.
5. Das Admin-Passwort **interaktiv** setzen:

   ```bash
   docker compose exec foxair-web python -m docker.setup_admin
   ```

   Das Skript ist speziell für Docker, erfordert keine systemd-Installation
   und speichert den Passwort-Hash auf dem persistierten Volume.

6. Für den Zugriff vom iPhone oder über das Netzwerk HTTPS und einen
   authentifizierenden Reverse Proxy konfigurieren.

**Achtung:** Gastzugriff auf Messwerte kann in der WebApp erlaubt sein. HTTP
nicht ungeschützt ins Internet stellen. Admin-/Schreibfunktionen benötigen
HTTPS oder einen zulässigen lokalen Loopback-Kontext. Der interne
`127.0.0.1`-Port eines Containers ist **nicht** derselbe wie das Host-Loopback.

### Reverse Proxy auf anderem Rechner

Wenn Nginx/Authelia auf einem anderen Host laufen, bindet die Standard-Compose-Datei
**nicht** ans LAN. In der Host-`.env` oder bei Portainer unter Stack-Variablen:

```dotenv
FOXAIR_BIND_IP=192.0.2.10
FOXAIR_HTTP_PORT=8081
```

`192.0.2.10` ist **nur ein Dokumentationsplatzhalter**; durch die private
IP-Adresse des Docker-Hosts ersetzen. Die Host-Firewall muss den Port
auf die Reverse-Proxy-IP begrenzen. Nicht nur auf `0.0.0.0` stellen.
TLS/Authelia und (bei Nutzung) Trusted-Proxy-SSO nach `docs/DEPLOYMENT.md`
konfigurieren.

### Portainer

In **Stacks** die Compose-Datei aus diesem Repository übernehmen (oder ein
Git-Repository-Stack verwenden) und die obigen Variablen setzen.
Portainer muss das Image von `ghcr.io` ziehen können. Öffentliche GHCR-Images
benötigen dafür keine GitHub-Anmeldung. Bei privaten Paketen sind passende
Registry-Zugangsdaten erforderlich. Vor dem ersten Release kann Portainer das
oben genannte Image noch nicht beziehen.

## Lokales Image bauen

Der Frontend-Build benötigt den aus dem **gepinnten**
`data/upstream.json`-Commit von `dosordie/FoxAir_Control` exportierten
`frontend/public/cloud_catalog.json`. Diese Datei ist absichtlich nicht
eingecheckt. Die Docker-CI erzeugt sie automatisch. Für einen lokalen Build:

```bash
git clone https://github.com/dosordie/FoxAir_Control_Web.git
cd FoxAir_Control_Web
# Falls der Docker-PR noch nicht gemergt ist, den Docker-Vorbereitungsbranch auschecken.
git clone https://github.com/dosordie/FoxAir_Control.git upstream
python3 - <<'PY'
import json, subprocess
ref = json.load(open('data/upstream.json'))['ref']
subprocess.run(['git', '-C', 'upstream', 'checkout', '--detach', ref], check=True)
PY
python3 scripts/export_cloud_catalog.py upstream frontend/public/cloud_catalog.json
docker build -t foxair-web:local .
```

Danach für die lokale Compose-Installation `FOXAIR_IMAGE=foxair-web:local`
setzen und `docker compose up -d` starten. Das Dockerfile bricht bewusst ab,
wenn der exportierte Cloud-Katalog fehlt; es verwendet **keine unbemerkte
veraltete Katalogdatei**.

## Updates, Backup und Rollback

```bash
docker compose pull
docker compose up -d
docker compose logs --tail=100 foxair-web
```

Das benannte Volume `foxair-web-state` wird bei Image-Updates nicht ersetzt.
Den Namen des tatsächlichen Volumes mit `docker volume ls` kontrollieren;
Compose kann den Projektnamen voranstellen. Vor Updates/Restore das Volume
konsistent sichern (Container dafür anhalten). Eine vollständige Sicherung
umfasst auch Informationen, die das integrierte verschlüsselte Web-Backup
absichtlich ausschließt (z. B. Audit und Admin-Notfallkonto).

Für ein Rollback ein zuvor verwendetes versioniertes GHCR-Image als
`FOXAIR_IMAGE` setzen und neu starten. `docker compose down -v` **nicht**
verwenden – es löscht das Datenvolume.

Der bisherige `backend/web_update.py`-Updater ist **systemd-spezifisch**.
Er kann innerhalb eines Containers nicht funktionieren und darf keine
Host-Docker-Socket-Berechtigung erhalten. Die vorhandene systemd-Aktualisierung
wird von dieser Vorbereitung **nicht** geändert; die spätere Work-Integration
muss die Update-UI im Docker-Modus geeignet kennzeichnen/deaktivieren.

## Automatischer GitHub-Build

`.github/workflows/docker.yml`:
- PR: Docker-Build + Start-/HTTP- und Volume-Smoke-Test, **ohne Veröffentlichung**
- manuell: derselbe Test, **ohne Veröffentlichung**
- GitHub Release (published): erfolgreich getestetes Image nach GHCR pushen;
  `latest` nur bei stabilem Release; versioniertes `X.Y.Z`-Tag
- Cloud-Katalog wird aus dem gepinnten Desktop-Commit vor dem Build generiert
- keine Speicherung großer Docker-Images als Actions-Artefakte

Vor öffentlicher Bereitstellung GHCR-Paketsichtbarkeit auf **Public** prüfen.
Zusätzliche Plattformen wie `linux/arm64` sind noch nicht Bestandteil
dieser ersten `linux/amd64`-Vorbereitung.

## Offene Freigabe- und Funktionstests für Work / Issue #9

- CI-Build und Smoke-Test auf GitHub Actions ausführen und Ergebnisse prüfen.
- Update-UI für Containerbetrieb korrekt abgrenzen (systemd-Update darf nicht
  als funktionierende Docker-Updatefunktion erscheinen).
- Netzwerk-/Sicherheitsprüfung (SSL, Proxy-Header, Login/Cookie/Sitzung),
  PWA-Cache, SSE, Cloud- und lokale Buskommunikation.
- Portainer/LAN-Test auf einem realen Docker-Host, inklusive Volume-Backup,
  Neustart, Image-Update und Rollback.
- GHCR-Paketsichtbarkeit und veröffentlichte Versions-Tags prüfen.
- Docker-/systemd-Betrieb funktional gleichwertig halten.

**Keine Produktionskonfiguration oder Zugangsdaten ins Git-Repository einchecken.**
