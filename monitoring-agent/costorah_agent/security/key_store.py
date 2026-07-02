"""
KeyStore — encrypts the organization API key at rest.

Honest scope statement: this uses symmetric encryption (Fernet/AES-128-CBC
+ HMAC via the `cryptography` package) with a locally-generated key file
restricted to the owner (chmod 600 on POSIX). This is meaningfully better
than a plaintext config file — an attacker who copies config.yaml alone
gets nothing usable — but it is *not* equivalent to an OS-native secret
store (Windows DPAPI / macOS Keychain / Linux Secret Service), which would
tie decryption to the OS user session and hardware-backed protections.
Wiring this into those OS-native stores is real, platform-specific work
tracked as follow-up in docs/TROUBLESHOOTING.md and docs/ARCHITECTURE.md
rather than claimed here.

Recommended production posture regardless: prefer supplying the API key
via the COSTORAH_AGENT_ORGANIZATION__API_KEY environment variable (e.g.
injected by your secret manager / orchestrator) over config.yaml or this
key store at all — see config.example.yaml.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class KeyStoreError(Exception):
    """Raised when the key store cannot be read, written, or decrypted."""


class KeyStore:
    """Encrypts/decrypts a single secret (the organization API key) at rest."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._key_file = self._dir / "keystore.key"
        self._secret_file = self._dir / "keystore.enc"

    def _load_or_create_fernet_key(self) -> bytes:
        self._dir.mkdir(parents=True, exist_ok=True)
        if self._key_file.exists():
            return self._key_file.read_bytes()
        key = Fernet.generate_key()
        self._key_file.write_bytes(key)
        self._restrict_permissions(self._key_file)
        return key

    @staticmethod
    def _restrict_permissions(path: Path) -> None:
        # POSIX only — Windows ACLs are a separate mechanism; the file is
        # still written under the user's own profile directory there.
        if os.name == "posix":
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def store(self, api_key: str) -> None:
        fernet = Fernet(self._load_or_create_fernet_key())
        token = fernet.encrypt(api_key.encode("utf-8"))
        self._secret_file.write_bytes(token)
        self._restrict_permissions(self._secret_file)

    def load(self) -> str | None:
        if not self._secret_file.exists() or not self._key_file.exists():
            return None
        fernet = Fernet(self._key_file.read_bytes())
        try:
            token = self._secret_file.read_bytes()
            return fernet.decrypt(token).decode("utf-8")
        except InvalidToken as exc:
            raise KeyStoreError("Stored API key could not be decrypted") from exc

    def clear(self) -> None:
        self._secret_file.unlink(missing_ok=True)
        self._key_file.unlink(missing_ok=True)
