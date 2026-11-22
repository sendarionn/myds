"""PySerialで角度指示をマイコンへ送信する"""

from __future__ import annotations

import serial
from serial.tools import list_ports

BAUDRATE = 115200


def format_command(pan: float, tilt: float) -> str:
    return f"P={round(pan)},T={round(tilt)}\n"


def available_ports() -> list[tuple[str, str]]:
    return [(p.device, p.description or p.device) for p in sorted(list_ports.comports())]


class SerialOutput:
    """接続しただけでは送信しない。arm() を呼んだ後だけ send() が送信する"""

    def __init__(self):
        self._ser: serial.Serial | None = None
        self.armed = False
        self.last_line: str | None = None

    @property
    def connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    @property
    def port(self) -> str | None:
        return self._ser.port if self._ser else None

    def connect(self, port: str) -> None:
        self.disconnect()
        self._ser = serial.Serial(port, BAUDRATE, timeout=0, write_timeout=0.2)
        self.armed = False
        self.last_line = None

    def disconnect(self) -> None:
        self.armed = False
        if self._ser is not None:
            try:
                self._ser.close()
            except serial.SerialException:
                pass
        self._ser = None

    def arm(self) -> None:
        if self.connected:
            self.armed = True
            self.last_line = None

    def disarm(self) -> None:
        self.armed = False

    def send(self, pan: float, tilt: float) -> bool:
        """送信した場合 True。値が前回と同じなら送らない。失敗時は例外を送出する"""
        if not (self.connected and self.armed):
            return False
        line = format_command(pan, tilt)
        if line == self.last_line:
            return False
        if self._ser.in_waiting:
            self._ser.read(self._ser.in_waiting)
        self._ser.write(line.encode("ascii"))
        self.last_line = line
        return True
