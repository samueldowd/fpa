#!/usr/bin/env python3
"""Run genuine HACS file validators against a local, unpublished checkout.

Usage:
  python scripts/validate_hacs.py --hacs-source /path/to/hacs/integration \
      --action-source /path/to/hacs/action

The supplied HACS checkout is executable trusted tooling. Its original schema
and Validator classes run unchanged through a filesystem repository adapter.
This does not call GitHub, execute the action's remote Docker image, or claim
that remote repository metadata/default-store submission checks have passed.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import sys
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from types import ModuleType, SimpleNamespace

# A whitespace-normalized hash of the standard MIT permission/warranty text,
# excluding the copyright line. Local license classification is deliberately
# narrower than GitHub's license API and is disclosed in the output.
_MIT_BODY_SHA256 = "fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5"
_VALIDATORS = (
    "hacsjson",
    "integration_manifest",
    "information",
    "brands",
    "license",
    "integration_categories",
)


class OfflineAccessError(RuntimeError):
    """A validator attempted a lookup unavailable in local-only validation."""


class _NoNetwork:
    async def get(self, *_args, **_kwargs):
        raise OfflineAccessError(
            "Remote lookup disabled; required local content is missing"
        )


def source_revision(source: Path) -> str:
    """Read clone provenance without changing the clone or invoking Git."""
    git = source / ".git"
    if not git.is_dir():
        return "unknown (not a clone with readable Git metadata)"
    head = (git / "HEAD").read_text().strip()
    if not head.startswith("ref: "):
        return head
    reference = head.removeprefix("ref: ")
    ref_file = git / reference
    if ref_file.is_file():
        return ref_file.read_text().strip()
    packed = git / "packed-refs"
    if packed.is_file():
        for line in packed.read_text().splitlines():
            if line.endswith(f" {reference}"):
                return line.split()[0]
    return "unknown (unresolved Git reference)"


@contextmanager
def upstream_modules(source: Path):
    """Load original HACS submodules without booting the HA integration.

    Namespace shells skip only package initialization. Validator, manifest model,
    schemas, enums and all their functional dependencies are upstream code.
    Restore module state afterwards so this utility can also be tested in HA.
    """
    root = source / "custom_components/hacs"
    if not (root / "validate/hacsjson.py").is_file():
        raise FileNotFoundError(f"HACS validator source not found in {source}")
    # HA 2026.10 installs probatio as voluptuous; initialize it before HACS imports
    # voluptuous so actual HA schema semantics match the running environment.
    import homeassistant  # noqa: F401

    names = {
        "custom_components.hacs": root,
        "custom_components.hacs.repositories": root / "repositories",
        "custom_components.hacs.utils": root / "utils",
        "custom_components.hacs.validate": root / "validate",
    }
    existing = {
        key: value
        for key, value in sys.modules.items()
        if key == "custom_components" or key.startswith("custom_components.hacs")
    }
    if "custom_components" not in sys.modules:
        package = ModuleType("custom_components")
        package.__path__ = [str(root.parent)]
        sys.modules["custom_components"] = package
    for name, path in names.items():
        module = ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    try:
        yield {
            name: importlib.import_module(f"custom_components.hacs.validate.{name}")
            for name in _VALIDATORS
        }
    finally:
        for key in list(sys.modules):
            if key == "custom_components" or key.startswith("custom_components.hacs"):
                sys.modules.pop(key)
        sys.modules.update(existing)


def local_mit_license(repository: Path) -> dict | None:
    """Recognize the complete local MIT body, never infer from the title alone."""
    license_file = repository / "LICENSE"
    if not license_file.is_file():
        return None
    text = license_file.read_text()
    if "Permission is hereby granted," not in text:
        return None
    body = (
        "Permission is hereby granted,"
        + text.split("Permission is hereby granted,", 1)[1]
    )
    if sha256(" ".join(body.split()).encode()).hexdigest() != _MIT_BODY_SHA256:
        return None
    return {"spdx_id": "MIT", "name": "MIT License (classified from local full text)"}


class LocalRepository:
    """Only the filesystem methods/metadata consumed by the selected validators."""

    def __init__(self, root: Path, logger: logging.Logger):
        self.root = root
        self.logger = logger
        self.ref = "local-working-tree"
        self.string = "<Local repository>"
        enums = importlib.import_module("custom_components.hacs.enums")
        manifest_model = importlib.import_module(
            "custom_components.hacs.repositories.base"
        )
        self.repository_manifest = manifest_model.HacsManifest.from_dict(
            self._json("hacs.json")
        )
        manifests = sorted((root / "custom_components").glob("*/manifest.json"))
        if len(manifests) != 1:
            raise ValueError(
                "Expected exactly one custom_components/<domain>/manifest.json"
            )
        self.manifest_path = manifests[0]
        self.domain = self._json(self.manifest_path.relative_to(root)).get("domain")
        if self.repository_manifest.content_in_root:
            raise ValueError(
                "This project requires the conventional custom_components layout"
            )
        if self.manifest_path.parent.name != self.domain:
            raise ValueError("Manifest domain does not match its integration directory")
        if not (root / "README.md").is_file():
            raise ValueError("This project requires a root README.md")
        files = []
        for directory, subdirs, filenames in root.walk():
            subdirs[:] = [
                name
                for name in subdirs
                if not name.startswith(".") and name != "__pycache__"
            ]
            files.extend(
                directory / name for name in filenames if not name.startswith(".")
            )
        self.tree = [SimpleNamespace(filename=path.name) for path in files]
        self.treefiles = [path.relative_to(root).as_posix() for path in files]
        self.content = SimpleNamespace(
            path=SimpleNamespace(
                remote=self.manifest_path.parent.relative_to(root).as_posix()
            )
        )
        self.data = SimpleNamespace(
            category=enums.HacsCategory.INTEGRATION, domain=self.domain
        )
        self.repository_object = SimpleNamespace(
            attributes={"license": local_mit_license(root)}
        )
        self.hacs = SimpleNamespace(
            log=logger, session=_NoNetwork(), async_download_file=self._no_download
        )

    def _json(self, path: str | Path):
        return json.loads((self.root / path).read_text())

    async def _no_download(self, *_args, **_kwargs):
        raise OfflineAccessError(
            "Remote SPDX/GitHub lookup disabled in local validation"
        )

    async def get_hacs_json_raw(self, *, version):
        return self._json("hacs.json")

    async def async_get_loaded_integration_manifest(self):
        return self._json(self.manifest_path.relative_to(self.root))


async def validate(
    repository: Path, hacs_source: Path, action_source: Path | None = None
) -> int:
    """Return zero only when all applicable local upstream checks pass."""
    logger = logging.getLogger("fpa.hacs.local")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    try:
        print(
            f"HACS source: https://github.com/hacs/integration @ {source_revision(hacs_source)}"
        )
        if action_source is not None:
            print(
                f"Action wrapper: https://github.com/hacs/action @ {source_revision(action_source)}"
            )
        print(
            "Mode: original upstream Python validators + local filesystem adapter; network disabled"
        )
        with upstream_modules(hacs_source) as validators:
            local = LocalRepository(repository, logger)
            print(
                f"PASS local install layout: {local.manifest_path.parent.relative_to(repository)}"
            )
            failures = 0
            for name, module in validators.items():
                try:
                    validator = await module.async_setup_validator(local)
                    await validator.async_validate()
                except Exception as error:
                    failures += 1
                    print(f"FAIL upstream {name}: {type(error).__name__}: {error}")
                else:
                    print(f"PASS upstream {name}")
        print(
            "License adapter: classification requires complete local MIT text; GitHub license API detection is unverified"
        )
        print(
            "NOT RUN: remote Docker action image, GitHub description/topics/issues/archive/license metadata, releases, default-store inclusion"
        )
        print(
            f"RESULT: {len(_VALIDATORS) - failures} upstream local validators passed; {failures} failed"
        )
        return 1 if failures else 0
    finally:
        logger.removeHandler(handler)
        handler.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--hacs-source", type=Path, required=True)
    parser.add_argument("--action-source", type=Path)
    args = parser.parse_args()
    try:
        return asyncio.run(
            validate(
                args.repository.resolve(),
                args.hacs_source.resolve(),
                args.action_source,
            )
        )
    except (FileNotFoundError, ValueError, ImportError) as error:
        print(f"FAIL local validation setup: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
