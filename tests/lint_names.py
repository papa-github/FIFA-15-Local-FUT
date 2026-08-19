"""Undefined-name check for the payload modules.

Catches the single most likely way a refactor breaks this project: code moves to
a new module, and something left behind still references a name that went with
it. That is exactly how `Cipher` ended up undefined in LSXHandler, which froze
FIFA on the language screen while every other test stayed green.

pyflakes or ruff would do this better, but neither is installed and this project
deliberately carries one runtime dependency. This uses only the stdlib.

The check is intentionally permissive: it unions every name bound anywhere in a
module, at any scope, and reports only names that are bound *nowhere* and are
not builtins. That cannot flag a shadowing or scope subtlety as an error, so a
report here is close to always real.

    py -3 tests/lint_names.py
"""

from __future__ import annotations

import ast
import builtins
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAYLOAD = REPO / "payload" / "localfut15"

# Module-level dunders the interpreter provides.
ALWAYS_DEFINED = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__spec__", "__package__",
    "__loader__", "__builtins__", "__debug__",
}


def bound_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                out.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            out.add(node.id)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            out.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            out.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            out.add(node.name)
    return out


def check(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(io.open(path, encoding="utf-8").read(), filename=str(path))
    defined = bound_names(tree) | ALWAYS_DEFINED
    seen: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in defined:
                seen.setdefault(node.id, node.lineno)
    return sorted((line, name) for name, line in seen.items())


def main() -> int:
    files = sorted(PAYLOAD.glob("*.py"))
    if not files:
        print(f"No modules found under {PAYLOAD}")
        return 2

    total = 0
    for path in files:
        try:
            problems = check(path)
        except SyntaxError as exc:
            print(f"  {path.name}: SYNTAX ERROR line {exc.lineno}: {exc.msg}")
            total += 1
            continue
        if problems:
            total += len(problems)
            for line, name in problems:
                print(f"  {path.name}:{line}: undefined name '{name}'")
        else:
            print(f"  {path.name}: clean")

    print()
    print("lint: %s" % ("clean" if not total else f"{total} undefined name(s)"))
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
