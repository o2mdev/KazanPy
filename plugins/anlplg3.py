"""Decay analysis plugin: port of ANLPLG3.mlapp.

Exponential decay fits of the source (time in us, real part):

* **SE** - mono-exponential ``A exp(-(t - t0)/T1)``.
* **SE + IRF** - mono-exponential convolved with a Gaussian instrument response (IRF),
  including the rise; the time offset is fitted.
* **DE** - bi-exponential.
* **DE + IRF** - bi-exponential with IRF.
* **Light-Dark** - (dark - light) of two-row light/dark data, with phase and skew of the
  imaginary part; other data are only phased.
* **Phase** - phase and skew of the imaginary part.

*Baseline* picks a range whose mean is subtracted before fitting. *Bound fit* limits the
amplitudes (0.01..5 x max, or -5..5 with *Negative amp*) and the time constants (LB / UB
factor x start value). Output: source, baseline points, fit (red), residual (green,
scaled and offset) and, for DE, the two components.

Differences from MATLAB (see Documentation/plugins.md):
* *SE + IRF* works (MATLAB compared the whole time axis with the fit range and called
  ``expIRF`` without the app, so it failed).
* *DE + IRF* starts T2 from its own *T2 guess* (MATLAB used the DE tab's).
* The time-offset buttons of the IRF tabs set the time offset start value (no-ops in
  MATLAB).
* 2D data: the current viewer slice is fitted.
* Light-Dark / Phase outputs are titled after what they show (MATLAB: 'Baseline').
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox, QLabel, QPlainTextEdit,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)
from scipy.special import erf

from kazan.core import KazanPlugin
from kazan.math.optim import fminsearch, fminsearchbnd
from kazan.viewer.main_window import RESOURCES
from kazan.viewer.widgets import SciSpinBox

TITLES = {'SE': 'Mono-Exponential Decay Fit', 'SE + IRF': 'Mono-Exponential Decay + IRF',
          'DE': 'Double-Exponential Decay Fit', 'DE + IRF': 'Double-Exponential Decay +IRF',
          'Light-Dark': 'Dark subtraction', 'Phase': 'Phase correction'}
HELP = ('Start with Reset Range. Then click on Time Offset selection button. Then choose First '
        'and Last points. For bound fit and negative amplitude exponent, one must select '
        'Negative amplitude.\nLB and UB factors are applied to amplitude and time constants.')


def exp_irf(t, tau, sigma):
    """Exponential decay with rise, both convolved with a Gaussian IRF (MATLAB expIRF);
    tau and sigma are limited to >= 30 ns."""
    tau, sigma = max(tau, 3e-2), max(sigma, 3e-2)
    s = sigma / 2
    decay = np.exp(s ** 2 / (2 * tau ** 2) - t / tau)
    rise = 0.5 * (1 - erf((s ** 2 - tau * t) / (tau * s * np.sqrt(2))))
    return decay * rise


def check_fit(p, lb, ub, names):
    """MATLAB CheckFit: flag parameters within 2.5% of a bound."""
    if lb is None or ub is None:
        return '', ''
    flag, msg = '', ''
    with np.errstate(divide='ignore', invalid='ignore'):
        near_ub = np.abs((p - ub) / ub) < 0.025
        near_lb = np.abs((p - lb) / lb) < 0.025
    if near_ub.any():
        flag = 'upper bound'
        msg = 'upper bound (parameter %s)' % ', '.join(n for n, b in zip(names, near_ub) if b)
    if near_lb.any():
        flag = 'lower bound'
        msg += 'lower bound (parameter %s)' % ', '.join(n for n, b in zip(names, near_lb) if b)
    return flag, msg


def _us_spin(value=0.0, minimum=0.0):
    return SciSpinBox(value, 1.0, minimum, 1e300)


def _cross():
    b = QPushButton()
    b.setIcon(QIcon(str(RESOURCES / 'pbCross.png')))
    b.setIconSize(QSize(14, 14))
    b.setToolTip('Pick the time offset on the viewer plot')
    return b


class ANLPLG3(KazanPlugin):
    menu_name = 'ANLPLG3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle(TITLES['SE'])
        self.resize(454, 486)
        self.baseline: np.ndarray | None = None
        self.tabs_w: dict[str, dict] = {}
        self._build_ui()

    # ================================================================ UI
    def _fit_tab(self, name, extra=()):
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(6, 6, 6, 6)
        for c in range(4):
            g.setColumnStretch(c, 1)
        c = {'offset': _us_spin(), 'first': _us_spin(), 'last': _us_spin(),
             'set_offset': _cross(), 'reset': QPushButton('Reset Range')}
        for row, (text, key) in enumerate((('Time Offset [us]', 'offset'),
                                           ('First Point [us]', 'first'),
                                           ('Last Point [us]', 'last'))):
            g.addWidget(QLabel(text), row, 0)
            g.addWidget(c[key], row, 1)
        g.addWidget(c['set_offset'], 0, 2)
        g.addWidget(c['reset'], 2, 2)
        for row, (text, key, val) in enumerate(extra, start=3):
            c[key] = _us_spin(val)
            g.addWidget(QLabel(text), row, 0)
            g.addWidget(c[key], row, 1)
        if name == 'SE':
            help_box = QPlainTextEdit(HELP)
            help_box.setReadOnly(True)
            g.addWidget(help_box, 3, 0, 2, 4)
        c['set_offset'].clicked.connect(lambda: self.set_time_offset(name))
        c['reset'].clicked.connect(lambda: self.reset_range(name))
        self.tabs_w[name] = c
        return w

    def _phase_tab(self, on_change):
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(6, 6, 6, 6)
        for c in range(4):
            g.setColumnStretch(c, 1)
        phase = SciSpinBox(0.0, 1.0)
        skew = SciSpinBox(1.0, 0.01, 0, 5)
        g.addWidget(QLabel('Phase'), 0, 0)
        g.addWidget(phase, 0, 1)
        g.addWidget(QLabel('Skew'), 1, 0)
        g.addWidget(skew, 1, 1)
        g.setRowStretch(3, 1)
        for sp in (phase, skew):
            sp.valueChanged.connect(on_change)
        return w, phase, skew

    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(2)
        self.UpdateonfilechangeCheckBox = QCheckBox('Update on file change')
        v.addWidget(self.UpdateonfilechangeCheckBox)

        self.TabGroupFittingMethods = QTabWidget()
        self.TabGroupFittingMethods.addTab(self._fit_tab('SE'), 'SE')
        self.TabGroupFittingMethods.addTab(
            self._fit_tab('SE + IRF', [('IRF guess [us]', 'irf', 0.0)]), 'SE + IRF')
        self.TabGroupFittingMethods.addTab(
            self._fit_tab('DE', [('T1 guess [us]', 't1', 50.0), ('T2 guess [us]', 't2', 100.0)]), 'DE')
        self.TabGroupFittingMethods.addTab(
            self._fit_tab('DE + IRF', [('IRF guess [us]', 'irf', 0.0), ('T1 guess [us]', 't1', 50.0),
                                       ('T2 guess [us]', 't2', 100.0)]), 'DE + IRF')
        tab, self.LDPhaseSpinner, self.LDSkewSpinner = self._phase_tab(self.light_dark)
        self.TabGroupFittingMethods.addTab(tab, 'Light-Dark')
        tab, self.PhaseSpinner, self.SkewSpinner = self._phase_tab(self.phase_correction)
        self.TabGroupFittingMethods.addTab(tab, 'Phase')
        self.TabGroupFittingMethods.setMinimumHeight(230)
        self.TabGroupFittingMethods.currentChanged.connect(self._tab_changed)
        v.addWidget(self.TabGroupFittingMethods)

        self.FittingparametersPanel = QGroupBox('Fitting parameters')
        g = QGridLayout(self.FittingparametersPanel)
        g.setContentsMargins(6, 4, 6, 4)
        for c in range(4):
            g.setColumnStretch(c, 1)
        self.cbBoundfit = QCheckBox('Bound fit')
        self.NegativeampCheckBox = QCheckBox('Negative amp')
        g.addWidget(self.cbBoundfit, 0, 2)
        g.addWidget(self.NegativeampCheckBox, 0, 3)
        self.BaselineButton = QPushButton('Baseline')
        self.BaselineButton.setToolTip('Pick a baseline range on the viewer plot '
                                       '(right-click / Esc clears it)')
        g.addWidget(self.BaselineButton, 1, 3)
        self.LBfactorSpinner = SciSpinBox(0.2, 0.1, -1, 1)
        self.UBfactorSpinner = SciSpinBox(2.0, 0.1, 0, 10)
        self.ShowresiduexSpinner = SciSpinBox(3.0, 0.1, 1, 50)
        self.ResidueoffsetSpinner = SciSpinBox(-0.5, 0.1)
        for (r, c), text, sp in (((2, 0), 'LB factor', self.LBfactorSpinner),
                                 ((2, 2), 'UB factor', self.UBfactorSpinner),
                                 ((3, 0), 'Show residue x', self.ShowresiduexSpinner),
                                 ((3, 2), 'Residue offset', self.ResidueoffsetSpinner)):
            g.addWidget(QLabel(text), r, c)
            g.addWidget(sp, r, c + 1)
        self.ComputeButton = QPushButton('Compute')
        g.addWidget(self.ComputeButton, 4, 1, 1, 2)
        v.addWidget(self.FittingparametersPanel)

        self.tOutput = QPlainTextEdit()
        self.tOutput.setReadOnly(True)
        v.addWidget(self.tOutput, 1)

        self.ComputeButton.clicked.connect(self.compute)
        self.ShowresiduexSpinner.valueChanged.connect(self.compute)
        self.ResidueoffsetSpinner.valueChanged.connect(self.compute)
        self.BaselineButton.clicked.connect(self.pick_baseline)

    def _tab(self) -> str:
        return self.TabGroupFittingMethods.tabText(self.TabGroupFittingMethods.currentIndex())

    def _tab_changed(self, _):
        name = self._tab()
        self.setWindowTitle(TITLES[name])
        self.FittingparametersPanel.setEnabled(name not in ('Light-Dark', 'Phase'))

    # ================================================================ host
    def file_update(self):
        if self.UpdateonfilechangeCheckBox.isChecked():
            name = self._tab()
            if name == 'Light-Dark':
                self.light_dark()
            elif name == 'Phase':
                self.phase_correction()
            else:
                self.compute()

    def show_message(self, message, flag=''):
        self.tOutput.setPlainText(message)
        color = {'error': '#ff0000', 'upper bound': '#0000ff', 'lower bound': '#0000ff'}.get(flag, '#000000')
        self.tOutput.setStyleSheet(f'color: {color};')

    # ================================================================ callbacks
    def reset_range(self, name):
        src = self.host.get_data('source')
        x = np.asarray(src.ax.x, float) * 1e6
        c = self.tabs_w[name]
        t_peak = x[int(np.argmax(self._trace(src).real))]
        if name == 'DE':
            c['last'].setValue(x.max())
            c['t1'].setValue(x.max() / 5)
            c['t2'].setValue(x.max() / 2)
            c['offset'].setValue(t_peak)
            c['first'].setValue(t_peak)
            return
        c['first'].setValue(x.min())
        c['last'].setValue(x.max())
        if name in ('SE + IRF', 'DE + IRF'):
            c['irf'].setValue(x.max() / 100)
        if name == 'DE + IRF':
            c['t1'].setValue(x.max() / 5)
            c['t2'].setValue(x.max() / 2)
        else:
            c['offset'].setValue(t_peak)

    def set_time_offset(self, name):
        pos = self.host.ginput(1)
        if len(pos) < 1:
            return
        c = self.tabs_w[name]
        c['offset'].setValue(pos[0, 0] * 1e6)
        if name in ('SE', 'DE'):
            c['first'].setValue(pos[0, 0] * 1e6)

    def pick_baseline(self):
        pos = self.host.ginput(2)
        if len(pos) < 2:
            self.baseline = None
            self.show_message('Baseline is cleared')
            return
        x = np.asarray(self.host.get_data('source').ax.x, float)
        lo, hi = np.sort(pos[:, 0])
        self.baseline = (x >= lo) & (x <= hi)

    # ================================================================ fitting
    def _trace(self, src) -> np.ndarray:
        y = np.asarray(src.y)
        col = min(int(self.host.get('slice') or 0), y.shape[1] - 1) if y.ndim > 1 else 0
        return y[:, col] if y.ndim > 1 else y

    def compute(self, *_):
        try:
            self._compute()
        except Exception as e:  # noqa: BLE001 - report like a MATLAB error
            self.show_message(str(e), 'error')

    def _compute(self):
        name = self._tab()
        if name not in ('SE', 'SE + IRF', 'DE', 'DE + IRF'):
            return
        src = self.host.get_data('source')
        t = np.asarray(src.ax.x, float) * 1e6
        y = self._trace(src).real
        base = self.baseline if self.baseline is not None and len(self.baseline) == len(y) else None
        bl = y[base].mean() if base is not None and base.any() else 0.0

        def trace(x_us, yy, title, color=None, **ax):
            d = src.copy()
            d.ax.pop('raw', None)
            d.ax.pop('data', None)
            d.ax.x = np.asarray(x_us) * 1e-6
            d.ax.y = np.array([0.0])
            d.y = np.asarray(yy).reshape(-1, 1)
            d.title = title
            if color:
                d.ax.Color = color
            d.ax.update(ax)
            return d

        out = [trace(t, y, 'Source')]
        if base is not None and base.any():
            out.append(trace(t[base], y[base], 'Baseline', 'k', Marker='o'))

        c = self.tabs_w[name]
        i0 = int(np.argmin(np.abs(t - c['first'].value())))
        i1 = int(np.argmin(np.abs(t - c['last'].value())))
        tr = t[i0:i1 + 1]
        yd = y[i0:i1 + 1] - bl
        if len(yd) < 3:
            raise ValueError('the fit range has fewer than 3 points')
        fnorm = yd.max()
        amax = np.abs(yd).max()
        lbamp = -5.0 if self.NegativeampCheckBox.isChecked() else 0.01
        lbf, ubf = self.LBfactorSpinner.value(), self.UBfactorSpinner.value()
        bound = self.cbBoundfit.isChecked()

        if name == 'SE':
            t0 = c['offset'].value()
            tt = tr - t0
            def model(p): return p[0] * np.exp(-tt / p[1])
            p0 = np.array([yd.max(), tt.max() / 5])
            lb = np.array([lbamp * amax, p0[1] * lbf])
            ub = np.array([5 * amax, p0[1] * ubf])
            tol, names, comps = 1e-8, ['A', 'T'], []
        elif name == 'SE + IRF':
            t0, tt = 0.0, tr
            def model(p): return p[0] * exp_irf(tt - abs(p[3]), abs(p[1]), abs(p[2]))
            p0 = np.array([yd.max(), tt.max() / 5, c['irf'].value(), c['offset'].value()])
            lb = np.array([lbamp * amax, *(p0[1:] * [lbf, lbf, -2])])
            ub = np.array([5 * amax, *(p0[1:] * [ubf, ubf, 2])])
            tol, names, comps = 1e-4, ['A1', 'T1', 'IRF', 'tcorr'], []
        elif name == 'DE':
            t0 = c['offset'].value()
            tt = tr - t0
            def one(p): return p[0] * np.exp(-tt / p[1])
            def two(p): return p[2] * np.exp(-tt / p[3])
            def model(p): return one(p) + two(p)
            p0 = np.array([yd.max() / 2, c['t1'].value(), yd.max() / 2, c['t2'].value()])
            lb = np.array([lbamp * amax, p0[1] * lbf, lbamp * amax, p0[3] * lbf])
            ub = np.array([5 * amax, p0[1] * ubf, 5 * amax, p0[3] * ubf])
            tol, names, comps = 1e-8, ['A1', 'T1', 'A2', 'T2'], [one, two]
        else:   # DE + IRF
            t0, tt = 0.0, tr
            def one(p): return p[0] * exp_irf(tt - abs(p[3]), abs(p[1]), abs(p[2]))
            def two(p): return p[4] * exp_irf(tt - abs(p[3]), abs(p[5]), abs(p[2]))
            def model(p): return one(p) + two(p)
            p0 = np.array([yd.max() / 2, c['t1'].value(), c['irf'].value(), c['offset'].value(),
                           yd.max() / 2, c['t2'].value()])
            lb = np.array([lbamp * amax, p0[1] * lbf, p0[2] * lbf, -200, lbamp * amax, p0[5] * lbf])
            ub = np.array([5 * amax, p0[1] * ubf, p0[2] * ubf, 200, 5 * amax, p0[5] * ubf])
            tol, names, comps = 1e-8, ['A1', 'T1', 'IRF', 'Tcorr', 'A2', 'T2'], [one, two]

        def cost(p):
            return float(np.sum((yd - model(p)) ** 2))
        opts = dict(max_iter=2000, max_fun_evals=2000, tol_x=tol, tol_fun=tol)
        if bound:
            p, fval = fminsearchbnd(cost, p0, lb, ub, **opts)
        else:
            p, fval = fminsearch(cost, p0, **opts)
            lb = ub = None

        fit = model(p)
        resi = yd - fit
        xt = t0 + tt
        out.append(trace(xt, fit + bl, 'Fit', 'r'))
        out.append(trace(xt, self.ShowresiduexSpinner.value()
                         * (resi + fnorm * self.ResidueoffsetSpinner.value()),
                         f'Residual x{self.ShowresiduexSpinner.value():g}', 'g'))
        for k, (f, color) in enumerate(zip(comps, ('m', 'k')), start=1):
            out.append(trace(xt, f(p) + bl, f'Exponent{k}', color, LineStyle='--'))

        flag, msg = check_fit(p, lb, ub, names)
        norm = np.sqrt(fval / len(yd)) / fnorm if fnorm else np.nan
        tail = f'fval={fval:.4g} fval_norm={norm:.4g}\n{msg}'
        if name == 'SE':
            text = f'T1 = {p[1]:.2f}us   Amp={p[0]:f}\n'
        elif name == 'SE + IRF':
            text = f'T1 = {p[1]:.2f}us   Amp={p[0]:.3f}\nIRF={p[2]:.2f}us   t_corr={p[3]:.3f}us\n'
        elif name == 'DE':
            text = f'T1 = {p[1]:.2f}us Amp={p[0]:f}\nT2 = {p[3]:.2f}us Amp={p[2]:f}\n'
        else:
            text = (f'T1 = {p[1]:.2f}us Amp={p[0]:f}\nT2 = {p[5]:.2f}us Amp={p[4]:f}\n'
                    f'IRF={p[2]:.2f}us   t_corr={p[3]:.3f}us\n')
        self.show_message(text + tail, flag)
        self.host.set_data('output', out)

    # ================================================================ light-dark / phase
    def light_dark(self, *_):
        src = self.host.get_data('source')
        phase, skew = self.LDPhaseSpinner.value(), self.LDSkewSpinner.value()
        y = np.asarray(src.y)
        if y.shape[0] == 2 and y.shape[1] > 2:          # light / dark rows
            data = (y[0] - y)[1:]
            data = (data.real + 1j * data.imag * skew) * np.exp(-1j * phase / 180 * np.pi)
            src.y = data.T
            src.ax.x, src.ax.xlabel = src.ax.y, src.ax.get('ylabel', '')
            src.ax.y = np.array([0.0])
            title = 'Light - Dark'
        else:
            src.y = (y.real + 1j * y.imag * skew) * np.exp(-1j * phase / 180 * np.pi)
            title = 'Phase corrected'
        src.ax.Color, src.title = 'k', title
        self.host.set_data('output', [src])

    def phase_correction(self, *_):
        src = self.host.get_data('source')
        y = np.asarray(src.y)
        src.y = ((y.real + 1j * y.imag * self.SkewSpinner.value())
                 * np.exp(-1j * self.PhaseSpinner.value() / 180 * np.pi))
        src.ax.Color, src.title = 'k', 'Phase corrected'
        self.host.set_data('output', [src])
