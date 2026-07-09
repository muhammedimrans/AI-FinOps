"""Organization slug generation — EP-21.2.

Used only by self-serve registration today (personal-workspace
auto-creation). No prior slug-generation code existed anywhere in the
codebase — `OrganizationRepository.slug_exists()` was the only related
helper (uniqueness check, not generation).
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Awaitable, Callable

_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated slug from arbitrary text.

    Falls back to a short random token if the input has no ASCII
    alphanumeric characters at all (e.g. a fully non-Latin display name).
    """
    slug = _NON_SLUG_CHARS.sub("-", value.lower()).strip("-")
    return slug or secrets.token_hex(4)


async def unique_slug(base: str, *, slug_exists: Callable[[str], Awaitable[bool]]) -> str:
    """Return `base` if free, otherwise `base-<n>` for the first free `n`.

    `slug_exists` is typically `OrganizationRepository.slug_exists` (bound
    method), called directly rather than reimplementing the existence check.
    """
    candidate = slugify(base)
    n = 1
    while await slug_exists(candidate):
        n += 1
        candidate = f"{slugify(base)}-{n}"
    return candidate
