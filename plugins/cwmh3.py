"""Multi-harmonic CW plugin: port of CWMH3.mlapp.

For SpecMan CW data recorded with 10 channels (``ax.raw``): channels 1-5 are the I
(real) parts of harmonics 1-5, channels 6-10 the Q (imaginary) parts.

* **As Is** - the channel(s) chosen in *Source* (I and Q of one harmonic, a single
  channel, or all five harmonics), optionally phased with *Phase* when *Use* is on.
* **MH** - the five harmonics as separate traces, offset-corrected; *Use* fits a
  phase that is linear in the harmonic number (printed in the report box).
* **Phases** - the five harmonics as one 2D set (same phase handling as MH).
* **Power saturation** - peak-to-peak amplitude of every trace against microwave power
  (reference 20 dBm minus the attenuation in ``ax.y``), with a saturation-curve fit
  ``A sqrt(P) / (1 + P/Ps)^e`` reporting ``Ps`` and ``e``.

Differences from MATLAB (see Documentation/plugins.md):
* Single-channel sources (*I Channel 6..10*) and *IQ all* work (MATLAB failed: the Q
  channel was undefined, and *IQ all* had no case).
* *MH* subtracts the offset per trace, and the fitted phase goes to the report box.
* The phase search cost is normalised by the signal power, so the optimiser does not stop
  at the start for weak signals.
* The power-saturation window (points 256..768) is limited to the data length.
* The window is titled *CWMH*; the phase toggle is labelled *Use*.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QGridLayout, QLabel, QPlainTextEdit,
                               QPushButton, QWidget)
from scipy.optimize import minimize

from kazan.core import KazanPlugin, KzData, Struct
from kazan.viewer.widgets import SciSpinBox

SOURCES = ['I Channel 1 and 6', 'I Channel 2 and 7', 'I Channel 3 and 8', 'I Channel 4 and 9',
           'I Channel 5 and 10', 'I Channel 6', 'I Channel 7', 'I Channel 8', 'I Channel 9',
           'I Channel 10', 'IQ all']
MODES = ['As Is', 'Power saturation', 'Phases', 'MH']
COLORS = ['b', 'r', 'g', 'm', 'y']
P_REF = 20.0   # dBm


def _fminsearch(f, x0):
    return minimize(f, x0, method='Nelder-Mead',
                    options={'maxiter': 200 * len(x0), 'maxfev': 200 * len(x0),
                             'xatol': 1e-4, 'fatol': 1e-4}).x


def harmonics(raw: np.ndarray) -> list[np.ndarray]:
    """Harmonics 1..5 as complex arrays (I = channel k, Q = channel k+5)."""
    if raw is None or raw.ndim < 3 or raw.shape[2] < 10:
        raise ValueError('the source has no 10-channel raw data (ax.raw)')
    return [raw[:, :, k] + 1j * raw[:, :, k + 5] for k in range(5)]


def find_lin_phase(ys) -> np.ndarray:
    """MATLAB FindLINPhase: [phase0, phase step per harmonic] in degrees that minimise
    the imaginary parts of all harmonics."""
    def f(x):
        return sum(np.sum(np.imag(y * np.exp(-1j * (x[0] + k * x[1]))) ** 2)
                   for k, y in enumerate(ys))
    grid = np.arange(181)
    s = [f([-5, p * np.pi / 180]) for p in grid]
    ph = _fminsearch(f, np.array([0.0, grid[int(np.argmin(s))] * np.pi / 180])) * 180 / np.pi
    if ph[0] < 0:
        ph[0] += 360
    return ph


def saturation_fit(att: np.ndarray, amp: np.ndarray):
    """Fit ``x0 sqrt(P) / (1 + P/x1)^e`` (e = x2 limited to 0.5..1.5), P in W."""
    p = 10 ** ((P_REF + att - 30) / 10)

    def sat(x):
        e = min(max(x[2], 0.5), 1.5)
        return x[0] * np.sqrt(p) / (1 + p / x[1]) ** e
    x = _fminsearch(lambda x: np.sqrt(np.sum((amp - sat(x)) ** 2)), np.array([1, 0.01, 1.0]))
    return x, sat(x)


class CWMH3(KazanPlugin):
    menu_name = 'CWMH3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('CWMH')
        self.resize(383, 386)
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(10, 10, 10, 10)
        for c, s in enumerate((4, 10, 2)):
            g.setColumnStretch(c, s)
        for r in range(7):
            g.setRowStretch(r, 1)
        lab = QLabel('Source')
        lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        g.addWidget(lab, 0, 0)
        self.SourceDropDown = QComboBox()
        self.SourceDropDown.addItems(SOURCES)
        g.addWidget(self.SourceDropDown, 0, 1)

        steps = QGridLayout()
        steps.setSpacing(2)
        self.step_group = QButtonGroup(self)
        for c, (text, step) in enumerate((('0.01', 0.01), ('0.1', 0.1), ('x1', 1.0), ('10', 10.0),
                                          ('100', 100.0), ('0.001', 0.001))):
            b = QPushButton(text)
            b.setCheckable(True)
            self.step_group.addButton(b)
            b.clicked.connect(lambda _=False, s=step: self.PhaseSpinner.setSingleStep(s))
            steps.addWidget(b, 0, c)
        g.addLayout(steps, 1, 1)

        lab = QLabel('Phase')
        lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        g.addWidget(lab, 2, 0)
        self.PhaseSpinner = SciSpinBox()
        g.addWidget(self.PhaseSpinner, 2, 1)
        self.btnUsePhase = QPushButton('Use')
        self.btnUsePhase.setCheckable(True)
        g.addWidget(self.btnUsePhase, 2, 2)

        self.Reports = QPlainTextEdit()
        g.addWidget(self.Reports, 4, 0, 2, 3)
        self.DropDown2 = QComboBox()
        self.DropDown2.addItems(MODES)
        g.addWidget(self.DropDown2, 6, 0)
        self.CalculateButton = QPushButton('Calculate')
        g.addWidget(self.CalculateButton, 6, 1)

        self.CalculateButton.clicked.connect(self.calculate)
        self.SourceDropDown.currentIndexChanged.connect(self.calculate)
        self.PhaseSpinner.valueChanged.connect(self.calculate)
        self.btnUsePhase.toggled.connect(self.calculate)

    def calculate(self, *_):
        try:
            self._calculate()
        except Exception as e:  # noqa: BLE001 - report like a MATLAB error
            self.host.set('message', f'CWMH: {e}')

    def _source_y(self, raw):
        name = self.SourceDropDown.currentText()
        if name == 'IQ all':
            return np.concatenate([h.reshape(h.shape[0], -1) for h in harmonics(raw)], axis=1), True
        nums = [int(t) for t in name.replace('I Channel', '').replace('and', ' ').split()]
        if raw is None or raw.ndim < 3 or raw.shape[2] < max(nums):
            raise ValueError(f'the source has no channel {max(nums)} in ax.raw')
        y = raw[:, :, nums[0] - 1].astype(complex)
        if len(nums) > 1:
            y = y + 1j * raw[:, :, nums[1] - 1]
        return y, len(nums) > 1

    def _phases(self, ys):
        if not self.btnUsePhase.isChecked():
            return np.zeros(5)
        phs = find_lin_phase(ys)
        self.Reports.setPlainText(f'{phs[1]:.2f}*(x-1) + {phs[0]:.2f}')
        return phs[0] + np.arange(5) * phs[1]

    def _calculate(self):
        signal = self.host.get_data('source')
        raw = signal.ax.get('raw')
        raw = None if raw is None else np.asarray(raw)
        mode = self.DropDown2.currentText()
        x = np.asarray(signal.ax.x)

        def trace(data, title, color=None, **ax):
            a = Struct(x=x, xlabel=signal.ax.get('xlabel', ''), **ax)
            if color:
                a.Color = color
            return KzData(y=data, ax=a, dsc=signal.dsc, filename=signal.filename, title=title)

        if mode == 'As Is':
            y, has_q = self._source_y(raw)
            if self.btnUsePhase.isChecked() and has_q:
                y = y * np.exp(-1j * self.PhaseSpinner.value() * np.pi / 180)
            yy = np.ravel(signal.ax.get('y', []))
            extra = {'y': yy, 'ylabel': signal.ax.get('ylabel', '')} if len(yy) == y.shape[1] else {}
            out = [trace(y, 'source', 'r', **extra)]
        elif mode in ('MH', 'Phases'):
            ys = harmonics(raw)
            ph = self._phases(ys)
            if mode == 'MH':
                out = []
                for k, y in enumerate(ys):
                    y = y.copy()
                    bl = y[:5].mean(axis=0)
                    y[-1] = bl
                    out.append(trace((y - bl) * np.exp(-1j * ph[k] * np.pi / 180), f'harmonic {k + 1}',
                                     COLORS[k]))
                    out[-1].ax.xlabel = 'Magnetic Field, G'
            else:
                y = np.column_stack([ys[k][:, 0] * np.exp(-1j * ph[k] * np.pi / 180) for k in range(5)])
                out = [trace(y, 'harmonics', y=np.arange(1.0, 6.0), ylabel='Harmonic')]
        else:   # Power saturation
            y, _ = self._source_y(raw)
            y = y.real
            idx = slice(min(255, y.shape[0] - 1), min(768, y.shape[0]))
            amp = y[idx].max(axis=0) - y[idx].min(axis=0)
            order = np.argsort(-np.ravel(signal.ax.y), kind='stable')
            att = -np.ravel(signal.ax.y)[order]
            amp = amp[order]
            xfit, fit = saturation_fit(att, amp)
            px = Struct(x=att + P_REF, xlabel='Power, dBm', y=np.array([0.0]))
            out = [KzData(y=20 * np.log10(amp), ax=Struct(px, Color='r'), title='source'),
                   KzData(y=20 * np.log10(fit), ax=Struct(px.copy(), Color='g'), title='fit')]
            self.Reports.setPlainText(
                f'Pref={P_REF:.1f}dBm\nPs={xfit[1] * 1e3:.1f}mW ({10 * np.log10(xfit[1] * 1e3):.1f}dBm) '
                f'e={xfit[2]:.3f}')
        self.host.set_data('output', out)
