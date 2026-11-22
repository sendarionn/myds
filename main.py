import sys

from PySide6.QtWidgets import QApplication

from speaker_tracker.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Speaker Tracker")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
