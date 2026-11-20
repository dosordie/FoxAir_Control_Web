# FoxAir Control Web

**Deine FoxAir-/PHNIX-Wärmepumpe im Browser – am Computer, auf dem iPhone oder als App auf dem Homescreen.**

FoxAir Control Web zeigt den Anlagenzustand und Messwerte, macht Parameter durchsuchbar und ermöglicht das Ändern unterstützter Einstellungen. Die Anwendung läuft auf einem eigenen Linux-Server. Das Windows-Programm [FoxAir_Control](https://github.com/dosordie/FoxAir_Control) wird für den Betrieb nicht benötigt.

> **Beta – aktiv in Entwicklung.** Funktionen, Registerzuordnungen und Verbindungen werden laufend verbessert. Noch nicht jede Wärmepumpenvariante und jeder Anschluss sind getestet. Prüfe vor Änderungen, was ein Parameter bewirkt, und kontrolliere anschließend den zurückgelesenen Wert.

[Installation](docs/INSTALLATION.md) · [Erste Schritte](#erste-schritte) · [Verbindungen](#verbindungen) · [Fehler melden](https://github.com/dosordie/FoxAir_Control_Web/issues)

## So sieht die App aus

### Übersicht am Desktop

Temperaturen, Sollwert, Durchfluss und Anlagenzustand auf einen Blick. Darunter findest du elektrische und thermische Leistung, COP sowie den Schnellzugriff auf Funktionen und Einstellungen.

![Desktop-Übersicht mit Anlagenstatus, Temperaturen und Funktionskacheln](docs/screenshots/dashboard-desktop.png)

### Für das iPhone gemacht

Übersicht, Parameterliste und Details als Pop-up: Die Suche öffnet sich über die Lupe, Favoriten über den Stern. Nach dem Schließen eines Parameters bleibt die Listenposition erhalten.

<table>
  <tr>
    <th>Übersicht</th>
    <th>Parameter finden</th>
    <th>Details und Readback</th>
  </tr>
  <tr>
    <td align="center"><strong>Übersicht</strong><br><a href="docs/screenshots/dashboard-iphone.png"><img src="docs/screenshots/dashboard-iphone.png" width="148" alt="iPhone-Übersicht mit Wärmepumpengrafik und Messwerten"></a></td>
    <td align="center"><strong>Parameterliste</strong><br><a href="docs/screenshots/parameters-iphone.png"><img src="docs/screenshots/parameters-iphone.png" width="148" alt="iPhone-Parameterliste mit Gruppen, Suche und Favoriten"></a></td>
    <td align="center"><strong>Parameterdetails</strong><br><a href="docs/screenshots/parameter-details-iphone.png"><img src="docs/screenshots/parameter-details-iphone.png" width="148" alt="Parameterdetails mit Quelle, Beschreibung und Schreiben mit Readback"></a></td>
  </tr>
</table>

Die Screenshots zeigen Beispielzustände einer Anlage. Messwerte und verfügbare Funktionen hängen von Gerät und Verbindung ab.

## Was die App bietet

- **Übersicht:** Anlagenzustand, Temperaturen, Sollwert, Durchfluss, Verdichterfrequenz, elektrische und thermische Leistung sowie COP, soweit verfügbar.
- **Parameter finden:** Suche nach Code, Name oder Register, sortierte Gruppen und persönliche Favoriten. Auf dem Smartphone öffnen sich Details als Dialog.
- **Werte nachvollziehen:** Datenquelle, Zeitstempel, Beschreibungen und zuletzt bekannte Werte. Veraltete Werte werden entsprechend gekennzeichnet.
- **Einstellungen ändern:** Unterstützte, laut Katalog schreibbare Parameter als Administrator bearbeiten. Vorprüfung und Readback kontrollieren den Auftrag; lesende Register bleiben gesperrt.
- **Spezialfunktionen:** Dialoge für Zeitprogramme, Ruhemodus, SG-Ready, AT-Kurve, Wärmepumpen-Sollwerte und Störungen. Der Umfang hängt von Verbindung und bekannten Registerdefinitionen ab.
- **Verlauf & Diagramme:** Historische Cloud-Daten bei Bedarf über einen Button auf der Startseite öffnen.
- **Live-Anzeige:** Neu empfangene LTE-Buswerte erscheinen automatisch. Bei der Cloud steht eine automatische Abfrage zur Verfügung.
- **Homescreen-App:** Auf dem iPhone zum Home-Bildschirm hinzufügen. Die Oberfläche kann zwischengespeichert werden; aktuelle Messwerte und Schreibaufträge benötigen eine Serververbindung. Offline-Aufträge werden nicht nachträglich gesendet.

## Verbindungen

| Anschluss | Stand der Beta |
| --- | --- |
| **PHNIX Cloud** | Zugang und Geräteauswahl über die Einstellungen; Lesen und unterstützte Schreibfunktionen. Historische Diagramme benötigen den Cloud-Zugang. |
| **LTE-/Warmlink-Modbus über TCP** | IP und Port einstellbar; gebündeltes Lesen zusammenhängender Register, Live-Buswerte und unterstützte Schreibfunktionen. Verbindungsdauer konfigurierbar. |
| **Standard-Modbus** | RTU-over-TCP/ser2net; IP, Port und Teilnehmer in den Verbindungseinstellungen. Lesen und unterstützte Schreibfunktionen, standardmäßig deaktiviert. |
| **Display-Modbus** | Passiver Empfang über RTU-over-TCP; manuelle Spezialfunktion „Alle Werte vom Bus lesen“. Normale Parameter-Schreibzugriffe gesperrt, standardmäßig deaktiviert. |

Lokale Busse nur aktivieren, wenn Anschluss und Busbelegung geklärt sind. Ein anderer Dienst oder Bus-Master kann den Zugriff beeinflussen.

## Installation

Für den Server gibt es einen fertigen Frontend-Build aus GitHub Actions: **Node.js ist dort nicht erforderlich.** Die Anwendung verwendet ein eigenes Python-Virtualenv und einen eigenen systemd-Dienst.

Die [kurze Installationsanleitung](docs/INSTALLATION.md) führt durch Einrichtung, Administratorpasswort, ersten Zugriff und Updates. Die mitgelieferten Skripte verwenden den Beispielpfad `/opt/foxair-web/app` und starten zunächst nur auf `127.0.0.1:8081`.

## Erste Schritte

1. App über HTTPS oder einen lokalen SSH-Tunnel öffnen.
2. Oben rechts mit dem separat eingerichteten **Administratorpasswort** anmelden.
3. **Einstellungen → Verbindungseinstellungen** öffnen und Cloud-Zugang bzw. lokalen LTE-Anschluss einrichten.
4. Auf der **Übersicht** die gewünschte Verbindung auswählen und Messwerte kontrollieren.
5. Unter **Parameter** eine Gruppe wählen oder die Lupe verwenden. Mit dem Stern lassen sich Favoriten filtern.
6. Einen Parameter antippen. Falls unterstützt, lässt sich ein neuer Wert mit **„Wert mit Readback senden“** übertragen.

Ohne Admin-Anmeldung ist lesender Zugriff möglich. Die lokale Admin-Sitzung bleibt bis zu 30 Tage bestehen und überlebt Dienstneustarts; das Passwort wird nicht im Browser gespeichert.

## Benutzer, Protokoll und Sicherung

Unter **Einstellungen → Benutzer & Berechtigungen** können Administratoren lokale Konten, SSO-Zuordnungen und Sitzungen verwalten. Leser sehen Messwerte; Bediener dürfen einzeln freigegebene MAIN-Register ändern. Administratoren verwalten Verbindungen und Updates. Das bestehende Konto `admin` bleibt als Notfallzugang erhalten.

Schreibaufträge erscheinen im privaten Änderungsprotokoll. Verschlüsselte Sicherungen umfassen lokale Benutzer, Cloud-Zugang und LTE-Einstellungen; Proxy-Secrets und das Notfallpasswort werden separat verwaltet. Zur Wiederherstellung ist das Sicherungspasswort erforderlich.

Hinweise zur Einrichtung und zum Display-Protokoll: [Lokale Modbus-Anschlüsse](docs/LOCAL_MODBUS.md).

## Zugriff und private Konfiguration

Die Anmeldung schützt schreibende und administrative Aktionen nach Rolle. **Lesender Gastzugriff ist standardmäßig erlaubt und kann in der Benutzerverwaltung deaktiviert werden.** Für einen öffentlichen Zugang ist deshalb ein vorgeschalteter Zugriffsschutz mit HTTPS nötig, beispielsweise Nginx mit Authelia.

Optionales Trusted-Proxy-SSO ist vorhanden und **standardmäßig deaktiviert**. Es benötigt eine ausdrücklich vertrauenswürdige Proxy-IP, ein gemeinsames Secret und eine feste Zuordnung zum vorhandenen lokalen Administratorkonto. Generische Beispiele liegen unter [deploy/](deploy/).

Zugangsdaten und anlagenspezifische Einstellungen gehören ausschließlich in die private Serverkonfiguration. **Keine echten IP-Adressen, Benutzernamen, Passwörter oder unbereinigten Diagnosedaten in Issues und Commits veröffentlichen.**

## Updates und Hilfe

Eine vorhandene Installation aktualisieren:

```bash
cd /opt/foxair-web/app
sudo bash scripts/update.sh
```

Der passende GitHub-Build muss zuvor erfolgreich abgeschlossen sein. Optional kann ein Updateknopf in der Weboberfläche eingerichtet werden; siehe [Installationsanleitung](docs/INSTALLATION.md#updates).

Ein Problem gefunden? Bitte ein [Issue öffnen](https://github.com/dosordie/FoxAir_Control_Web/issues) und diese Angaben ergänzen:

- installierter Commit bzw. angezeigte Version,
- verwendete Verbindung, Browser und Gerät,
- erwartetes Verhalten, tatsächliches Verhalten und Schritte zum Nachstellen,
- bereinigter Screenshot oder kurzer Diagnoseauszug, soweit hilfreich.

## Für Mitwirkende

Vue 3 und TypeScript bilden das Frontend, FastAPI das Python-Backend. Register und Bezeichnungen stammen aus einem geprüften Snapshot von [FoxAir_Control](https://github.com/dosordie/FoxAir_Control).

- [Wartung und Code-Struktur](docs/MAINTENANCE.md)
- [Register-Snapshot und Synchronisierung](docs/SNAPSHOT_SYNC.md)
- [Allgemeine Deployment-Hinweise](docs/DEPLOYMENT.md)
- [Lokale Entwicklungsumgebung](docs/INSTALLATION.md#lokal-entwickeln)

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE), entsprechend der [Lizenzdatei von FoxAir_Control](https://github.com/dosordie/FoxAir_Control/blob/main/LICENSE).

Copyright (c) 2026 DosOrDie.

Optionale zusätzliche HomeServer-Werte: [Gira-Experteneinstellungen (Beta)](docs/GIRA.md).

Der Entwicklungszweig `work` erhält einen eigenen passenden Web-Build. Der geplante gemeinsame Releaseweg für Linux und Docker ist in [Releases und Updates](docs/RELEASES.md) beschrieben; `v0.1.0` ist noch nicht veröffentlicht.
