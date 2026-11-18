"""Symmetrize plugin: port of Symmetrize.mlapp (reference plugin for the KazanHost API).

Mirrors the source around a symmetry center and shows source (red), flipped (blue)
and their average (green) in the viewer's Output.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDoubleSpinBox, QGridLayout,
                               QHBoxLayout, QLabel, QPushButton, QWidget)

from kazan.core import KazanPlugin


def _interp_columns(x, y, xq):
    """MATLAB interp1(x, Y, xq): column-wise, NaN outside the range."""
    order = np.argsort(x)
    xs = x[order]
    out = np.empty((len(xq), y.shape[1]), dtype=y.dtype)
    for k in range(y.shape[1]):
        col = y[order, k]
        if np.iscomplexobj(col):
            out[:, k] = (np.interp(xq, xs, col.real, left=np.nan, right=np.nan)
                         + 1j * np.interp(xq, xs, col.imag, left=np.nan, right=np.nan))
        else:
            out[:, k] = np.interp(xq, xs, col, left=np.nan, right=np.nan)
    return out


class Symmetrize(KazanPlugin):
    menu_name = 'SYMMETRIZE'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.resize(365, 356)
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 2)

        g.addWidget(QLabel('Symmetry center'), 0, 0)
        self.eCenter = QDoubleSpinBox(decimals=4, minimum=-1e12, maximum=1e12, singleStep=1)
        g.addWidget(self.eCenter, 0, 1)

        steps = QHBoxLayout()
        steps.setSpacing(1)
        self.step_group = QButtonGroup(self)
        for text, step in (('0.001', 0.001), ('0.01', 0.01), ('0.1', 0.1), ('x1', 1.0),
                           ('10', 10.0), ('100', 100.0)):
            b = QPushButton(text, checkable=True)
            b.setChecked(step == 1.0)
            b.clicked.connect(lambda _=False, s=step: self.eCenter.setSingleStep(s))
            self.step_group.addButton(b)
            steps.addWidget(b)
        g.addLayout(steps, 1, 1)

        self.cbInvY = QCheckBox('Inv Y')
        self.cbSource = QCheckBox('Show Source', checked=True)
        self.cbFlip = QCheckBox('Show flipped')
        self.cbSum = QCheckBox('Show Sum', checked=True)
        for row, (cb, note) in enumerate(((self.cbInvY, 'multiply symmetric spectrum by -1'),
                                          (self.cbSource, '(red)'), (self.cbFlip, '(blue)'),
                                          (self.cbSum, '(green)')), start=2):
            g.addWidget(cb, row, 0)
            g.addWidget(QLabel(note), row, 1)
            cb.toggled.connect(self.calculate)

        self.pbCalculate = QPushButton('Calculate')
        self.pbCalculate.setMinimumHeight(60)
        self.pbCalculate.clicked.connect(self.calculate)
        g.addWidget(self.pbCalculate, 6, 0, 2, 2)
        self.eCenter.valueChanged.connect(self.calculate)

        # start at the middle of the data, as a sensible default
        x = self.host.get_data('source').ax.x
        if len(x):
            self.eCenter.blockSignals(True)
            self.eCenter.setValue(float((x[0] + x[-1]) / 2))
            self.eCenter.blockSignals(False)

    def file_update(self):
        self.calculate()

    def calculate(self):
        signal = self.host.get_data('source')
        if signal.is_empty:
            return
        x0 = self.eCenter.value()
        x = signal.ax.x
        flipped = _interp_columns(x, signal.y, 2 * x0 - x)
        if self.cbInvY.isChecked():
            flipped = -flipped

        out = []
        if self.cbSource.isChecked():
            s = signal.copy()
            s.title = 'source'
            s.ax.Color = 'r'
            out.append(s)
        if self.cbFlip.isChecked():
            s = signal.copy()
            s.y = flipped
            s.title = 'signal'
            s.ax.Color = 'b'
            out.append(s)
        if self.cbSum.isChecked():
            s = signal.copy()
            s.y = (flipped + signal.y) / 2
            s.title = 'signal'
            s.ax.Color = 'g'
            out.append(s)
        self.host.set_data('output', out)
