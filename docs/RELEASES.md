# FoxAir Control Web – Releases aus main

## Festlegung
- **`main` ist der einzige laufende Entwicklungs- und Stable-Zweig.** Kein separater Stable- oder Development-Branch, kein neuer Update-Kanal.
- Produktversion nach SemVer: Beginn mit **`0.1.0`**. Git-Tag und GitHub Release **`v0.1.0`**.
- Linux/systemd, Docker/Portainer und künftig Windows-Webmodul tragen **dieselbe Web-Version** und dieselbe Release-Commit-SHA. `FoxAir_Control` Desktop bleibt eigenständig versioniert.
- Änderungen gelangen weiter wie bisher in `main`; ein Release markiert einen **getesteten Commit von main**. Der Update-Button soll später nur die **neueste freigegebene Release-Version** installieren, nicht jeden dazwischenliegenden Commit.
- Keine Tags/Release-Assets nachträglich austauschen. Fehlerkorrektur immer mit einer neuen Patch-Version.

## Bereits vorbereitet (ohne produktiven Updater-Umbau)
- Die maschinenlesbare `VERSION` startet bei `0.1.0`; `scripts/check_release_version.py` vergleicht VERSION, FastAPI und Frontend (`package.json`, `package-lock.json`), optional den Tag.
- `.github/workflows/release-check.yml` prüft die Version im Pull Request und auf main sowie optional manuell; das ist ein **Release-Vorabcheck, kein Publish**.
- Der Docker-Workflow im Docker-Vorbereitungs-PR #10 kann aus einem **veröffentlichten GitHub Release-Tag** ein GHCR-Image `X.Y.Z` bauen und nach Smoke-Test veröffentlichen. `latest` nur für Stable; noch **kein** Image für Endanwender verfügbar.
- Der bestehende `main` -> `web-dist`-Build bleibt bis zum Work-Umbau für bestehende systemd-Installationen **unverändert aktiv**.

## Erstes v0.1.0 Release (nach Review / Work-Umstellung)
1. PR #10 prüfen und nach `main` übernehmen. Prüfen, dass `VERSION`, FastAPI-, Frontend- und Lockfile-Version **0.1.0** sind.
2. Vorabcheck, bestehende FoxAir Web CI und Docker-Smoke-Test auf dem vorgesehenen Commit müssen grün sein.
3. Work migriert systemd-Updater auf releasegebundene, **unveränderliche** Frontend-/Backend-Assets. Der aktuell immer überschreibbare Branch `web-dist` darf für einen Release-Rollback nicht die einzige Buildquelle sein.
4. Erst danach `v0.1.0`-Tag auf genau diesem **main-Commit** erstellen und den zugehörigen GitHub Release veröffentlichen. Der Docker-Workflow baut dann das getestete GHCR-Image `0.1.0` und `latest`.
5. **Wichtig: Veröffentlichung des GitHub Releases startet den Docker-Build asynchron.** Erst nach erfolgreichem GHCR-Push und systemd-Release-Asset-Verifikation ist das Release plattformübergreifend vollständig bereit. Work soll diesen Zustand konsistent anzeigen oder die Pipeline zu einem synchronen Release-Gate zusammenfassen.
6. Installierte Version/Commit in UI/API anzeigen und erstes Upgrade eines bisherigen `main`-Deployments mit Backup und Rollback testen.

## Manuelle Vorprüfung (noch ohne Veröffentlichung)
```bash
python3 scripts/check_release_version.py --tag v0.1.0
python3 scripts/sync_registers.py --check
```
Der Actions-Workflow `Release version check` kann zusätzlich über GitHub Actions manuell getestet werden. **Er erstellt keinen Tag und kein Release.**

## Verbleibende Work-Aufgaben (Issue #11)
- Systemd-Updater `scripts/update.sh` auf releasegebundenen, gepinnten Quellcode/Frontend umstellen (bestehende Installation/State beibehalten).
- `backend/web_update.py`, `frontend/src/components/UpdatePanel.vue` und API-Version von SHA-Vergleich auf Release-Version/Status umstellen; SHA nur als technische Detailinformation.
- Für Docker Updates nur anzeigen und Compose/Portainer-Hinweis; kein `systemctl` im Container.
- Release-Assets und GHCR-Paket auf denselben Commit pinnen, Versionsmanifest/OCI-Labels sowie Release-Fertigstellung koordinieren.
- Release Notes, Migration von bestehenden `main`-Installationen und Rollback testen.

Siehe [Release-Versionierung #11](https://github.com/dosordie/FoxAir_Control_Web/issues/11), [Docker #9](https://github.com/dosordie/FoxAir_Control_Web/issues/9) und [PR #10](https://github.com/dosordie/FoxAir_Control_Web/pull/10).
