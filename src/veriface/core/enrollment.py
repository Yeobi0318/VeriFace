"""Enrollment session: capture a varied set of face embeddings for one user.

Variety is the key to the requested robustness: we deliberately collect samples
across small pose changes (and we prompt the user to enrol both with and
without glasses), so the stored template spans the natural appearance changes -
hair restyled/cut, glasses on/off - that a single snapshot would miss.

The session runs on a worker thread and reports progress through callbacks; it
owns its camera and model and releases both when it finishes or is stopped.
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

FrameCb = Callable[[object, dict], None]   # (bgr_frame, status_info)


@dataclass
class EnrollResult:
    ok: bool
    count: int = 0
    message: str = ""


class EnrollmentSession:
    def __init__(self, cfg: Config, on_update: FrameCb) -> None:
        self.cfg = cfg
        self.on_update = on_update
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.result: Optional[EnrollResult] = None
        self.embeddings: list[list[float]] = []

    def start(self, on_done: Callable[[EnrollResult], None]) -> None:
        def runner() -> None:
            self.result = self._run()
            on_done(self.result)
        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> EnrollResult:
        import numpy as np

        target = max(3, int(self.cfg.enroll_samples))
        last_vec = None
        live = LivenessTracker(self.cfg.liveness_challenge, self.cfg.min_face_sharpness)
        next_capture = 0.0
        try:
            with Camera(self.cfg.camera_index) as cam, \
                    FaceEngine(self.cfg.det_size) as engine:
                while not self._stop.is_set():
                    if len(self.embeddings) >= target:
                        return EnrollResult(True, len(self.embeddings),
                                            "Enrollment complete.")
                    frame = cam.read()
                    det = engine.largest(frame)
                    info = {"count": len(self.embeddings), "target": target}

                    if det is None or det.score < 0.85:
                        info["status"] = "Position your face in the frame"
                        self.on_update(frame, info)
                        continue

                    vec, aligned = engine.embed(frame, det)
                    live.update(det, aligned)

                    now = time.time()
                    novel = last_vec is None or FaceEngine.cosine(vec, last_vec) < 0.985
                    if now >= next_capture and novel:
                        self.embeddings.append([float(x) for x in vec])
                        last_vec = vec
                        next_capture = now + 0.4  # pace captures for variety
                        info["captured"] = True

                    info["count"] = len(self.embeddings)
                    info["bbox"] = det.bbox
                    info["status"] = ("Great - keep slowly changing your angle "
                                      "(try glasses on/off)")
                    self.on_update(frame, info)
            return EnrollResult(False, len(self.embeddings), "Cancelled.")
        except Exception as exc:  # surface camera/model errors to the UI
            return EnrollResult(False, len(self.embeddings), str(exc))
