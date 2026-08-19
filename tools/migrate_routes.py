"""Move top-level `if low == "..."` branches out of route_fut into the table.

The branch body is copied verbatim, only de-indented. Nothing is renamed:
whatever locals the body used (method, query, payload, ...) are unpacked from
the FutRequest on the first line of the handler, and only the ones it actually
reads. That keeps each migration a pure move, which is the whole point - a
rename hidden inside a move is exactly the kind of change no reviewer catches.

Usage: py -3 tools/migrate_routes.py <server.py> <path literal> [...]

On Git Bash prefix with MSYS_NO_PATHCONV=1, or the leading slash in each
path argument is rewritten into a Windows path.

Limitations, in order of how likely they are to bite:

- Only handles top-level `if low == "literal":` branches. Branches whose test
  also checks the verb (`low == x and method == "POST"`), or that test a tuple
  (`low in (...)`), or that use startswith, still need doing by hand or by
  extending this. Those are what remain in the chain.
- The chain is positional. Moving a branch to the table makes it match FIRST.
  That is safe for exact paths, but check anything preceded by a broad
  startswith or regex branch that could have swallowed it.
- An endpoint absent from tests/corpus.json has no snapshot, so its migration
  is unverified. Add it and re-record before trusting the move.

Always: RUN_TESTS.cmd after each batch, and commit per batch.
"""

from __future__ import annotations

import ast
import io
import re
import sys

CTX = ["method", "raw_path", "path", "low", "query", "headers", "body", "payload"]


def handler_name(literal: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", literal).strip("_").lower()
    slug = re.sub(r"^(ut|pow|fut)_", "", slug)
    slug = slug.replace("game_fifa15_", "")
    return "_route_" + slug


def used_context(node: ast.AST) -> list[str]:
    bound = {x.id for x in ast.walk(node)
             if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}
    loaded = {x.id for x in ast.walk(node)
              if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
    # A name assigned inside the branch is its own local, not the request field.
    return [c for c in CTX if c in loaded and c not in bound]


def main(argv: list[str]) -> int:
    path, literals = argv[0], argv[1:]
    raw = io.open(path, encoding="utf-8", newline="").read()
    lines = raw.split("\r\n")
    tree = ast.parse(raw)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "route_fut")

    found = {}
    for st in fn.body:
        if not (isinstance(st, ast.If) and isinstance(st.test, ast.Compare)):
            continue
        left, comps = st.test.left, st.test.comparators
        if not (isinstance(left, ast.Name) and left.id == "low"
                and isinstance(comps[0], ast.Constant)):
            continue
        lit = comps[0].value
        if lit in literals and lit not in found:
            found[lit] = st

    missing = [l for l in literals if l not in found]
    if missing:
        print("NOT FOUND:", missing)
        return 2

    handlers = []
    for lit in literals:
        st = found[lit]
        body_lines = lines[st.body[0].lineno - 1: st.end_lineno]
        dedented = [(l[4:] if l.startswith("    ") else l) for l in body_lines]
        ctx = used_context(st)
        unpack = ""
        if ctx:
            names = ", ".join(ctx)
            values = ", ".join(f"req.{c}" for c in ctx)
            unpack = f"    {names} = {values}\r\n" if len(ctx) > 1 else \
                     f"    {ctx[0]} = req.{ctx[0]}\r\n"
        # The literal becomes a regex, so escape it. An unescaped dot in a
        # path like storepackdescriptions.en_us.xml silently widens the route.
        handlers.append(
            f'@fut_route(r"{re.escape(lit)}")\r\n'
            f"def {handler_name(lit)}(req: FutRequest):\r\n"
            + unpack
            + "\r\n".join(dedented)
        )

    for lit in sorted(found, key=lambda l: -found[l].lineno):
        st = found[lit]
        del lines[st.lineno - 1: st.end_lineno]

    out = "\r\n".join(lines)
    anchor = ("def route_fut(method: str, raw_path: str, "
              "headers: dict[str, str], body: bytes)")
    if out.count(anchor) != 1:
        print("anchor not unique")
        return 2
    out = out.replace(anchor, "\r\n\r\n".join(handlers) + "\r\n\r\n\r\n" + anchor, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(out)

    for lit in literals:
        print(f"  moved {lit}  -> {handler_name(lit)}({', '.join(used_context(found[lit])) or 'req'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
