"""CW plugin: port of CWplugin3.mlapp.

Baseline (step 1), phase (step 2) and filter (step 3) processing of a CW trace,
conversion absorption / derivative / integral, integration and line-width fits.

Differences from MATLAB (see README):
* 2D data: the current viewer slice is processed (MATLAB assumed 1D data).
* LW-L / LW-G report the integral of the fitted line (MATLAB printed the start value),
  LW-V fits the selected range only, LWhh uses range indices consistently.
* Fit width guesses come from the measured peak-to-peak / half-height width
  (MATLAB: range/5, which diverges for narrow lines).
* Baseline buttons 3/4/5 select polynomial baselines of that order (no-ops in MATLAB).
* LW-Md (spin-probe model fit) is unfinished in MATLAB and disabled here.
"""
from __future__ import annotations

import re

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout,
                               QGroupBox, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
                               QPushButton, QWidget)
from scipy.integrate import cumulative_trapezoid
from scipy.optimize import least_squares
from scipy.signal import hilbert, savgol_filter

from kazan.core import KazanPlugin, KzData, Struct
from kazan.math.autofit import autofit
from kazan.math.lineshapes import lshape, voigtian
from kazan.viewer.main_window import RESOURCES

BASELINE_SCRIPTS = {
    '-': [],
    '1': ['f = a', 'a = 0'],
    '2': ['f = a*x + b', 'a = 0', 'b = 0 '],
    '3': ['f = polyfit(x,y,n)', 'n = 3'],
    '4': ['f = polyfit(x,y,n)', 'n = 4'],
    '5': ['f = polyfit(x,y,n)', 'n = 5'],
}
STEP_SIZES = ['1e-7', '1e-6', '1e-5', '1e-4', '1e-3', '0.01', '0.1', '1', '10', '100', '1000',
              '1e4', '1e5', '1e6', '1e7', '1e8']


def _state(text, checked=False):
    b = QPushButton(text)
    b.setCheckable(True)
    b.setChecked(checked)
    return b


def _exclusive(*buttons):
    g = QButtonGroup(buttons[0])
    for b in buttons:
        g.addButton(b)
    return g


def _panel(title, rows, cols, col_stretch=None):
    box = QGroupBox(title)
    g = QGridLayout(box)
    g.setContentsMargins(6, 4, 6, 4)
    g.setSpacing(4)
    for c in range(cols):
        g.setColumnStretch(c, (col_stretch or [1] * cols)[c])
    for r in range(rows):
        g.setRowStretch(r, 1)
    return box, g


def _cross_button():
    b = QPushButton()
    b.setIcon(QIcon(str(RESOURCES / 'pbCross.png')))
    b.setIconSize(QSize(14, 14))
    b.setToolTip('Select two points on the viewer plot')
    return b


def _fit(model, a0, x, y):
    """lsqcurvefit twice, as in MATLAB."""
    res = model
    a = np.asarray(a0, float)
    for _ in range(2):
        a = least_squares(lambda p: res(p, x) - y, a, method='trf').x
    return a


class CWplugin3(KazanPlugin):
    menu_name = 'CWPLUGIN3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('cwplugin')
        self.resize(688, 509)
        self.areafit = np.zeros(0, bool)        # points used for the baseline fit
        self.area_evaluate = np.zeros(0, bool)  # integration / line fit range
        self.baseline = np.zeros(0)
        self.fit: Struct | None = None
        self._build_ui()

    # ================================================================ UI
    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        main = QGridLayout(w)
        main.setSpacing(6)
        for r in range(7):
            main.setRowStretch(r, 1)
        main.setColumnStretch(0, 1)
        main.setColumnStretch(1, 1)

        # ---- Data
        box, g = _panel('Data', 1, 3)
        self.tbSrcSource = _state('Source', True)
        self.tbSrcProcSource = _state('Proc. Source')
        self.tbSrcOutput = _state('Output')
        for c, b in enumerate((self.tbSrcSource, self.tbSrcProcSource, self.tbSrcOutput)):
            g.addWidget(b, 0, c)
        _exclusive(self.tbSrcSource, self.tbSrcProcSource, self.tbSrcOutput)
        main.addWidget(box, 0, 0)

        # ---- Input type
        box, g = _panel('Input Type', 1, 3)
        self.tbSrcDerivative = _state('Derivative')
        self.tbSrcAbsorption = _state('Absorption', True)
        g.addWidget(self.tbSrcDerivative, 0, 1)
        g.addWidget(self.tbSrcAbsorption, 0, 2)
        _exclusive(self.tbSrcDerivative, self.tbSrcAbsorption)
        main.addWidget(box, 1, 0)

        # ---- Output type
        box, g = _panel('Output Type', 1, 3)
        self.tbDestDerivative = _state('Derivative')
        self.tbDestAbsorption = _state('Absorption', True)
        self.tbDestIntegral = _state('Integral')
        for c, b in enumerate((self.tbDestDerivative, self.tbDestAbsorption, self.tbDestIntegral)):
            g.addWidget(b, 0, c)
            b.clicked.connect(self._on_dest_changed)
        _exclusive(self.tbDestDerivative, self.tbDestAbsorption, self.tbDestIntegral)
        main.addWidget(box, 2, 0)

        # ---- Baseline
        box, g = _panel('Baseline (processing step 1)', 7, 7, [3, 2, 2, 2, 2, 2, 2])
        self.pbBaseline = _state('Use')
        g.addWidget(self.pbBaseline, 0, 0)
        self.base_buttons = {}
        for c, key in enumerate(('-', '1', '2', '3', '4', '5'), start=1):
            b = _state(key, key == '2')
            b.clicked.connect(lambda _=False, k=key: self._on_select_baseline(k))
            g.addWidget(b, 0, c)
            self.base_buttons[key] = b
        _exclusive(*self.base_buttons.values())
        self.cbBaselineShow = QCheckBox('Show')
        g.addWidget(self.cbBaselineShow, 1, 0)
        self.lbPars = QListWidget()
        self.lbPars.addItems(BASELINE_SCRIPTS['2'])
        self.lbPars.setCurrentRow(0)
        self.lbPars.currentRowChanged.connect(self._on_par_selected)
        g.addWidget(self.lbPars, 1, 1, 2, 6)
        self.ddStepSize = QComboBox()
        self.ddStepSize.addItems(STEP_SIZES)
        self.ddStepSize.setCurrentText('0.1')
        self.ddStepSize.currentTextChanged.connect(lambda t: self.pmPars.setSingleStep(float(t)))
        g.addWidget(self.ddStepSize, 3, 1, 1, 2)
        self.pmPars = QDoubleSpinBox(decimals=6, minimum=-1e12, maximum=1e12, singleStep=0.1)
        self.pmPars.setEnabled(False)
        self.pmPars.valueChanged.connect(self._on_par_value)
        g.addWidget(self.pmPars, 3, 3, 1, 4)
        self.cbApplyLin4Integration = QCheckBox('Apply linear b-line before integration')
        g.addWidget(self.cbApplyLin4Integration, 4, 0, 1, 3)
        self.ePars = QLineEdit()
        self.ePars.returnPressed.connect(self._on_par_text)
        g.addWidget(self.ePars, 4, 3, 1, 4)
        g.addWidget(QLabel('Range'), 5, 0)
        self.btnAddFitRange = _cross_button()
        self.btnRemoveFitRange = _cross_button()
        g.addWidget(self.btnAddFitRange, 5, 1)
        g.addWidget(QLabel('Add'), 5, 2, 1, 2)
        g.addWidget(self.btnRemoveFitRange, 5, 4)
        g.addWidget(QLabel('Remove'), 5, 5, 1, 2)
        self.btnFit = QPushButton('Fit')
        g.addWidget(self.btnFit, 6, 1, 1, 5)
        main.addWidget(box, 3, 0, 4, 1)

        # ---- Phase
        box, g = _panel('Phase (processing step 2)', 2, 5)
        self.pbPhase = _state('Phase')
        g.addWidget(self.pbPhase, 0, 0)
        steps = {}
        for c, (text, step) in enumerate((('x0.1', 0.01), ('x1', 1.0), ('x10', 10.0)), start=2):
            b = _state(text, text == 'x1')
            b.clicked.connect(lambda _=False, s=step: self.ePhase.setSingleStep(s))
            g.addWidget(b, 0, c)
            steps[text] = b
        _exclusive(*steps.values())
        self.cbUseDispersion = QCheckBox('Use Dispersion', checked=True)
        g.addWidget(self.cbUseDispersion, 1, 0, 1, 2)
        self.ePhase = QDoubleSpinBox(decimals=2, minimum=-360, maximum=360, singleStep=1)
        g.addWidget(self.ePhase, 1, 2, 1, 3)
        main.addWidget(box, 0, 1)

        # ---- Filter
        box, g = _panel('Filter (processing step 3)', 1, 6)
        self.tbFilterOn = _state('Filter')
        g.addWidget(self.tbFilterOn, 0, 0)
        self.filter_buttons = []
        for c in range(4):
            b = _state(str(c + 1), c == 0)
            g.addWidget(b, 0, c + 2)
            self.filter_buttons.append(b)
            b.clicked.connect(self.update_output)
        _exclusive(*self.filter_buttons)
        main.addWidget(box, 1, 1)

        # ---- Integration range
        box, g = _panel('Integration and fitting range', 2, 6)
        self.cbFullIntRange = QCheckBox('Full Range', checked=True)
        self.cbShowIntRange = QCheckBox('Show Range')
        g.addWidget(self.cbFullIntRange, 0, 0, 1, 2)
        g.addWidget(self.cbShowIntRange, 0, 2, 1, 2)
        self.eFirstPos = QLineEdit('-')
        self.eFirstPos.returnPressed.connect(self._on_range_text)
        g.addWidget(self.eFirstPos, 1, 0, 1, 5)
        self.btnGetEvaluationRange = _cross_button()
        g.addWidget(self.btnGetEvaluationRange, 1, 5)
        main.addWidget(box, 2, 1)

        # ---- Line fitting
        box, g = _panel('Line fitting', 7, 5)
        self.pbIntegral = QPushButton('Integral')
        self.cbShift = QCheckBox('Shift 2 min')
        self.cbSquare = QCheckBox('Magnitude')
        g.addWidget(self.pbIntegral, 0, 0)
        g.addWidget(self.cbShift, 0, 1, 1, 2)
        g.addWidget(self.cbSquare, 0, 3, 1, 2)
        self.fit_buttons = {}
        for c, name in enumerate(('LW-V', 'LW-L', 'LW-G', 'LWhh', 'LWpp')):
            b = QPushButton(name)
            b.clicked.connect(lambda _=False, n=name: self.fit_line(n))
            g.addWidget(b, 1, c)
            self.fit_buttons[name] = b
        g.addWidget(QLabel('Guess\n(0 - auto)'), 2, 0, 2, 1)
        g.addWidget(QLabel('Lorenz'), 2, 2)
        self.eLV_Lorentz = QDoubleSpinBox(decimals=4, minimum=0, maximum=1e9)
        g.addWidget(self.eLV_Lorentz, 2, 3, 1, 2)
        self.cbFixGauss = QCheckBox('Fix')
        g.addWidget(self.cbFixGauss, 3, 1)
        g.addWidget(QLabel('Gauss'), 3, 2)
        self.eLV_Gauss = QDoubleSpinBox(decimals=4, minimum=0, maximum=1e9)
        g.addWidget(self.eLV_Gauss, 3, 3, 1, 2)
        self.pbFitLW_Mod = QPushButton('LW-Md')
        self.pbFitLW_Mod.setEnabled(False)
        self.pbFitLW_Mod.setToolTip('Spin-probe model fit: unfinished in the MATLAB version')
        g.addWidget(self.pbFitLW_Mod, 4, 0)
        self.eSpinProbe = QComboBox()
        self.eSpinProbe.addItems(['OX063', 'OX071'])
        self.eSpinProbe.setEnabled(False)
        g.addWidget(self.eSpinProbe, 4, 2, 1, 3)
        self.eResInt = QPlainTextEdit()
        g.addWidget(self.eResInt, 5, 0, 2, 5)
        main.addWidget(box, 3, 1, 4, 1)

        # ---- wiring (MATLAB MajorUpdateCallback and friends)
        for b in (self.tbSrcSource, self.tbSrcProcSource, self.tbSrcOutput,
                  self.tbSrcDerivative, self.tbSrcAbsorption, self.pbBaseline,
                  self.pbPhase, self.tbFilterOn):
            b.clicked.connect(self.update_output)
        for cb in (self.cbApplyLin4Integration, self.cbBaselineShow, self.cbFullIntRange,
                   self.cbShift, self.cbShowIntRange, self.cbSquare, self.cbUseDispersion):
            cb.toggled.connect(self.update_output)
        self.ePhase.valueChanged.connect(self.update_output)
        self.btnAddFitRange.clicked.connect(lambda: self._pick_range('add'))
        self.btnRemoveFitRange.clicked.connect(lambda: self._pick_range('remove'))
        self.btnGetEvaluationRange.clicked.connect(lambda: self._pick_range('evaluate'))
        self.btnFit.clicked.connect(self._on_fit_baseline)
        self.pbIntegral.clicked.connect(self._on_integral)
        self._on_par_selected(0)

    # ================================================================ data
    def file_update(self):
        self.update_output()

    def _raw(self) -> tuple[Struct, np.ndarray]:
        """GetRawData: the selected data set, current slice of 2D data."""
        if self.tbSrcOutput.isChecked():
            out = self.host.get_data('output')
            d = out[0] if out else self.host.get_data('source')
        elif self.tbSrcProcSource.isChecked():
            d = self.host.get_data('psource')
        else:
            d = self.host.get_data('source')
        k = min(self.host.get('slice') or 0, d.y.shape[1] - 1) if d.y.size else 0
        return d.ax, (d.y[:, k] if d.y.size else np.zeros(0))

    def _ensure_masks(self, n: int):
        if len(self.areafit) != n:
            self.areafit = np.ones(n, bool)
            third = n // 3
            if third:
                self.areafit[third - 1:2 * third] = False
        if len(self.baseline) != n:
            self.baseline = np.zeros(n)
        if len(self.area_evaluate) != n:
            self.area_evaluate = np.zeros(n, bool)

    def processed(self) -> tuple[Struct, np.ndarray]:
        """GetData: baseline -> phase -> conversion -> filter."""
        ax, yy = self._raw()
        xx = np.asarray(ax.x, float)
        self._ensure_masks(len(xx))
        if len(xx) < 2:
            return ax, yy
        yy = self._phase(self._baseline(yy.astype(complex) if np.iscomplexobj(yy) else yy.astype(float)))
        src_abs = self.tbSrcAbsorption.isChecked()
        if src_abs and self.tbDestDerivative.isChecked():
            yy = np.gradient(yy, np.mean(np.diff(xx)))
        elif src_abs and self.tbDestIntegral.isChecked():
            yy = cumulative_trapezoid(yy, xx, initial=0)
        elif not src_abs and self.tbDestAbsorption.isChecked():
            yy = cumulative_trapezoid(yy, xx, initial=0)
            if self.cbApplyLin4Integration.isChecked():
                yy = self._baseline_lin(yy)
        elif not src_abs and self.tbDestIntegral.isChecked():
            yy = cumulative_trapezoid(yy, xx, initial=0)
            if self.cbApplyLin4Integration.isChecked():
                yy = self._baseline_lin(yy)
            yy = cumulative_trapezoid(yy, xx, initial=0)
        if self.tbFilterOn.isChecked():
            frame = (7, 13, 35, 53)[[b.isChecked() for b in self.filter_buttons].index(True)]
            if len(yy) > frame:
                f = lambda a: savgol_filter(a, frame, 1)
                yy = f(yy.real) + 1j * f(yy.imag) if np.iscomplexobj(yy) else f(yy)
        return ax, yy

    def _baseline(self, yy):
        return yy - self.baseline if self.pbBaseline.isChecked() else yy

    def _baseline_lin(self, yy):
        if not self.pbBaseline.isChecked():
            return yy
        idx = np.arange(len(yy), dtype=float)
        p = np.polyfit(idx[self.areafit], np.real(yy)[self.areafit], 1)
        return yy - np.polyval(p, idx)

    def _phase(self, yy):
        if not self.pbPhase.isChecked():
            return yy
        if not self.cbUseDispersion.isChecked():
            re = np.real(yy).ravel()
            h = np.imag(hilbert(np.concatenate([re[::-1], re])))
            yy = re + 1j * h[len(re):]
        return yy * np.exp(-1j * self.ePhase.value() / 180 * np.pi)

    def _integral(self, xx, yy) -> float:
        if self.cbSquare.isChecked():
            yy = np.abs(yy)
        if self.cbShift.isChecked():
            yy = yy - (np.min(np.real(yy)) + 1j * np.min(np.imag(yy)) if np.iscomplexobj(yy)
                       else np.min(yy))
        return float(np.real(np.trapezoid(yy, xx)))

    def _range(self, xx, yy):
        if self.cbFullIntRange.isChecked() or not self.area_evaluate.any():
            return xx, np.real(yy)
        return xx[self.area_evaluate], np.real(yy[self.area_evaluate])

    # ================================================================ output
    def update_output(self):
        """BigProcessingFunction."""
        ax, yy = self.processed()
        if len(yy) == 0:
            return
        xx = np.asarray(ax.x, float)
        show_base = self.pbBaseline.isChecked() and self.cbBaselineShow.isChecked()
        if show_base:
            yy = yy + self.baseline
        data = Struct(ax)
        data.x = xx
        out = [KzData(y=yy, ax=data, title='Data')]
        if self.cbShowIntRange.isChecked() and self.area_evaluate.any():
            out.append(KzData(y=yy[self.area_evaluate], title='Range',
                              ax=Struct(x=xx[self.area_evaluate], Color=[1, 0, 1])))
        if self.cbBaselineShow.isChecked():
            out.append(KzData(y=self.baseline.copy(), title='Baseline',
                              ax=Struct(x=xx, Color=[0, 0, 0], LineStyle=':')))
        if self.pbBaseline.isChecked() and not self.areafit.all():
            out.append(KzData(y=yy[self.areafit], title='fit area',
                              ax=Struct(x=xx[self.areafit], Color=[0, 0, 0], Marker='o',
                                        LineStyle='none')))
        if self.fit is not None:
            out.append(KzData(y=self.fit.y, title='Fit',
                              ax=Struct(x=self.fit.x, Color=[1, 0, 0], LineStyle='-')))
        self.host.set_data('output', out)

    def _on_dest_changed(self):
        self.fit = None
        self.update_output()

    # ================================================================ baseline
    def _on_select_baseline(self, key: str):
        self.lbPars.clear()
        self.lbPars.addItems(BASELINE_SCRIPTS[key])
        if self.lbPars.count():
            self.lbPars.setCurrentRow(0)

    def _on_fit_baseline(self):
        ax, yy = self._raw()
        self._ensure_masks(len(ax.x))
        script = [self.lbPars.item(i).text() for i in range(self.lbPars.count())]
        if not script:
            return
        try:
            new_script, bline = autofit(script, ax.x, np.real(yy), self.areafit)
        except Exception as e:
            self.host.set('message', f'Baseline fit: {e}')
            return
        row = self.lbPars.currentRow()
        self.lbPars.blockSignals(True)
        self.lbPars.clear()
        self.lbPars.addItems(new_script)
        self.lbPars.setCurrentRow(min(max(row, 0), len(new_script) - 1))
        self.lbPars.blockSignals(False)
        self._on_par_selected(self.lbPars.currentRow())
        self.baseline = np.broadcast_to(bline, len(ax.x)).astype(float)
        self.update_output()

    def _on_par_selected(self, row: int):
        """lbPars_Callback: show the selected line in the editor / spinner."""
        item = self.lbPars.item(row) if row >= 0 else None
        if item is None:
            self.ePars.clear()
            self.pmPars.setEnabled(False)
            return
        name, _, value = item.text().partition('=')
        value = value.strip()
        self.pmPars.blockSignals(True)
        if name.strip() == 'f' or value.startswith("'"):
            self.ePars.setText(value.strip("'"))
            self.pmPars.setEnabled(False)
        else:
            try:
                self.pmPars.setValue(float(value))
                self.pmPars.setEnabled(True)
            except ValueError:
                self.pmPars.setEnabled(False)
            self.ePars.setText(value)
        self.pmPars.blockSignals(False)

    def _set_line(self, text: str):
        item = self.lbPars.currentItem()
        if item is not None:
            item.setText(text)

    def _on_par_value(self, value: float):
        item = self.lbPars.currentItem()
        if item is None:
            return
        name = item.text().partition('=')[0].strip()
        self._set_line(f'{name} = {value:g}')
        self.ePars.setText(f'{value:g}')
        self.update_output()

    def _on_par_text(self):
        item = self.lbPars.currentItem()
        if item is not None:
            name = item.text().partition('=')[0].strip()
            self._set_line(f'{name} = {self.ePars.text().strip()}')
            self._on_par_selected(self.lbPars.currentRow())

    # ================================================================ ranges
    def _pick_range(self, mode: str):
        self.host.set('message', 'Select the beginning and the end of the range')
        pts = self.host.ginput(2)
        if len(pts) < 2:
            return
        p0, p1 = sorted(pts[:, 0])
        ax, _ = self._raw()
        xx = np.asarray(ax.x, float)
        self._ensure_masks(len(xx))
        inside = (xx > p0) & (xx < p1)
        if mode == 'add':
            self.areafit[inside] = True
        elif mode == 'remove':
            self.areafit[inside] = False
        else:
            self.area_evaluate = inside
            self.eFirstPos.setText(f'{p0:f}  - {p1:f}')
        self.update_output()

    def _on_range_text(self):
        nums = re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', self.eFirstPos.text())
        if len(nums) < 2:
            return
        p0, p1 = sorted(float(v) for v in nums[:2])
        ax, _ = self._raw()
        xx = np.asarray(ax.x, float)
        self._ensure_masks(len(xx))
        self.area_evaluate = (xx > p0) & (xx < p1)
        self.update_output()

    # ================================================================ integral / fits
    def _on_integral(self):
        ax, yy = self.processed()
        xxx, yyy = self._range(np.asarray(ax.x, float), yy)
        self.eResInt.setPlainText(f'INT={self._integral(xxx, yyy):f}')

    def fit_line(self, kind: str):
        """pbFitLW_Callback."""
        ax, yy = self.processed()
        xx = np.asarray(ax.x, float)
        xxx, yyy = self._range(xx, yy)
        if len(xxx) < 4:
            return
        deriv = self.tbDestDerivative.isChecked()
        absorp = self.tbDestAbsorption.isChecked()
        imax, imin = int(np.argmax(yyy)), int(np.argmin(yyy))
        x0_deriv = xxx[(imax + imin) // 2]
        # Width guess from the data (MATLAB used range/5, which diverges for narrow lines)
        if deriv:
            lw0 = abs(xxx[imax] - xxx[imin])
        else:
            above = np.nonzero(yyy >= yyy[imax] / 2)[0]
            lw0 = abs(xxx[above[-1]] - xxx[above[0]]) if len(above) > 1 else 0.0
        if not lw0:
            lw0 = (xxx.max() - xxx.min()) / 5.0
        text = ''
        model = None
        try:
            if kind in ('LW-L', 'LW-G'):
                alpha = 0.0 if kind == 'LW-L' else 1.0
                guess = self.eLV_Lorentz.value() if kind == 'LW-L' else self.eLV_Gauss.value()
                if deriv:
                    lw = guess or lw0
                    model = lambda a, x: abs(a[0]) * lshape(x, a[1], abs(a[2]), 1, alpha)
                    a = _fit(model, [lw * (yyy.max() - yyy.min()), x0_deriv, lw], xxx, yyy)
                elif absorp:
                    model = lambda a, x: abs(a[0]) * lshape(x, a[1], abs(a[2]), 0, alpha)
                    a = _fit(model, [self._integral(xxx, yyy), xxx[imax], lw0], xxx, yyy)
                else:
                    self.eResInt.setPlainText('Select Derivative or Absorption output.')
                    return
                sd = float(np.std(yyy - model(a, xxx)))
                tag = 'LW-L' if kind == 'LW-L' else 'LW-G'
                text = f'{tag} = {abs(a[2]):5.4f}\nSD={sd:f}\nINT={abs(a[0]):f}'
            elif kind == 'LW-V':
                lwl = self.eLV_Lorentz.value() or lw0
                lwg = self.eLV_Gauss.value() or lw0
                d = 1 if deriv else 0
                if not (deriv or absorp):
                    self.eResInt.setPlainText('Select Derivative or Absorption output.')
                    return
                x0 = x0_deriv if deriv else xxx[imax]
                amp = lw0 * (yyy.max() - yyy.min())
                if self.cbFixGauss.isChecked():
                    model = lambda a, x: abs(a[0]) * voigtian(x, a[1], [lwg, abs(a[2])], d)
                    a = np.abs(_fit(model, [amp, x0, lwl], xxx, yyy))
                    widths = (lwg, a[2])
                else:
                    model = lambda a, x: abs(a[0]) * voigtian(x, a[1], [abs(a[2]), abs(a[3])], d)
                    a = np.abs(_fit(model, [amp, x0, lwg, lwl], xxx, yyy))
                    widths = (a[2], a[3])
                sd = float(np.std(yyy - model(a, xxx)))
                text = (f'LW-GL = {widths[0]:5.4f} / {widths[1]:5.4f}\nSD={sd:5.4f}\n'
                        f'INT={abs(a[0]):f}')
            elif kind == 'LWhh':
                if not absorp:
                    self.eResInt.setPlainText('Not a direct detected spectra')
                    return
                half = yyy[imax] / 2
                left = next((i for i in range(imax, -1, -1) if yyy[i] < half), 0)
                right = next((i for i in range(imax, len(yyy)) if yyy[i] < half), len(yyy) - 1)
                text = f'LWhh = {xxx[right] - xxx[left]:5.4f}\nINT={self._integral(xxx, yyy):f}'
            elif kind == 'LWpp':
                if not deriv:
                    self.eResInt.setPlainText('Not a derivative.')
                    return
                text = (f'LWpp = {abs(xxx[imax] - xxx[imin]):5.4f}\n'
                        f'INT={self._integral(xxx, yyy):f}')
        except Exception as e:
            self.eResInt.setPlainText(f'Fit failed: {e}')
            return
        if model is not None:
            self.fit = Struct(x=xxx, y=model(a, xxx))
        self.eResInt.setPlainText(text)
        self.update_output()
