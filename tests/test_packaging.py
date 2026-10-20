"""Validate the complete runtime archive, determinism and clean contents."""

import json
import zipfile
from hashlib import sha256
from pathlib import Path

from scripts.build_release import build


def test_release_is_reproducible_and_self_contained(tmp_path):
    root = Path(__file__).resolve().parents[1]
    archive = build(root, tmp_path)
    first = archive.read_bytes()
    build(root, tmp_path)
    assert archive.read_bytes() == first
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert all(name.startswith("custom_components/fpa/") for name in names)
        assert not any(
            "__pycache__" in n or n.endswith(".pyc") or "reference.json" in n
            for n in names
        )
        for required in (
            "__init__.py",
            "manifest.json",
            "sensor.py",
            "binary_sensor.py",
            "select.py",
            "button.py",
            "diagnostics.py",
            "privacy.py",
            "vendor/pybabyfpa/__init__.py",
            "vendor/pybabyfpa/LICENSE",
            "translations/en.json",
            "brand/icon.png",
        ):
            assert f"custom_components/fpa/{required}" in names
        manifest = json.loads(package.read("custom_components/fpa/manifest.json"))
        assert manifest["requirements"] == []
        assert manifest["iot_class"] == "cloud_push"
        inventory = json.loads((tmp_path / "inventory.json").read_text())
        assert {f["path"] for f in inventory} == set(names)
        for record in inventory:
            assert sha256(package.read(record["path"])).hexdigest() == record["sha256"]
