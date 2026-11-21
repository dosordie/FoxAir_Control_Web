# Änderungen

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
