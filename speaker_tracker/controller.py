"""顔位置から目標角度を計算し、平滑化・デッドゾーン・更新頻度制限を行う"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .detector import Face

CENTER = 90.0


@dataclass
class TrackingSettings:
    hfov_deg: float = 70.0
    vfov_deg: float = 43.0
    pan_min: float = 0.0
    pan_max: float = 180.0
    tilt_min: float = 45.0
    tilt_max: float = 135.0
    invert_pan: bool = False
    invert_tilt: bool = False
    deadzone_deg: float = 1.5
    smoothing: float = 0.6  # 0 = 平滑化なし, 1に近いほど遅く追従
    max_speed_deg_s: float = 90.0
    update_hz: float = 20.0
    min_confidence: float = 0.6
    lost_timeout_s: float = 2.0
    # 将来の補正用: カメラから見たスピーカー回転中心の位置 [m]（x=右, y=下, z=前方）
    speaker_offset_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # 顔までの距離推定に使う顔幅 [m]
    face_width_m: float = 0.15


def face_to_angles(face: Face, width: int, height: int, s: TrackingSettings) -> tuple[float, float]:
    """ピンホールカメラモデルで顔方向を求め、サーボ角度(Pan, Tilt)に変換する"""
    fx = (width / 2) / math.tan(math.radians(s.hfov_deg) / 2)
    fy = (height / 2) / math.tan(math.radians(s.vfov_deg) / 2)
    # カメラ座標系の視線ベクトル (x=右, y=下, z=前方)
    x = (face.cx - width / 2) / fx
    y = (face.cy - height / 2) / fy
    z = 1.0

    ox, oy, oz = s.speaker_offset_m
    if (ox, oy, oz) != (0.0, 0.0, 0.0) and face.w > 0:
        # 顔幅から距離を推定し、スピーカー位置から見た方向に補正する
        depth = fx * s.face_width_m / face.w
        x, y, z = x * depth - ox, y * depth - oy, depth - oz

    yaw = math.degrees(math.atan2(x, z))
    pitch = math.degrees(math.atan2(-y, math.hypot(x, z)))
    pan = CENTER - yaw if s.invert_pan else CENTER + yaw
    tilt = CENTER - pitch if s.invert_tilt else CENTER + pitch
    return pan, tilt


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class TrackingController:
    settings: TrackingSettings = field(default_factory=TrackingSettings)
    auto: bool = True
    paused: bool = False
    estop: bool = False
    target_pan: float = CENTER
    target_tilt: float = CENTER
    raw: tuple[float, float] | None = None
    lost: bool = True
    _filtered: tuple[float, float] | None = None
    _last_commit: float = -1e9
    _last_face_t: float | None = None

    @property
    def tracking_active(self) -> bool:
        return self.auto and not self.paused and not self.estop and not self.lost

    @property
    def target(self) -> tuple[float, float]:
        return self.target_pan, self.target_tilt

    def on_face(self, face: Face | None, width: int, height: int, now: float) -> None:
        if face is None:
            return
        self._last_face_t = now
        self.lost = False
        self.raw = face_to_angles(face, width, height, self.settings)
        if not self.tracking_active:
            self._filtered = None
            return

        a = clamp(self.settings.smoothing, 0.0, 0.98)
        if self._filtered is None:
            self._filtered = self.raw
        else:
            fp, ft = self._filtered
            self._filtered = (a * fp + (1 - a) * self.raw[0], a * ft + (1 - a) * self.raw[1])

        if now - self._last_commit < 1.0 / max(self.settings.update_hz, 0.1):
            return
        self._last_commit = now
        fp, ft = self._filtered
        dz = self.settings.deadzone_deg
        if abs(fp - self.target_pan) >= dz:
            self.target_pan = fp
        if abs(ft - self.target_tilt) >= dz:
            self.target_tilt = ft
        self.clamp_target()

    def tick(self, now: float) -> None:
        """顔を一定時間見失ったら追従を止め、最後の目標角度を保持する"""
        if self._last_face_t is None or now - self._last_face_t > self.settings.lost_timeout_s:
            if not self.lost:
                self.lost = True
                self._filtered = None

    def mark_camera_error(self) -> None:
        self.lost = True
        self._last_face_t = None
        self._filtered = None

    def set_manual(self, pan: float, tilt: float) -> None:
        if self.auto or self.estop:
            return
        self.target_pan, self.target_tilt = pan, tilt
        self.clamp_target()

    def center(self) -> None:
        if self.estop:
            return
        self.auto = False
        self.target_pan = self.target_tilt = CENTER
        self.clamp_target()

    def emergency_stop(self, current: tuple[float, float]) -> None:
        """その場で停止し、現在角度を目標にする（中央へ戻さない）"""
        self.estop = True
        self.auto = False
        self.target_pan, self.target_tilt = current
        self._filtered = None

    def release_stop(self) -> None:
        self.estop = False

    def clamp_target(self) -> None:
        s = self.settings
        self.target_pan = clamp(self.target_pan, s.pan_min, s.pan_max)
        self.target_tilt = clamp(self.target_tilt, s.tilt_min, s.tilt_max)

    def status(self) -> str:
        if self.estop:
            return "緊急停止中"
        if not self.auto:
            return "手動"
        if self.paused:
            return "一時停止"
        if self.lost:
            return "顔ロスト（角度保持）"
        return "追従中"
