"""Build a request corpus from a real Local FUT server log.

The server logs every request it served, so a play session is already a
recording of what FIFA 15 actually asks for. This turns one of those logs into
tests/corpus.json, which golden_runner.py replays.

Usage:
    py -3 tests/extract_corpus.py                     # use the newest log found
    py -3 tests/extract_corpus.py path/to/server.log  # use a specific log
    py -3 tests/extract_corpus.py --merge             # add to the existing corpus

Re-run it after a play session that exercises new screens to grow coverage;
--merge keeps everything already captured.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
CORPUS = TESTS / "corpus.json"

# 2026-08-19 12:38:56,227 INFO FUT8199 127.0.0.1 - "GET /ut/... HTTP/1.1" 200 -
LINE = re.compile(
    r"(?P<logger>[A-Za-z0-9_]+)\s+[\d.]+\s+-\s+"
    r'"(?P<method>GET|POST|PUT|DELETE|HEAD|PATCH)\s+(?P<path>\S+)\s+HTTP/[\d.]+"\s+'
    r"(?P<status>\d{3})"
)

# Which logger name maps to which entry point under test.
SERVICE_BY_LOGGER = {
    "FUT8199": "fut",
    "FUT8099": "fut",
    "POW": "fut",
}


def default_logs() -> list[Path]:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        return []
    logs = Path(root) / "FIFA15LocalFUT" / "logs"
    if not logs.is_dir():
        return []
    return sorted(logs.glob("*.log"), key=lambda p: p.stat().st_size, reverse=True)


def parse(log_path: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = LINE.search(line)
        if not m:
            continue
        service = SERVICE_BY_LOGGER.get(m.group("logger"))
        if service is None:
            continue
        method = m.group("method")
        path = m.group("path")
        # One entry per distinct method+path. Repeats of the same endpoint add
        # nothing to a golden snapshot and would just slow the run down.
        key = f"{method} {path}"
        found.setdefault(key, {
            "name": slug(method, path),
            "service": service,
            "method": method,
            "path": path,
            "body_b64": "",
            "observed_status": int(m.group("status")),
        })
    return found


def slug(method: str, path: str) -> str:
    s = f"{method}_{path}"
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    # Truncation alone collides: several endpoints share a long common prefix
    # and differ only in the query string. The digest keeps names unique so
    # every case gets its own snapshot file.
    digest = hashlib.sha1(f"{method} {path}".encode("utf-8")).hexdigest()[:8]
    return f"{s[:100]}_{digest}"


def main(argv: list[str]) -> int:
    merge = "--merge" in argv
    args = [a for a in argv if not a.startswith("--")]

    if args:
        logs = [Path(args[0])]
    else:
        logs = default_logs()
        if not logs:
            print("No server log found. Pass one explicitly:")
            print("  py -3 tests/extract_corpus.py path/to/server.log")
            return 2

    entries: dict[str, dict] = {}
    if merge and CORPUS.is_file():
        for e in json.loads(CORPUS.read_text(encoding="utf-8")):
            entries[f"{e['method']} {e['path']}"] = e

    before = len(entries)
    used = []
    for log_path in logs:
        if not log_path.is_file():
            continue
        got = parse(log_path)
        if got:
            used.append((log_path, len(got)))
        for k, v in got.items():
            entries.setdefault(k, v)

    if not entries:
        print("No FUT requests found in:", ", ".join(str(p) for p in logs))
        return 1

    ordered = sorted(entries.values(), key=lambda e: (e["method"], e["path"]))
    CORPUS.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")

    for path, n in used:
        print(f"  read {n:>4} distinct requests from {path.name}")
    print(f"corpus: {len(ordered)} entries ({len(ordered) - before} new) -> {CORPUS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
