from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
)


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)

        root.setContentsMargins(40, 32, 40, 32)

        title = QLabel("Settings")
        title.setObjectName("pageTitle")

        root.addWidget(title)

        hint = QLabel("Changes apply the next time a book is opened.")
        hint.setObjectName("secondaryText")

        root.addWidget(hint)

        form = QFormLayout()

        self.voice_input = QComboBox()
        self.voice_input.addItems(["af_heart", "af_bella", "am_adam"])

        self.speed_input = QDoubleSpinBox()
        self.speed_input.setRange(0.5, 2.0)
        self.speed_input.setSingleStep(0.05)
        self.speed_input.setValue(0.85)

        self.footnotes_input = QCheckBox("Read footnotes")
        self.captions_input = QCheckBox("Read figure captions")
        self.sidebars_input = QCheckBox("Read sidebars")

        form.addRow("Voice", self.voice_input)
        form.addRow("Narration speed", self.speed_input)

        form.addRow(self.footnotes_input)
        form.addRow(self.captions_input)
        form.addRow(self.sidebars_input)

        root.addLayout(form)

        root.addStretch()

    def load_settings(self, settings):
        """Populate widgets without emitting the signals that persist them."""
        widgets = (
            self.voice_input,
            self.speed_input,
            self.footnotes_input,
            self.captions_input,
            self.sidebars_input,
        )

        for widget in widgets:
            widget.blockSignals(True)

        self.voice_input.setCurrentText(settings.get_voice())
        self.speed_input.setValue(settings.get_speed())

        self.footnotes_input.setChecked(settings.get_read_footnotes())
        self.captions_input.setChecked(settings.get_read_captions())
        self.sidebars_input.setChecked(settings.get_read_sidebars())

        for widget in widgets:
            widget.blockSignals(False)
