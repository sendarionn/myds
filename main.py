import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # MediaPipeが読み込むmatplotlibのフォントキャッシュを永続化し、起動のたびの再生成（約14秒）を避ける
    cache = Path.home() / "Library" / "Caches" / "myds" / "matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache)
    os.environ.setdefault("MPLBACKEND", "Agg")

from PySide6.QtWidgets import QApplication  # noqa: E402

from speaker_tracker.ui import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("myds")
    win = MainWindow()
    app.aboutToQuit.connect(win.shutdown)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
