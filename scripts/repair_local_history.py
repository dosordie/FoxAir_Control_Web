"""Attach one orphaned FoxAir history archive to the current installation."""

from contextlib import closing
from datetime import datetime, timezone
import sqlite3

from backend import local_history
from backend.cloud_config import STATE_DIR
from backend.last_values import installation_key


def repair(path, target):
    if not path.is_file():
        raise SystemExit("Archivdatei fehlt.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"local-history.backup-{stamp}.sqlite")
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        tables = set(
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE name IN ('history', 'defrost')"
            )
        )
        if not tables:
            raise SystemExit("Keine Archivtabellen gefunden.")
        orphaned = {
            scope
            for table in tables
            for (scope,) in db.execute(
                f"SELECT DISTINCT scope FROM {table} WHERE scope != ?", (target,)
            )
        }
        if not orphaned:
            print("Alle Archiveinträge sind bereits zugeordnet.")
            return
        if len(orphaned) != 1:
            raise SystemExit(
                "Mehrere alte Archivzuordnungen gefunden. Keine Änderungen vorgenommen."
            )
        source = orphaned.pop()
        backup.touch(mode=0o600, exist_ok=False)
        with closing(
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as reader:
            with closing(sqlite3.connect(backup)) as destination:
                reader.backup(destination)
        print(f"Sicherung: {backup}")
        try:
            counts = {
                table: db.execute(
                    f"UPDATE {table} SET scope=? WHERE scope=?", (target, source)
                ).rowcount
                for table in sorted(tables)
            }
        except sqlite3.IntegrityError:
            raise SystemExit(
                "Archivzeiträume überschneiden sich. Keine Änderungen am Original vorgenommen."
            ) from None
    for table, count in counts.items():
        print(f"{table}: {count} Einträge wieder zugeordnet")


if __name__ == "__main__":
    repair(
        STATE_DIR / "local-history.sqlite",
        getattr(local_history, "ARCHIVE_SCOPE", None) or installation_key(),
    )
