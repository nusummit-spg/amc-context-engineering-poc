#!/usr/bin/env python3
"""Non-destructive Wave 2.0 overlay installer. Preview is the default.

Requires amc-dev or feature/* branch, refuses overwriting existing files.
Never writes existing ingestion, publication, governance, or credential files.
"""
from argparse import ArgumentParser
from pathlib import Path
from shutil import copy2
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATHS = ["backend/amc_quality", "backend/tests", ".github/workflows", "remediation/wave2_0", "tools"]


def entries():
    for prefix in PATHS:
        root = ROOT / prefix
        for f in sorted(root.rglob("*")):
            if not f.is_file() or "__pycache__" in f.parts or f.suffix in (".pyc", ".pyo"):
                continue
            rel = f.relative_to(ROOT)
            if prefix == "backend/tests" and not f.name.startswith("test_wave20_"):
                continue
            if prefix == "tools" and f.name not in ("install_wave20_overlay.py", "audit_legacy_quality_bypasses.py", "demo_wave20_offline.py"):
                continue
            yield rel


def install(repo: Path, apply: bool = False) -> int:
    destination = repo.resolve()
    if not (destination / ".git").exists():
        raise ValueError("must specify a local Git checkout root")
    branch = subprocess.check_output(["git", "branch", "--show-current"],cwd=destination,text=True).strip()
    if branch != "amc-dev" and not branch.startswith("feature/"):
        raise ValueError(f"refusing branch {branch!r}; use amc-dev or feature/*")
    files = list(entries())
    collisions = [str(rel) for rel in files if (destination / rel).exists()]
    if collisions:
        raise FileExistsError("existing files would be overwritten; aborting:\n" + "\n".join(collisions))
    for rel in files:
        target = destination / rel
        print(("COPY " if apply else "WOULD COPY ") + rel.as_posix())
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(ROOT / rel, target)
    print(f"files={len(files)} applied={apply}")
    return len(files)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="copy only new files; no overwrite")
    args = parser.parse_args(argv)
    try:
        install(args.repo, apply=args.apply)
        return 0
    except (ValueError, FileExistsError, subprocess.CalledProcessError) as exc:
        print("INSTALL REFUSED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
