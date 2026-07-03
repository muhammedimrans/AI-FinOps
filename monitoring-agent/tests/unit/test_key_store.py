from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from costorah_agent.security.key_store import KeyStore, KeyStoreError


def test_store_and_load_round_trip(tmp_path: Path) -> None:
    store = KeyStore(tmp_path)
    store.store("costorah_live_secret123")
    assert store.load() == "costorah_live_secret123"


def test_load_returns_none_when_never_stored(tmp_path: Path) -> None:
    store = KeyStore(tmp_path / "empty")
    assert store.load() is None


def test_clear_removes_stored_key(tmp_path: Path) -> None:
    store = KeyStore(tmp_path)
    store.store("costorah_live_secret123")
    store.clear()
    assert store.load() is None


def test_clear_on_never_stored_is_a_no_op(tmp_path: Path) -> None:
    store = KeyStore(tmp_path)
    store.clear()  # must not raise


def test_load_with_tampered_secret_raises(tmp_path: Path) -> None:
    store = KeyStore(tmp_path)
    store.store("costorah_live_secret123")
    secret_file = tmp_path / "keystore.enc"
    secret_file.write_bytes(b"not-a-valid-fernet-token")
    with pytest.raises(KeyStoreError):
        store.load()


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions only")
def test_key_files_are_owner_only_on_posix(tmp_path: Path) -> None:
    store = KeyStore(tmp_path)
    store.store("costorah_live_secret123")
    for name in ("keystore.key", "keystore.enc"):
        mode = stat.S_IMODE((tmp_path / name).stat().st_mode)
        assert mode == stat.S_IRUSR | stat.S_IWUSR
