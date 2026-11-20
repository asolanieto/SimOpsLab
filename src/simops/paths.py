"""Filesystem-safe stable path components derived from user-supplied IDs."""

from __future__ import annotations

import hashlib
import re


def path_component(identifier: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", identifier).strip("._-")[:48] or "item"
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"
