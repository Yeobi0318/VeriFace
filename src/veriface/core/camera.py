"""Thin, lazy webcam wrapper.

The camera device is only opened when a session needs frames and is always
released afterwards (also via the context-manager protocol), so the webcam LED
is off and no device handle is held while VeriFace is idle.
"""
from __future__ import annotations


class Camera:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480) -> None:
        self.index = index
        self.width = width
        self.height = height
        self._cap = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    def open(self) -> None:
        import cv2  # local import: heavy, only needed during a session

        # CAP_DSHOW opens noticeably faster on Windows than the default backend.
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not cap or not cap.isOpened():
            if cap:
                cap.release()
            raise RuntimeError(
                f"Could not open camera #{self.index}. "
                "Check it is connected and not in use by another app."
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap

    def read(self):
        """Return a BGR frame or raise if the camera dropped."""
        if self._cap is None:
            raise RuntimeError("Camera is not open.")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read a frame from the camera.")
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
