from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget


class RainbowSpinner(QWidget):
    """A compact rotating spectral ring for long-running reader tasks."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._angle = 0

        self.setFixedSize(72, 72)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._timer = QTimer(self)
        self._timer.setInterval(32)
        self._timer.timeout.connect(self._advance)

    def sizeHint(self):
        return QSize(72, 72)

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self):
        self._angle = (self._angle - 5) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ring = self.rect().adjusted(8, 8, -8, -8)

        gradient = QConicalGradient(ring.center(), self._angle)
        gradient.setColorAt(0.00, QColor("#ff557f"))
        gradient.setColorAt(0.17, QColor("#ffb84d"))
        gradient.setColorAt(0.34, QColor("#80e36c"))
        gradient.setColorAt(0.51, QColor("#48d8e8"))
        gradient.setColorAt(0.68, QColor("#6695ff"))
        gradient.setColorAt(0.85, QColor("#b96cff"))
        gradient.setColorAt(1.00, QColor("#ff557f"))

        rainbow_pen = QPen(QBrush(gradient), 7)
        rainbow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        painter.setPen(rainbow_pen)
        painter.drawArc(ring, self._angle * 16, 285 * 16)
