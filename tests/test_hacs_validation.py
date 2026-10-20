"""Local HACS adapter checks; original validator checks accept HACS_SOURCE."""

import json
import os
from pathlib import Path

import pytest

from scripts.validate_hacs import local_mit_license, upstream_modules, validate


def test_local_mit_classification_requires_complete_permission_and_warranty(tmp_path):
    license_text = (Path(__file__).resolve().parents[1] / "LICENSE").read_text()
    (tmp_path / "LICENSE").write_text(license_text)
    assert local_mit_license(tmp_path)["spdx_id"] == "MIT"
    (tmp_path / "LICENSE").write_text(
        "MIT License\nPermission is hereby granted, but no warranty text"
    )
    assert local_mit_license(tmp_path) is None


def test_missing_upstream_source_fails_before_loading_modules(tmp_path):
    with pytest.raises(FileNotFoundError, match="HACS validator source not found"):
        with upstream_modules(tmp_path):
            pytest.fail("Missing validator sources must fail closed")


@pytest.fixture
def hacs_source():
    """Tooling sources are an explicit developer checkout, never fetched by tests."""
    if not (source := os.environ.get("HACS_SOURCE")):
        pytest.skip("Set HACS_SOURCE to run original upstream HACS validator contracts")
    return Path(source)


@pytest.fixture
def local_repository(tmp_path):
    component = tmp_path / "custom_components/fpa"
    (component / "brand").mkdir(parents=True)
    (component / "manifest.json").write_text(
        json.dumps(
            {
                "domain": "fpa",
                "name": "Formula Pro Advanced WiFi",
                "version": "1.0.0",
                "documentation": "https://github.com/samueldowd/fpa",
                "issue_tracker": "https://github.com/samueldowd/fpa/issues",
                "codeowners": ["@samueldowd"],
            }
        )
    )
    (component / "brand/icon.png").write_bytes(b"Local asset existence fixture")
    (tmp_path / "hacs.json").write_text(
        json.dumps({"name": "Formula Pro Advanced WiFi", "homeassistant": "2025.10.4"})
    )
    (tmp_path / "README.md").write_text("# Integration fixture\n")
    (tmp_path / "LICENSE").write_text(
        (Path(__file__).resolve().parents[1] / "LICENSE").read_text()
    )
    return tmp_path


@pytest.mark.parametrize(
    "failure", [None, "invalid_hacs_key", "missing_brand", "missing_license"]
)
async def test_original_upstream_validators_are_executed_and_fail_closed(
    hacs_source, local_repository, failure, capsys
):
    if failure == "invalid_hacs_key":
        (local_repository / "hacs.json").write_text(
            json.dumps({"name": "Fixture", "invented_key": True})
        )
    elif failure == "missing_brand":
        (local_repository / "custom_components/fpa/brand/icon.png").unlink()
    elif failure == "missing_license":
        (local_repository / "LICENSE").unlink()
    assert await validate(local_repository, hacs_source) == (
        0 if failure is None else 1
    )
    output = capsys.readouterr().out
    assert "original upstream Python validators" in output
    if failure is None:
        assert "6 upstream local validators passed; 0 failed" in output
    else:
        assert "FAIL upstream" in output
        if failure == "missing_brand":
            assert "Remote lookup disabled" in output
