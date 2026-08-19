from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
)


class PlayerControls(QWidget):
    play_clicked = Signal()
    previous_clicked = Signal()
    next_clicked = Signal()

    back_clicked = Signal()
    forward_clicked = Signal()

    seek_requested = Signal(float)

    def __init__(self):
        super().__init__()

        self.duration = 0.0

        self._build_ui()
        self._connect_events()

    def _build_ui(self):
        root = QVBoxLayout(self)

        root.setContentsMargins(0, 0, 0, 0)

        seek_row = QHBoxLayout()

        self.current_time_label = QLabel("0:00")

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)

        self.duration_label = QLabel("0:00")

        seek_row.addWidget(self.current_time_label)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addWidget(self.duration_label)

        root.addLayout(seek_row)

        controls = QHBoxLayout()

        controls.addStretch()

        self.back_button = QPushButton("-15")
        self.previous_button = QPushButton("Previous")
        self.play_button = QPushButton("Play")
        self.next_button = QPushButton("Next")
        self.forward_button = QPushButton("+15")

        self.play_button.setObjectName("primaryPlayerButton")

        controls.addWidget(self.back_button)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.forward_button)

        controls.addStretch()

        root.addLayout(controls)

    def _connect_events(self):
        self.play_button.clicked.connect(self.play_clicked.emit)
        self.previous_button.clicked.connect(self.previous_clicked.emit)
        self.next_button.clicked.connect(self.next_clicked.emit)
        self.back_button.clicked.connect(self.back_clicked.emit)
        self.forward_button.clicked.connect(self.forward_clicked.emit)

        self.seek_slider.sliderReleased.connect(self._seek_finished)

    def _seek_finished(self):
        if self.duration <= 0:
            return

        ratio = self.seek_slider.value() / 1000

        self.seek_requested.emit(ratio * self.duration)

    def set_enabled_controls(self, enabled: bool):
        self.back_button.setEnabled(enabled)
        self.seek_slider.setEnabled(enabled)
        self.forward_button.setEnabled(enabled)
        self.previous_button.setEnabled(enabled)
        self.play_button.setEnabled(enabled)
        self.next_button.setEnabled(enabled)

    def set_playing(self, playing: bool):
        self.play_button.setText("Pause" if playing else "Play")

    def set_timing(self, position: float, duration: float):
        self.duration = duration

        if not self.seek_slider.isSliderDown():

            if duration > 0:
                ratio = position / duration

                value = int(max(0, min(ratio, 1)) * 1000)

            else:
                value = 0

            self.seek_slider.setValue(value)

        self.current_time_label.setText(self._format_time(position))
        self.duration_label.setText(self._format_time(duration))

    @staticmethod
    def _format_time(seconds: float) -> str:
        seconds = max(0, int(seconds))

        minutes = seconds // 60
        remaining = seconds % 60

        return f"{minutes}:{remaining:02}"
