# FoxAir Control Web

Responsive Web-App / PWA für FoxAir-/PHNIX-Wärmepumpen.

**Projektstatus:** Initialplanung. Diese Web-App ist ein eigenständiges Projekt; sie ersetzt nicht das Windows-Diagnosetool [FoxAir_Control](https://github.com/dosordie/FoxAir_Control).

## Ziel

- WarmLink-ähnliche Übersichtsseite mit Betriebszustand, Temperaturen und wichtigen Livewerten.
- Von der Übersicht per Button in die Parameter-/Einstellungsansicht.
- PHNIX-/Linked-Go-Cloud sowie lokale Modbus-Verbindungen über bestehende ser2net-Gateways.
- Speichern der zuletzt gewählten Verbindungsart.
- Lokale ser2net-Verbindungen im On-Demand-Modus nur während konkreter Abfragen öffnen; optionaler Livebetrieb mit automatischem Timeout.
- Ein responsives Frontend für iPhone und Desktop.
- Registerkatalog und Cloud-Mappings aus dem Quellprojekt FoxAir_Control übernehmen statt parallel zu pflegen.

## Geplante Komponenten

- Backend: Python / FastAPI
- Frontend: Vue 3 / TypeScript / Vite (PWA)
- Deployment: Debian LXC in Proxmox hinter vorhandenem Nginx-Reverse-Proxy/ACME.
- Verbindungsarten: Cloud, Standard-Modbus, Display-Modbus und Warmlink-/LTE-Modbus (serielles RTU via ser2net, kein MBAP-Modbus-TCP).

## Sicherheitsprinzipien

Konfiguration und Cloud-Geheimnisse nur im Backend; kein ungeprüfter Registerwrite, kein stillschweigender Transport-Fallback, keine unkontrollierte Dauersitzung auf fremden RS485-Bussen.

Die App ist derzeit **noch nicht implementiert oder produktiv nutzbar**.
