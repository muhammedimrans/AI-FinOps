"""
Compression — gzip large batch payloads before upload. Tiny payloads
aren't compressed (the ticket's "Do not compress tiny payloads"): gzip's
own framing overhead can make a small payload *larger*, so there's a
configurable size threshold below which compression is skipped entirely.
"""

from __future__ import annotations

import gzip

DEFAULT_THRESHOLD_BYTES = 1024


def maybe_compress(
    body: bytes, *, threshold_bytes: int = DEFAULT_THRESHOLD_BYTES
) -> tuple[bytes, bool]:
    """Returns (possibly-compressed bytes, was_compressed). Callers set
    `Content-Encoding: gzip` on the request only when was_compressed is
    True."""
    if len(body) < threshold_bytes:
        return body, False
    compressed = gzip.compress(body, compresslevel=6)
    return compressed, True


def compression_ratio(original_bytes: int, compressed_bytes: int) -> float:
    """1.0 means no reduction; 0.25 means the compressed body is a quarter
    of the original size. Used for the compression_ratio metric."""
    if original_bytes <= 0:
        return 1.0
    return compressed_bytes / original_bytes
