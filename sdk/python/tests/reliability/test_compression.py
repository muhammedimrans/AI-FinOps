from __future__ import annotations

import gzip

from costorah.reliability.compression import compression_ratio, maybe_compress


def test_tiny_payload_not_compressed() -> None:
    body = b'{"a":1}'
    result, was_compressed = maybe_compress(body, threshold_bytes=1024)
    assert was_compressed is False
    assert result == body


def test_large_payload_compressed() -> None:
    body = b"x" * 2000
    result, was_compressed = maybe_compress(body, threshold_bytes=1024)
    assert was_compressed is True
    assert result != body
    assert gzip.decompress(result) == body


def test_compression_ratio_reflects_reduction() -> None:
    body = b"a" * 5000
    compressed, _ = maybe_compress(body, threshold_bytes=100)
    ratio = compression_ratio(len(body), len(compressed))
    assert 0 < ratio < 1


def test_compression_ratio_handles_zero_original() -> None:
    assert compression_ratio(0, 0) == 1.0
