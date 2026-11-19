"""Rapid-scan plugin: port of RapidScan3.mlapp.

Processing modes (the *Processing* group, run with *Go!* or any setting change):

* **As is** - one scan cycle of every trace, optionally filtered (Butterworth, *Use
  filter*), phased, circularly shifted by the scan phase; output is the sum of the cycle
  and its time-reversed copy (*A and B* also shows both), optionally on the sinusoidal
  field axis (*B mapping*).
* **Find Time** - data against a cosine of the scan frequency, to find the scan phase
  and the *Time factor*.
* **Deconvolve (new)** - sinusoidal rapid-scan deconvolution with background removal
  (``sinDecoBG``, M. Tseytlin); *auto* estimates the scan phase. *Visual* selects
  A+B, A and B, or the interleaved cycle before / after the RF phase.
* **Baseline** - fit of a sinusoidal background ``a cos + i b sin + offset``.

Scan parameters come from the description (SpecMan JIVA25 / Eclypse / aliases, or
Denver files); *Scan factor* and *Time factor* correct the scan width and sampling.

Differences from MATLAB (see Documentation/plugins.md):
* Filter / BL / Nharm / dB callbacks called ``ProcessDataMain`` with too many arguments
  (error); they all reprocess now. The *Linear* tab controls have no effect (the linear
  scan code in MATLAB was unreachable), as before.
* The scan-phase spinner gets the phase *applied* by the auto search (MATLAB stored the
  correction with the opposite sign, so switching *auto* off reprocessed with the
  wrong phase).
* *Update* reprocesses when a new file is loaded (MATLAB's ``FileUpdate`` was empty).
* *Script* shows a Python script for the current deconvolution instead of printing a
  MATLAB one; outputs get a field label.
* Undefined ``ha`` in the aliases / Denver parameter branches fixed.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QGridLayout, QGroupBox,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton,
                               QTabWidget, QVBoxLayout, QWidget)
from scipy.optimize import minimize
from scipy.signal import butter, lfilter

from kazan.core import KazanPlugin, KzData, Struct
from kazan.io.units import getvalue
from kazan.math.rapidscan import mround, sin_deco_bg
from kazan.viewer.widgets import SciSpinBox

VISUAL_MODES = ['Sum', 'A and B', 'Interleave-1', 'Interleave-2', 'Interleave-3']
FIELD_LABEL = 'Magnetic Field, G'


def _state(text, checked=False):
    b = QPushButton(text)
    b.setCheckable(True)
    b.setChecked(checked)
    return b


def _value(dsc, key, default):
    return getvalue(dsc.get(key, default))[0]


def scan_parameters(src: KzData) -> tuple[np.ndarray, dict]:
    """MATLAB ``get_data``: time-domain data (conjugated where needed) and the scan
    parameters ``Freq`` [Hz], ``ScanWidth`` [G], ``sampling`` [s], ``CentralField``."""
    dsc, ax = src.dsc or Struct(), src.ax
    y = np.asarray(src.y)
    pars = {'CentralField': 0.0}
    conj = True
    dconfig = str(dsc.get('general_dconfig', '')) + str(dsc.get('dconfig', ''))
    dx = float(np.mean(np.diff(ax.x))) if len(ax.x) > 1 else 1.0
    if 'RapidScan_Freq' in ax:
        pars.update(origin='specman', Freq=ax.RapidScan_Freq, ScanWidth=ax.RapidScan_ScanWidth,
                    sampling=ax.RapidScan_Sampling, CentralField=ax.RapidScan_CenterField)
    elif 'RS_Frequency' in dsc or 'RS_RSFrequency' in dsc:          # Eclypse FPGA
        if 'RS_RSFrequency' in dsc:
            f, w = _value(dsc, 'RS_RSFrequency', 0), _value(dsc, 'RS_RSAmplitude', 0)
        else:
            f, w = _value(dsc, 'RS_Frequency', 0), _value(dsc, 'RS_Amplitude', 0)
        pars.update(origin='specman', Freq=f, ScanWidth=w, sampling=dx)
        if not (f > 0 and w > 0 and dx > 0):
            raise ValueError('Eclypse header: invalid Freq/ScanWidth/sampling')
    elif 'JIVA25RapidScan' in dconfig:
        pars.update(origin='specman', Freq=_value(dsc, 'SCAN_Frequency1', '1'),
                    ScanWidth=_value(dsc, 'SCAN_AmplitudePP1', '1'),
                    sampling=_value(dsc, 'DG_Sampling', '100e-9'))
        conj = False
    elif 'JIVA25' in dconfig:
        pars.update(origin='specman', Freq=_value(dsc, 'SCAN_Frequency1', '1'),
                    ScanWidth=_value(dsc, 'SCAN_AmplitudePP1', '1') * 20.25, sampling=100e-9)
    elif 'aliases_RSfrequency' in dsc:
        pars.update(origin='specman', Freq=_value(dsc, 'aliases_RSfrequency', '500 Hz'),
                    ScanWidth=_value(dsc, 'aliases_RSwidth', '500 Hz'), sampling=dx)
    else:
        pars.update(origin='denver', Freq=_value(dsc, 'ScanFrequency', '1') * 1e3,
                    ScanWidth=_value(dsc, 'ScanWidth', '7') * 10, sampling=dx * 1e-9)
        conj = False
    if conj:
        y = np.conj(y)
    return y, pars


class RapidScan3(KazanPlugin):
    menu_name = 'RAPIDSCAN3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('RapidScanPLG')
        self.resize(331, 394)
        self.magnifier = 1.0
        self._build_ui()

    # ================================================================ UI
    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(5, 5, 5, 5)
        g.setSpacing(5)
        for c in range(3):
            g.setColumnStretch(c, 1)

        self.cbFileUpdate = QCheckBox('Update')
        g.addWidget(self.cbFileUpdate, 0, 2)

        self.pbFilter = _state('Use filter')
        g.addWidget(self.pbFilter, 1, 0)
        g.addWidget(self._center('CutOff [MHz]'), 1, 1)
        self.spinCutOff = SciSpinBox(1.0, 0.1, 0, 100)
        g.addWidget(self.spinCutOff, 1, 2)

        self.pbPhase = _state('Use phase')
        g.addWidget(self.pbPhase, 2, 0)
        g.addWidget(self._center('Phase [deg]'), 2, 1)
        self.spinPhase = SciSpinBox(0.0, 1.0, -360, 360)
        g.addWidget(self.spinPhase, 2, 2)

        factor = QGridLayout()
        factor.setSpacing(2)
        factor.addWidget(QLabel('Factor'), 0, 0)
        self.factor_group = QButtonGroup(self)
        self.factor_buttons = {}
        for c, (text, val) in enumerate((('x0.001', 0.001), ('x0.01', 0.01), ('x0.1', 0.1),
                                         ('x1', 1.0), ('x10', 10.0)), start=1):
            b = _state(text, val == 1.0)
            self.factor_group.addButton(b)
            self.factor_buttons[val] = b
            b.clicked.connect(lambda _=False, v=val: self._set_magnifier(v))
            factor.addWidget(b, 0, c)
        g.addLayout(factor, 3, 0, 1, 3)

        self.cbAutoPhase = QCheckBox('auto')
        self.cbAutoPhase.setToolTip('Estimate the scan phase (Deconvolve)')
        g.addWidget(self.cbAutoPhase, 4, 0)
        g.addWidget(QLabel('Scan phase [deg]'), 4, 1)
        self.spinScanPhase = SciSpinBox(0.0, 1.0, -360, 360)
        g.addWidget(self.spinScanPhase, 4, 2)

        # tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(QWidget(), 'Sinusoidal')
        lin = QWidget()
        lg = QGridLayout(lin)
        lg.setContentsMargins(5, 5, 5, 5)
        self.pbBaseline = _state('BL')
        self.eNharm = QLineEdit('4')
        self.edb = QLineEdit('1')
        for e in (self.eNharm, self.edb):
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lg.addWidget(self.pbBaseline, 0, 0)
        lg.addWidget(self.eNharm, 0, 1)
        lg.addWidget(self._center('Nharm'), 0, 2)
        lg.addWidget(self._center('dB [G]'), 1, 0)
        lg.addWidget(self.edb, 1, 1)
        self.tabs.addTab(lin, 'Linear')
        comp = QWidget()
        cg = QGridLayout(comp)
        cg.setContentsMargins(4, 4, 4, 4)
        cg.setSpacing(2)
        for c in range(4):
            cg.setColumnStretch(c, 1)
        self.spinBsweep = SciSpinBox(1.0, 0.001, -10, 10)
        self.spinSample = SciSpinBox(1.0, 1e-5, -2, 2)
        cg.addWidget(QLabel('Scan factor'), 0, 0)
        cg.addWidget(self.spinBsweep, 0, 1)
        cg.addWidget(QLabel('Time factor'), 1, 0)
        cg.addWidget(self.spinSample, 1, 1)
        self.tabs.addTab(comp, 'Compensation')
        self.TextArea = QPlainTextEdit()
        self.TextArea.setFont(QFont('Consolas'))
        self.TextArea.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.tabs.addTab(self.TextArea, 'Tab')
        g.addWidget(self.tabs, 5, 0, 2, 3)

        self.pmScanDir = QComboBox()
        self.pmScanDir.addItems(['/\\', '\\/'])
        g.addWidget(self.pmScanDir, 7, 0)
        self.cbFieldMapping = QCheckBox('B mapping')
        g.addWidget(self.cbFieldMapping, 7, 1)
        self.VisualMode = QComboBox()
        self.VisualMode.addItems(VISUAL_MODES)
        g.addWidget(self.VisualMode, 7, 2)

        box = QGroupBox('Processing')
        bl = QGridLayout(box)
        bl.setContentsMargins(4, 2, 4, 2)
        bl.setSpacing(0)
        self.rb1, self.rb2 = QRadioButton('As is'), QRadioButton('Find Time')
        self.rb3, self.rb4 = QRadioButton('Deconvolve (new)'), QRadioButton('Baseline')
        self.rb3.setChecked(True)
        self.mode_group = QButtonGroup(self)
        for b, (r, c) in ((self.rb1, (0, 0)), (self.rb2, (1, 0)), (self.rb3, (2, 0)),
                          (self.rb4, (0, 1))):
            self.mode_group.addButton(b)
            bl.addWidget(b, r, c)
        g.addWidget(box, 8, 0, 2, 2)
        self.pbDeconvolute = QPushButton('Go!')
        f = self.pbDeconvolute.font()
        f.setPointSizeF(f.pointSizeF() * 1.6)
        f.setBold(True)
        self.pbDeconvolute.setFont(f)
        self.pbDeconvolute.setMinimumHeight(40)
        g.addWidget(self.pbDeconvolute, 8, 2)
        self.pbShowScript = QPushButton('Script')
        self.pbShowScript.setStyleSheet('font-weight: bold;')
        g.addWidget(self.pbShowScript, 9, 2)

        # wiring (MATLAB ProcessDataMainEvent and friends)
        for b in (self.pbFilter, self.pbPhase, self.pbBaseline, self.cbFieldMapping):
            b.toggled.connect(self.process)
        for sp in (self.spinCutOff, self.spinPhase, self.spinScanPhase, self.spinBsweep,
                   self.spinSample):
            sp.valueChanged.connect(self.process)
        for cb in (self.pmScanDir, self.VisualMode):
            cb.currentIndexChanged.connect(self.process)
        for e in (self.eNharm, self.edb):
            e.editingFinished.connect(self.process)
        self.mode_group.buttonClicked.connect(self.process)
        self.pbDeconvolute.clicked.connect(self.process)
        self.pbShowScript.clicked.connect(self.show_script)

    @staticmethod
    def _center(text):
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lab

    def _set_magnifier(self, value: float):
        self.magnifier = value
        for sp in (self.spinPhase, self.spinScanPhase, self.spinBsweep):
            sp.setSingleStep(value)

    # ================================================================ host
    def file_update(self):
        if self.cbFileUpdate.isChecked():
            self.process()

    # ================================================================ processing
    def process(self, *_):
        try:
            if self.rb4.isChecked():
                self.process_baseline()
            elif self.rb3.isChecked():
                self.process_deconvolve()
            elif self.rb2.isChecked():
                self.process_find_time()
            else:
                self.show_data()
        except Exception as e:  # noqa: BLE001 - report to the viewer like MATLAB errors
            self.host.set('message', f'RapidScan: {e}')

    def _deco_pars(self, pars):
        return dict(dt=pars['sampling'] * self.spinSample.value(),
                    hm=pars['ScanWidth'] * self.spinBsweep.value(), vm=pars['Freq'],
                    up=1 if self.pmScanDir.currentIndex() == 0 else -1,
                    ph=self.spinPhase.value() if self.pbPhase.isChecked() else 0.0,
                    fp=self.spinScanPhase.value(), n_iter=1)

    def process_deconvolve(self):
        """MATLAB ProcessDataDenverNew."""
        src = self.host.get_data('source')
        y, pars = scan_parameters(src)
        kw = self._deco_pars(pars)
        auto = self.cbAutoPhase.isChecked()
        if auto:
            kw.update(fp=0.0, n_iter=4)
        self.TextArea.setPlainText(
            f"Process1D:\nFreq {pars['Freq'] * 1e-3:.1f}kHz, ScanWidth {kw['hm']:.1f}G, "
            f"sampling {kw['dt'] * 1e9:.4f}ns\nFP {kw['fp']:g},Phase {kw['ph']:.0f}deg")
        aa, bb = [], []
        for col in y.T:
            h, a, b, fp_corr, _, _, rs = sin_deco_bg(col, **kw)
            aa.append(a)
            bb.append(b)
        aa, bb = np.array(aa).T, np.array(bb).T
        if auto:
            self.spinScanPhase.blockSignals(True)
            self.spinScanPhase.setValue(kw['fp'] - fp_corr)   # phase actually applied
            self.spinScanPhase.blockSignals(False)

        x = h + pars['CentralField']
        mode = self.VisualMode.currentText()
        if mode == 'A and B':
            out = [self._out(x, aa, src, 'A', 'r'), self._out(x, bb, src, 'B', 'g')]
        elif mode in ('Interleave-1', 'Interleave-2'):
            key = 'rs_i' if mode == 'Interleave-1' else 'rs_ii'
            out = [self._out(np.arange(1, len(rs[key]) + 1), rs[key], src, key, 'b',
                             xlabel='Points, pnt')]
        else:
            out = [self._out(x, aa + bb, src, 'A+B')]
        self.host.set_data('output', out)

    def process_find_time(self):
        """MATLAB ProcessDataDenver."""
        src = self.host.get_data('source')
        _, pars = scan_parameters(src)
        a = src.copy()
        a.y = a.y.real - np.mean(a.y, axis=0).real
        a.title = 'A'
        amp = a.y.max(axis=0)
        b = src.copy()
        b.y = amp * np.cos(np.asarray(b.ax.x)[:, None] * pars['Freq'] * self.spinSample.value()
                           * 2 * np.pi + self.spinScanPhase.value() * np.pi / 180)
        b.ax.Color = 'r'
        b.title = 'B'
        self.host.set_data('output', [a, b])

    def process_baseline(self):
        """MATLAB ProcessExtractBaseline: fit of a sinusoidal baseline."""
        src = self.host.get_data('source')
        _, pars = scan_parameters(src)
        dt = pars['sampling'] * self.spinSample.value()
        ph = self.spinScanPhase.value() * np.pi / 180
        f = pars['Freq']
        y = src.y[:, 0]
        t = dt * np.arange(1, len(y) + 1)

        def model(p):
            return (p[0] * np.cos(2 * np.pi * f * t + p[4]) + 1j * p[1] * np.sin(2 * np.pi * f * t + p[4])
                    + p[2] + 1j * p[3])

        mxr, mnr, mxi, mni = y.real.max(), y.real.min(), y.imag.max(), y.imag.min()
        p0 = [(mxr - mnr) / 2, (mxi - mni) / 2, (mxr + mnr) / 2, (mxi + mni) / 2, ph]
        res = minimize(lambda p: np.sum(np.abs(y - model(p)) ** 2), p0, method='Nelder-Mead',
                       options={'maxiter': 1000, 'maxfev': 1000, 'xatol': 1e-4, 'fatol': 1e-4})
        p = res.x
        data = KzData(y=y[:, None], ax=Struct(x=t, xlabel='Time, s', Color='b'), dsc=src.dsc,
                      title='data')
        fit = KzData(y=model(p)[:, None], ax=Struct(x=t, xlabel='Time, s', Color='r'),
                     dsc=src.dsc, title='sum')
        self.TextArea.setPlainText(
            f'baseline sin {2 * np.hypot(p[0], p[1]):.3f} offset ({p[2]:.3f} {p[3]:.3f})')
        self.host.set_data('output', [data, fit])

    def show_data(self):
        """MATLAB ShowData ('As is'): one scan cycle and its time-reversed copy."""
        src = self.host.get_data('source')
        y, pars = scan_parameters(src)
        dt = pars['sampling']
        if self.pbFilter.isChecked():
            wn = self.spinCutOff.value() * 1e6 / (1 / 2 / dt)
            if 0 < wn < 0.99:
                b, a = butter(2, wn)
                y = lfilter(b, a, y, axis=0)
        t = dt * np.arange(y.shape[0]) * self.spinSample.value()
        m = int(np.sum(t < 1 / pars['Freq']))
        rsi = np.roll(y[:m], int(mround(self.spinScanPhase.value() / 360 * m)), axis=0)
        if self.pbPhase.isChecked():
            rsi = rsi * np.exp(-1j * self.spinPhase.value() / 180 * np.pi)
        if self.cbFieldMapping.isChecked():
            xx = pars['ScanWidth'] / 2 * -np.cos(np.arange(m) / (m - 1) * 2 * np.pi)
            idx = slice(0, m // 2)
        else:
            xx = np.linspace(-pars['ScanWidth'] / 2, pars['ScanWidth'] / 2, m)
            idx = slice(0, m)
        frsi = rsi[::-1]
        out = [self._out(xx[idx], rsi[idx] + frsi[idx], src, 'sum', 'r')]
        if self.VisualMode.currentText() == 'A and B':
            out += [self._out(xx[idx], rsi[idx], src, 'rsi', 'b'),
                    self._out(xx[idx], frsi[idx], src, 'flip', 'g')]
        self.host.set_data('output', out)

    @staticmethod
    def _out(x, y, src, title, color=None, xlabel=FIELD_LABEL):
        y = np.asarray(y)
        y = y[:, None] if y.ndim == 1 else y
        ax = Struct(x=np.asarray(x, float), xlabel=xlabel)
        if len(np.ravel(src.ax.get('y', []))) == y.shape[1]:
            ax.y, ax.ylabel = np.ravel(src.ax.y), src.ax.get('ylabel', '')
        if color:
            ax.Color = color
        return KzData(y=y, ax=ax, dsc=src.dsc, title=title)

    # ================================================================ script
    def show_script(self):
        """Python equivalent of the current deconvolution (MATLAB printed a script)."""
        try:
            src = self.host.get_data('source')
            _, pars = scan_parameters(src)
        except Exception as e:  # noqa: BLE001
            self.host.set('message', f'RapidScan: {e}')
            return
        kw = self._deco_pars(pars)
        if self.cbAutoPhase.isChecked():
            kw['fp'] = 0.0
        conj ='y_TD = np.conj(y_TD)\n' if pars['origin'] != 'denver' and \
            'JIVA25RapidScan' not in str(src.dsc.get('general_dconfig', '')) + \
            str(src.dsc.get('dconfig', '')) else ''
        self.TextArea.setPlainText(
            '# y_TD: complex time-domain data, one trace per column\n'
            'import numpy as np\nfrom kazan.math.rapidscan import sin_deco_bg\n'
            f'{conj}'
            f"h, A, B, fp_corr, *_ = sin_deco_bg(y_TD[:, 0], dt={kw['dt']:.6g}, "
            f"hm={kw['hm']:.6g}, vm={kw['vm']:.6g},\n"
            f"    up={kw['up']}, ph={kw['ph']:.6g}, fp={kw['fp']:.6g}, "
            f"n_iter={4 if self.cbAutoPhase.isChecked() else 1})\n"
            f"x = h + {pars['CentralField']:g}   # field, G\ny = A + B\n")
        self.tabs.setCurrentWidget(self.TextArea)
