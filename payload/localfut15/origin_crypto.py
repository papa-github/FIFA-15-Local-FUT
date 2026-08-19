"""Origin/EA SDK crypto used by the local LSX service.

Extracted verbatim from server.py. FIFA 15's OriginSDK handshake is a
server-first challenge followed by AES-128-ECB encrypted hex frames, so this
owns both the deterministic PRNG that derives the session key and the cipher
itself - along with the optional cryptography import they depend on.
"""

from __future__ import annotations

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except Exception as _crypto_import_error:
    padding = Cipher = algorithms = modes = None
else:
    _crypto_import_error = None


class OriginRandom:
    """Origin/EA SDK deterministic PRNG used for LSX session-key derivation."""

    def __init__(self, seed: int):
        self.seed = int(seed) & 0xFFFFFFFF

    def set_seed(self, seed: int) -> None:
        self.seed = int(seed) & 0xFFFFFFFF

    def next(self) -> int:
        # Same LCG used by the legacy Origin SDK.
        self.seed = (self.seed * 214013 + 2531011) & 0xFFFFFFFF
        return (self.seed >> 16) & 0x7FFF


class OriginCrypto:
    def __init__(self, seed: int = 0):
        self.key = bytes(range(16))
        self.set_key(seed)

    def set_key(self, seed: int) -> None:
        seed = int(seed) & 0xFFFFFFFF
        if seed == 0:
            self.key = bytes(range(16))
            return
        rng = OriginRandom(7)
        new_seed = (rng.next() + seed) & 0xFFFFFFFF
        rng.set_seed(new_seed)
        self.key = bytes((rng.next() & 0xFF) for _ in range(16))

    def encrypt(self, text: str) -> bytes:
        if Cipher is None:
            raise RuntimeError(f"cryptography package is unavailable: {_crypto_import_error}")
        padder = padding.PKCS7(128).padder()
        raw = padder.update(text.encode("utf-8")) + padder.finalize()
        enc = Cipher(algorithms.AES(self.key), modes.ECB()).encryptor()
        return enc.update(raw) + enc.finalize()

    def decrypt(self, ciphertext: bytes) -> str:
        if Cipher is None:
            raise RuntimeError(f"cryptography package is unavailable: {_crypto_import_error}")
        dec = Cipher(algorithms.AES(self.key), modes.ECB()).decryptor()
        padded = dec.update(ciphertext) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        raw = unpadder.update(padded) + unpadder.finalize()
        return raw.decode("utf-8")

    def challenge_response(self, challenge: str) -> str:
        response = self.encrypt(challenge).hex()
        b = response.encode("ascii")
        if len(b) < 2:
            raise ValueError("challenge response was too short")
        seed = (b[0] << 8) | b[1]
        self.set_key(seed)
        return response

    def set_session_from_response(self, response: str) -> int:
        b = response.encode("ascii", errors="strict")
        if len(b) < 2:
            raise ValueError("ChallengeResponse.response is too short")
        seed = (b[0] << 8) | b[1]
        self.set_key(seed)
        return seed
