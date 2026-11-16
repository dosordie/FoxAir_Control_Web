#!/usr/bin/env python3
"""Refresh ONLY register JSON snapshots from a reviewed FoxAir_Control commit.

Usage: python scripts/sync_registers.py --ref <reviewed_upstream_commit_sha>
Review git diff before merging. Never replace the runtime mapping via a live,
unverified 'main' fetch. Stdlib only.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "foxair_phnix_registers.json",
    "foxair_phnix_display_registers.json",
    "foxair_phnix_knowledge.json",
)
UPSTREAM = "dosordie/FoxAir_Control"


def checksum(content: str) -> str:
    """Ignore checkout newline conversion, preserve every other source byte."""
    return hashlib.sha256(content.replace('\r\n', '\n').encode('utf-8')).hexdigest()


def validate(downloads: dict[str, str]) -> None:
    docs = {name: json.loads(content) for name, content in downloads.items()}
    for name, doc in docs.items():
        if not isinstance(doc, dict) or len(doc) < 20:
            raise ValueError('Unplausible Registerdatei: ' + name)
        for number, entry in doc.items():
            if number.startswith('_'):
                continue
            # Display catalog also contains virtual diagnostic IDs above 65535.
            # These IDs describe projections and must never become RTU addresses.
            if not number.isdigit() or not isinstance(entry, dict):
                raise ValueError(f'Ungültiger Registereintrag: {name}/{number}')
            if name != FILES[2]:
                for field in ('name', 'type'):
                    if not isinstance(entry.get(field), str) or not entry[field].strip():
                        raise ValueError(f'Fehlendes Feld: {name}/{number}/{field}')
                if 'mode' in entry and entry['mode'] not in ('read', 'read-only', 'r/w', 'service'):
                    raise ValueError(f'Unbekannte Schreibrechte: {name}/{number}')
                if 'value_map' in entry and not isinstance(entry['value_map'], dict):
                    raise ValueError(f'Ungültige Wertetabelle: {name}/{number}')
    known = set(docs[FILES[0]]) | set(docs[FILES[1]])
    if any(n not in known for n in docs[FILES[2]] if not n.startswith('_')):
        raise ValueError('Wissenskatalog verweist auf unbekannte Register')


def manifest(ref: str, downloads: dict[str, str]) -> dict:
    return {'repository': UPSTREAM, 'ref': ref.lower(), 'managed_files': list(FILES),
            'checksum_format': 'sha256-utf8-lf',
            'sha256': {name: checksum(downloads[name]) for name in FILES}}


def verify(target: Path) -> None:
    recorded = json.loads((target / 'upstream.json').read_text(encoding='utf-8'))
    downloads = {name: (target / name).read_text(encoding='utf-8') for name in FILES}
    validate(downloads)
    if recorded != manifest(recorded['ref'], downloads):
        raise ValueError('Snapshot-Prüfsummen oder Herkunft stimmen nicht überein')


def download(ref: str, name: str) -> str:
    url = f"https://raw.githubusercontent.com/{UPSTREAM}/{ref}/data/{name}"
    req = Request(url, headers={"User-Agent": "FoxAir-Control-Web-register-sync"})
    with urlopen(req, timeout=15) as res:
        return res.read().decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", help="40-character reviewed upstream commit SHA")
    parser.add_argument("--check", action="store_true", help="Validate committed snapshot without network access")
    args = parser.parse_args()
    if args.check:
        verify(ROOT / 'data')
        print('Register-Snapshot: Schema, Referenzen und Prüfsummen gültig')
        return
    ref = (args.ref or '').strip().lower()
    if len(ref) != 40 or any(ch not in "0123456789abcdef" for ch in ref.lower()):
        parser.error("--ref must be a 40-character commit SHA")
    target = ROOT / "data"
    target.mkdir(exist_ok=True)
    downloads = {}
    for name in FILES:
        content = download(ref, name)
        downloads[name] = content
    validate(downloads)  # All files must pass before replacing any snapshot.
    for name, content in downloads.items():
        (target / name).write_text(content, encoding="utf-8", newline='\n')
        print(name, len(content.encode('utf-8')), "bytes")
    (target / "upstream.json").write_text(
        json.dumps(manifest(ref, downloads), indent=2) + "\n",
        encoding="utf-8", newline='\n',
    )


if __name__ == "__main__":
    main()
