"""At-rest encryption via the Windows Data Protection API (DPAPI).

Implemented with pure ``ctypes`` against crypt32.dll so there is no pywin32
dependency to complicate the PyInstaller build.

DPAPI binds the ciphertext to the current *Windows user account*: another local
user, or an attacker copying the files to a different machine, cannot decrypt
them offline. This is the same class of protection Windows itself uses for
Credential Manager. It is the at-rest layer; the face match is the access gate
enforced by the application on top of it.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

# Namespacing entropy so VeriFace blobs cannot be swapped with other apps' DPAPI
# data. Not a secret - it only scopes the protection.
_ENTROPY = b"VeriFace/v1/dpapi"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data: bytes):
    buf = ctypes.create_string_buffer(bytes(data), len(data))
    blob = _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return blob, buf  # keep buf alive in caller


def _from_blob(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, int(blob.cbData))


_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32


class DpapiError(RuntimeError):
    """Raised when a DPAPI protect/unprotect call fails."""


def protect(data: bytes) -> bytes:
    """Encrypt ``data`` for the current Windows user."""
    blob_in, _b = _to_blob(data)
    entropy, _e = _to_blob(_ENTROPY)
    blob_out = _DataBlob()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(blob_in), "VeriFace", ctypes.byref(entropy),
        None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    )
    if not ok:
        raise DpapiError(f"CryptProtectData failed (err={_kernel32.GetLastError()})")
    try:
        return _from_blob(blob_out)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


def unprotect(data: bytes) -> bytes:
    """Decrypt data produced by :func:`protect`."""
    blob_in, _b = _to_blob(data)
    entropy, _e = _to_blob(_ENTROPY)
    blob_out = _DataBlob()
    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, ctypes.byref(entropy),
        None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
    )
    if not ok:
        raise DpapiError(f"CryptUnprotectData failed (err={_kernel32.GetLastError()})")
    try:
        return _from_blob(blob_out)
    finally:
        _kernel32.LocalFree(blob_out.pbData)
