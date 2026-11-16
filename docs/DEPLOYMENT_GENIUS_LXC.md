# Deployment auf Genius-Gateway-LXC (CT 103)

Stand: 2026-11-16. **Planungsstand; noch nicht installiert.** Die Werte unten stammen aus der einmaligen Benutzermessung im laufenden LXC und sind keine Langzeitmetriken.

## Zielsystem

- Proxmox-Knoten: `PVE-Keller`, unprivilegierter Debian-LXC `103` (Genius-Gateway)
- LXC-IP (beobachtet): `192.0.2.59`
- Bestehender Dienst: `genius-gateway.service`, TCP `0.0.0.0:8080` (Python, PID 1942 im Messzeitpunkt)
- Weitere belegte TCP-Ports: `:22` (SSH), `127.0.0.1:25` und `[::1]:25` (Postfix)
- Port `:8081` beim Messzeitpunkt frei
- Bestehender Nginx-Reverse-Proxy mit ACME läuft **außerhalb** des LXC. Deswegen muss der FoxAir-Upstream auf einer erreichbaren LXC-LAN-IP lauschen, nicht nur auf Loopback. Eingehenden Zugriff auf Port 8081 im Netzwerk/auf Firewall auf Reverse Proxy und ggf. Adminnetz beschränken.

## Ressourcen zum Messzeitpunkt

| Kennzahl | Ist |
| --- | ---: |
| vCPU | 1 |
| RAM-Limit | 512 MiB |
| used / available RAM (`free -h`) | 51 MiB / 460 MiB |
| Swap | 40 MiB von 512 MiB |
| Rootdisk | 4.0 GiB, 1009 MiB belegt, ca. 3.1 GiB frei |
| Genius-Hauptprozess | ca. 31 MiB RSS, ca. 3,9 % CPU |
| systemd-journald | ca. 19 MiB RSS |

**Bewertung:** Für einen gelegentlich genutzten FastAPI-Dienst zunächst **keine Erhöhung der LXC-Grenzen erforderlich**. FoxAir-Builds (Vue/Vite/npm) außerhalb des Produktionscontainers erzeugen, nur fertige statische Assets installieren. Aktiven Swap-Verkehr, RSS-Spitzen und CPU-Spitzen vor und nach Installation beobachten; 40 MiB *belegter* Swap allein beweist keinen aktuellen Speicherdruck. Falls signifikante Engpässe entstehen, zuerst RAM auf 1 GiB, ggf. vCPU auf 2 und Rootdisk auf 8 GiB erhöhen. Keine Änderungen am laufenden CT ohne separate Freigabe.

## Eigenständige Anwendungsisolation

| Funktion | Genius (bestehend) | FoxAir (neu) |
| --- | --- | --- |
| systemd | `genius-gateway.service` | `foxair-web.service` |
| Dienstbenutzer | `genius-gateway` | `foxair-web` (neu) |
| Python venv | `/opt/genius-gateway/venv` | `/opt/foxair-web/venv` |
| Code | `/opt/genius-gateway/app` | `/opt/foxair-web/app` |
| Konfiguration | `/etc/genius-gateway/` | `/etc/foxair-web/` |
| State | `/var/lib/genius-gateway/` | `/var/lib/foxair-web/` |
| Listen-Port | 8080 | 8081 |
| Prozess | eigenständig | eigenständig |
| Update | Genius-eigene Skripte | FoxAir-eigene Skripte |

Die FoxAir-Installation darf **keine Genius-Pakete per pip/apt verändern**, keine Genius-Konfiguration, keinen Genius-State, keine bestehenden systemd-Units oder Update-Skripte überschreiben und den Genius-Dienst weder neu starten noch auf ihn verweisen.

Technisch teilen sich Prozesse weiterhin denselben Host-Kernel, vCPU, RAM, I/O und Netzwerk. Vollständige Fehler-/Sicherheitsisolation wäre nur mit einem eigenen LXC möglich. Die hier gewählte Prozess-/Serviceisolation ist ein Kompromiss gemäß Anforderung „gleicher CT“.

## Vorgesehene systemd-Schutzmaßnahmen für FoxAir

- `User=foxair-web`, `Group=foxair-web`, eigene restriktive Pfadberechtigungen
- `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`, `ReadWritePaths=/var/lib/foxair-web`; später weitere Sandbox-Regeln nach Integrationstests
- `CPUWeight=25`, `IOWeight=25` (beide nur relativ gegenüber Mitbewerbern auf geeigneten Cgroups; keine garantierte Echtzeitpriorisierung)
- optional `MemoryHigh=128M`, `MemoryMax=256M`, erst nach Messung des realen Speicherbedarfs aktivieren; beim 512-MiB-CT kein unbegrenzter Worker-/Build-Betrieb
- Ein Uvicorn-Worker zum Start; keine automatischen Reload-/Debug-Modi im Produktionsbetrieb
- Keine Dauerpolls im Idle: on-demand ser2net-Verbindungen, Browser-Lease-Timeouts, kleine Request-Queues
- eigene Journald-Kennung; Log-Limits; niemals Credentials oder Session-Tokens loggen
- Deployment- und Update-Rollback getrennt vom Genius-Gateway

**Hinweis:** Niedriges CPUWeight begrenzt nicht die gesamte CPU-Nutzung bei Leerlauf, und MemoryMax kann FoxAir per OOM beenden. Die Zielwerte sind Startideen, müssen vor Aktivierung real geprüft werden.

## Netzwerk

```text
iPhone / Desktop
   HTTPS
      |
      v
separater Nginx-LXC mit ACME + Auth
  |                                |
  | vorhandener Genius-Upstream    | neuer FoxAir-Upstream
  v                                v
192.0.2.59:8080              192.0.2.59:8081
genius-gateway.service          foxair-web.service
                                    |          |
                                    v          v
                              PHNIX HTTPS   LAN ser2net (raw RTU)
```

- Externer Hostname separat (z. B. `foxair.<eigene-domain>`, Name bewusst noch nicht festgelegt).
- FoxAir-Endpunkt für Reverse Proxy erreichbar, kein ungeschützter Port 8081 aus dem Internet.
- Cloud-Ausgangszugriff auf den im FoxAir_Control-Core konfigurierten Provider-Endpunkt; ser2net-Ziele nur statisch serverseitig erlauben.
- TLS-Terminierung am bestehenden Nginx; `X-Forwarded-*` nur vom vertrauenswürdigen Proxy akzeptieren.
- Separate Authentifizierung/Sitzungen; kein Wiederverwenden der Genius-Session-Cookies.
- Für Änderungen kritischer Parameter: serverseitige Prüfungen, CSRF-Schutz, SameSite/HttpOnly/Secure-Cookies und bestätigter Write-Readback.

## Noch abzuklären / vor Installation prüfen

- Aktuelle LXC-Grenzen und etwaige Cgroup-CPU-/Memory-Limits prüfen; insbesondere Proxmox-CPU-Pressure und Speicherlastspitzen.
- Proxy-LXC-IP für Firewall-Freigabe und endgültigen DNS-Namen ermitteln.
- Ser2net-Adressen und Ports der FoxAir-Busse konfigurieren, keine fremden Geräte scannen.
- Disk-Reserve für Python-Venv, Cache und Journals nach Installation prüfen.
- Inbetriebnahme mit `foxair-web.service` ohne RF-/Genius-Konfigurationsänderungen; Smoke-Test beider Web-UIs und `systemctl status genius-gateway.service`.
- Veeam/Proxmox-Backups einbeziehen; vor Änderung am produktiven LXC Backup/Snapshot nach Betriebsanforderungen erstellen.

## Messbefehle (read-only)

```bash
systemctl status genius-gateway.service --no-pager
ss -lntup
free -h
df -h /
ps -eo pid,comm,rss,%cpu --sort=-rss | head -20
vmstat 1 5
```
