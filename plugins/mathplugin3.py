"""Math plugin: port of mathplugin3.mlapp.

Simple data manipulation of the source, shown in Output: part (as is / real / imag /
abs), cut by point ranges or by a MATLAB index expression on the 2nd dimension,
transpose, sum over the 2nd dimension, zero- and first-order phase.

Indices in the plugin are 1-based, as in MATLAB (they are shown to the user).

Differences from MATLAB (see README):
* The point ranges start as the full data (MATLAB set them to 1..1 when the limits
  were applied, so *Cut Data* first showed a single point).
* The 2nd-dimension expression accepts MATLAB index syntax only (``[5,8,9]``,
  ``1:2:end``) instead of a general ``eval``.
"""
from __future__ import annotations

import re

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QWidget)

from kazan.core import KazanPlugin
from kazan.viewer.widgets import SciSpinBox


def matlab_index(expr: str, n: int) -> np.ndarray:
    """MATLAB index expression (1-based, ``end`` allowed) -> 0-based integer array."""
    expr = expr.strip().strip('[]').replace('end', str(n))
    out = []
    for part in re.split(r'[,\s]+', expr.strip()):
        if not part:
            continue
        nums = [float(eval(p, {'__builtins__': {}}, {})) for p in part.split(':')]
        if len(nums) == 1:
            out.append(nums[0])
        elif len(nums) in (2, 3):
            a, st, b = (nums[0], 1.0, nums[1]) if len(nums) == 2 else nums
            count = int(np.floor((b - a) / st + 1e-9)) + 1 if st else 0
            out.extend(a + st * np.arange(max(count, 0)))
        else:
            raise ValueError(f'bad index {part!r}')
    idx = np.asarray(out, int) - 1
    if idx.size and (idx.min() < 0 or idx.max() >= n):
        raise IndexError(f'index exceeds dimension ({n})')
    return idx


def _state(text, checked=False):
    b = QPushButton(text)
    b.setCheckable(True)
    b.setChecked(checked)
    return b


def _label(text, align=Qt.AlignmentFlag.AlignRight, bold=False):
    lab = QLabel(text)
    lab.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    if bold:
        lab.setStyleSheet('font-weight: bold;')
    return lab


class mathplugin3(KazanPlugin):  # noqa: N801 - MATLAB name
    menu_name = 'MATHPLUGIN3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('mathplugin')
        self.resize(315, 465)
        self._build_ui()
        self.file_update()

    # ================================================================ UI
    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(4, 4, 4, 4)
        g.setSpacing(4)
        for c in range(5):
            g.setColumnStretch(c, 1)
        g.setRowMinimumHeight(1, 8)
        g.setRowMinimumHeight(7, 8)

        # row 1: data part, transpose
        self.bAsIs, self.bReal, self.bImag, self.bAbs = (
            _state('as is', True), _state('real'), _state('imag'), _state('abs'))
        self.part_group = QButtonGroup(self)
        for c, b in enumerate((self.bAsIs, self.bReal, self.bImag, self.bAbs)):
            self.part_group.addButton(b)
            g.addWidget(b, 0, c)
        self.part_group.buttonClicked.connect(self.plott)
        self.pbTranspose = _state('Transpose')
        g.addWidget(self.pbTranspose, 0, 4)

        # rows 3-7: cut
        self.bCutData = _state('Cut Data')
        g.addWidget(self.bCutData, 2, 0, 1, 2)
        g.addWidget(_label('1', Qt.AlignmentFlag.AlignHCenter, True), 3, 1)
        g.addWidget(_label('2', Qt.AlignmentFlag.AlignHCenter, True), 4, 1)
        self.bResetCut = QPushButton('Reset')
        g.addWidget(self.bResetCut, 5, 0)
        self.tbSum = _state('sum(y,2)')
        g.addWidget(self.tbSum, 5, 1)
        self.e1DFirst, self.e1DLast, self.e2DFirst, self.e2DLast = (QSpinBox() for _ in range(4))
        for row, (text, sp) in enumerate((('start', self.e1DFirst), ('end', self.e1DLast),
                                          ('start', self.e2DFirst), ('end', self.e2DLast)), start=2):
            g.addWidget(_label(text), row, 2)
            sp.setKeyboardTracking(False)
            sp.setRange(1, 1)
            g.addWidget(sp, row, 3, 1, 2)
        self.cbExpression2Dim = QCheckBox(' eval')
        self.cbExpression2Dim.setToolTip('Expression (i.e. [5,8,9])')
        g.addWidget(self.cbExpression2Dim, 6, 2)
        self.eCut2Dim = QLineEdit()
        self.eCut2Dim.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.eCut2Dim.setToolTip('Expression (i.e. [5,8,9])')
        g.addWidget(self.eCut2Dim, 6, 3, 1, 2)

        # rows 9-12: phase
        self.pbPhase = _state('Phase')
        g.addWidget(self.pbPhase, 8, 0, 1, 2)
        self.pb0p1, self.pbPhaseStep1, self.pb10 = _state('x0.1'), _state('x1', True), _state('x10')
        self.step_group = QButtonGroup(self)
        for row, (b, step) in enumerate(((self.pb0p1, 0.1), (self.pbPhaseStep1, 1.0),
                                         (self.pb10, 10.0)), start=9):
            self.step_group.addButton(b)
            g.addWidget(b, row, 1)
            b.clicked.connect(lambda _=False, s=step: self._set_step(s))
        self.ePhase = SciSpinBox(minimum=-360, maximum=360)
        self.ePhase1 = SciSpinBox(minimum=-360, maximum=360)
        self.ePhase1Pivot = SciSpinBox()
        self.ePhase1sh = SciSpinBox()
        for row, (text, sp) in enumerate((('0 order', self.ePhase), ('1 order', self.ePhase1),
                                          ('pivot', self.ePhase1Pivot), ('dt', self.ePhase1sh)),
                                         start=8):
            g.addWidget(_label(text), row, 2)
            g.addWidget(sp, row, 3, 1, 2)

        # every control updates the plot (MATLAB UpdatePlot / UpdateDataProcessing)
        for b in (self.pbTranspose, self.bCutData, self.tbSum, self.pbPhase):
            b.toggled.connect(self.plott)
        self.cbExpression2Dim.toggled.connect(self.plott)
        self.eCut2Dim.editingFinished.connect(self.plott)
        for sp in (self.e1DFirst, self.e1DLast, self.e2DFirst, self.e2DLast, self.ePhase,
                   self.ePhase1, self.ePhase1Pivot, self.ePhase1sh):
            sp.valueChanged.connect(self.plott)
        self.bResetCut.clicked.connect(self._reset_cut)

    def _set_step(self, step: float):
        self.ePhase.setSingleStep(step)
        self.ePhase1.setSingleStep(step)
        self.plott()

    def _spinners(self):
        return (self.e1DFirst, self.e1DLast, self.e2DFirst, self.e2DLast)

    # ================================================================ host
    def file_update(self):
        sz = self.host.get_data('source').y.shape
        for (first, last), n in (((self.e1DFirst, self.e1DLast), sz[0]),
                                 ((self.e2DFirst, self.e2DLast), sz[1])):
            for sp in (first, last):
                sp.blockSignals(True)
                full = sp.maximum() <= 1 or sp.value() > n
                sp.setRange(1, max(n, 1))
                sp.setEnabled(n > 1)
                if sp is last and full:
                    sp.setValue(n)
                sp.blockSignals(False)

    def _reset_cut(self):
        sz = self.host.get_data('source').y.shape
        for sp, v in zip(self._spinners(), (1, sz[0], 1, sz[1])):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)
        self.plott()

    # ================================================================ processing
    def plott(self):
        try:
            self._plott()
        except Exception as e:
            self.host.set('message', f'mathplugin: {e}')

    def _plott(self):
        src = self.host.get_data('source')
        if src.is_empty:
            return
        if self.bReal.isChecked():
            src.y = np.real(src.y)
        elif self.bImag.isChecked():
            src.y = np.imag(src.y)
        elif self.bAbs.isChecked():
            src.y = np.abs(src.y)

        sz = src.y.shape
        ax = src.ax
        if self.bCutData.isChecked():
            d1f, d1l, d2f, d2l = (sp.value() for sp in self._spinners())
            d1f, d1l = min(d1f, sz[0]), min(d1l, sz[0])
            d2f, d2l = min(d2f, sz[1]), min(d2l, sz[1])
            rows = slice(d1f - 1, d1l)
            if sz[1] > 1 and self.cbExpression2Dim.isChecked():
                cols = matlab_index(self.eCut2Dim.text(), sz[1])
            else:
                cols = np.arange(d2f - 1, d2l)
            src.y = src.y[rows][:, cols]
            ax.x = np.asarray(ax.x)[rows]
            ax.y = np.asarray(ax.y)[cols]

        if self.pbTranspose.isChecked():
            src.y = src.y.T
            ax.x, ax.y = ax.y, ax.x
            ax.xlabel, ax.ylabel = ax.ylabel, ax.xlabel

        if self.tbSum.isChecked():
            src.y = src.y.sum(axis=1, keepdims=True)
            ax.y = np.array([1.0])

        if self.pbPhase.isChecked():
            n1, n2 = src.y.shape
            pts = np.arange(1, n1 + 1)[:, None] - self.ePhase1Pivot.value()   # 1-based points
            first = self.ePhase1.value() + self.ePhase1sh.value() * np.arange(n2)[None, :]
            src.y = src.y * np.exp(-1j * (self.ePhase.value() / 180 * np.pi
                                          + first * np.pi / 180 * pts))
        self.host.set_data('output', [src])
