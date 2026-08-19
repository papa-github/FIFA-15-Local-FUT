"""Smoke tests for the Origin LSX service.

The golden suite covers route_fut, which is the FUT HTTP path only. LSX and
Blaze are not exercised by it - and that gap is not theoretical: moving the
cryptography imports into origin_crypto.py left a stale `Cipher` reference in
LSXHandler, every LSX connection died with NameError before sending anything,
and FIFA froze on the language select screen. The golden suite stayed green
throughout.

The decisive property is that the server speaks first: FIFA's OriginSDK waits
for a Challenge frame and will hang forever if one never arrives. Any exception
in the handler before that write reproduces the freeze, so asserting the frame
arrives catches the whole class of bug.

    py -3 tests/lsx_smoke.py
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def isolate_runtime() -> str:
    tmp = tempfile.mkdtemp(prefix="localfut-lsx-")
    os.environ["LOCALAPPDATA"] = tmp
    os.environ.pop("LOCALFUT_GAME_DIR", None)
    return tmp


def recv_frame(sock: socket.socket, timeout: float = 5.0) -> bytes:
    """Read one NUL-terminated LSX frame."""
    sock.settimeout(timeout)
    buf = bytearray()
    while b"\x00" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError(
                "LSX server closed the connection without sending a frame. "
                "The handler almost certainly raised - check the server log."
            )
        buf += chunk
    return bytes(buf.split(b"\x00", 1)[0])


def test_server_speaks_first(server) -> None:
    srv = server.ThreadingTCPServer(("127.0.0.1", 0), server.LSXHandler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        client = socket.create_connection(("127.0.0.1", port), timeout=5)
        try:
            frame = recv_frame(client).decode("utf-8", errors="replace")
        finally:
            client.close()
    finally:
        srv.shutdown()
        srv.server_close()

    assert "<Challenge" in frame, f"expected a Challenge frame, got: {frame[:200]}"
    assert 'sender="EALS"' in frame, f"challenge missing EALS sender: {frame[:200]}"
    assert 'key="' in frame, f"challenge missing key attribute: {frame[:200]}"
    print("  server speaks first    : OK  (%s)" % frame[:60])


def test_crypto_round_trip(server) -> None:
    crypto = server.OriginCrypto(0)
    assert crypto.key == bytes(range(16)), "seed 0 must keep the primary OriginSDK key"

    text = "<LSX><Event sender='EbisuSDK'><Login IsLoggedIn='true' /></Event></LSX>"
    assert crypto.decrypt(crypto.encrypt(text)) == text, "AES round-trip lost the payload"

    # Seeded keys must differ from the primary key, or protocol 3 would silently
    # keep using the primary one.
    assert server.OriginCrypto(0x4142).key != bytes(range(16))
    print("  crypto round-trip      : OK")


def test_origin_random_is_deterministic(server) -> None:
    a = server.OriginRandom(12345)
    b = server.OriginRandom(12345)
    seq_a = [a.next() for _ in range(5)]
    seq_b = [b.next() for _ in range(5)]
    assert seq_a == seq_b, "OriginRandom must be reproducible for a given seed"
    assert len(set(seq_a)) > 1, f"LCG produced a constant sequence: {seq_a}"
    print("  OriginRandom LCG       : OK  %s" % seq_a)


def main() -> int:
    tmp = isolate_runtime()
    sys.path.insert(0, str(REPO / "payload" / "localfut15"))
    try:
        import logging
        logging.disable(logging.CRITICAL)
        import server
    except Exception as exc:
        print(f"Could not import server.py: {type(exc).__name__}: {exc}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 2

    failures = 0
    try:
        for test in (test_server_speaks_first, test_crypto_round_trip,
                     test_origin_random_is_deterministic):
            try:
                test(server)
            except Exception as exc:
                failures += 1
                print(f"  FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("LSX smoke: %s" % ("all passed" if not failures else f"{failures} failed"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
