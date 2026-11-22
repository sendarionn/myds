"""カメラ映像取得と顔検出を別スレッドで実行する"""

from __future__ import annotations

import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .detector import FaceDetector, pick_target


def list_cameras() -> list[str]:
    """カメラ名の一覧。順序をOpenCV(AVFoundation)のインデックスとして扱う"""
    try:
        from PySide6.QtMultimedia import QMediaDevices

        names = [d.description() for d in QMediaDevices.videoInputs()]
    except Exception:
        names = []
    return names or ["カメラ 0"]


class CaptureWorker(QThread):
    # QImage(RGB), Face | None, 映像幅, 映像高さ
    frame_ready = Signal(QImage, object, int, int)
    failed = Signal(str)

    def __init__(self, camera_index: int, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        # macOSのカメラ許可要求はメインスレッドでしか処理できないため、ここで開く
        self._cap = cv2.VideoCapture(camera_index, cv2.CAP_AVFOUNDATION)
        if self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    def run(self) -> None:
        cap = self._cap
        if not cap.isOpened():
            self.failed.emit("カメラを開けません（カメラの使用許可を確認してください）")
            return
        try:
            detector = FaceDetector()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"顔検出の初期化に失敗: {e}")
            cap.release()
            return

        misses = 0
        try:
            while not self.isInterruptionRequested():
                ok, frame = cap.read()
                if not ok or frame is None:
                    misses += 1
                    if misses > 30:
                        self.failed.emit("カメラから映像を取得できません")
                        return
                    time.sleep(0.03)
                    continue
                misses = 0
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                faces = detector.detect(rgb, int(time.monotonic() * 1000))
                face = pick_target(faces, self._settings.min_confidence)
                image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                self.frame_ready.emit(image, face, w, h)
        finally:
            detector.close()
            cap.release()

    def stop(self) -> None:
        self.requestInterruption()
        self.wait(2000)
