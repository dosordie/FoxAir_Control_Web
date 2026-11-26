# Änderungen

## v0.1.15

- Der Update-Button in der Kopfzeile öffnet direkt den Updatebereich in den Einstellungen.
- Standard- und Sieben-Punkt-Heizkurve zeigen Außentemperatur und Sollwert am Mauszeiger. Stützpunkte der Sieben-Punkt-Kurve lassen sich ziehen und gemeinsam mit Rücklesebestätigung speichern. Die lineare Kurve zeigt Steigung und Offset, bei ausgeschalteter Kurve bleibt die Moduswahl sichtbar.
- In beiden Dashboard-Bereichen lassen sich alle verfügbaren Kacheln auswählen und am Griff per Maus oder Finger sortieren. Die Pfeiltasten bleiben verfügbar.
- **Umwälzpumpe · Rückmeldung** (Register 2116) und **Letztes Abtauen** sind in beiden Bereichen auswählbar. Die Abtau-Kachel zeigt Stunden und Minuten seit dem letzten archivierten Abtauende.
- Gira-WebSocket: HomeServer-Verbindung und einzelne KNX-Objekte lassen sich separat aufklappen. Objektschlüssel können mit oder ohne `CO@` eingegeben werden.
- Die Sollwertabweichung hat am Desktop eine dünnere Schrift. Negative Werte sind heller blau, positive kräftiger rot.

## v0.1.14

- Die Abweichung zwischen Vorlauf und Sollwert ist kräftiger rot oder blau. Im Neutralbereich entspricht die Schriftfarbe dem aktuellen Sollwert.
- Timer und weitere Einstellungsdialoge zeigen letzte bekannte Werte aus dem gemeinsamen Speicher, auch nach einem Wechsel der Verbindung. Quelle und Abrufzeit bleiben sichtbar. Fehlende Timerfelder bleiben leer, Display-Modbus bleibt lesend.
- Einstellwerte werden nach zwölf Stunden als veraltet markiert. Die Übersicht weist darauf hin, wenn über die gewählte Verbindung seit mehr als 30 Minuten keine neuen Werte eintreffen.
- Die Kopfzeile zeigt bei SSO und lokaler Anmeldung den Benutzernamen. Die Rolle steht im geöffneten Benutzermenü.
- Kamera, Bedien- und Sollwertdialoge sowie die Messwertabfragen der Übersicht sind in eigene Frontend-Module aufgeteilt.

## v0.1.13

- Die Wärmepumpen-Kamera lässt sich unter **Experteneinstellungen → Kamera** aktivieren. Ein Klick auf die Wärmepumpengrafik öffnet das Kamerabild für angemeldete Benutzer. FoxWeb ruft die Kamera im privaten Netz serverseitig ab.
- Unterstützt werden MJPEG-Livestreams und JPEG-Einzelbilder mit einstellbarem Abrufintervall. Die Kamera wird nur abgefragt, solange das Pop-up geöffnet ist.
- Das Kamera-Pop-up nutzt am Desktop die Breite der Übersicht. Kamera und Gira-WebSocket haben eigene Abschnitte unter **Experteneinstellungen**.

## v0.1.12

- Die Kachel **Last Timer** zeigt die Leistungsgrenze von M1, seinen Status und das aktuelle Zeitfenster. Sie ist für den farbigen Bereich und **Auf einen Blick** auswählbar.
- Zeitprogramme sind über Display-Modbus lesbar. Standard-Modbus unterstützt auch das Speichern von Zeitprogrammen sowie Ein/Aus, Betriebsart und Ruhemodus direkt auf der Startseite.
- **Schalterzustände** zeigt Lastausgänge und Eingangskontakte in getrennten Reitern, auch mit bestätigten Cloudwerten. Die Anzeige berücksichtigt die unterschiedliche Schaltlogik der Eingangskontakte.
- Werte in der Übersicht lassen sich sortieren. Gira-Datenpunkte unterstützen eigene Symbole und einstellbare Nachkommastellen. Die Sollwertabweichung ist farblich hervorgehoben.
- Diagramme zeigen Messwerte am Mauszeiger oder beim Antippen. Der lokale Verlauf verbindet dichter beieinanderliegende Messpunkte und lässt längere Aufzeichnungslücken sichtbar.

## v0.1.11

- Die Kommunikationspause stoppt Cloud, Modbus, Gira und automatische Updateprüfungen. Gespeicherte Daten bleiben abrufbar.
- **Auf einen Blick** lässt sich getrennt für Smartphone und Tablet/PC konfigurieren. Die Symbole für Heizen und Abtauen sind am Desktop größer.
- Störmeldungen mit Klartext, SG-Ready, AT-Kurve und Wärmepumpe verwenden ihre bekannten lokalen Modbus-Register.
- Der lokale Verlauf lässt sich mit frei wählbarem Zeitraum als CSV exportieren. Neue Archiveinträge bleiben auch bei geänderten Verbindungseinstellungen sichtbar.
- Beim GUI-Update auf work prüft der Updater die Git-Historie nach dem getrennten Frontend-Abruf erneut, bevor er FoxAir stoppt.

## v0.1.10

- Zwei gemeinsame Dashboard-Profile für Smartphone und Tablet/PC mit auswählbaren Messwerten, Diagnose- und Gira-Werten sowie einstellbarer Spaltenzahl.
- Der aktuelle Heiz-Sollwert öffnet für Benutzer mit Schreibrecht den Editor für den Basissollwert mit Rücklesebestätigung.
- Optionaler lokaler Verlauf mit einstellbarer Aufbewahrung und Abtauvorgängen. Cloud- und lokale Diagramme haben beschriftete Achsen und zeigen Einzelwerte.
- Gira-Objekte können ohne Bezeichnung gespeichert werden. In den Registeranzeigen entfallen das Präfix MAIN und der doppelte Cloud-Code.
- Die Linux-Testinstallation auf work unterstützt GUI-Updates nach einmaliger Einrichtung des systemd-Helfers.

## v0.1.9

- Neue Linux-Installationen sind direkt im privaten Heimnetz auf Port 8081 erreichbar. Das Admin-Passwort wird beim ersten Aufruf im Browser vergeben.
- Bei bestehenden Linux-Diensten kann der LAN-Modus per `--lan-http` aktiviert werden. Updates behalten vorhandene Netzwerkeinstellungen und Konten bei.
- Die Linux-Anleitung beschreibt das Update per Serverterminal oder SSH.

## v0.1.8

- Unter **Webzugriff** können Administratoren die IP-Adressen vertrauenswürdiger HTTPS-Reverse-Proxys direkt speichern.
- Die Anmeldung erklärt Adressabweichungen und HTTPS-Probleme. Die Einstellungsseite zeigt den Anmeldestatus und bietet Gästen einen Anmeldebutton.
- Webzugriff und Experteneinstellungen stehen am Ende der Einstellungsseite.

## v0.1.7

- Administratoren können zusätzliche Hostnamen für Docker unter **Einstellungen → Webzugriff** freigeben. Die Freigabe gilt sofort, auch für Namen eines Reverse Proxys.
- Bei einem gesperrten Hostnamen erklärt FoxAir Web, wie du ihn über die lokale IP-Adresse freigibst.

## v0.1.6

- Modbus-Standard, Modbus-LTE und Modbus-Display unterstützen neben IP/TCP auch USB-RS485.
- Die Modbus-Diagnose unterscheidet zwischen Fehlern beim TCP-Verbindungsaufbau und fehlenden Antworten auf dem Bus. Wenn ein zweiter Client eine mögliche Ursache ist, zeigt FoxAir Web einen Hinweis.
- Bei einer offenen Display-Modbus-Verbindung zeigt die Übersicht an, wenn FoxAir Web noch auf gültige Telegramme lauscht.

## v0.1.5

- Die Übersicht heißt jetzt „Live-Registerübersicht“. Die Verbindungseinstellungen zeigen Cloud, Modbus-Standard, Modbus-LTE und Modbus-Display in dieser Reihenfolge.
- Standard-Modbus hält die Verbindung standardmäßig offen, solange ein Browser verbunden ist.
- Die README erklärt die Installation mit Docker und Linux sowie die unterstützten Verbindungen.

## v0.1.4

- Die installierte Version steht in der Kopfzeile und in den Einstellungen. Die App prüft beim Öffnen und alle 15 Minuten im sichtbaren Tab auf Updates.
- Docker und Linux erhalten ihre stabilen Releases aus demselben Commit. Docker bietet zusätzlich das laufende Tag `latest`.

## v0.1.3

- Das erste Admin-Passwort lässt sich direkt im Browser einrichten. Danach meldet die App den Administrator automatisch an.
- Die Docker-Ersteinrichtung akzeptiert LAN-Hostnamen und merkt sich den bei der Einrichtung verwendeten Namen.

## v0.1.2

- Docker akzeptiert neben LAN-IP-Adressen ausdrücklich konfigurierte Hostnamen, etwa `docker.box`.

## v0.1.1

- Die Docker-Compose-Vorlage macht die Weboberfläche auf Port 18081 über die LAN-IP des Servers erreichbar.
- Das passende Docker-Image steht auf GHCR bereit.

## v0.1.0

- Erste öffentliche Vorschau für Docker und Linux mit systemd.
- Die Ersteinrichtung legt das Admin-Konto im Browser an.
- Die Übersicht zeigt die Pumpenansteuerung als „UP“. Längere Gira-Textwerte werden umgebrochen.
