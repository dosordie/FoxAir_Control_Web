# FoxAir Control Web

Responsive Web-App / PWA für FoxAir-/PHNIX-Wärmepumpen. Ein **eigenständiges Projekt**, das das Windows-Diagnosetool [FoxAir_Control](https://github.com/dosordie/FoxAir_Control) nicht ersetzen und nicht im Dauerbetrieb benötigen soll.

## MVP 0.1

- WarmLink-inspirierte **Übersichtsseite** für iPhone und Desktop mit Wärmepumpenillustration, Betriebszustand, Temperaturen, Durchfluss und Sollwertanzeige.
- **Parameter / Einstellungen** per Button erreichbar: Suchfunktion nach Code/Registernummer/Name, Details, einzelne Reads.
- Letzter Transport pro Browser gespeichert.
- FoxAir_Control-Registerdatenbank als überprüfter Snapshot ohne parallele manuelle Pflege.
- **Standard-Modbus read-only** über rohes ser2net/RTU: nur während einer Abfrage geöffnet. **Keine aktive Display-/LTE-Multi-Master-Kommunikation** in dieser Version.
- FastAPI + Vue 3/TypeScript/Vite und PWA-Manifest.
- GitHub Actions prüfen Python-Backend und Frontend-Build.

**Grenze:** Cloud-Adapter, Live-Leases, Sollwertschreiben und alle schreibenden Parameterfunktionen sind noch nicht implementiert. Die angezeigten `—` sind echte *fehlende* Werte, keine Simulationen.

**Sicherheit:** Die erste Implementierung hat noch **keine eigene Authentifizierung**. Nicht ohne Nginx-Zugriffsschutz/MFA, Firewallbegrenzung und Abschluss der Sicherheitsprüfung ins Internet stellen.

### Schnellstart zum lokalen Test

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8081
```

In einem zweiten Terminal:

```bash
cd frontend
npm install
npm run dev
```

Dann `http://127.0.0.1:5173/` öffnen. Ohne ser2net-Konfiguration ist die Benutzeroberfläche inklusive Registerbrowser sichtbar, aber es werden keine Livewerte vorgetäuscht.

Alle Details: [MVP-Test und Betrieb](docs/RUN_MVP.md), [Architektur](docs/ARCHITECTURE.md), [UX](docs/UX.md), [Deployment im Genius-LXC CT 103](docs/DEPLOYMENT_GENIUS_LXC.md).

## Lizenz

Vor einer Veröffentlichung/Kopplung der Quellmodule ist die widersprüchliche Lizenzangabe des Upstream-Projekts (README vs. LICENSE) zu klären. Die Quellcode-Synchronisierung erfordert einen geprüften Upstream-Commit.
