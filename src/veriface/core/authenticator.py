"""Authentication session: verify the live person against the stored template.

A match requires BOTH:
  1. cosine similarity to an enrolled embedding >= the configured threshold, and
  2. a passed liveness challenge (see liveness.py).

The session is time-boxed (config.auth_timeout_seconds) and releases the camera
and model as soon as it ends, so nothing keeps running in the background.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .camera import Camera
from .config import Config
from .face_engine import FaceEngine
from .liveness import LivenessTracker
from .store import TemplateStore

FrameCb = Callable[[object, dict], None]


@dataclass
class AuthResult:
    ok: bool
    score: float = 0.0
    message: str = ""


class AuthSession:
    def __init__(self, cfg: Config, on_update: FrameCb) -> None:
        self.cfg = cfg
        self.on_update = on_update
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.result: Optional[AuthResult] = None

    def start(self, on_done: Callable[[AuthResult], None]) -> None:
        def runner() -> None:
            self.result = self._run()
            on_done(self.result)
        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> AuthResult:
        import numpy as np

        store = TemplateStore()
        if not store.enrolled:
            return AuthResult(False, 0.0, "No face is enrolled yet.")
        templates = np.asarray(store.embeddings(), dtype=np.float32)
        threshold = float(self.cfg.match_threshold)
        deadline = time.time() + max(3, int(self.cfg.auth_timeout_seconds))
        live = LivenessTracker(self.cfg.liveness_challenge, self.cfg.min_face_sharpness)
        best = 0.0

        try:
            with Camera(self.cfg.camera_index) as cam, \
                    FaceEngine(self.cfg.det_size) as engine:
                while not self._stop.is_set():
                    if time.time() > deadline:
                        return AuthResult(False, best,
                                          "Timed out - face not recognised.")
                    frame = cam.read()
                    det = engine.largest(frame)
                    info = {"score": best, "threshold": threshold}

                    if det is None or det.score < 0.85:
                        info["status"] = "Looking for your face..."
                        self.on_update(frame, info)
                        continue

                    vec, aligned = engine.embed(frame, det)
                    live.update(det, aligned)
                    score = float(np.max(templates @ vec))  # best cosine vs templates
                    best = max(best, score)

                    live_ok, live_msg = (True, "") if not self.cfg.liveness_enabled \
                        else live.passed()

                    info.update(score=score, bbox=det.bbox,
                                live_progress=live.progress())
                    if score >= threshold and live_ok:
                        info["status"] = "Recognised"
                        self.on_update(frame, info)
                        return AuthResult(True, score, "Face recognised.")
                    if score >= threshold and not live_ok:
                        info["status"] = f"Match found - {live.hint()}"
                    else:
                        info["status"] = "Not recognised - keep still and face camera"
                    self.on_update(frame, info)
            return AuthResult(False, best, "Cancelled.")
        except Exception as exc:
            return AuthResult(False, best, str(exc))


def verify_blocking(cfg: Config, timeout: Optional[int] = None) -> AuthResult:
    """Headless one-shot verification used by the CLI. No preview callback."""
    if timeout is not None:
        cfg.auth_timeout_seconds = timeout
    done = threading.Event()
    holder: dict[str, AuthResult] = {}

    def on_done(res: AuthResult) -> None:
        holder["r"] = res
        done.set()

    session = AuthSession(cfg, on_update=lambda *_: None)
    session.start(on_done)
    done.wait(timeout=(cfg.auth_timeout_seconds + 10))
    return holder.get("r", AuthResult(False, 0.0, "No result."))
