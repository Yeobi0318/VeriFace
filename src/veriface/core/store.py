"""DPAPI-encrypted JSON stores for face templates and the password vault.

Each store is a small JSON document serialised to UTF-8, encrypted with
:mod:`crypto`, and written atomically. Face *embeddings* (numeric vectors) are
stored - never raw face images - so a leaked template cannot be turned back
into a photograph of the user.
"""
from __future__ import annotations

import json
import time
from typing import Any

from . import crypto, paths


def _read_encrypted(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    blob = path.read_bytes()
    if not blob:
        return {}
    try:
        return json.loads(crypto.unprotect(blob).decode("utf-8"))
    except (crypto.DpapiError, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Could not decrypt {path.name}: {exc}") from exc


def _write_encrypted(path, obj: dict[str, Any]) -> None:
    paths.ensure_dirs()
    blob = crypto.protect(json.dumps(obj).encode("utf-8"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    tmp.replace(path)


# --- face templates ---------------------------------------------------------
class TemplateStore:
    """Persists enrolled face embeddings for a single local user.

    Each embedding carries a timestamp so the set can *age*: after a very
    confident match the live embedding is added and the oldest one is evicted
    once the cap is reached. This lets the template follow slow appearance
    changes (ageing, weight, facial hair) without ever being retrained on a
    low-confidence (possibly wrong) face.
    """

    def __init__(self) -> None:
        self._data = _read_encrypted(paths.TEMPLATES_PATH)
        self._migrate()

    def _migrate(self) -> None:
        embs = self._data.get("embeddings")
        if embs and "timestamps" not in self._data:
            base = float(self._data.get("created_at", time.time()))
            self._data["timestamps"] = [base] * len(embs)

    @property
    def enrolled(self) -> bool:
        return bool(self._data.get("embeddings"))

    @property
    def created_at(self) -> float:
        return float(self._data.get("created_at", 0.0))

    def embeddings(self) -> list[list[float]]:
        return list(self._data.get("embeddings", []))

    def count(self) -> int:
        return len(self._data.get("embeddings", []))

    def meta(self) -> dict[str, Any]:
        return dict(self._data.get("meta", {}))

    def save(self, embeddings: list[list[float]], meta: dict[str, Any]) -> None:
        now = time.time()
        self._data = {
            "version": 2,
            "created_at": now,
            "embeddings": [list(map(float, e)) for e in embeddings],
            "timestamps": [now] * len(embeddings),
            "meta": meta,
        }
        _write_encrypted(paths.TEMPLATES_PATH, self._data)

    def add_adaptive(self, embedding, max_templates: int = 40) -> None:
        """Append a freshly-verified embedding and evict the oldest if over cap."""
        if not self.enrolled:
            return
        embs = self._data.setdefault("embeddings", [])
        tss = self._data.setdefault("timestamps", [])
        embs.append([float(x) for x in embedding])
        tss.append(time.time())
        # keep the enrollment baseline safe: evict by oldest timestamp, but never
        # let the set fall below a handful of samples.
        while len(embs) > max(5, int(max_templates)):
            oldest = min(range(len(tss)), key=lambda i: tss[i])
            embs.pop(oldest)
            tss.pop(oldest)
        _write_encrypted(paths.TEMPLATES_PATH, self._data)

    def clear(self) -> None:
        self._data = {}
        if paths.TEMPLATES_PATH.exists():
            paths.TEMPLATES_PATH.unlink()


# --- password vault ---------------------------------------------------------
class VaultStore:
    """Encrypted credential vault, gated by a successful face match."""

    def __init__(self) -> None:
        self._data = _read_encrypted(paths.VAULT_PATH)
        self._data.setdefault("entries", [])

    def entries(self) -> list[dict[str, Any]]:
        return list(self._data.get("entries", []))

    def add(self, title: str, username: str, secret: str, url: str = "") -> None:
        self._data.setdefault("entries", []).append({
            "id": f"{int(time.time()*1000)}",
            "title": title, "username": username,
            "secret": secret, "url": url,
            "updated_at": time.time(),
        })
        self._flush()

    def update(self, entry_id: str, **fields: Any) -> None:
        for e in self._data.get("entries", []):
            if e.get("id") == entry_id:
                e.update(fields)
                e["updated_at"] = time.time()
                break
        self._flush()

    def delete(self, entry_id: str) -> None:
        self._data["entries"] = [
            e for e in self._data.get("entries", []) if e.get("id") != entry_id
        ]
        self._flush()

    def _flush(self) -> None:
        _write_encrypted(paths.VAULT_PATH, self._data)
