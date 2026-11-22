"""PySide6 GUI"""

from __future__ import annotations

import math
import time

import serial
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .camera import CaptureWorker, list_cameras
from .controller import TrackingController
from .detector import Face
from .serial_controller import SerialOutput, available_ports, format_command
from .simulation import VirtualServo

TARGET_COLOR = QColor(230, 130, 30)
CURRENT_COLOR = QColor(40, 120, 230)
GRID_COLOR = QColor(120, 120, 120)


class VideoView(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(480, 270)
        self._image: QImage | None = None
        self._face: Face | None = None
        self._message = "カメラ起動中"

    def set_frame(self, image: QImage, face: Face | None) -> None:
        self._image, self._face, self._message = image, face, ""
        self.update()

    def set_message(self, text: str) -> None:
        self._message = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), Qt.GlobalColor.black)
        img = self._image
        if img is not None:
            scale = min(self.width() / img.width(), self.height() / img.height())
            w, h = img.width() * scale, img.height() * scale
            ox, oy = (self.width() - w) / 2, (self.height() - h) / 2
            p.drawImage(QRectF(ox, oy, w, h), img)

            p.setPen(QPen(QColor(255, 255, 255, 90), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(ox + w / 2, oy), QPointF(ox + w / 2, oy + h))
            p.drawLine(QPointF(ox, oy + h / 2), QPointF(ox + w, oy + h / 2))

            f = self._face
            if f is not None:
                p.setPen(QPen(QColor(60, 220, 90), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(ox + f.x * scale, oy + f.y * scale, f.w * scale, f.h * scale))
                c = QPointF(ox + f.cx * scale, oy + f.cy * scale)
                p.setBrush(QColor(255, 60, 60))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(c, 5, 5)
                p.setPen(Qt.GlobalColor.white)
                p.drawText(
                    QRectF(ox + 8, oy + 8, w - 16, 20),
                    f"中心 ({f.cx:.0f}, {f.cy:.0f})  信頼度 {f.score:.2f}",
                )
        if self._message:
            p.setPen(Qt.GlobalColor.white)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)


class SpeakerView(QWidget):
    """上面図(Pan)と側面図(Tilt)"""

    def __init__(self, controller: TrackingController, servo: VirtualServo):
        super().__init__()
        self.ctrl, self.servo = controller, servo
        self.setMinimumSize(420, 220)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.palette().base())
        s = self.ctrl.settings
        half = self.width() / 2
        area_h = self.height() - 44

        # 上面図: 前方が上、Pan 180 が右
        top = QRectF(0, 0, half, area_h)
        r = min(top.width() / 2 - 20, top.height() - 36)
        base = QPointF(top.center().x(), top.bottom() - 10)
        to_screen = lambda pan: 180.0 - pan  # noqa: E731
        self._draw_dial(p, base, r, to_screen, 0, 180, s.pan_min, s.pan_max,
                        self.ctrl.target_pan, self.servo.pan, "上面図 Pan", top, ("180°", "0°"))

        # 側面図: 前方が右、Tilt 180 が上
        side = QRectF(half, 0, half, area_h)
        r2 = min(side.width() - 50, side.height() / 2 - 24)
        base2 = QPointF(side.left() + 24, side.top() + 18 + (side.height() - 18) / 2)
        to_screen2 = lambda tilt: tilt - 90.0  # noqa: E731
        self._draw_dial(p, base2, r2, to_screen2, -90, 90, s.tilt_min, s.tilt_max,
                        self.ctrl.target_tilt, self.servo.tilt, "側面図 Tilt", side, ("0°", "180°"))

        p.setPen(self.palette().text().color())
        font = QFont(p.font())
        font.setPointSize(font.pointSize() + 1)
        p.setFont(font)
        y = self.height() - 40
        p.setPen(TARGET_COLOR)
        p.drawText(QRectF(10, y, self.width() - 20, 18), Qt.AlignmentFlag.AlignLeft,
                   f"目標  Pan {self.ctrl.target_pan:6.1f}°   Tilt {self.ctrl.target_tilt:6.1f}°")
        p.setPen(CURRENT_COLOR)
        p.drawText(QRectF(10, y + 20, self.width() - 20, 18), Qt.AlignmentFlag.AlignLeft,
                   f"現在  Pan {self.servo.pan:6.1f}°   Tilt {self.servo.tilt:6.1f}°")

    @staticmethod
    def _pt(base: QPointF, r: float, deg: float) -> QPointF:
        a = math.radians(deg)
        return QPointF(base.x() + r * math.cos(a), base.y() - r * math.sin(a))

    def _draw_dial(self, p, base, r, to_screen, a_lo, a_hi, lim_lo, lim_hi,
                   target, current, title, area, end_labels):
        text = self.palette().text().color()
        p.setPen(text)
        p.drawText(QRectF(area.left() + 8, area.top() + 4, area.width(), 16), title)

        # 可動範囲の円弧
        rect = QRectF(base.x() - r, base.y() - r, 2 * r, 2 * r)
        p.setPen(QPen(GRID_COLOR, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, int(a_lo * 16), int((a_hi - a_lo) * 16))
        lo, hi = sorted((to_screen(lim_lo), to_screen(lim_hi)))
        p.setPen(QPen(QColor(120, 120, 120, 120), 6))
        p.drawArc(rect, int(lo * 16), int((hi - lo) * 16))
        p.setPen(QPen(GRID_COLOR, 1, Qt.PenStyle.DotLine))
        for lim in (lim_lo, lim_hi):
            p.drawLine(base, self._pt(base, r, to_screen(lim)))
        p.setPen(GRID_COLOR)
        # end_labels: (a_lo側のラベル, a_hi側のラベル)
        p.drawText(self._pt(base, r + 4, a_lo) + QPointF(-14, 14), end_labels[0])
        p.drawText(self._pt(base, r + 4, a_hi) + QPointF(-14, -4 if a_hi < 180 else 14), end_labels[1])

        # 目標方向
        p.setPen(QPen(TARGET_COLOR, 2, Qt.PenStyle.DashLine))
        p.drawLine(base, self._pt(base, r, to_screen(target)))

        # 現在方向のビームとスピーカー本体
        a = to_screen(current)
        p.setPen(QPen(CURRENT_COLOR, 3))
        p.drawLine(base, self._pt(base, r * 0.9, a))
        body = QPolygonF([
            self._pt(base, 14, a + 90), self._pt(base, 14, a - 90),
            self._pt(base, 26, a - 25), self._pt(base, 26, a + 25),
        ])
        p.setBrush(CURRENT_COLOR)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(body)
        p.setBrush(text)
        p.drawEllipse(base, 4, 4)


def _spin(lo, hi, value, step, decimals=1, suffix=""):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(value)
    if suffix:
        w.setSuffix(suffix)
    return w


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Speaker Tracker")
        self.ctrl = TrackingController()
        self.servo = VirtualServo()
        self.serial = SerialOutput()
        self.worker: CaptureWorker | None = None
        self.output_mode = "Simulation"
        self._last_tick = time.monotonic()
        self._last_send = 0.0
        self._frame_times: list[float] = []

        self.video = VideoView()
        self.speaker = SpeakerView(self.ctrl, self.servo)
        self.status = QLabel()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.speaker, 1)
        rl.addWidget(self._build_tabs(), 1)

        splitter = QSplitter()
        splitter.addWidget(self.video)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.addWidget(splitter, 1)
        cl.addWidget(self.status)
        self.setCentralWidget(central)
        self.resize(1320, 760)

        self._sync_controls()
        self.start_camera(0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    # ---------- UI構築 ----------
    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_control_tab(), "操作")
        tabs.addTab(self._build_settings_tab(), "設定")
        tabs.addTab(self._build_output_tab(), "出力")
        return tabs

    def _build_control_tab(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)

        self.auto_box = QCheckBox("自動追従")
        self.auto_box.setChecked(True)
        self.auto_box.toggled.connect(self._on_auto)
        self.pause_btn = QPushButton("一時停止")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause)
        center_btn = QPushButton("中央へ (90°, 90°)")
        center_btn.clicked.connect(self._on_center)
        self.estop_btn = QPushButton("緊急停止")
        self.estop_btn.setCheckable(True)
        self.estop_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:white;font-weight:bold;padding:6px}"
            "QPushButton:checked{background:#6d1b1b}"
        )
        self.estop_btn.toggled.connect(self._on_estop)

        g.addWidget(self.auto_box, 0, 0)
        g.addWidget(self.pause_btn, 0, 1)
        g.addWidget(center_btn, 0, 2)
        g.addWidget(self.estop_btn, 1, 0, 1, 3)

        self.pan_slider, self.pan_val = self._slider()
        self.tilt_slider, self.tilt_val = self._slider()
        self.pan_slider.valueChanged.connect(self._on_slider)
        self.tilt_slider.valueChanged.connect(self._on_slider)
        g.addWidget(QLabel("Pan"), 2, 0)
        g.addWidget(self.pan_slider, 2, 1)
        g.addWidget(self.pan_val, 2, 2)
        g.addWidget(QLabel("Tilt"), 3, 0)
        g.addWidget(self.tilt_slider, 3, 1)
        g.addWidget(self.tilt_val, 3, 2)
        g.setRowStretch(4, 1)
        return w

    @staticmethod
    def _slider():
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 1800)
        s.setValue(900)
        lbl = QLabel("90.0°")
        lbl.setMinimumWidth(56)
        return s, lbl

    def _build_settings_tab(self) -> QWidget:
        s = self.ctrl.settings
        form_w = QWidget()
        f = QFormLayout(form_w)

        self.camera_combo = QComboBox()
        self.camera_combo.addItems(list_cameras())
        self.camera_combo.currentIndexChanged.connect(self.start_camera)
        f.addRow("カメラ", self.camera_combo)

        def add(label, widget, attr, after=None):
            def apply(v):
                setattr(s, attr, v)
                if after:
                    after()
            if isinstance(widget, QCheckBox):
                widget.toggled.connect(apply)
            else:
                widget.valueChanged.connect(apply)
            f.addRow(label, widget)

        add("検出信頼度", _spin(0.1, 0.95, s.min_confidence, 0.05, 2), "min_confidence")
        add("デッドゾーン", _spin(0, 10, s.deadzone_deg, 0.5, suffix="°"), "deadzone_deg")
        add("平滑化", _spin(0, 0.95, s.smoothing, 0.05, 2), "smoothing")
        add("最大回転速度", _spin(5, 360, s.max_speed_deg_s, 5, 0, "°/s"), "max_speed_deg_s")
        add("角度更新頻度", _spin(1, 60, s.update_hz, 1, 0, " Hz"), "update_hz")
        add("顔ロスト判定", _spin(0.2, 10, s.lost_timeout_s, 0.5, suffix=" s"), "lost_timeout_s")
        add("水平画角", _spin(20, 150, s.hfov_deg, 1, suffix="°"), "hfov_deg")
        add("垂直画角", _spin(10, 120, s.vfov_deg, 1, suffix="°"), "vfov_deg")
        add("Pan 最小", _spin(0, 180, s.pan_min, 1, 0, "°"), "pan_min", self._on_limits)
        add("Pan 最大", _spin(0, 180, s.pan_max, 1, 0, "°"), "pan_max", self._on_limits)
        add("Tilt 最小", _spin(0, 180, s.tilt_min, 1, 0, "°"), "tilt_min", self._on_limits)
        add("Tilt 最大", _spin(0, 180, s.tilt_max, 1, 0, "°"), "tilt_max", self._on_limits)
        inv_p, inv_t = QCheckBox(), QCheckBox()
        add("Pan 反転", inv_p, "invert_pan")
        add("Tilt 反転", inv_t, "invert_tilt")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_w)
        return scroll

    def _build_output_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Simulation", "Serial"])
        self.mode_combo.currentTextChanged.connect(self._on_mode)
        f.addRow("出力", self.mode_combo)

        self.port_combo = QComboBox()
        refresh = QPushButton("更新")
        refresh.clicked.connect(self._refresh_ports)
        row = QHBoxLayout()
        row.addWidget(self.port_combo, 1)
        row.addWidget(refresh)
        f.addRow("ポート", row)

        self.connect_btn = QPushButton("接続")
        self.connect_btn.clicked.connect(self._on_connect)
        self.arm_btn = QPushButton("送信開始")
        self.arm_btn.clicked.connect(self._on_arm)
        row2 = QHBoxLayout()
        row2.addWidget(self.connect_btn)
        row2.addWidget(self.arm_btn)
        f.addRow("", row2)

        self.cmd_label = QLabel()
        self.cmd_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addRow("角度指示", self.cmd_label)
        self.serial_status = QLabel()
        self.serial_status.setWordWrap(True)
        f.addRow("状態", self.serial_status)

        self._refresh_ports()
        self._update_serial_ui()
        return w

    # ---------- カメラ ----------
    def start_camera(self, index: int) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.video.set_message("カメラ起動中")
        self.worker = CaptureWorker(index, self.ctrl.settings)
        self.worker.frame_ready.connect(self._on_frame)
        self.worker.failed.connect(self._on_camera_failed)
        self.worker.start()

    def _on_frame(self, image: QImage, face, w: int, h: int) -> None:
        now = time.monotonic()
        self.video.set_frame(image, face)
        self.ctrl.on_face(face, w, h, now)
        self._frame_times = [t for t in self._frame_times if now - t < 1.0] + [now]

    def _on_camera_failed(self, msg: str) -> None:
        self.video.set_message(msg)
        self.ctrl.mark_camera_error()
        self._frame_times.clear()
        if self.serial.armed:
            self.serial.disarm()
            self._set_serial_error(f"カメラエラーのため送信停止: {msg}")
        self._update_serial_ui()
        # カメラ許可後や再接続後に復帰できるよう再試行する
        failed_worker = self.sender()
        QTimer.singleShot(3000, lambda: self._retry_camera(failed_worker))

    def _retry_camera(self, failed_worker) -> None:
        if self.worker is failed_worker and not self.isHidden():
            self.start_camera(self.camera_combo.currentIndex())

    # ---------- 操作 ----------
    def _on_auto(self, on: bool) -> None:
        self.ctrl.auto = on
        self._sync_controls()

    def _on_pause(self, on: bool) -> None:
        self.ctrl.paused = on
        self._sync_controls()

    def _on_center(self) -> None:
        self.ctrl.center()
        self._sync_controls()

    def _on_estop(self, on: bool) -> None:
        if on:
            self.ctrl.emergency_stop(self.servo.angles)
            if self.serial.armed:
                self.serial.disarm()
        else:
            self.ctrl.release_stop()
        self._sync_controls()
        self._update_serial_ui()

    def _on_slider(self) -> None:
        pan, tilt = self.pan_slider.value() / 10, self.tilt_slider.value() / 10
        self.ctrl.set_manual(pan, tilt)
        self._sync_sliders()

    def _on_limits(self) -> None:
        self.ctrl.clamp_target()
        self._sync_sliders()

    def _sync_controls(self) -> None:
        c = self.ctrl
        for wdg, val in ((self.auto_box, c.auto), (self.pause_btn, c.paused)):
            wdg.blockSignals(True)
            wdg.setChecked(val)
            wdg.blockSignals(False)
        self.auto_box.setEnabled(not c.estop)
        self.pause_btn.setEnabled(c.auto and not c.estop)
        manual = not c.auto and not c.estop
        self.pan_slider.setEnabled(manual)
        self.tilt_slider.setEnabled(manual)
        self._sync_sliders()

    def _sync_sliders(self) -> None:
        for sl, lbl, v in ((self.pan_slider, self.pan_val, self.ctrl.target_pan),
                           (self.tilt_slider, self.tilt_val, self.ctrl.target_tilt)):
            sl.blockSignals(True)
            sl.setValue(round(v * 10))
            sl.blockSignals(False)
            lbl.setText(f"{v:.1f}°")

    # ---------- 出力 ----------
    def _refresh_ports(self) -> None:
        current = self.port_combo.currentData()
        self.port_combo.clear()
        for dev, desc in available_ports():
            self.port_combo.addItem(f"{dev} ({desc})" if desc != dev else dev, dev)
        idx = self.port_combo.findData(current)
        if idx >= 0:
            self.port_combo.setCurrentIndex(idx)
        self._update_serial_ui()

    def _on_mode(self, mode: str) -> None:
        self.output_mode = mode
        if mode == "Simulation":
            self.serial.disconnect()
        self.serial_status.setStyleSheet("")
        self.serial_status.setText("")
        self._update_serial_ui()

    def _on_connect(self) -> None:
        if self.serial.connected:
            self.serial.disconnect()
            self._update_serial_ui()
            return
        port = self.port_combo.currentData()
        if not port:
            return
        ok = QMessageBox.question(
            self, "シリアル接続",
            f"{port} に 115200bps で接続します\n接続後は「送信開始」を押すまで角度指示を送信しません",
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            self.serial.connect(port)
            self.serial_status.setStyleSheet("")
            self.serial_status.setText(f"{port} に接続済み（送信停止中）")
        except (serial.SerialException, OSError) as e:
            self._set_serial_error(f"接続失敗: {e}")
        self._update_serial_ui()

    def _on_arm(self) -> None:
        if self.serial.armed:
            self.serial.disarm()
        elif not self.ctrl.estop:
            self.serial.arm()
            self._last_send = 0.0
        self._update_serial_ui()

    def _set_serial_error(self, msg: str) -> None:
        self.serial_status.setStyleSheet("color:#d32f2f")
        self.serial_status.setText(msg)

    def _update_serial_ui(self) -> None:
        serial_mode = self.output_mode == "Serial"
        self.port_combo.setEnabled(serial_mode and not self.serial.connected)
        self.connect_btn.setEnabled(serial_mode and (self.serial.connected or self.port_combo.count() > 0))
        self.connect_btn.setText("切断" if self.serial.connected else "接続")
        self.arm_btn.setEnabled(serial_mode and self.serial.connected and not self.ctrl.estop)
        self.arm_btn.setText("送信停止" if self.serial.armed else "送信開始")
        if serial_mode and self.port_combo.count() == 0 and not self.serial.connected:
            self.serial_status.setStyleSheet("")
            self.serial_status.setText("シリアルポートが見つかりません")
        elif serial_mode and self.serial.connected and self.serial_status.styleSheet() == "":
            state = "送信中" if self.serial.armed else "送信停止中"
            self.serial_status.setText(f"{self.serial.port} に接続済み（{state}）")

    def _send_serial(self, now: float) -> None:
        if self.output_mode != "Serial" or not self.serial.armed or self.ctrl.estop:
            return
        if now - self._last_send < 1.0 / max(self.ctrl.settings.update_hz, 0.1):
            return
        self._last_send = now
        try:
            self.serial.send(*self.servo.angles)
        except (serial.SerialException, OSError) as e:
            self.serial.disconnect()
            self._set_serial_error(f"送信エラーのため切断: {e}")
            self._refresh_ports()

    # ---------- メインループ ----------
    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        self.ctrl.tick(now)
        if not self.ctrl.estop:
            self.servo.step(self.ctrl.target, dt, self.ctrl.settings.max_speed_deg_s)
        self._send_serial(now)

        if self.ctrl.auto:
            self._sync_sliders()
        self.speaker.update()
        cmd = format_command(*self.servo.angles).strip()
        sending = self.output_mode == "Serial" and self.serial.armed
        self.cmd_label.setText(f"{cmd}  {'送信中' if sending else '未送信'}")
        raw = self.ctrl.raw
        raw_txt = f"  顔方向 P {raw[0]:.1f}° T {raw[1]:.1f}°" if raw and not self.ctrl.lost else ""
        self.status.setText(
            f"状態: {self.ctrl.status()}   出力: {self.output_mode}   "
            f"{len(self._frame_times)} fps{raw_txt}"
        )

    def closeEvent(self, event):
        self.timer.stop()
        if self.worker is not None:
            self.worker.stop()
        self.serial.disconnect()
        super().closeEvent(event)
