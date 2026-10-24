"""Face detection + embedding using OpenCV's YuNet and SFace models.

Why these models meet the brief:

* **SFace** produces a 128-D embedding trained for face *verification*. Those
  embeddings are driven by stable identity structure (inter-ocular geometry,
  nose/jaw shape), so they stay close together across greasy/cut/restyled hair
  and glasses on/off - exactly the robustness requested.
* Both are tiny ONNX graphs that run in real time on CPU, so recognition is
  fast and leaves almost no memory footprint once :meth:`close` is called.

Models load lazily on first use and are fully released by :meth:`close`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import model_manager


@dataclass
class Detection:
    row: object          # 1x15 float32 YuNet row in original-frame coords
    bbox: tuple[int, int, int, int]
    score: float
    area: int


class FaceEngine:
    # SFace matches by cosine similarity; OpenCV's recommended same-identity
    # threshold is 0.363. We expose it via config so it can be tuned.
    COSINE_DEFAULT = 0.363

    def __init__(self, det_size: int = 320, score_threshold: float = 0.8) -> None:
        self.det_size = int(det_size)
        self.score_threshold = float(score_threshold)
        self._detector = None
        self._recognizer = None

    # -- lifecycle --------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._detector is not None:
            return
        if not model_manager.all_installed():
            raise RuntimeError("Models are not installed yet. Run PC Analysis first.")
        import cv2

        self._detector = cv2.FaceDetectorYN_create(
            str(model_manager.model_path("detector")), "",
            (self.det_size, self.det_size), self.score_threshold, 0.3, 5000,
        )
        self._recognizer = cv2.FaceRecognizerSF_create(
            str(model_manager.model_path("recognizer")), "",
        )

    def close(self) -> None:
        """Release the ONNX graphs so idle memory returns to baseline."""
        self._detector = None
        self._recognizer = None
        import gc
        gc.collect()

    def __enter__(self) -> "FaceEngine":
        self._ensure_loaded()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- detection --------------------------------------------------------
    def detect(self, frame) -> list[Detection]:
        """Detect faces in a BGR frame; coordinates are in frame space."""
        self._ensure_loaded()
        import cv2
        import numpy as np

        h, w = frame.shape[:2]
        scale = self.det_size / float(max(h, w))
        if scale < 1.0:
            small = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))))
        else:
            small, scale = frame, 1.0

        self._detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = self._detector.detect(small)
        if faces is None:
            return []

        faces = faces.astype(np.float32)
        faces[:, :14] /= scale  # rescale box + 5 landmarks back to frame space

        out: list[Detection] = []
        for row in faces:
            x, y, bw, bh = (int(round(v)) for v in row[:4])
            out.append(Detection(
                row=row.reshape(1, -1),
                bbox=(x, y, bw, bh),
                score=float(row[14]),
                area=max(0, bw) * max(0, bh),
            ))
        out.sort(key=lambda d: d.area, reverse=True)
        return out

    def largest(self, frame) -> Optional[Detection]:
        dets = self.detect(frame)
        return dets[0] if dets else None

    # -- embedding --------------------------------------------------------
    def embed(self, frame, det: Detection):
        """Return an L2-normalised 128-D embedding for a detected face."""
        self._ensure_loaded()
        import numpy as np

        aligned = self._recognizer.alignCrop(frame, det.row)
        feat = self._recognizer.feature(aligned).flatten().astype(np.float32)
        norm = float(np.linalg.norm(feat))
        if norm > 0:
            feat = feat / norm
        return feat, aligned

    @staticmethod
    def cosine(a, b) -> float:
        import numpy as np
        return float(np.dot(a, b))  # inputs are already L2-normalised
