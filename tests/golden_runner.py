"""Golden-master tests for server.py.

Replays tests/corpus.json through route_fut and compares each response against
a recorded snapshot in tests/golden/. The point is not to assert that any
response is *correct* - it is to prove that a refactor did not change what the
server returns.

    py -3 tests/golden_runner.py             verify against the snapshots
    py -3 tests/golden_runner.py --update    re-record the snapshots
    py -3 tests/golden_runner.py --only cred run cases whose name contains "cred"

Isolation: RUNTIME_ROOT in server.py is derived from %LOCALAPPDATA%, so this
points that at a fresh temp directory before importing server. Every run gets a
newly seeded starter club and the real save in
%LOCALAPPDATA%\\FIFA15LocalFUT is never opened, let alone written.

Recording a snapshot is only meaningful from a known-good tree. Re-record only
when a behavior change is intended, and eyeball the resulting git diff.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
CORPUS = TESTS / "corpus.json"
GOLDEN = TESTS / "golden"

# Anything above this is stored as a digest instead of full text, to keep the
# snapshots reviewable in a diff.
MAX_INLINE_BODY = 200_000

# Deterministic seed so pack/market randomness reproduces across runs.
SEED = 20260819


def isolate_runtime() -> str:
    """Point the server's runtime root at a throwaway directory."""
    tmp = tempfile.mkdtemp(prefix="localfut-golden-")
    os.environ["LOCALAPPDATA"] = tmp
    # install.json lives under LOCALAPPDATA, so it is absent here and the game
    # folder resolves to the legacy fallback. route_fut never touches it.
    os.environ.pop("LOCALFUT_GAME_DIR", None)
    return tmp


ISO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
SESSION_ID = re.compile(r"^(?:pow|ut)\.[0-9a-f]{32}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
DIGITS = re.compile(r"^\d{10,13}$")

# Epoch seconds up to 2096 - the store sends expiry dates decades out, which a
# 2_000_000_000 ceiling would miss. Nothing else in this API reaches 1e9: coin
# balances cap at 15,000,000 and resource ids are 8 digits, so the range cannot
# swallow a real game value.
EPOCH_S_MIN, EPOCH_S_MAX = 1_000_000_000, 4_000_000_000
EPOCH_MS_MIN, EPOCH_MS_MAX = 1_000_000_000_000, 4_000_000_000_000


def scrub_number(value):
    if EPOCH_S_MIN <= value <= EPOCH_S_MAX:
        return "<EPOCH_S>"
    if EPOCH_MS_MIN <= value <= EPOCH_MS_MAX:
        return "<EPOCH_MS>"
    return None


def scrub(value):
    """Replace values that legitimately differ between runs."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return scrub_number(value) or value
    if isinstance(value, str):
        if ISO.match(value):
            return "<TIMESTAMP>"
        if SESSION_ID.match(value):
            return "<SESSION_ID>"
        if HEX32.match(value):
            return "<HEX32>"
        # Timestamps are sometimes sent as decimal strings, e.g. "established".
        if DIGITS.match(value):
            return scrub_number(int(value)) or value
        return value
    return value


def normalize(status: int, headers: dict, body: bytes) -> dict:
    # Headers carry generated values too - the auth endpoints return the new
    # session id in X-UT-SID / X-POW-SID - so they get the same scrubbing.
    kept = {k: scrub(v) for k, v in sorted(headers.items())
            if k.lower() not in ("date", "server", "content-length")}

    out = {"status": status, "headers": kept}

    if not body:
        out["body_kind"] = "empty"
        return out

    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        digest = hashlib.sha256(body).hexdigest()[:32]
        out["body_kind"] = "opaque"
        out["body_sha256_32"] = digest
        out["body_len"] = len(body)
        return out

    text = json.dumps(scrub(parsed), indent=2, sort_keys=True, ensure_ascii=False)
    if len(text) > MAX_INLINE_BODY:
        out["body_kind"] = "json_digest"
        out["body_sha256_32"] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        out["body_len"] = len(text)
    else:
        out["body_kind"] = "json"
        out["body"] = json.loads(text)
    return out


def first_difference(a, b, path="") -> str | None:
    if type(a) is not type(b):
        return f"{path or '<root>'}: type {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{path}.{k}: missing in recorded"
            if k not in b:
                return f"{path}.{k}: missing in current"
            d = first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if a != b:
        return f"{path or '<root>'}: {a!r} != {b!r}"
    return None


def main(argv: list[str]) -> int:
    update = "--update" in argv
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]

    if not CORPUS.is_file():
        print("No corpus. Run: py -3 tests/extract_corpus.py")
        return 2

    cases = json.loads(CORPUS.read_text(encoding="utf-8"))
    if only:
        cases = [c for c in cases if only in c["name"] or only in c["path"]]
    cases = [c for c in cases if c.get("service") == "fut"]
    if not cases:
        print("No matching cases.")
        return 2

    tmp = isolate_runtime()
    sys.path.insert(0, str(REPO / "payload" / "localfut15"))
    try:
        # server.py logs every request at WARNING to stdout, which buries the
        # test output. Snapshots capture responses, not logs.
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: E402  (import must follow the env isolation)
        logging.disable(logging.CRITICAL)
    except Exception as exc:
        print(f"Could not import server.py: {exc}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 2

    GOLDEN.mkdir(exist_ok=True)
    passed = failed = recorded = errored = 0
    failures: list[str] = []

    try:
        for case in cases:
            name = case["name"]
            body = case["body_b64"].encode("ascii") if case["body_b64"] else b""
            headers = {"Accept": "application/json", "Content-Type": "application/json"}

            random.seed(SEED)
            try:
                status, resp_headers, resp_body = server.route_fut(
                    case["method"], case["path"], headers, body)
                if isinstance(resp_body, str):
                    resp_body = resp_body.encode("utf-8")
                current = normalize(status, resp_headers, resp_body or b"")
            except Exception as exc:
                errored += 1
                failures.append(f"  ERROR  {name}\n         {type(exc).__name__}: {exc}")
                continue

            snap = GOLDEN / f"{name}.json"
            if update:
                snap.write_text(json.dumps(current, indent=2, sort_keys=True,
                                           ensure_ascii=False) + "\n", encoding="utf-8")
                recorded += 1
                continue

            if not snap.is_file():
                failed += 1
                failures.append(f"  MISSING SNAPSHOT  {name}  (run with --update)")
                continue

            expected = json.loads(snap.read_text(encoding="utf-8"))
            diff = first_difference(expected, current)
            if diff is None:
                passed += 1
            else:
                failed += 1
                failures.append(f"  FAIL   {name}\n         {diff}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if update:
        print(f"recorded {recorded} snapshots into {GOLDEN}")
        if errored:
            print(f"{errored} case(s) raised:")
            print("\n".join(failures))
        return 1 if errored else 0

    for line in failures:
        print(line)
    print()
    print(f"passed {passed}   failed {failed}   errored {errored}   of {len(cases)}")
    return 0 if (failed == 0 and errored == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
