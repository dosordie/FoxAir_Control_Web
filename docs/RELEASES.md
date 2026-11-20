# Gemeinsame Web-Releases (Vorbereitung auf work)

**Noch kein v0.1.0 veröffentlicht. main ist Stable/Release, work bleibt Entwicklung. Kein automatisches Produktivdeployment.** Das Desktop-Projekt hat eigene Versionsnummern.

## Versionsvertrag

`VERSION` ist die Produktversion. `scripts/check_release_version.py` prüft package.json, Lockdatei und die daraus abgeleitete FastAPI-Version. `scripts/build_manifest.py` erzeugt identische `build-manifest.json` im Paket und im Frontend: Version, volle Quell-SHA, Frontend-SHA, gepinnte Register-SHA, Kanal. `/api/health` und das Updatepanel zeigen diese Identität. Work wird als `0.1.0-dev+SHA` gekennzeichnet; bisherige Installationen ohne Manifest als `legacy/main`.

## Test-VM auf work

Nach grünem **FoxAir Web CI** liegt das passende Frontend separat in `web-dist-work`. `web-dist` gehört weiterhin nur zu main. Auf einer bereits eingerichteten Linux-Test-VM mit Checkout auf work:

```bash
cd /opt/foxair-web/app
bash scripts/update-work.sh
```

Der Helfer prüft den work-/Build-SHA-Abgleich vor dem Update, führt ein Fast-Forward aus, aktualisiert Abhängigkeiten und Frontend und startet nur einen zuvor aktiven Dienst wieder. Der Zustand in `FOXAIR_STATE_DIR` bleibt erhalten. Ein eigenes `git pull --ff-only origin work` bleibt erlaubt, aktualisiert aber allein keine gebauten Dateien: danach denselben Helfer verwenden, bevor der Dienst neu gestartet wird. Scheitert eine Installation nach dem Anhalten, bleibt der Dienst sicherheitshalber gestoppt; Ursache beheben, Helfer erneut ausführen und den Dienst bewusst starten. `--no-restart` ist nur für kontrollierte Wartung gedacht.

Die App prüft beim Öffnen und alle 15 Minuten im sichtbaren Tab, ob ein Update bereitsteht. Docker liest dafür die Version von GHCR `latest`, Linux Stable das vollständige GitHub-Release und `work` den Commit mit passendem Web-Build. Ein Hinweis im Kopf führt zur Versionsanzeige in den Einstellungen.

Die produktive GUI hat keinen frei wählbaren Development-Kanal. Auf work ist der systemd-Release-Updateknopf gesperrt und verweist auf den manuellen Testablauf.

## Freigabe und Veröffentlichung

Der Workflow **Approved immutable stable release** wird ausschließlich manuell auf main mit ausdrücklicher Freigabe ausgeführt. Der bereits freigegebene Tag `vX.Y.Z` muss existieren und auf einen main-Commit zeigen; der Workflow erzeugt keinen Tag. Bisher freigegebene Versionen und Images werden nicht überschrieben.

1. Nach Nutzerfreigabe work prüfen/übernehmen, den exakten main-Commit freigeben und einmalig taggen. Erstes Release ist v0.1.0.
2. Workflow auf main mit diesem Tag und Freigabeschalter ausführen. Backend-, Frontend- und Registerprüfungen laufen vor der Veröffentlichung. Ein und dasselbe gebaute Frontend wird für Linux-Paket und Docker verwendet.
3. Das getestete amd64-Image bekommt den festen GHCR-Versionstag und OCI-Version/Revision/Source. Das Linux-Archiv enthält Code, Frontend und Manifest derselben SHA; SHA256SUMS und release-ready.json werden als Draft-Assets angehängt.
4. Erst nach erfolgreichem **anonymem Pull des exakten Image-Digests** und Prüfung der OCI-Labels wird das GitHub Release öffentlich. Für das erste GHCR-Paket muss ein Berechtigter die Paketsichtbarkeit auf Public stellen. Falls dieser Job stoppt: Sichtbarkeit korrigieren und nur den fehlgeschlagenen Publish-Job erneut ausführen, keine Versionsimages neu bauen/überschreiben.
5. `latest` wird erst nach dem öffentlichen Stable-Release verschoben. Bei einem Fehler dieses optionalen Aliases bleibt der feste Versionstag gültig; den Publish-Job gezielt wiederholen. Vorabversionen erscheinen unter eigenen Tags und verschieben den laufenden Tag `latest` bei späteren Veröffentlichungen nicht. Docker und Linux werden als Paar aus derselben Version und demselben Commit gebaut. `work` bleibt der Linux-Testzweig.

Es gibt keinen `release: published`-Build mehr, der ein sichtbares Release mit noch fehlendem Image erzeugt. Updates akzeptieren nur vollständige Stable-Releases mit gültigem Fertigmanifest, Prüfsumme und übereinstimmender Quell-/Frontend-SHA. Rate-Limits, fehlende Assets oder GitHub-Ausfälle führen zu keiner Installation. Release-Assets liegen bei GitHub Releases, nicht als dauerhafte Actions-Artefakte.

## Linux-Migration und Rollback

Vor der ersten produktiven Migration müssen Nutzer-/Proxy-Konfiguration und State extern gesichert werden. Den alten main/SHA-Updatepfad bis zur bewussten Migration nicht mehr verwenden. **Nicht einfach ungeprüft main in die laufende alte Installation ziehen.** Den freigegebenen Quellstand zunächst separat bereitstellen und von dort den geprüften `scripts/install_release.py` mit der vorhandenen FoxAir-venv als root starten. Der Installer verwendet ausschließlich den fest definierten Release-Kanal; der Browser kann keine URL, Befehle oder Tags übergeben.

Der Installer prüft Download-Hash, sichere Archivpfade und beide Manifeste, erstellt pro Release eine eigene venv und prüft Imports vor der Umschaltung. EnvironmentFiles innerhalb des App-Verzeichnisses müssen vor der Migration bewusst nach außerhalb verlegt werden; der Installer verweigert diese Fälle ohne Umschaltung. Die vorhandene systemd-Unit, ihre Listenadresse, HTTPS-/SSO-Konfiguration und das State-Verzeichnis werden nicht ersetzt. Nur ein zuvor aktiver FoxAir-Dienst wird angehalten und wieder gestartet. Quellcode und venv werden durch die App-Verknüpfung gemeinsam ausgewählt. Die alte Git-Installation und ihre Python-Umgebung bleiben als lokale Rückfallstände erhalten. Fehlgeschlagene Health-/Versionsprüfungen stellen den vorherigen Stand wieder her.

Nach erfolgreicher Migration kann ein vorhandener Update-Path-Service weiterverwendet werden. Falls er noch nicht eingerichtet ist, `bash /opt/foxair-web/app/scripts/install_web_update.sh` als root ausführen; dieser unterstützt sowohl den ursprünglichen Checkout als auch validierte Releasepakete. Anschließend:

```bash
bash /opt/foxair-web/app/scripts/update.sh
# Bewusster lokaler Rückweg zu vorherigem Code UND vorheriger Python-Umgebung:
bash /opt/foxair-web/app/scripts/update.sh --rollback
```

Die erstmalige Umwandlung bestehender Verzeichnisse benötigt einen Wartungszeitraum. Bei Stromausfall zwischen diesen Schritten kann der Dienst gestoppt bleiben und lokale Wiederherstellung nötig sein; es werden keine Benutzerdaten migriert oder gelöscht. Alte Releases/Legacy-Verzeichnisse werden nicht automatisch entsorgt. Datenformatmigrationen benötigen künftig eine eigene Freigabe; ein Code-Rollback ersetzt kein State-Backup.

## Docker

Compose empfiehlt den festen Tag `ghcr.io/dosordie/foxair-control-web:0.1.0` **nach dessen Freigabe**. Updates erfolgen extern über Compose/Portainer. Die Container-GUI ruft weder systemctl noch einen Docker-Socket auf. Dasselbe Volume erhält Nutzer, Passwörter, Sitzungen, Bus-/Cloud-/Gira-Konfigurationen und Caches. Rückweg: vorherigen festen Image-Tag bzw. Digest auswählen. Siehe INSTALLATION_DOCKER.md.

## Noch vor dem ersten Release abzunehmen

Realer Portainer-/Proxy-/Hardwaretest, GHCR-Berechtigungen/Public-Sichtbarkeit, tatsächliche Erst-Migration einer vorhandenen Installation sowie der erste echte Release-/Rollback-Lauf bleiben Freigabegates. Die vorbereiteten CI-/Simulatorprüfungen sind kein behauptetes produktives v0.1.0-Release.
