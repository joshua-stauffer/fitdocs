"""Stage a series for consumers that do not run the drain."""

from collections import Counter
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path

from fitdocs.wellness.model import SeriesValue
from fitdocs.wellness.series import Manifest, ManifestFile, encode_manifest, encode_year


def write_series(data_root: Path, values: Iterable[SeriesValue]) -> tuple[Path, ...]:
    items = tuple(values)
    keys = [(item.day, item.metric, item.source) for item in items]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate day, metric and source")
    groups = {(item.day, item.metric) for item in items}
    canonicals = Counter((item.day, item.metric) for item in items if item.canonical)
    if any(canonicals[group] != 1 for group in groups):
        raise ValueError("exactly one canonical value required per day and metric")
    files = []
    staged = []
    for year in sorted({item.day.year for item in items}):
        data = encode_year(item for item in items if item.day.year == year)
        ref = f"wellness/{year:04}.csv"
        files.append(
            ManifestFile(
                ref,
                sha256(data).hexdigest(),
                sum(item.day.year == year for item in items),
            )
        )
        staged.append((data_root / ref, data))
    manifest_path = data_root / "wellness/manifest.toml"
    manifest = encode_manifest(Manifest("staged-by-test", files=tuple(files)))
    staged.append((manifest_path, manifest))
    for path, data in staged:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return tuple(path for path, _ in staged)
