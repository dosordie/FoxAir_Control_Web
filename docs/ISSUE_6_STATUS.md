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

## Oberfläche: Verbindungspop-up und Originalmotiv

Verbindungseinstellungen liegen jetzt in einem nativen modalen Dialog (Cloud/LTE, eigener Scrollbereich, Fokusbindung, Escape/Schließen). Auf Desktop und 390-Pixel-Breite visuell geprüft. Hauptseite verwendet das unveränderte `app_icon.png` aus FoxAir_Control 34ce0ed als `foxair-heatpump.png`; Ist-Hz und animierter Lüfterstatus bleiben als Overlays erhalten. Keine KI-generierte Ersatzgrafik.

Zusätzlich: Spezialdialoge aktualisieren bei lokalen Transporten bestätigte lokale Register statt heimlich Cloudwerte zu lesen. Quelle wird im Dialogkopf angezeigt, der Knopf heißt „Werte aktualisieren“. Cloud-only-Codes werden nicht als lokale Register angefragt. Lokale Aktualisierung erfolgt einzeln und bedarfsgesteuert; kein passiver Dauerempfang. Texte zur entfernten Schreibbestätigung und zum Verbindungsprotokoll korrigiert.

## Nächster Schritt: integrierter Lüfter, Betriebs- und Timereditoren

- Transparente modifizierte FoxAir-Grafik ohne graue Bildfläche. Animation liegt als separater Rotor an der Lüfteröffnung, stationäres Gitter darüber; keine drehende Extra-Plakette. Bewegung nur bei frischem gemeldetem Ein, respektiert reduzierte Bewegung. Ursprungsbild bleibt erhalten.
- Ein/Aus, Modus und Ruhemodus auf der Startseite öffnen native modale Bedienfenster mit frischem Lesen, Admin-Prüfung und Readback. Power (MAIN1011) und H22 (MAIN1030) sind jetzt über Cloud/LTE binär schreibbar, auch in den Parameterdetails; keine allgemeine unvalidierte Registerfreigabe.
- Grafische Timereditoren: sechs Betriebsartenprogramme M1–M6 (Zeiten, Tage, Aktivierung, Modus, Zieltemperaturen, Leistung), sechs Ein-/Aus-Wochentimer, Silent-Start/Stop mit getrennten Freigaben. Vollständige Rohwort-Baselines; keine Nullwerte als Ersatz für fehlende Antworten. Gemeinsame Tagesmasken erhalten Partnerbytes. Standard-/Displaytimer bleiben nicht verfügbar.
- Timer-Schreibablauf: vollständiges frisches Lesen/optimistischer Vergleich; geänderte Sollwerte zusätzlich gegen R36/R37, R10/R11 bzw. R08/R09 prüfen; betroffene aktive Programme deaktivieren, Parameter setzen, Freigaben erst nach Readbacks wieder setzen. Abbruch bei Mehrdeutigkeit, kein Retry oder automatisches Rollback. Eine abgebrochene Folge kann Freigaben deaktiviert lassen; UI fordert erneutes Lesen.
- Cloud nutzt bestätigte KG-/M-/Silent-Codes und Engineering-/Binär-Konversion nach Desktop 34ce0ed; LTE FC16 mit 16-Bit-Wörtern. Betriebsarten- und Wochentimer sind unterschiedliche Registerbereiche, werden nicht vermischt. Fehler im bisherigen Timerkatalog korrigiert: KG-Codes und MAIN1270 berücksichtigt.
- LTE-Erstlesefehler konkret reproduziert: Restbytes `00 3d` ohne Frameanfang blieben im Parserpuffer. Nach 800 ms Ruhe können solche verwaisten Restbytes verworfen werden; echte unvollständige Kandidaten und unbeantwortete Fremdreads sperren weiterhin TX. Regressionstests für beide Fälle. Drei anschließende lokale Hardware-Reads erfolgreich. Keine Behauptung physischer Multi-Master-Arbitrierung.

Geprüft: 97 Backendtests, drei Frontendtests, Typecheck/Build; lokal alle drei Timerarten live per LTE gelesen und unveränderte Aufträge akzeptiert. Power-Pop-up ebenfalls mit unverändertem Wert geprüft. Keine Gerätewerte oder Zeitpläne verändert. Ändernde Timer-/Power-/H22-Schreibvorgänge bisher nur mit Mocks geprüft, nicht als Hardwareabnahme markieren.

Weiter offen: permanenter passiver RX, vollständige SG-/AT-Schreibeditoren, allgemeine parameterabhängige Schreibfreigaben und Displaybus. Aus früheren Abschnitten offene Timer-/Betriebs-Pop-ups sind mit diesem Abschnitt teilweise umgesetzt; die Hardwareabnahme von Änderungen steht aus.

Nachprüfung: 98 Backendtests erfolgreich. Dezimale Cloud-Schalter wie 1.0/0.0 werden wie lokale Schalter übersetzt (Klartext und Lüfterzustand). Ungültige Timer-Eingaben bleiben als Entwurf sichtbar und sperren Senden; frisches Lesen setzt sie zurück.

## Verbindung offen halten und Cloud-Erkenntnisse aus Issue 7

LTE-Verbindungsmodus ist privat konfigurierbar: bei Bedarf, Browser-Lease (90 Sekunden nach letztem Lebenszeichen), dauerhaft einschließlich Dienstneustart. Ein Prozess besitzt genau einen Socket, aktives Lesen/Schreiben und passiver Empfang teilen dieselbe Sperre. Hintergrundempfang sendet nichts; bei Fehlern nur Neuverbindung, keine Wiederholung von Writes. CRC-geprüfte FC16-Statusblöcke werden separat als beobachtete Rohwerte mit Alter erfasst (`/api/warmlink/connection`); Schreibabsichten werden nicht als Messwerte übernommen. Noch keine vollständige Projektion aller passiven Rohwerte in sämtliche Parameter-/Dashboardansichten. Betrieb mit einem API-Worker vorgesehen.

Issue 7: begrenzte Historienadressen (vier Temperaturen und Verbrauchs-Alias 2078+9), maximal 31 Tage, feste beobachtete Zeitzone UTC+1; Graph mit Zeitachse und Messpunkten, Cache und Abfragelimit. Aktueller Verbrauchstag ausdrücklich unvollständig. Lesende OTA-Verfügbarkeitsprüfung (kein Flash/Download/Start) und separater Hersteller-Servicekatalog ohne Mapping-/Schreibrechtsänderungen. Enum-Detailtabellen und AI-Supportanzeige sind noch offen; Issue 7 bleibt offen. Herstellerkatalog-Schema muss auf der Installation geprüft werden.

Tests ergänzt für Lease-Ablauf, Socket-Wiederverwendung, vergiftete Sitzungen, passive Statusblöcke gegenüber Schreibabsichten, Historienvalidierung, OTA-Leerantwort, Cache, Fehler-Ratelimit, unvollständige Tageswerte und Metadaten-Filterung. Display-Modbus bleibt in diesem Schritt deaktiviert; kein blindes Freischalten als Standard-RTU und kein unbestätigter Displaybus-Init.

## Nachprüfung: passiver Empfang, Historie und Snapshot-Prüfung

Die Übersicht übernimmt nun alle 15 Sekunden verfügbare CRC-geprüfte LTE-Buswerte, ohne dafür eigene Registerabfragen auszulösen. Messzeitpunkte bleiben die tatsächlichen Empfangszeiten; nach fünf Minuten oder bei unterbrochener passiver Verbindung werden Beobachtungen als veraltet markiert. Neuere aktiv gelesene Werte werden nicht von älteren Beobachtungen überschrieben. Der aktuelle Sollwert 2014 hat bei plausibler frischer Beobachtung Vorrang vor R02. Beobachtungen ersetzen keinen Schreib-Readback. Parameterlisten und Displaybus sind weiterhin nicht vollständig passiv angebunden.

Live vor diesem Schritt geprüft: permanenter Anschluss und Browser-Lease verbunden, gezielter R02-Read auf wiederverwendeter Sitzung erfolgreich, 180 beobachtete Rohwörter erfasst. Testweise geänderten Modus anschließend auf vorheriges „bei Bedarf“ zurückgesetzt. Keine Gerätewerte oder Zeitprogramme verändert.

Cloud: Historie lieferte live 25 Temperaturpunkte; OTA-Prüfung erfolgreich ohne angebotenes Update. Stunden-Zeitstempel werden jetzt in vollständiges ISO mit dem beobachteten UTC+1 umgewandelt, damit auch Chrome die Kurve zeichnet. Der Servicekatalog scheitert live am bisher dokumentierten Request. Weitere Versuche mit geratenen Feldnamen unterbleiben; Nutzer liefert später die Mac-Mitschnitte. Enum-/AI-Erweiterungen bleiben offen.

Issue 2: offline prüfbare Herkunft und SHA-256 je Registerdatei, Schema-/Referenzprüfung, Regressionstest für manipulierte Metadaten und reviewbare Änderungen sowie manuell auslösbarer Review-PR-Ablauf ergänzt. Der Build nutzt dieselbe Manifest-Revision statt eines zweiten festen SHAs. Details und offene Punkte in SNAPSHOT_SYNC.md. Der Workflow wurde bisher nicht mit einer tatsächlich neuen Upstream-Revision ausgeführt; keine vollständige Upstream-Synchronisierung oder Lizenzklärung behauptet.

Stand dieses Schritts: 113 Backendtests, drei Frontendtests und Typecheck/Build erfolgreich. Live-Abnahme der geänderten passiven Anzeige folgt nach CI/Installation.

## Flows-2 und Startseiten-Verlauf

Der lokal bereitgestellte Mitschnitt flows-2 bestätigt den Servicekatalog-Request mit deviceCode, pageIndex=1, pageSize=9999, paramName, num und protocalId. Die Protokollkennung wird privat über das ausgewählte Gerät und dessen Produkt abgefragt; Geräte-/Produktzuordnung werden verglichen. Antwortstruktur objectResult.dataList/total statt einer direkten Liste. Keine Rohmitschnitte, Kennungen oder Zugangsdaten übernommen.

Enum-Bedeutungen werden auf Klick anhand kurzlebiger, kontogebundener Referenzen aus dem geladenen Katalog abgerufen. Interne Hersteller-IDs bleiben auf dem Server. Metadaten und Enum-Tabellen verleihen weiterhin keine Schreibrechte.

Historische Diagramme sind jetzt ausschließlich über „Verlauf & Diagramme“ auf der Startseite erreichbar. Der modale Dialog und seine Diagrammkomponente öffnen erst nach Klick; Messdaten werden erst durch „Verlauf laden“ angefragt. OTA und Servicekatalog bleiben in den App-Einstellungen.

Der AI-/SG-Herstellerstatus aus flows-2 ist ebenfalls lesend abrufbar. Die Anzeige trennt Frequenzregelungs-Unterstützung, eingeschaltetes AI-Energiesparen, SG-Unterstützung und den gemeldeten SG-Modus. Finanz-/Accountfelder aus derselben Antwort werden verworfen. App-Kontext der untersuchten deutschen Installation: Germany / CET/CEST (serverseitig über FOXAIR_CLOUD_COUNTRY / FOXAIR_CLOUD_TIMEZONE anpassbar). Serviceeinträge zeigen separat den Abgleich mit bestätigten statischen Cloud-Zuordnungen; Abweichungen werden nicht übernommen. 117 Backendtests erfolgreich.

## Live-Abnahme am 17.11.2026

Installiert und im bestehenden angemeldeten Browser geprüft: Startseitenbutton öffnet leeren Verlaufdialog; erst „Verlauf laden“ fragt Daten ab. 25 Temperaturpunkte und endliche SVG-Koordinaten, Bereich 23,9–38,8 °C. Servicekatalog: 206 Einträge. ModeState-Enums lesbar; SG-Status bestätigt 0=Disable, 1–4=Mode1–Mode4, 5=Standard. AI: Frequenzregelungs-Unterstützung ja, Energiesparen aus, SG-Unterstützung ja, Modus 0. MAIN2157/2158/2146_Bit9 als separate Herstellerangaben sichtbar. Admin-Anmeldung überstand die Installation.

Passivtest Browser-Modus: verbundener Socket, 170 beobachtete Wörter, acht Dashboardgrößen aus Empfang übernommen. Übersicht änderte sich ohne eigenen Refresh von 37 auf 31 Hz, Vorlauf von 38 auf 38,1 °C und Durchfluss auf 0,68 m³/h; Zeitpunkt „Letzter Buswert“ sichtbar. Während des Beobachtungsfensters keine zusätzlichen LTE-TX-Ereignisse. Kein Gerätewert geändert. Verbindungsmodus abschließend wieder auf vorheriges „bei Bedarf“ gesetzt. Backend-Zugriffstests decken alle fünf neuen Cloud-Leserouten ohne Admin, ohne HTTPS, mit fremdem Origin und mit berechtigtem Aufruf ab; fehlende/ungültige Historienpunkte werden nicht ersetzt. 119 Backendtests erfolgreich. CI/Frontendprüfung ebenfalls erfolgreich.

Weiter offen bleiben insbesondere SG-/AT-Schreibeditoren, allgemeine validierte Parameter-Schreibrechte, Display-Modbus, vollständige passive Parameteransichten sowie die in SNAPSHOT_SYNC.md genannten Teile von Issue 2. Issue 4 enthält weiterhin die echte iPhone-/Safari-Abnahme; Chromium-Breitensimulation ist kein Ersatz dafür.

## FC3-Blöcke und direkte Live-Übertragung

Die vorherige Web-App verwendete bereits FC03 zum Lesen (auch für Einzelregister), FC16 für geprüfte Einzelwrites; FC06 wurde lediglich vom Parser erkannt und nicht zum Lesen gesendet. LTE-Übersicht jetzt drei statt sieben FC03-Requests: 1011/20, 1158/1, 2012/66. Standard-Modbus bleibt unverändert.

Beim Öffnen der Parameterliste unter LTE startet einmalig ein gemeinsam genutzter Hintergrundscan nach FoxAir_Control 34ce0ed workers/warmlink_worker.py: 1001, 1091, 1181, 1271, 1361, 1451, 2001, 2091, jeweils 90 Wörter. Ein Socket, streng sequenziell nach Antwort/Ruhephase, bei erster Mehrdeutigkeit Abbruch ohne Retry. Fortschritt und bestätigte Teilwerte erscheinen sofort. Andere Browser teilen laufende bzw. in den letzten 30 Sekunden abgeschlossene Abfragen. Gruppenwechsel/Suche lösen keinen neuen Scan aus. Zusätzliche Diagnose-/virtuelle Register außerhalb dieser belegten Init-Blöcke werden nicht blind mitgescannt; die Anzeige nennt die acht Blöcke explizit.

Aktive Antworten und passive Statusblöcke speisen denselben quellgebundenen Cache, neuere Empfangszeiten gewinnen. Paketköpfe/ASCII-/virtuelle Daten werden nicht an den Browser gestreamt. Aktive Reads bleiben bis zu fünf Minuten frisch; Beobachtungen nach Verbindungsabbruch bzw. fünf Minuten veraltet. Keine Beobachtung ersetzt den Schreib-Readback.

SSE /api/warmlink/events ersetzt den bisherigen 15-Sekunden-Rhythmus für Live-Anzeigen. Unidirektionale Serverübertragung ist hierfür ausreichend; WebSocket wäre erst für eine bidirektionale Protokollfunktion erforderlich. Initialer Cache, danach Änderungen/Entfernungen und Verbindungs-/Scanstatus, automatische Wiederverbindung, Keepalive und abgeschaltete Proxy-Pufferung. Verarbeitung im Server spätestens im nächsten 0,5-Sekunden-Takt, zusätzlich Netz-/Browserlatenz. Parameterliste, Hauptfensterregister und Übersicht nutzen diese Werte. SSE öffnet für sich keinen DTU-Socket und sendet keine Registerreads. Bei Übertragungsproblemen bleibt ein lesender Cache-Abruf alle 15 Sekunden als Rückfall erhalten. Für passiven Empfang zwischen aktiven Abfragen muss weiterhin Browser- oder Dauerverbindung gewählt sein.

Geprüft: 129 Backendtests, drei Frontendtests, Typecheck/Build. Neue Tests prüfen das FC03-Telegramm mit 90 Wörtern, acht sequenzielle Blöcke, Abbruch ohne Wiederholung/bei Anschlusswechsel, gemeinsame Jobs, ausblendbare Kopf-/virtuelle Werte, Cache-Alter/Quelle und SSE-Änderungen samt Entfernungen. Live-Abnahme folgt nach CI und Installation.
