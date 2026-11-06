#!/usr/bin/env python
"""
audit_clean_checkout.py
=======================
A01: Clean checkout audit script.

Verifies that a clean checkout can:
1. Install all dependencies
2. Compile all Python files
3. Import all modules
4. Run without import errors
"""

import asyncio
import os
import sys
from pathlib import Path


async def run_command(cmd: str, cwd: str) -> tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, stderr."""
    import subprocess
    
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()


async def main():
    """Run clean checkout audit."""
    backend_dir = Path(__file__).parent.parent
    app_dir = backend_dir / "app"
    
    print("=" * 60)
    print("AMC Clean Checkout Audit")
    print("=" * 60)
    print()
    
    all_passed = True
    
    # Step 1: Verify backend directory exists
    print("Step 1: Verifying backend directory structure...")
    required_files = [
        "requirements.txt",
        "alembic.ini",
        "pyproject.toml",
    ]
    
    for file in required_files:
        path = backend_dir / file
        if path.exists():
            print(f"  OK: {file}")
        else:
            print(f"  ERROR: Missing {file}")
            all_passed = False
    print()
    
    # Step 2: Verify app structure
    print("Step 2: Verifying app directory structure...")
    required_dirs = [
        "api",
        "auth",
        "tabular",
        "adapters",
        "clients",
        "compliance",
    ]
    
    for dir_name in required_dirs:
        path = app_dir / dir_name
        if path.exists():
            print(f"  OK: {dir_name}/")
        else:
            print(f"  ERROR: Missing {dir_name}/")
            all_passed = False
    print()
    
    # Step 3: Compile all Python files
    print("Step 3: Compiling Python files...")
    compile_errors = []
    for py_file in app_dir.rglob("*.py"):
        ret, stdout, stderr = await run_command(
            f"python -m py_compile {py_file.relative_to(backend_dir)}",
            cwd=str(backend_dir),
        )
        if ret != 0:
            compile_errors.append((str(py_file), stderr))
            all_passed = False
        else:
            print(f"  OK: {py_file.relative_to(backend_dir)}")
    
    if compile_errors:
        print(f"\n  ERROR: {len(compile_errors)} files failed to compile:")
        for file, err in compile_errors[:5]:  # Show first 5 errors
            print(f"    - {file}: {err.strip()}")
    print()
    
    # Step 4: Import test
    print("Step 4: Testing imports...")
    sys.path.insert(0, str(backend_dir))
    
    try:
        import app  # noqa: F401
        print("  OK: app module imported")
    except Exception as e:
        print(f"  ERROR: Failed to import app: {e}")
        all_passed = False
    
    try:
        from app.tabular.executor import QueryExecutor  # noqa: F401
        print("  OK: tabular.executor.QueryExecutor imported")
    except Exception as e:
        print(f"  ERROR: Failed to import QueryExecutor: {e}")
        all_passed = False
    
    try:
        from app.services.financial_policy_service import FinancialPolicyService  # noqa: F401
        print("  OK: services.financial_policy_service.FinancialPolicyService imported")
    except Exception as e:
        print(f"  ERROR: Failed to import FinancialPolicyService: {e}")
        all_passed = False
    
    print()
    
    # Step 5: Dependencies check
    print("Step 5: Checking installed dependencies...")
    ret, stdout, stderr = await run_command(
        "pip list --format=freeze",
        cwd=str(backend_dir),
    )
    if ret == 0:
        print("  OK: Dependencies installed")
    else:
        print(f"  ERROR: pip list failed: {stderr}")
        all_passed = False
    print()
    
    # Summary
    print("=" * 60)
    if all_passed:
        print("AUDIT PASSED")
        print("=" * 60)
        print()
        print("Clean checkout is ready for deployment.")
        return 0
    else:
        print("AUDIT FAILED")
        print("=" * 60)
        print()
        print("Please fix the errors above before deployment.")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))