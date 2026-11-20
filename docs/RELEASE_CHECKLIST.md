# Checkliste: erstes FoxAir Control Web Release v0.1.0

**Status:** Freigabevorbereitung, **noch kein Tag/Release**. Die hier genannten
Prüfungen sind eine Übergabe an Work; kein Produktions-Update wurde ausgeführt.

## Branch-Vertrag
- `work`: Entwicklungs-/Teststand auf der Linux-Test-VM, `scripts/update-work.sh` hält Git-Quellstand und passenden Vue-Build zusammen; ein manuelles `git pull` allein aktualisiert den Build noch nicht.
- `main`: freigegebener Stable-/Release-Quellstand. Änderungen von `work` nach Review nach `main` übernehmen.
- Ein GitHub Release `vX.Y.Z` markiert **genau einen getesteten main-Commit**. Docker-Tag `X.Y.Z` und Linux/systemd erhalten dieselbe Versionsnummer.
- Desktop-Anwendung `FoxAir_Control` ist unabhängig versioniert.

## In work umgesetzt, vor Freigabe prüfen

- [x] Gemeinsame `VERSION` und Prüfung von Backend-/Frontend-Version.
- [x] Identisches Quell-/Frontend-Manifest in Linux-Paket und Docker-Image.
- [x] Secure GUI-Ersteinrichtung mit lokalem Einmalcode; bestehende Konten erhalten.
- [x] Separates passendes Frontend `web-dist-work` und Helfer `scripts/update-work.sh`.
- [x] Release-basierter systemd-Installer mit Prüfsummen, eigener venv und lokalem Rollback.
- [x] Container-Updatepanel ohne Host-/systemd-Aufrufe.
- [x] Manuell freizugebender Workflow: Draft-Assets und öffentliches Image vor sichtbarem Release.
- [ ] CI des finalen work-Commits grün; konkrete Ergebnisse in Issues #9/#11.

## Vor dem ersten Release ausdrücklich freigeben und abnehmen

- [ ] Work-Änderungen und Draft-PR #10 gemeinsam reviewen; erst nach Freigabe nach main übernehmen.
- [ ] Exakten main-Commit freigeben und `v0.1.0` einmalig taggen.
- [ ] Release Notes und Sicherung der bestehenden Benutzer-/Proxy-/Cloud-/Busdaten.
- [ ] Reale systemd-Erstmigration inklusive Rückweg zu Code UND Abhängigkeiten testen.
- [ ] Realer Portainer-/HTTPS-/SSO-/PWA-/SSE-/Hardwaretest, Volume-Backup und Image-Rollback.
- [ ] GHCR-Paket auf Public stellen und anonymen Pull bestätigen.
- [ ] Approved immutable stable release auf main mit Freigabeschalter ausführen.
- [ ] Linux-Paket, Frontend, Docker-OCI-Version und Quell-SHA identisch; Fertigmanifest vorhanden.
- [ ] Veröffentlichung von v0.1.0 und erst danach optional `latest` bestätigen.

Der aktuelle Ablauf steht in [RELEASES.md](RELEASES.md). Der ältere manuelle
Preflight bleibt eine ergänzende Prüfung; er veröffentlicht nichts und ersetzt
nicht die Freigaben oder den gemeinsamen Release-Workflow.

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
**Kein `v0.1.0`-Tag, kein GitHub-Release, keine produktive systemd-Migration,
kein GHCR-Push und kein Portainer-Deployment.** Das bleibt bis zur gemeinsamen
Work-Abnahme offen. Referenz: Issue #11, Docker-Issue #9 und Draft-PR #10.
