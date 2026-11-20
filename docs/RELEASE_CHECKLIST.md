# Checkliste: erstes FoxAir Control Web Release v0.1.0

**Status:** Freigabevorbereitung, **noch kein Tag/Release**. Die hier genannten
Prüfungen sind eine Übergabe an Work; kein Produktions-Update wurde ausgeführt.

## Branch-Vertrag
- `work`: Entwicklungs-/Teststand auf der Linux-Test-VM, manuelles `git pull --ff-only origin work`. Dazu passenden Vue-Build separat bereitstellen.
- `main`: freigegebener Stable-/Release-Quellstand. Änderungen von `work` nach Review nach `main` übernehmen.
- Ein GitHub Release `vX.Y.Z` markiert **genau einen getesteten main-Commit**. Docker-Tag `X.Y.Z` und Linux/systemd erhalten dieselbe Versionsnummer.
- Desktop-Anwendung `FoxAir_Control` ist unabhängig versioniert.

## Vor dem ersten Release
- [ ] PR #10 prüfen, alle CI-Checks grün und nach `main` übernehmen.
- [ ] `VERSION`, `backend/main.py`, `frontend/package.json`,
      `frontend/package-lock.json` stimmen auf `0.1.0` überein.
- [ ] Bei jedem Versionswechsel diese Dateien zusammen ändern und
      `python scripts/check_release_version.py --tag vX.Y.Z` ausführen.
- [ ] Prüfen, ob der manuelle GitHub-Actions-Workflow
      **v0.1.0 release preflight (no publish)** grün ist.
      Er validiert `main`, `v0.1.0` und `web-dist`; er publiziert **nichts**.
- [ ] GitHub Web CI erfolgreich und Docker-Smoke-Test erfolgreich.
- [ ] Der produktive systemd-Updater ist von `git pull main` auf
      **immutable release assets/tag** umgestellt (Work, Issue #11).
- [ ] Frontend-Artefakt ist zu **derselben SHA** wie das Backend gebunden,
      nicht ausschließlich an den veränderlichen `web-dist`-Branch.
- [ ] `/api/health` und Update-UI melden verlässlich `0.1.0` als Webversion;
      Release-Commit steht als zusätzliches technisches Detail zur Verfügung.
- [ ] Bestehende systemd-Nutzer-/Cloud-/Proxy- und Admin-Konfiguration vor
      dem Upgrade sichern und Migration inklusive Rollback testen.

## Release-Freigabe (nach Work-Review)
- [ ] Exakten freigegebenen `main`-Commit auswählen.
- [ ] `v0.1.0` **einmalig** auf diesen Commit taggen; keine nachträgliche
      Änderung eines veröffentlichten Tags.
- [ ] Release Notes erstellen (Änderungen, Upgrade, bekannte Einschränkungen).
- [ ] Sicherstellen, dass systemd-Artefakt + Docker-Image
      zum **gleichen Commit** gehören.
- [ ] GitHub-Release und GHCR-Push orchestrieren: Beim aktuellen Trigger
      `release: published` kann die Release-Seite bereits sichtbar sein,
      während Docker noch baut. **Nicht** vor fertigen Artefakten
      als installierbare Version anbieten (Work-Gate/Manifest).
- [ ] GHCR-Paket-Sichtbarkeit (Public) und tatsächlichen Pull prüfen.
- [ ] Docker-Tag `0.1.0`, OCI-Version `0.1.0` und Quell-SHA vergleichen;
      `latest` erst nach Stable-Freigabe setzen.
- [ ] Portainer-Test auf realem Docker-Host: Admin-Einrichtung, Proxy/HTTPS,
      Persistenz, Cloud/LTE/Modbus, PWA, Update und Rollback.

## Möglicher Release-Notes-Text (nur Vorlage)
```markdown
# FoxAir Control Web v0.1.0

Erstes versioniertes Stable-Release von FoxAir Control Web.

## Enthalten
- Weboberfläche und FastAPI-Backend aus dem freigegebenen main-Commit
- [Konkrete Änderungen hier beim Release ergänzen]

## Installation
- Linux/systemd: [Link zur aktualisierten Release-Installationsanleitung]
- Docker/Portainer: [Link zum GHCR-Image und zur Compose-Anleitung]

## Hinweise
- Vor der Aktualisierung Konfigurations-/Benutzerdaten sichern.
- Web- und Docker-Version sind identisch; Desktop FoxAir Control ist separat versioniert.
```

## Explizit noch nicht erledigt
**Kein `v0.1.0`-Tag, kein GitHub-Release, kein produktiver systemd-Updater-Umbau,
kein GHCR-Push und kein Portainer-Deployment.** Das bleibt bis zur gemeinsamen
Work-Abnahme offen. Referenz: Issue #11, Docker-Issue #9 und Draft-PR #10.
