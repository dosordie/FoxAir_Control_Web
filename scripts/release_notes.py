"""Render the required changelog section for a GitHub release."""

import argparse
import re
import sys
from pathlib import Path


def render_release_notes(tag: str, changelog: str, *, prerelease: bool = False) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"Invalid release tag: {tag}")

    sections = re.split(r"^## ", changelog, flags=re.MULTILINE)[1:]
    changes = []
    for section in sections:
        heading, _, body = section.partition("\n")
        if heading.strip() == tag:
            changes.append(body.strip())
    if len(changes) != 1 or not re.search(r"^- \S", changes[0], flags=re.MULTILINE):
        raise ValueError(f"Expected one nonempty '## {tag}' section in CHANGELOG.md")

    repository = "https://github.com/dosordie/FoxAir_Control_Web"
    if prerelease:
        compose = f"{repository}/releases/download/{tag}/compose.yaml"
        installation = (
            f"Für Docker die [compose.yaml]({compose}) herunterladen und "
            "`docker compose up -d` ausführen. Das Linux-Archiv für diese "
            "Vorabversion liegt unter den Release-Assets."
        )
    else:
        readme = f"{repository}/blob/{tag}/README.md"
        installation = (
            f"Installation: [Docker]({readme}#docker-im-heimnetz) · "
            f"[Linux mit systemd]({readme}#linux-mit-systemd)"
        )
    return f"## Änderungen in {tag}\n\n{changes[0]}\n\n{installation}\n"



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Release tag, for example v0.1.5")
    parser.add_argument("--prerelease", action="store_true")
    args = parser.parse_args()

    changelog = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    try:
        notes = render_release_notes(
            args.tag, changelog.read_text(encoding="utf-8"), prerelease=args.prerelease
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(notes)


if __name__ == "__main__":
    main()
