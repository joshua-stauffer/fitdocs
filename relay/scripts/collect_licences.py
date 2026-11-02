"""Copy the licence files of every installed distribution into one directory.

Run by the image build with the relay environment's own interpreter, standard
library only:

    /opt/fitdocs-relay/bin/python scripts/collect_licences.py <destination>

For each installed distribution the destination gets a directory
`<name>-<version>/` holding the distribution's licence, copying and notice
files. A distribution that ships none gets `LICENCE-METADATA.txt` instead,
quoting what its metadata declares (or saying it declares nothing); no text is
invented.
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import Distribution, distributions
from pathlib import Path

_LICENCE_FILE = re.compile(r"(licen[cs]e|copying|notice|authors)", re.IGNORECASE)
METADATA_FILE = "LICENCE-METADATA.txt"


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]", "_", part)


def directory_name(dist: Distribution) -> str:
    return f"{_safe(dist.metadata['Name'])}-{_safe(dist.version)}"


def _licence_files(dist: Distribution) -> list[Path]:
    found: list[Path] = []
    for entry in dist.files or ():
        if _LICENCE_FILE.search(entry.name):
            located = Path(str(dist.locate_file(entry)))
            if located.is_file():
                found.append(located)
    return found


def _declared(dist: Distribution) -> str:
    lines = []
    for field in ("License-Expression", "License"):
        for value in dist.metadata.get_all(field) or ():
            lines.append(f"{field}: {value.strip()}")
    for classifier in dist.metadata.get_all("Classifier") or ():
        if classifier.startswith("License ::"):
            lines.append(f"Classifier: {classifier}")
    if not lines:
        lines.append("The distribution's metadata declares no licence.")
    return "\n".join(lines) + "\n"


def collect(destination: Path) -> list[str]:
    """Write the licence directories; return the directory names written."""
    destination.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for dist in distributions():
        target = destination / directory_name(dist)
        target.mkdir(exist_ok=True)
        files = _licence_files(dist)
        for source in files:
            copy_to = target / source.name
            suffix = 1
            while copy_to.exists():
                suffix += 1
                copy_to = target / f"{suffix}-{source.name}"
            copy_to.write_bytes(source.read_bytes())
        if not files:
            (target / METADATA_FILE).write_text(_declared(dist), encoding="utf-8")
        written.append(target.name)
    return sorted(written)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: collect_licences.py <destination>", file=sys.stderr)
        return 2
    names = collect(Path(argv[1]))
    print(f"collected licences for {len(names)} distributions")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
