"""Start the viewer: ``python -m kazan``."""
import sys

from PySide6.QtWidgets import QApplication

from kazan.viewer import KazanViewer


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName('KazanPy')
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
    win = KazanViewer()
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
