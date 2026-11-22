"""MediaPipe Face Detector による顔検出"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

# PyInstallerでビルドしたアプリでは同梱データの展開先を基準にする
_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
MODEL_PATH = _BASE_DIR / "models" / "blaze_face_short_range.tflite"


@dataclass(frozen=True)
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h


class FaceDetector:
    """RGB画像から顔の一覧を返す。信頼度による絞り込みは呼び出し側で行う"""

    def __init__(self, model_path: Path = MODEL_PATH):
        if not model_path.exists():
            raise FileNotFoundError(f"モデルファイルがありません: {model_path}")
        options = vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.2,
        )
        self._detector = vision.FaceDetector.create_from_options(options)
        self._last_ts = -1

    def detect(self, rgb, timestamp_ms: int) -> list[Face]:
        ts = max(timestamp_ms, self._last_ts + 1)
        self._last_ts = ts
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect_for_video(image, ts)
        faces = []
        for d in result.detections:
            bb = d.bounding_box
            score = d.categories[0].score if d.categories else 0.0
            faces.append(Face(bb.origin_x, bb.origin_y, bb.width, bb.height, score))
        return faces

    def close(self) -> None:
        self._detector.close()


def pick_target(faces: list[Face], min_confidence: float) -> Face | None:
    """信頼度を満たす顔のうち最も大きいものを返す"""
    candidates = [f for f in faces if f.score >= min_confidence]
    return max(candidates, key=lambda f: f.area) if candidates else None
