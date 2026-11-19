# Optionale Gira-Anzeigen (Beta)

Als Administrator **Einstellungen → Experteneinstellungen** öffnen. Die Funktion ist standardmäßig aus und gehört nicht zur normalen Wärmepumpen-Einrichtung.

1. Gira-Anzeigen aktivieren, private HomeServer-IP, Port und WebSocket-Pfad eintragen.
2. Bei Bedarf Benutzername und Passwort ergänzen. Ein leeres Passwortfeld behält das gespeicherte Passwort; zum Entfernen gibt es eine eigene Auswahl.
3. Objekte mit Schlüssel (z. B. `CO@123`), Bezeichnung und optionaler Einheit hinzufügen. Bis zu 24 Objekte sind möglich. Numerische Schlüssel werden wie im Referenzadapter mit `CO@` ergänzt.
4. Speichern. Die benannten Werte erscheinen unter den Leistungs-/COP-Anzeigen in „Auf einen Blick“. Zahlen und Texte werden unterstützt; ein noch nicht empfangener Wert erscheint als Strich.

Der Server hält genau einen eigenen Gira-WebSocket. Er sendet ausschließlich `subscribe` für die eingetragenen Schlüssel und empfängt danach Werte. Es gibt keine Gira-Schreibfunktion, keinen frei eingebbaren Befehl und keinen direkten Browserzugriff auf den HomeServer. Die Wärmepumpen-Verbindungswahl wird dadurch nicht verändert.

Anmeldung und JSON-Formate entsprechen dem überprüften Referenzstand [ioBroker.gira-endpoint](https://github.com/dosordie/ioBroker.gira-endpoint/tree/c276c287fcb2217942ddb0ef7f1a1334a4ef4f41), insbesondere `src/lib/GiraClient.ts` und den Subscribe-/Push-Zuordnungen in `src/main.ts`. Standard ist das dortige `authorization`-URL-Verfahren; alternativ ist ein Basic-HTTP-Header wählbar. TLS prüft das Zertifikat gegen den System-Vertrauensspeicher. Ein selbstsigniertes Zertifikat muss dort administrativ eingerichtet sein.

Zugangsdaten liegen nur in der privaten `gira.json`, werden nicht zurück an den Browser ausgegeben und sind in der verschlüsselten Sicherung enthalten. Die GUI zeigt Objektbezeichnungen und Werte gemäß derselben Leseberechtigung wie die Wärmepumpenwerte. Beim Wiederherstellen oder Ändern der Konfiguration werden alte Werte nicht unter neue Bezeichnungen übernommen. Bei Ausfällen erfolgt eine begrenzte Wiederverbindungsrate; letzte Werte sind als veraltet gekennzeichnet.

Die automatisierte Abnahme verwendet einen lokalen WebSocket-Simulator mit Zahlen- und Textwerten. Die Verbindung zu einem konkreten HomeServer muss anschließend mit dessen privaten Zugangsdaten geprüft werden.
