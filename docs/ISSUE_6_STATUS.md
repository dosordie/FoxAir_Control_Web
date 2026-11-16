# Issue 6 – Stand 16.11.2026

## In dieser Änderung

- Admin-Anmeldung oben rechts; öffentliche Anzeige bleibt ohne Anmeldung verfügbar.
- Sitzungsbasierte Cloud-Aktionen akzeptieren ein fehlendes/leeres Passwort; nur Login verlangt ein nichtleeres Passwort. HTTPS-, Session- und CSRF-Prüfungen bleiben bestehen.
- Fehlertexte für FastAPI-Validierungsarrays und Objekte, ohne `[object Object]` oder Wiedergabe sensibler Eingaben.
- R02: Zahlen aus Vue-Zahlenfeldern werden vor `.trim()` in Text umgewandelt. Ausgangswerte können in beiden Schreibdialogen gezielt neu gelesen werden. Das Cloud-Payload bleibt wie im Desktop: Engineering-Temperatur, kein zusätzliches ×10.
- Parameterkatalog nach natürlichen Cloud-/Parametercodes, bereits vor dem Ergebnislimit. Nur die Hauptfensterübersicht bleibt nach MAIN-Adressen sortiert.
- Soll–Vorlauf-Differenz unter dem aktuellen Sollwert; Kompressor-Istfrequenz aus T31/MAIN 2072 im WP-Symbol.
- Cloud-Gerätename (Nickname vor Gerätename) wird serverseitig und kontogebunden gespeichert; Fallback FoxAir. Hintergrundabfrage höchstens alle 15 Minuten.
- Browser-Titel FoxAir Control Web.
- LTE-IP und TCP-Port als Admin einstellbar, Vorgabe 192.168.1.50:2001. Erst nach explizitem Aktivieren nutzbar. Konfiguration privat im bestehenden Zustandsverzeichnis `warmlink.json`, keine Cloud-Zugangsdaten darin.
- LTE-Register-/Dashboard-Lesen sowie Mode/R02-Schreiben mit frischen Ausgangswerten, R10/R11-Grenzen, genau einem FC16-Schreibversuch und FC03-Readback. Lokale TEMP1-Werte werden auf der Leitung ×10 skaliert.

## LTE-Protokoll und praktische Grenzen

Raw-TCP/ser2net am LTE-/Warmlink-Bus: 9600 8N1, Slave 99. Kein Modbus-TCP/MBAP und kein Displaybus. Parser aus dem bestätigten Desktop-Kern übernommen: FC03-Requests/-Responses, FC06 und FC16-Blöcke/-ACKs, CRC, fragmentierte TCP-Pakete und Echo-Erkennung. Pro Host/Port nur eine eigene Operation gleichzeitig, 300 ms Ruhe vor jeder Anfrage, begrenzte Wartezeit, Abbruch bei beobachteten konkurrierenden FC03-Anfragen. Nach Timeout/Mehrdeutigkeit wird die Verbindung geschlossen; kein Schreib-Retry. Mindestabstand zwischen Schreibversuchen: fünf Sekunden.

Eine lokale Sperre und Ruheprüfung koordinieren **keinen fremden DTU-Master auf dem physischen RS485-Bus**. Zeitgleiche Telegramme können weiterhin kollidieren; FC03 hat keine Transaktionskennung. Die Webapp bricht bei erkennbarer Mehrdeutigkeit ab, statt einen Erfolg zu behaupten. Hardwareprüfung dieses neuen Adapters steht aus.

## Überprüfung

- Backend: `python -m unittest discover -s backend/tests -v`.
- Frontend: `npm test` und `npm run build`.
- Tests umfassen Sitzungsaktionen ohne Passwort, fehlende Berechtigungen/CSRF, R02-Zahlenfeldwerte, Fehlerdarstellung, Sortierung vor Limit, Gerätename und Istfrequenz.
- LTE ausschließlich mit synthetischen Telegrammen/Mocks: Fragmentierung, eingebettete Header in FC16-Blöcken, fremde Abfragen, CRC, passende ACKs, Konflikte/Grenzen, Skalierung, unklare Schreibantwort ohne Retry.
- Reale Geräte-Schreibvorgänge sind durch diese automatisierten Tests nicht nachgewiesen.

## Weiter offen

- Tatsächliche Änderung von R02 und Mode mit anschließendem Geräte-Readback über Cloud und LTE unter Beobachtung.
- Vollständige SG-/AT-/Timer-Schreibdialoge. Desktop nutzt hierfür eigene Wertevalidierung, Disable/Parameter/Enable-Barrieren sowie Timer-Bitmasken und Readback je Stufe; diese Abläufe sind hier noch nicht portiert. Bestehende Spezialdialoge bleiben lesend (WP: Mode/R02 ausgenommen).
- Echte iPhone-/Safari-Prüfung und Offline-/Wiederanlauftest an der Installation.
- Optional konfigurierbarer Stale-Grenzwert und individuelle Admin-Konten.

CI veröffentlicht nach erfolgreichem Backend-/Frontendlauf `web-dist` mit `.build-source-sha`. Installation erst, wenn diese Revision zum aktuellen `main` passt.

## Zweiter Prüfschritt

- Delta jetzt Vorlauf minus Soll; positiv bedeutet Vorlauf wärmer als Soll.
- Parametercode im Rahmen, MAIN-Adresse darunter; Hauptfensterregister behalten MAIN-Darstellung.
- Verbindungseinstellungen per Schaltfläche ein-/ausblendbar (Cloud und LTE).
- Anmeldung 30 Tage mit HttpOnly-Cookie; serverseitig nur Tokenhashes privat gespeichert, überlebt Dienstneustarts. Abmelden widerruft die Sitzung.
- Zusätzliche Browser-Bestätigungsabfrage beim Schreiben entfernt; Validierung und Readback bleiben.
- LTE TX/RX, CRC-bestätigte Antworten, ACKs und unklare Antworten erscheinen im Verbindungsprotokoll.
- Versionsanzeige unterscheidet aktuellen Build und neue Version deutlicher.
- Grauer Hero-Hintergrund bei gemeldetem Power=Aus.
- Serverlogs geprüft: sporadische LTE-Lesefehler, danach erfolgreiche Reads. HTTP-200-Schreibantwort allein gilt nicht als Hardwarebestätigung.

Weiter offen: dauerhafter passiver Busempfang, vollständiger Mapping-Audit gegen Desktop, allgemeine Schreibfreigaben mit quellbasierten Wertebereichen, Betriebs-Popups, grafische Spezialdialoge und neues WP-Motiv. Displaybus bleibt nicht implementiert. Kein Modus-/Power-Test mit Geräteänderung in diesem Schritt.
