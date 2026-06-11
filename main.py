import ctypes
import sys
import os

# DPI-aware (Windows)
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from botforge.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BotForge")
    app.setOrganizationName("BotForge")
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
