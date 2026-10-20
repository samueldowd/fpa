#!/usr/bin/env python3
"""Exercise the extracted runtime in a separate Python/HA test process."""

import argparse
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from build_release import build


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default="python")
    parser.add_argument("--label", default="artifact")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Keep the venv symlink (resolve() would select the base interpreter), but
    # make paths absolute before the subprocess changes to the extraction.
    interpreter = os.path.abspath(shutil.which(args.python) or args.python)
    archive = build(root)
    with tempfile.TemporaryDirectory(prefix="fpa-install-") as temporary:
        install = Path(temporary)
        with zipfile.ZipFile(archive) as package:
            package.extractall(install)
        # Only test/documentation resources are copied from checkout; runtime
        # code must come exclusively from the released ZIP.
        for directory in ("tests", "docs", ".github/ISSUE_TEMPLATE"):
            shutil.copytree(
                root / directory,
                install / directory,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        for filename in ("README.md", "pyproject.toml", "LICENSE"):
            shutil.copy2(root / filename, install / filename)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.pop("HACS_SOURCE", None)
        probe = subprocess.run(
            [
                interpreter,
                "-c",
                "from pathlib import Path; import custom_components.fpa as m; p=Path(m.__file__).resolve(); assert p.is_relative_to(Path.cwd()),p; print('Runtime import verified inside extracted install')",
            ],
            cwd=install,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        print(probe.stdout.strip())
        test_files = [
            str(path.relative_to(install))
            for path in sorted((install / "tests").glob("test_*.py"))
            if path.name not in {"test_hacs_validation.py", "test_packaging.py"}
        ]
        result = subprocess.run(
            [interpreter, "-m", "pytest", "-q", *test_files],
            cwd=install,
            env=environment,
            capture_output=True,
            text=True,
        )
        output = (result.stdout + result.stderr).replace(
            str(install), "<extracted-install>"
        )
        print(output, end="")
        target = root / "docs/validation" / f"{args.label}-install.txt"
        target.write_text(probe.stdout + output)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
