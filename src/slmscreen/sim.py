"""A simulated output with the same interface as slmscreen.Display: paced at the refresh rate, no window."""

from __future__ import annotations

import threading
import time

import numpy as np


class SimDisplay:
    """Same interface as displays.Display, paced at the configured refresh rate, no window."""

    def __init__(self, role: str, width=1920, height=1080, refresh_hz=60, edid_name=None, **_):
        self.role = role
        self.info = {"connector": f"SIM-{role}", "edid_name": edid_name or f"SIM {role}", "width": width,
                     "height": height, "refresh_hz": refresh_hz, "renderer": "simulated"}
        self._period = 1.0 / refresh_hz
        self._next_flip = time.perf_counter()
        self._lock = threading.Lock()
        self._uploaded: dict[str, np.ndarray] = {}
        self.current: np.ndarray | None = None
        self.frame = 0

    def _check(self, image) -> np.ndarray:
        img = np.asarray(image)
        h, w = self.info["height"], self.info["width"]
        if img.dtype != np.uint8:
            raise TypeError(f"images must be uint8, got {img.dtype}")
        if img.shape[:2] != (h, w) or img.ndim not in (2, 3) or (img.ndim == 3 and img.shape[2] != 3):
            raise ValueError(f"image shape {img.shape} does not fit the display: need ({h}, {w}) or ({h}, {w}, 3)")
        return img

    def show(self, image=None, key=None) -> dict:
        if key is not None:
            if key not in self._uploaded:
                raise KeyError(f"no uploaded pattern named {key!r}")
            img = self._uploaded[key]
        elif image is not None:
            img = self._check(image)
        else:
            raise ValueError("show needs an image or the key of an uploaded pattern")
        with self._lock:
            now = time.perf_counter()
            self._next_flip = max(self._next_flip + self._period, now + 0.0005)
            time.sleep(max(0.0, self._next_flip - now))
            self.current, self.frame = img, self.frame + 1
            return {"frame": self.frame, "t_flip": time.perf_counter()}

    def upload(self, key: str, image) -> dict:
        self._uploaded[key] = self._check(image).copy()
        return {"key": key, "uploaded": len(self._uploaded)}

    def forget(self, key=None) -> dict:
        for k in list(self._uploaded) if key is None else [key]:
            self._uploaded.pop(k, None)
        return {"uploaded": len(self._uploaded)}

    def close(self) -> None:
        pass
