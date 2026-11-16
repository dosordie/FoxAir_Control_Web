# Deployment (allgemein)

Dieses öffentliche Repository beschreibt **keine konkrete private Serverumgebung**. Interne Dienstnamen, Hostnamen, Netzadressen, Containerkennungen, Ressourcenmessungen, Benutzer und Installationspfade gehören in private Betriebsdokumentation.

## Getrennter Betrieb neben vorhandenen Anwendungen

- Eigener unprivilegierter Benutzer und eigener Dienstprozess.
- Separates Python-Virtualenv, unabhängig von anderen Programmen.
- Eigene Konfiguration, State-Dateien und Logs außerhalb des Quellcodes.
- Eigener Backend-Port, TLS über einen vorgeschalteten Reverse Proxy.
- Unabhängige Aktualisierung und Neustarts ohne Einfluss auf andere Dienste.
- Passende CPU-/RAM-/I/O-Grenzen und Überwachung, keine Build-Prozesse im Produktionsbetrieb.
- Lokale Modbus-Endpunkte ausschließlich aus serverseitiger, nicht eingecheckter Konfiguration verwenden.
- Vor öffentlichem Zugriff zuverlässige Authentifizierung, möglichst MFA, Firewall-Regeln und serverseitige Schreibvalidierung einrichten.

Beispiel-Konfigurationsfelder sind `<APP_HOST>`, `<APP_PORT>` und `<MODBUS_HOST>`; reale Werte nicht in GitHub-PRs, Issues oder CI-Logs veröffentlichen.

## Abnahme

Anwendung und andere Dienste funktionieren parallel; Neustarts sind isoliert, im Idle bleiben keine unnötigen ser2net-Sockets offen und der Reverse Proxy schützt alle API-Endpunkte.
