#!/usr/bin/env python3
"""Write a local delivery receipt after the final Git commit is recorded."""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tested-commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()

    archive = root / "dist/fpa-1.0.0.zip"
    receipt = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": str(root),
        "branch": git("branch", "--show-current"),
        "base_commit": "d69d8c0a765f8137a04e38f6ae3ea4f95120c488",
        "tested_commit": args.tested_commit,
        "final_commit": git("rev-parse", "HEAD"),
        "working_tree_status": git("status", "--porcelain"),
        "archive": archive.name,
        "archive_sha256": sha256(archive.read_bytes()).hexdigest(),
        "destination": "https://github.com/samueldowd/fpa",
        "published": False,
        "production_deployed": False,
        "physical_dispensing_performed": False,
    }
    (root / "dist/DELIVERY.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
