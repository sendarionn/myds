"""仮想サーボ: 最大回転速度を考慮して現在角度を目標へ近づける"""

from __future__ import annotations

from .controller import CENTER


def _approach(current: float, target: float, max_step: float) -> float:
    diff = target - current
    if abs(diff) <= max_step:
        return target
    return current + max_step if diff > 0 else current - max_step


class VirtualServo:
    def __init__(self, pan: float = CENTER, tilt: float = CENTER):
        self.pan = pan
        self.tilt = tilt

    @property
    def angles(self) -> tuple[float, float]:
        return self.pan, self.tilt

    def step(self, target: tuple[float, float], dt: float, max_speed_deg_s: float) -> None:
        max_step = max_speed_deg_s * max(dt, 0.0)
        self.pan = _approach(self.pan, target[0], max_step)
        self.tilt = _approach(self.tilt, target[1], max_step)
