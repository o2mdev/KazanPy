"""Small widgets shared by the viewer and plugins."""
from __future__ import annotations

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox


class SciSpinBox(QDoubleSpinBox):
    """MATLAB ``uispinner``: keeps full precision and shows ``%g`` (1e-06, 3.5e+09)."""

    def __init__(self, value: float = 0.0, step: float = 1.0, minimum: float = -1e300,
                 maximum: float = 1e300):
        super().__init__(decimals=320, minimum=minimum, maximum=maximum, singleStep=step,
                         keyboardTracking=False)
        self.setValue(value)

    def textFromValue(self, v):
        return f'{v:.6g}'

    def valueFromText(self, text):
        try:
            return float(text)
        except ValueError:
            return self.value()

    def validate(self, text, pos):
        try:
            float(text)
            return QValidator.State.Acceptable, text, pos
        except ValueError:
            return QValidator.State.Intermediate, text, pos
