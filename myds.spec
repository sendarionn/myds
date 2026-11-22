# PyInstaller ビルド設定: scripts/build.sh から実行する
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

APP_NAME = "myds"
BUNDLE_ID = "io.github.sendarionn.myds"
VERSION = "0.1.0"

# MediaPipe Tasks は mediapipe/tasks/c/libmediapipe.dylib を ctypes で読み込むため、同じ位置に同梱する
binaries = collect_dynamic_libs("mediapipe")
datas = [("models/blaze_face_short_range.tflite", "models")]
datas += collect_data_files("mediapipe", excludes=["**/*.dylib", "**/__pycache__/**"])
hiddenimports = collect_submodules("mediapipe.tasks") + ["PySide6.QtMultimedia"]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir 構成
    name=APP_NAME,
    console=False,  # --windowed 相当
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "NSCameraUsageDescription": "顔の位置を検出してスピーカーの向きを制御するためにカメラを使用します",
        "NSHighResolutionCapable": True,
        "LSUIElement": False,  # 通常のDockアプリとして起動
        "LSMinimumSystemVersion": "12.0",
    },
)
