# Display- und Standard-Modbus

Beide neuen Anschlüsse bleiben standardmäßig deaktiviert. Reale IP-Adressen und Zugangsdaten gehören nur in die private Serverkonfiguration.

## Einrichtung

Als Administrator über HTTPS **Einstellungen → Verbindungseinstellungen** öffnen. Für jeden Bus die eigene IP-Adresse des seriellen TCP-Gateways und den TCP-Port eintragen. Das Gateway muss rohe Modbus-RTU-Frames inklusive CRC transparent übertragen (beispielsweise ser2net). Ein Modbus-TCP-Gateway mit MBAP-Header ist ein anderes Protokoll und wird hier nicht unterstützt. Direkte USB-/COM-Anschlüsse sind nicht Bestandteil dieses Web-Anschlusses.

Vor dem Aktivieren prüfen, dass Display, Standard und LTE unterschiedliche physische Anschlüsse verwenden. Die Anwendung verweigert eine doppelte IP/Port-Belegung zwischen diesen drei Verbindungen. Andere Programme bzw. ein zweiter Master müssen unabhängig davon berücksichtigt werden. Die Web-App sperrt einen TCP-Endpunkt pro Prozess; andere Rechner werden dadurch nicht gesperrt.

## Display-Modbus – zuerst passiv

- Bestätigter HMI-Steuerpfad: Teilnehmer **3**. Dieser Wert ist für die Spezialfunktion fest vorgegeben.
- Verbindung wahlweise während eines verbundenen Browsers (einstellbarer Nachlauf) oder dauerhaft auf dem Server offen halten.
- Nach Auswahl von Display-Modbus in der Übersicht öffnet die App eine eigene passive Empfangsverbindung. Normale Übersicht-, Parameter- und Gruppenzugriffe lösen keine aktiven FC3-Scans und keine Parameterschreibbefehle auf diesem Bus aus.
- Livewerte und empfangene Parameter fließen mit Quelle und Zeitstempel in denselben privaten Wertebestand wie Cloud und LTE ein. Bei Verbindungsausfall bleiben letzte Werte erkennbar als Altwerte verfügbar. Ein geänderter Endpunkt trennt die Datenquelle und verwirft laufende Protokollzuordnungen.
- Normale Schreibfunktionen, Timer-Schreiben und manuelle Registeränderungen sind auf dem Display-Bus serverseitig gesperrt. Es gibt keine frei wählbare Display-Schreibadresse und keinen frei wählbaren Schreibwert in der API.

### „Alle Werte vom Bus lesen“

In der Parameteransicht steht für Administratoren der Button **Alle Werte vom Bus lesen**. Er startet die aus FoxAir_Control übernommene Snapshot-Spezialfunktion. Die Busverbindung muss bereits bestehen. Mehrfachklicks werden zusammengefasst.

1. FC16 an Unit 3: `0x5112 = 0x0000`; auf ein passendes CRC-geprüftes ACK warten.
2. Erst danach FC16: `0x0BC3 = 0x8000`; auf ACK oder das bestätigte Flag im beobachteten FC3-Statuspoll `3001/21` warten.
3. Frische 90-Wort-Parameterpakete ab **1001, 1091, 1181, 1271, 1361 und 1451** empfangen. **1541** ist optional.
4. Nur mit allen sechs Pflichtpaketen wird der Vorgang als vollständig bestätigt; ansonsten erscheinen fehlende Pakete bzw. Timeout/Teilergebnis.

Wie im Desktop-Controller ist der Ablauf begrenzt: höchstens drei Gesamtversuche, bis zu drei Vorbereitungs- und vier Flag-Sendungen pro Versuch. Nur diese beiden festen, idempotenten Snapshot-Steuerbefehle dürfen wiederholt werden. Es werden keine Betriebsparameter geändert. ACKs mit falscher Unit, Adresse oder Anzahl und eigene TX-Echos bestätigen keinen Schritt. Nach Verbindungsabbruch wird eine Spezialabfrage **nicht automatisch erneut gestartet**.

Der Web-Ablauf wartet vor den aktiven Telegrammen auf eine ruhige Busphase und eine abgeschlossene beobachtete Leseanfrage. Auf einem dauerhaft belegten Bus kann er deshalb ohne Telegrammversand abbrechen; das Ergebnis ist keine Erfolgsmeldung. In diesem Fall Busbelegung und andere aktive Anwendungen prüfen.

### Empfangszuordnung

Das bestehende CRC-/Stream-Framing behandelt zerteilte und zusammenhängende TCP-Telegramme. Zur Übernahme von Mainboard-Paketdaten werden der Headeraufbau (`WF` und zehn Ziffern), Marker `0x0210`, innere Startadresse und 90 Wörter geprüft. Identitätsfelder werden weder im öffentlichen Wertebestand noch in Diagnosemeldungen ausgegeben.

Parameterpakete an Unit 3 und die bestätigten Live-Broadcasts an Unit 0 (2001/2091) werden getrennt von DWIN-Speicher und Unit-1-Inverterdaten behandelt. Fremde oder nicht eindeutig korrelierte FC3-Antworten werden nicht als MAIN-Werte interpretiert. Die virtuellen Inverterkanäle sind keine frei lesbaren Modbus-Adressen; sie werden nicht als MAIN-Telemetrie umgedeutet.

Protokollreferenz: FoxAir_Control, geprüft gegen Commit `a98b16c17d9226dd1084d87176b7497b4d837cd9`, insbesondere `core/display_protocol.py`, `_display_fake_reboot_*`, `_enqueue_display_fc16_single` und die passiven Zuordnungsregeln. Der Registerkatalog bleibt separat auf seinem überprüften Snapshot; ein Protokollvergleich aktualisiert ihn nicht automatisch.

## Standard-Modbus

IP, TCP-Port, Teilnehmer (1–247) und Antwort-Timeout werden ebenfalls im Verbindungsdialog gespeichert. Standardmäßig ist der Anschluss aus. Die bisherige Umgebungsvariablen-Konfiguration bleibt als Fallback erhalten, solange noch keine private Web-Konfiguration gespeichert wurde.

Der Standard-Anschluss ist ein dedizierter aktiver Master-Pfad über RTU-over-TCP. Übersicht und Parametergruppen lesen mit FC3; zusammenhängende Gruppen werden in Blöcke bis 90 Wörter aufgeteilt. Beim Schreiben gelten die vorhandenen Rollen, Registerfreigaben, Grenzwertprüfungen, Ausgangswertvergleich und Readback. Ein unklarer Schreibauftrag wird nicht automatisch wiederholt. Verbindungen werden nach der jeweiligen Operation geschlossen.

## Speicherung, Sicherung und Diagnose

Private Anschlusskonfigurationen liegen als `display_modbus.json` und `standard_modbus.json` im geschützten Zustandsverzeichnis. Die verschlüsselte Sicherung schließt sie mit ein; ältere Sicherungen ohne diese Dateien bleiben lesbar und ersetzen die neuen Anschlüsse nicht. Beim Wiederherstellen werden kollidierende Endpunkte abgelehnt.

Das gemeinsame Diagnoseprotokoll zeigt Empfang, Verbindungsausfälle und Snapshot-Schritte, jedoch keine Rohpakete mit Geräteidentitäten oder Zugangsdaten. Schreibversuche und die Snapshot-Spezialfunktion erscheinen zusätzlich im privaten Änderungsprotokoll.

## Verifikation und Hardware-Abnahme

Automatisierte Tests verwenden synthetische Frames sowie einen lokalen TCP-Gegenpart. Sie prüfen passiven Empfang ohne TX, die beiden exakten Trigger, ACK-Reihenfolge, CRC, Fragmentierung, fremde Units, alte/unvollständige Pakete, begrenzte Wiederholungen, Berechtigungen und normale Schreibsperren. Echte Wärmepumpenwerte werden dabei nicht verändert.

Der abschließende Hardwaretest benötigt die jeweiligen privaten Endpunkte: zunächst passiven Empfang prüfen, dann einmal den Snapshot anfordern und alle sechs Pflichtpakete kontrollieren. Den Desktop-Client dabei nicht parallel als aktiven Busnutzer betreiben. Ein erfolgreicher Softwaretest ersetzt diese Prüfung am konkreten Gerät und TCP-Gateway nicht.
