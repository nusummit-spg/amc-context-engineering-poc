#!/usr/bin/env python3
"""Install only NEW Wave 1.9 files into a local AMC checkout.

No existing repo files are overwritten. The sole optional mutator of an
existing file is repair_ci_gitleaks.py, which must be run separately.
"""
from pathlib import Path
from argparse import ArgumentParser
from shutil import copy2
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def entries():
    for root in ("backend/amc_publication", "backend/tests", "backend/alembic/versions",
                 ".github/workflows", "remediation/wave1_9", "tools"):
        p = ROOT / root
        for f in sorted(p.glob("**/*")):
            if not f.is_file() or "__pycache__" in f.parts or f.suffix in (".pyc", ".pyo"):
                continue
            relative = f.relative_to(ROOT)
            if str(relative).startswith("backend/tests/") and not f.name.startswith("test_wave19_"):
                continue
            if str(relative).startswith("backend/alembic/versions/") and not f.name.startswith("012_wave19_"):
                continue
            if str(relative).startswith(".github/workflows/") and f.name != "amc-publication-v2.yml":
                continue
            yield relative


def install(destination: Path, dry_run: bool = True) -> int:
    repo = destination.resolve()
    if not (repo / ".git").exists():
        raise ValueError("Destination must be an existing Git checkout")
    branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                     cwd=repo, text=True).strip()
    if branch != "amc-dev" and not branch.startswith("feature/"):
        raise ValueError(f"Refusing to install over branch {branch}: use amc-dev or a feature branch")
    files = list(entries())
    conflicts = [str(x) for x in files if (repo / x).exists()]
    if conflicts:
        raise FileExistsError("Overlay never overwrites files. Existing paths:\n" + "\n".join(conflicts))
    for path in files:
        target = repo / path
        print(("WOULD COPY " if dry_run else "COPY ") + str(path))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(ROOT/path, target)
    print(f"{len(files)} new files, dry_run={dry_run}")
    return len(files)


def main():
    ap=ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True, help="Local AMC Git checkout root")
    ap.add_argument("--apply", action="store_true", help="Actually copy; default is dry-run")
    args=ap.parse_args()
    try:
        install(args.repo, dry_run=not args.apply)
    except (ValueError, FileExistsError, subprocess.CalledProcessError) as exc:
        print("INSTALL ABORTED: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
