"""Regression: Wave 2.5 patch removed the function-local PatchStatus import in
approve_correction while the function still used PatchStatus.APPROVED, so every
approval of an existing patch raised NameError. This test is a static AST check,
so it needs no database, Neo4j or app startup.
"""
import ast
from pathlib import Path

GOVERNANCE = Path(__file__).resolve().parents[1] / "app" / "api" / "routes" / "governance.py"
NAME = "PatchStatus"


def _imports_name(node: ast.AST, name: str) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.ImportFrom) and any((a.asname or a.name) == name for a in sub.names):
            return True
    return False


def unresolved_users(source: str, name: str = NAME) -> list[str]:
    """Functions that load `name` but neither import it locally nor see a module import."""
    tree = ast.parse(source)
    module_level = any(
        _imports_name(stmt, name) for stmt in tree.body
        if isinstance(stmt, (ast.Import, ast.ImportFrom))
    )
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        uses = any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)
                   for n in ast.walk(fn))
        if uses and not module_level and not _imports_name(fn, name):
            bad.append(fn.name)
    return bad


def test_every_function_using_patchstatus_can_resolve_it():
    assert unresolved_users(GOVERNANCE.read_text(encoding="utf-8")) == []


def test_approve_correction_imports_patchstatus_locally():
    tree = ast.parse(GOVERNANCE.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "approve_correction")
    assert _imports_name(fn, NAME)


def test_checker_detects_the_original_defect():
    broken = (
        "def approve(patch):\n"
        "    patch.status = PatchStatus.APPROVED\n"
    )
    assert unresolved_users(broken) == ["approve"]
