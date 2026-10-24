"""Selection, installation check, and consented download of the local AI models.

VeriFace uses two small open-source ONNX models from the OpenCV Model Zoo
(Apache-2.0):

* **YuNet**  - face detection + 5 landmarks
* **SFace**  - face recognition (128-D embedding)

They are only a few megabytes, run in real time on CPU, and never phone home.
Downloads happen exclusively through :func:`ensure_installed`, which the GUI
calls *after* the user grants permission.
"""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import paths

_ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models"


@dataclass(frozen=True)
class ModelSpec:
    key: str
    filename: str
    url: str
    role: str
    min_bytes: int  # sanity floor to reject truncated downloads


MODELS: dict[str, ModelSpec] = {
    "detector": ModelSpec(
        key="detector",
        filename="face_detection_yunet_2023mar.onnx",
        url=f"{_ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        role="Face detection (YuNet)",
        min_bytes=200_000,
    ),
    "recognizer": ModelSpec(
        key="recognizer",
        filename="face_recognition_sface_2021dec.onnx",
        url=f"{_ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        role="Face recognition (SFace)",
        min_bytes=30_000_000,
    ),
}


def model_path(key: str) -> Path:
    return paths.MODELS_DIR / MODELS[key].filename


def is_installed(key: str) -> bool:
    p = model_path(key)
    return p.exists() and p.stat().st_size >= MODELS[key].min_bytes


def all_installed() -> bool:
    return all(is_installed(k) for k in MODELS)


def missing() -> list[ModelSpec]:
    return [spec for k, spec in MODELS.items() if not is_installed(k)]


ProgressCb = Callable[[str, int, int], None]  # (filename, downloaded, total)


def _download(spec: ModelSpec, progress: ProgressCb | None) -> None:
    paths.ensure_dirs()
    dest = model_path(spec.key)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(spec.url, headers={"User-Agent": "VeriFace"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed host)
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(262_144)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(spec.filename, done, total)
    if tmp.stat().st_size < spec.min_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{spec.filename} download looks truncated.")
    tmp.replace(dest)


def ensure_installed(progress: ProgressCb | None = None) -> list[str]:
    """Download any missing models. Returns the list of filenames fetched.

    Call only after the user has consented. Safe to call when nothing is
    missing (returns an empty list).
    """
    fetched: list[str] = []
    for spec in missing():
        _download(spec, progress)
        fetched.append(spec.filename)
    return fetched
