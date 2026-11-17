# Register-Snapshots prüfen und vorschlagen

`python scripts/sync_registers.py --check` prüft ohne Netzwerk die drei
Registerdateien, ihre Wissensreferenzen und die SHA-256-Prüfsummen aus
`data/upstream.json`. Prüfsummen beziehen sich auf UTF-8 mit LF-Zeilenenden;
Windows-Checkout-Konvertierung verändert das Ergebnis nicht.

`python scripts/sync_registers.py --ref <vollständige Commit-SHA>` lädt alle
drei Dateien aus exakt dieser FoxAir_Control-Revision. Erst wenn alle Dateien
validiert sind, werden die Snapshots ersetzt. Anschließend Diff und Tests prüfen.
Die bisherige Revision 34ce0ed bleibt mit Einführung der Prüfung unverändert.

Der manuelle GitHub-Ablauf **Propose upstream register snapshot** erstellt dafür
einen eigenen Branch und Review-PR. Er führt keinen Merge und keine Installation
aus. GitHub muss das Erstellen von Pull Requests durch Actions erlauben; ohne
diese Repository-Einstellung schlägt die PR-Erstellung sichtbar fehl.
Der Frontend-Build liest dieselbe Revision aus dem Manifest und exportiert
Cloud-Kandidaten weiterhin mit dem Upstream-Resolver. Kein zweiter fest
eingetragener Upstream-Commit im Build.

Die Prüfung ist keine Freigabe neuer Schreibrechte: Kandidaten, virtuelle
Diagnose-IDs und Service-Metadaten werden dadurch nicht zu erlaubten Writes.
Die gezielten Backend-Schreibpfade und deren Grenzen bleiben separat geprüft.
Eine vollständige Ablösung aller bestätigten Backend-Mappings durch einen
gemeinsamen generierten Resolver sowie der in Issue #2 genannte Abgleich der
Lizenzkennzeichnungen bleiben offen. Die Dateien werden weiterhin aus dem
bereits verwendeten Stand übernommen; keine Lizenzkennzeichnung wird geändert.


Der Review-Ablauf prüft zusätzlich montags automatisch den aktuellen Upstream-Commit.
Er löst zuerst dessen vollständige SHA auf und verwendet danach ausschließlich diese
Revision. Pro Revision wird höchstens ein Review-Branch erzeugt; vorhandene Vorschläge
werden nicht überschrieben. Der Zeitplan installiert und merged weiterhin nichts.

Lizenzabgleich am eingebundenen Stand: `LICENSE` enthält MIT, `README.md` verlinkt dieselbe
Datei mit dem Text GPLv3. Dieser Widerspruch ist tatsächlich noch vorhanden und wird durch
keine Änderung im Web-Repository als geklärt ausgegeben.
