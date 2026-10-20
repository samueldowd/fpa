#!/usr/bin/env python3
"""Build a deterministic manual-install archive from runtime files only."""

import json
import zipfile
from hashlib import sha256
from pathlib import Path


def build(root: Path, destination: Path | None = None) -> Path:
    component = root / "custom_components/fpa"
    version = json.loads((component / "manifest.json").read_text())["version"]
    destination = destination or root / "dist"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"fpa-{version}.zip"
    inventory = []
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as package:
        for path in sorted(component.rglob("*")):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or path.suffix in {".pyc", ".pyo"}
            ):
                continue
            content = path.read_bytes()
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 10, 19, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, content, compresslevel=9)
            inventory.append(
                {
                    "path": relative,
                    "bytes": len(content),
                    "sha256": sha256(content).hexdigest(),
                }
            )
    digest = sha256(archive.read_bytes()).hexdigest()
    (destination / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n")
    (destination / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    print(f"Built {archive.name}: {len(inventory)} files, SHA256 {digest}")
    return archive


if __name__ == "__main__":
    build(Path(__file__).resolve().parents[1])
