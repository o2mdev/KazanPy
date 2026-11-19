"""Minus box: port of MinusBox3.mlapp (B. Epel and A. Silakov, 2003-04).

Result = Reference (+ - .* ./) CurData(x*zoomx + shiftx)*zoomy + shifty, or
Result = CurData(x*zoomx + shiftx)*zoomy + shifty ("Res = Zoom*Src+Shift").
When the abscissas differ, both traces are spline-interpolated on the common range.
The result can be inverted and shifted along Y. Zoom Y / Shift Y can be set per
slice of 2D data.

Differences from MATLAB (see Documentation/plugins.md):
* Shift Y is applied per slice (MATLAB used the first slice's shift for all).
* *Reset* of the shift sets it to 0 (MATLAB set 1).
* The current data is always the raw source (MATLAB switched to the processed
  source when *Show Reference* was checked).
* A 1-slice reference combined with 2D current data works for every slice
  (MATLAB had parameters for the reference's slices only).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QGridLayout, QLabel,
                               QMessageBox, QPushButton, QWidget)
from scipy.interpolate import CubicSpline

from kazan.core import KazanPlugin, KzData
from kazan.viewer.widgets import SciSpinBox

STEPS = ['1e-7', '1e-6', '1e-5', '1e-4', '0.001', '0.01', '0.1', '1', '10', '100', '1000', '1e4',
         '1e5', '1e6', '1e7', '1e8']
ZOOM_STEPS = ['1e-5', '1e-4', '1e-3', '0.001', '0.01', '0.1', '1', '10', '100', '1000', '1e4',
              '1e5', '1e6']
OPERATORS = {'+': np.add, '-': np.subtract, '.*': np.multiply, './': np.divide}
ABOUT = ('MINUSBOX3\nby Boris Epel and Alexey Silakov, 2003-04\n\n'
         'Result = Reference +-*/ CurData(x*zoomx + shiftx)*zoomy+shifty\n'
         'or Result = CurData(x*zoomx + shiftx)*zoomy+shifty\n'
         "If abscissas of the Reference and Current Data are not identical,\n"
         "'spline' procedure is used to interpolate the data\n"
         'The Result can be inverted and shifted along Y axis\n\n'
         'IMPORTANT: The Ref. and Cur. Data must have same number of columns')


def _default():
    return dict(shift_x=0.0, shift_y=0.0, zoom_x=1.0, zoom_y=1.0)


def _spline(x, y, xq):
    order = np.argsort(x)
    xs, keep = np.unique(np.asarray(x)[order], return_index=True)
    return CubicSpline(xs, np.asarray(y)[order][keep], axis=0)(xq)


class MinusBox3(KazanPlugin):
    menu_name = 'MINUSBOX3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('Minusbox')
        self.resize(260, 420)
        self.ref: KzData | None = None
        self.operator = '-'
        self.params = [_default()]
        self._build_menus()
        self._build_ui()
        self.update_slice()

    # ================================================================ UI
    def _build_menus(self):
        m = self.menuBar().addMenu('View')
        self.mShowReference = self._check(m, 'Show Reference')
        self.mShowTrace = self._check(m, 'Show Trace 2')
        self.mShowResult = self._check(m, 'Show Result')
        self.menuBar().addAction('About').triggered.connect(
            lambda: QMessageBox.information(self, 'About', ABOUT))

    def _check(self, menu, text):
        a = QAction(text, self, checkable=True)
        a.setChecked(True)
        a.triggered.connect(self.plot_this)
        menu.addAction(a)
        return a

    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(4, 4, 4, 4)
        g.setSpacing(4)
        for c in range(4):
            g.setColumnStretch(c, 1)

        self.bSetReference = QPushButton('Set as reference')
        self.bSetReference.clicked.connect(self.set_reference)
        g.addWidget(self.bSetReference, 0, 0, 1, 4)

        self.op_group = QButtonGroup(self)
        self.cbPlus, self.cbMinus, self.cbMultiply, self.cbDivide = (
            QCheckBox(t) for t in ('+', '-', '.*', './'))
        self.cbSimpleMath = QCheckBox('Res = Zoom*Src+Shift')
        for c, cb in enumerate((self.cbPlus, self.cbMinus, self.cbMultiply, self.cbDivide)):
            g.addWidget(cb, 1, c)
        g.addWidget(self.cbSimpleMath, 2, 0, 1, 4)
        for cb in (self.cbPlus, self.cbMinus, self.cbMultiply, self.cbDivide, self.cbSimpleMath):
            self.op_group.addButton(cb)
        self.cbMinus.setChecked(True)
        self.op_group.buttonClicked.connect(self._on_operation)

        self.spin = {}
        self.steps = {}
        for row, (text, key, steps, default) in (
                (4, ('Shift X', 'shift_x', STEPS, '0.1')), (5, ('Shift Y', 'shift_y', STEPS, '0.1')),
                (8, ('Zoom X', 'zoom_x', ZOOM_STEPS, '1')), (9, ('Zoom Y', 'zoom_y', ZOOM_STEPS, '1'))):
            g.addWidget(QLabel(text), row, 0)
            dd = QComboBox()
            dd.addItems(steps)
            dd.setCurrentText(default)
            g.addWidget(dd, row, 1)
            sp = SciSpinBox(value=1.0 if key.startswith('zoom') else 0.0, step=float(default))
            sp.valueChanged.connect(lambda v, k=key: self.edit_value(k, v))
            g.addWidget(sp, row, 2, 1, 2)
            self.spin[key] = sp
            self.steps[key] = dd
        for row, text, fn in ((6, 'Reset', self.reset_shift), (10, 'Reset', self.reset_zoom)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            g.addWidget(b, row, 0, 1, 2)
        self.pbToRef = QPushButton('-> Ref.')
        self.pbToRef.clicked.connect(self.to_ref)
        g.addWidget(self.pbToRef, 6, 2, 1, 2)
        g.addWidget(QLabel('slice'), 10, 2)
        self.pmSlice = QComboBox()
        self.pmSlice.currentIndexChanged.connect(self._on_slice)
        g.addWidget(self.pmSlice, 10, 3)
        for row in (3, 7, 11):
            g.setRowMinimumHeight(row, 6)

        self.cbShiftResult = QCheckBox('Shift result')
        self.cbShiftResult.toggled.connect(self.plot_this)
        g.addWidget(self.cbShiftResult, 12, 0, 1, 2)
        self.eShiftResult = SciSpinBox(step=0.1)
        self.eShiftResult.valueChanged.connect(self.plot_this)
        g.addWidget(self.eShiftResult, 12, 2, 1, 2)
        self.cbInverseResult = QCheckBox('Inverse result')
        self.cbInverseResult.toggled.connect(self.plot_this)
        g.addWidget(self.cbInverseResult, 13, 0, 1, 2)

        for key, dd in self.steps.items():
            dd.currentTextChanged.connect(lambda t, k=key: self._on_step(k, float(t)))

    def _on_step(self, key: str, step: float):
        self.spin[key].setSingleStep(step)
        if key == 'shift_y':
            self.eShiftResult.setSingleStep(step)

    # ================================================================ state
    def update_slice(self):
        n = self.ref.y.shape[1] if self.ref is not None else 1
        self._ensure_params(n)
        self.pmSlice.blockSignals(True)
        self.pmSlice.clear()
        self.pmSlice.addItems(['All'] + ([str(i + 1) for i in range(n)] if self.ref is not None else []))
        self.pmSlice.blockSignals(False)
        color = '#bfbff2' if self.ref is not None else '#b3b3b3'
        self.bSetReference.setStyleSheet(f'QPushButton {{ background: {color}; }}')

    def _ensure_params(self, n: int):
        while len(self.params) < n:
            self.params.append(dict(self.params[0]))

    def _selected(self) -> list[int]:
        k = self.pmSlice.currentIndex()
        return list(range(len(self.params))) if k <= 0 else [k - 1]

    def _show_params(self, p: dict):
        for key, sp in self.spin.items():
            sp.blockSignals(True)
            sp.setValue(p[key])
            sp.blockSignals(False)

    def _store_params(self):
        for i in self._selected():
            self.params[i].update({k: sp.value() for k, sp in self.spin.items()})

    def file_update(self):
        return  # as in MATLAB

    # ================================================================ callbacks
    def _on_operation(self, button):
        if button is not self.cbSimpleMath:
            self.operator = button.text()
        self.plot_this()

    def edit_value(self, key: str, value: float):
        for i in self._selected():
            self.params[i][key] = value
        self.plot_this()

    def _on_slice(self, index: int):
        self._show_params(self.params[max(index - 1, 0)])

    def set_reference(self):
        self.ref = self.host.get_data('source')
        self.update_slice()
        self.plot_this()

    def reset_shift(self):
        for key in ('shift_x', 'shift_y'):
            self.spin[key].blockSignals(True)
            self.spin[key].setValue(0.0)
            self.spin[key].blockSignals(False)
        self._store_params()
        self.plot_this()

    def reset_zoom(self):
        for key in ('zoom_x', 'zoom_y'):
            self.spin[key].blockSignals(True)
            self.spin[key].setValue(1.0)
            self.spin[key].blockSignals(False)
        self._store_params()
        self.plot_this()

    def to_ref(self):
        if self.ref is None:
            return
        y = np.real(self.ref.y)
        y1 = np.real(self.host.get_data('source').y)
        span1 = y1.max() - y1.min()
        kk = (y.max() - y.min()) / span1 if span1 else 1.0
        self._show_params(dict(shift_x=0.0, shift_y=float(y.min() - (y1 * kk).min()), zoom_x=1.0,
                               zoom_y=float(kk)))
        self._store_params()
        self.plot_this()

    # ================================================================ plotting
    def plot_this(self):
        try:
            self._plot_this()
        except Exception as e:
            self.host.set('message', str(e))

    def _plot_this(self):
        src = self.host.get_data('source')
        if src.is_empty:
            return
        isref = not self.cbSimpleMath.isChecked()
        if isref and self.ref is None:
            raise ValueError('Please set the reference.')

        sec = src.copy()
        ref = self.ref.copy() if isref else src.copy()
        ref.ax.Color = (0, 0, 1)
        ref.title = 'Ref'

        self._ensure_params(sec.y.shape[1])
        sec.ax.x = np.asarray(sec.ax.x) * self.spin['zoom_x'].value() + self.spin['shift_x'].value()
        sec.y = np.stack([sec.y[:, i] * self.params[i]['zoom_y'] + self.params[i]['shift_y']
                          for i in range(sec.y.shape[1])], axis=1)
        sec.ax.Color = (1, 0, 0)
        sec.ax.s = 0
        sec.ax.dx = 0
        sec.title = 'Op 2'

        if isref:
            nr, ns = ref.y.shape[1], sec.y.shape[1]
            if nr != ns:
                if nr == 1:
                    ref.y = np.repeat(ref.y, ns, axis=1)
                    ref.ax.y = sec.ax.y
                elif ns == 1:
                    sec.y = np.repeat(sec.y, nr, axis=1)
                    sec.ax.y = ref.ax.y
                else:
                    raise ValueError('The Ref. and Cur. Data must have same number of columns')
            rx, sx = np.asarray(ref.ax.x, float), np.asarray(sec.ax.x, float)
            if len(rx) == len(sx) and np.array_equal(rx, sx):
                tmp1, tmp2, xax = ref.y, sec.y, rx
            else:
                x1 = max(rx.min(), sx.min())
                x2 = min(rx.max(), sx.max())
                if x2 <= x1:
                    raise ValueError('Reference and data do not overlap')
                xax = np.linspace(x1, x2, len(rx))
                if rx[0] > rx[-1]:
                    xax = xax[::-1]
                tmp1, tmp2 = _spline(rx, ref.y, xax), _spline(sx, sec.y, xax)
            with np.errstate(divide='ignore', invalid='ignore'):
                y = OPERATORS[self.operator](tmp1, tmp2)
        else:
            y, xax = sec.y, sec.ax.x

        res = ref.copy()
        res.ax.x = xax
        res.y = -y if self.cbInverseResult.isChecked() else y
        res.ax.Color = (0, 0.8, 0)
        res.ax.s = self.eShiftResult.value() if self.cbShiftResult.isChecked() else 0
        res.ax.dx = 0
        res.title = 'Result'

        out = []
        if self.mShowReference.isChecked():
            out.append(ref)
        if self.mShowTrace.isChecked() and isref:
            out.append(sec)
        if self.mShowResult.isChecked():
            out.append(res)
        self.host.set_data('output', out)
