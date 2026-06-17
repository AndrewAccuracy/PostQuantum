"""KEM backend adapters providing a uniform interface for pqcrypto and liboqs."""

from __future__ import annotations

import importlib
import importlib.metadata
from typing import Tuple


_VARIANT_NAMES = {512: "ML-KEM-512", 768: "ML-KEM-768", 1024: "ML-KEM-1024"}
SUPPORTED_VARIANTS = sorted(_VARIANT_NAMES)
SUPPORTED_BACKENDS = ("pqcrypto", "liboqs")


class PqcryptoBackend:
    """Adapter wrapping pqcrypto.kem.ml_kem_{512,768,1024} module-level functions."""

    def __init__(self, variant: int) -> None:
        if variant not in _VARIANT_NAMES:
            raise ValueError(f"variant must be one of {SUPPORTED_VARIANTS}")
        self._mod = importlib.import_module(f"pqcrypto.kem.ml_kem_{variant}")
        self.variant = variant
        self.name = f"pqcrypto.kem.ml_kem_{variant}"
        self.version = importlib.metadata.version("pqcrypto")

    def generate_keypair(self) -> Tuple[bytes, bytes]:
        return self._mod.generate_keypair()

    def encrypt(self, public_key: bytes) -> Tuple[bytes, bytes]:
        return self._mod.encrypt(public_key)

    def decrypt(self, private_key: bytes, ciphertext: bytes) -> bytes:
        return self._mod.decrypt(private_key, ciphertext)


class LiboqsBackend:
    """Adapter wrapping liboqs.KeyEncapsulation for ML-KEM.

    Requires: pip install liboqs
    The private key is cached so the decapsulation object is initialised once
    per keypair, not once per call, keeping the inner timing loop clean.
    """

    def __init__(self, variant: int) -> None:
        # Initialise cache attributes first so __del__ is safe even if __init__ raises.
        self._cached_sk: bytes | None = None
        self._cached_dec = None
        if variant not in _VARIANT_NAMES:
            raise ValueError(f"variant must be one of {SUPPORTED_VARIANTS}")
        try:
            import oqs as _oqs  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "liboqs Python bindings are required for the liboqs backend.\n"
                "Install with: pip install liboqs"
            ) from exc
        self.variant = variant
        self._alg = _VARIANT_NAMES[variant]
        self.name = f"liboqs.{self._alg}"
        try:
            self.version = importlib.metadata.version("liboqs")
        except importlib.metadata.PackageNotFoundError:
            self.version = "unknown"

    def generate_keypair(self) -> Tuple[bytes, bytes]:
        import oqs

        kem = oqs.KeyEncapsulation(self._alg)
        public_key: bytes = kem.generate_keypair()
        private_key: bytes = bytes(kem.export_secret_key())
        kem.free()
        # Pre-initialise the decapsulation object so the timing loop pays no
        # per-call init overhead.
        if self._cached_dec is not None:
            self._cached_dec.free()
        self._cached_dec = oqs.KeyEncapsulation(self._alg, secret_key=private_key)
        self._cached_sk = private_key
        return public_key, private_key

    def encrypt(self, public_key: bytes) -> Tuple[bytes, bytes]:
        import oqs

        enc = oqs.KeyEncapsulation(self._alg)
        ciphertext, shared_secret = enc.encap_secret(public_key)
        enc.free()
        return ciphertext, shared_secret

    def decrypt(self, private_key: bytes, ciphertext: bytes) -> bytes:
        if private_key != self._cached_sk:
            import oqs

            if self._cached_dec is not None:
                self._cached_dec.free()
            self._cached_dec = oqs.KeyEncapsulation(self._alg, secret_key=private_key)
            self._cached_sk = private_key
        return self._cached_dec.decap_secret(ciphertext)

    def __del__(self) -> None:
        if self._cached_dec is not None:
            try:
                self._cached_dec.free()
            except Exception:
                pass


def make_kem(variant: int, backend: str = "pqcrypto") -> PqcryptoBackend | LiboqsBackend:
    """Return a KEM adapter for *variant* using the specified *backend*."""
    if backend == "pqcrypto":
        return PqcryptoBackend(variant)
    if backend == "liboqs":
        return LiboqsBackend(variant)
    raise ValueError(f"backend must be one of {SUPPORTED_BACKENDS!r}, got {backend!r}")
