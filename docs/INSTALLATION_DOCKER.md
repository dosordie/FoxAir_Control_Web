# Docker / Portainer – vorbereitete Installation

> **Beta / Entwicklung auf `work`:** Die Vorbereitungen aus Draft-PR #10 sind enthalten.
> Ein öffentliches Image `0.1.0` und ein Release werden erst nach ausdrücklicher Freigabe veröffentlicht.
> Diese Anleitung allein führt kein Update der bestehenden Linux-Installation aus.

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
5. Für den Netzwerkzugriff HTTPS und einen authentifizierenden Reverse Proxy konfigurieren.
6. WebApp öffnen. Bei einer frischen Installation erscheint die Ersteinrichtung.
   Den privaten einmaligen Code lokal abrufen:

   ```bash
   docker compose exec foxair-web python -m backend.setup
   ```

   Code und ein neues, mindestens zwölf Zeichen langes Passwort in der GUI eingeben.
   Vorhandene Konten werden erhalten; es gibt kein gemeinsames Standardpasswort.
   Der Code wird anschließend entwertet, danach normal anmelden.

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
git switch work # Entwicklungsstand; später einen freigegebenen Release-Tag verwenden.
git clone https://github.com/dosordie/FoxAir_Control.git upstream
python3 - <<'PY'
import json, subprocess
ref = json.load(open('data/upstream.json'))['ref']
subprocess.run(['git', '-C', 'upstream', 'checkout', '--detach', ref], check=True)
PY
python3 scripts/export_cloud_catalog.py upstream frontend/public/cloud_catalog.json
docker build --build-arg FOXAIR_VERSION="$(cat VERSION)" --build-arg FOXAIR_SOURCE_SHA="$(git rev-parse HEAD)" --build-arg FOXAIR_BUILD_CHANNEL=work -t foxair-web:local .
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

Die Container-GUI zeigt Release-Informationen und Anweisungen für Compose/Portainer.
Sie führt keine systemd-Befehle aus und benötigt keinen Docker-Socket.
Zum Update den festen Tag in `FOXAIR_IMAGE` ändern, dann die obigen Befehle ausführen.

## GitHub-Prüfung und Veröffentlichung

- **FoxAir Web CI** prüft Backend, Frontend und ein Container-Image mit genau demselben Frontend-Build.
- **Manual Docker verification (no publish)** prüft zusätzlich den eigenständigen Docker-Build bei Bedarf.
- **Approved immutable stable release** wird ausschließlich manuell auf `main` nach Freigabe gestartet.
  Erst nach fertigen Linux-Assets und anonymem Pull des exakten GHCR-Digests wird das Release öffentlich.
- Kein Workflow wird durch Veröffentlichung eines Releases nachträglich zum Image-Bau gestartet.
- Keine großen Images als dauerhafte Actions-Artefakte.

Details zu Manifest, Freigabe, Migration und Rollback: [RELEASES.md](RELEASES.md).

Vor öffentlicher Bereitstellung GHCR-Paketsichtbarkeit auf **Public** prüfen.
Zusätzliche Plattformen wie `linux/arm64` sind noch nicht Bestandteil
dieser ersten `linux/amd64`-Vorbereitung.

## Netzwerk, Einrichtung und noch offene Abnahmen

Der Smoke-Test prüft frische GUI-Einrichtung, nicht privilegierten Betrieb,
Healthcheck, sauberes Stoppen sowie Passwort-/Sitzungs-/Dateierhalt bei Neustart
und Container-Neuanlage mit demselben Volume. Reale Portainer-, Proxy-/SSO-,
Hardware- und Image-Update-/Rollback-Tests bleiben vor der Freigabe nötig.

Der interaktive `python -m docker.setup_admin` bleibt ein lokaler Fallback für
frische Installationen und verweigert das Überschreiben bestehender Admin-Dateien.
Bei verlorenen Zugangsdaten die lokale administrative Recovery bzw. Backups
verwenden; State-Dateien nicht pauschal löschen.

HTTPS ist für Netzwerkzugriffe erforderlich. Bei vorgeschaltetem Proxy dessen **tatsächliche TCP-Peer-IP** über FOXAIR_TRUSTED_PROXY_IPS explizit im Compose-Environment konfigurieren; keine pauschalen Netze/Client-Forwarded-For-Werte vertrauen. Für SSO gelten zusätzlich die vorhandenen eigenen Proxy-Secret-/Benutzermapping-Regeln. Ein selbst behauptetes X-Forwarded-Proto ersetzt weder lokalen Einrichtungscode noch eine vertrauenswürdige Proxy-Konfiguration.

Das Image enthält das gemeinsame Build-Manifest und meldet Version und SHA über /api/health. Im Container zeigt das Updatepanel Release-Informationen und Compose-/Portainer-Hinweise; systemd-Aufrufe und Hostupdates sind gesperrt. Feste Tags verwenden; latest ist nur eine ausdrückliche Rolling-Stable-Wahl. Zum Aktualisieren die gewählte Version in FOXAIR_IMAGE ändern, dann docker compose pull und docker compose up -d. Das benannte Volume bleibt erhalten. Ein Bind-Mount muss UID/GID 10001 gehören und darf keine bestehenden Dateien durch eine leere Verzeichnisquelle verdecken.

**Keine Produktionskonfiguration oder Zugangsdaten ins Repository einchecken.**
