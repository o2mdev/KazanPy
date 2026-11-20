"""Multi-harmonic CW plugin (CWMH3), reworked for multiharmonic acquisition.

Works on the lock-in channels of a SpecMan CW file (``ax.raw``: points x slices x
channels, with their names in ``ax.raw_names`` such as ``a: C1_H3I``).

**Source** - how the channels map to harmonics:

* *Auto* - from the channel names (``C<in>_H<h><I|Q>``; input 1). Without names, *Blocks*.
* *Harmonics [1, 2, ...]* - every channel is the in-phase signal of the next harmonic
  (LinMode ``CH1:I10``, the 20-harmonic RS board).
* *Pairs [1r, 1i, 2r, 2i, ...]* - I and Q of each harmonic in turn (``CH1-IQ5``).
* *Blocks [1r, 2r, ..., 1i, 2i, ...]* - all I, then all Q (the Kazan3 CWMH3 layout).

*Harmonics* limits the set used (``1-10``, ``1,3,5``; empty = all).

**Phase** - harmonic h is rotated by ``Phase + Slope (h - 1)`` degrees when *Use* is on
(I and Q needed). *Fit* finds Phase and Slope from the data: *principal axis* (the angle of
every harmonic's I/Q cloud, then a line fit mod 180, SNR^2 weighted; SpecMan multiharmonic
skill) or *min. imaginary* (Kazan3: minimise the imaginary parts of all harmonics).

**Mode**

* *As Is* - the selected harmonics as separate traces (phased, edge baseline removed).
* *Harmonics 2D* - the harmonics as one 2D set (the slider steps through them).
* *MH reconstruction* - the absorption from all harmonics (Kalin, Gromov, Schweiger, JMR
  160, 166 (2003)): every harmonic is the absorption seen through 2 i^h J_h(k Bm/2) in the
  Fourier domain; they are combined by noise-weighted least squares (``mu``: Tikhonov term).
  *Show*: the absorption, the pseudo 1st harmonic at *Bm out* (what a small-modulation
  measurement would give, without overmodulation), pseudo vs measured H1, or the harmonics
  with the model.
* *MH joint fit* - one Voigt (or Lorentzian) line fitted to all harmonics at once with Bm
  free: position, widths, dBpp, Bm (a modulation calibration).
* *Power saturation* - peak-to-peak of harmonic 1 for every slice against microwave power
  (reference 20 dBm minus the attenuation in ``ax.y``), with ``A sqrt(P) / (1 + P/Ps)^e``.

The field axis is the source X axis when it is a field (G, mT); otherwise it is built from
the lock-in's ``ScanAmplitude`` (relative to the sweep centre), as the board sweeps. *Bm*
starts at the file's ``ModAmplitude``. Bm must be the true field (calibrated CCmod).
"""
from __future__ import annotations

import re

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)
from scipy.optimize import minimize

from kazan.core import KazanPlugin, KzData, Struct
from kazan.io.units import getvalue
from kazan.math import multiharmonic as mh
from kazan.viewer.widgets import SciSpinBox

LAYOUTS = [('Auto (channel names)', 'auto'), ('Harmonics [1, 2, ...]', 'harm'),
           ('Pairs [1r, 1i, 2r, 2i, ...]', 'pairs'), ('Blocks [1r, 2r, ..., 1i, 2i, ...]', 'blocks')]
MODES = ['As Is', 'Harmonics 2D', 'MH reconstruction', 'MH joint fit', 'Power saturation']
SHOW = [('Absorption', 'abs'), ('Pseudo 1st harmonic', 'd1'), ('Pseudo vs measured H1', 'cmp'),
        ('Harmonics + model', 'model')]
PHASE_FITS = [('principal axis', 'axis'), ('min. imaginary', 'imag')]
SIGNS = [('Auto (H2 vs H1)', 'auto'), ('As recorded', 'as'), ('Alternate (-1)^(h-1)', 'alt')]
COLORS = ['b', 'r', 'g', 'm', 'c', 'k']
P_REF = 20.0   # dBm


# ================================================================ data helpers
def parse_harmonics(text: str) -> list[int] | None:
    """'1-10' / '1,3,5' / '2-4, 7' -> harmonic numbers; empty -> None (all)."""
    out = []
    for part in re.split(r'[,\s]+', text.strip()):
        if not part:
            continue
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return sorted(set(out)) or None


def split_harmonics(raw: np.ndarray, layout: str, names=None):
    """Channels (N, m, k) -> (harmonic numbers, H (n_h, N, m) real or complex, has_q, note)."""
    raw = np.asarray(raw, float)
    if raw.ndim == 2:
        raw = raw[:, None, :]
    n, m, k = raw.shape
    note = ''
    if layout == 'auto':
        found = {}
        for i, name in enumerate(names or []):
            mm = re.search(r'C(\d+)_H(\d+)([IQ])', str(name))
            if mm and mm.group(1) == '1' and i < k:
                found.setdefault(int(mm.group(2)), {})[mm.group(3)] = i
        if found:
            hs = sorted(h for h in found if 'I' in found[h])
            has_q = all('Q' in found[h] for h in hs)
            hh = np.array([raw[:, :, found[h]['I']] + (1j * raw[:, :, found[h]['Q']] if has_q else 0)
                           for h in hs])
            return hs, hh, has_q, 'channels from their names'
        layout, note = 'blocks', 'no channel names: Blocks assumed'
    if layout == 'harm':
        return list(range(1, k + 1)), np.moveaxis(raw, 2, 0), False, note
    if k % 2:
        raise ValueError(f'{k} channels cannot be I/Q pairs')
    nh = k // 2
    if layout == 'pairs':
        hh = raw[:, :, 0::2] + 1j * raw[:, :, 1::2]
    else:
        hh = raw[:, :, :nh] + 1j * raw[:, :, nh:]
    return list(range(1, nh + 1)), np.moveaxis(hh, 2, 0), True, note


def device_value(dsc, prop: str):
    """A lock-in property from the description (``LIN_ScanAmplitude``, ``RS_...``)."""
    for key, v in (dsc or {}).items():
        if str(key).endswith('_' + prop) and not str(key).startswith(('params_', 'devices_')):
            return v
    return None


def field_axis(src: KzData, n: int):
    """Field (G) of the n points and a label: the X axis when it is a field, else the
    board's sweep (ScanAmplitude, bin centres relative to the sweep centre)."""
    label = str(src.ax.get('xlabel') or '')
    unit = label.rpartition(',')[2].strip()
    x = np.ravel(src.ax.get('x', []))
    if unit in ('G', 'mT', 'T') and x.size >= n:
        k = {'G': 1.0, 'mT': 10.0, 'T': 1e4}[unit]
        return x[:n] * k, label if unit == 'G' else label.rpartition(',')[0] + ', G'
    amp = device_value(src.dsc, 'ScanAmplitude')
    if amp is None:
        raise ValueError('no field axis: X is not a field and ScanAmplitude is not in the file')
    a = getvalue(str(amp))[0]
    return -a / 2 + (np.arange(n) + 0.5) * a / n, 'Field (sweep centre = 0), G'


def find_lin_phase(hc) -> tuple[float, float]:
    """Kazan3 FindLINPhase: Phase, Slope (deg) minimising the imaginary parts of all
    harmonics (the cost normalised by the signal power)."""
    power = sum(np.sum(np.abs(y) ** 2) for y in hc) or 1.0

    def f(x):
        return sum(np.sum(np.imag(y * np.exp(-1j * (x[0] + k * x[1]))) ** 2)
                   for k, y in enumerate(hc)) / power
    grid = np.arange(181)
    s = [f([-5 * np.pi / 180, p * np.pi / 180]) for p in grid]
    x = minimize(f, [0.0, grid[int(np.argmin(s))] * np.pi / 180], method='Nelder-Mead',
                 options={'xatol': 1e-5, 'fatol': 1e-8}).x * 180 / np.pi
    return float(x[0] % 360), float(x[1])


def saturation_fit(att: np.ndarray, amp: np.ndarray):
    """Fit ``x0 sqrt(P) / (1 + P/x1)^e`` (e = x2 limited to 0.5..1.5), P in W."""
    p = 10 ** ((P_REF + att - 30) / 10)
    la = np.log(np.maximum(amp, 1e-300))

    def log_sat(q):       # q = ln x0, ln Ps, e  (fitted in log space: amplitudes of any scale)
        e = min(max(q[2], 0.5), 1.5)
        return q[0] + 0.5 * np.log(p) - e * np.log1p(p / np.exp(q[1]))

    best = None
    for ps0 in np.exp(np.linspace(np.log(p.min()), np.log(p.max()), 7)):
        for e0 in (0.5, 1.0, 1.5):
            q0 = [float(np.mean(la - 0.5 * np.log(p) + e0 * np.log1p(p / ps0))), np.log(ps0), e0]
            r = minimize(lambda q: np.sum((la - log_sat(q)) ** 2), q0, method='Nelder-Mead',
                         options={'maxiter': 4000, 'xatol': 1e-8, 'fatol': 1e-14})
            if best is None or r.fun < best.fun:
                best = r
    q = best.x
    x = np.array([np.exp(q[0]), np.exp(q[1]), min(max(q[2], 0.5), 1.5)])
    return x, np.exp(log_sat(q))


# ================================================================ plugin
class CWMH3(KazanPlugin):
    menu_name = 'CWMH3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('CWMH')
        self.resize(430, 600)
        self._build_ui()
        self.file_update()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        box = QGroupBox('Source')
        f = QFormLayout(box)
        self.SourceDropDown = QComboBox()
        for label, key in LAYOUTS:
            self.SourceDropDown.addItem(label, key)
        f.addRow('Layout', self.SourceDropDown)
        row = QHBoxLayout()
        self.eHarmonics = QLineEdit()
        self.eHarmonics.setPlaceholderText('all')
        self.eHarmonics.setToolTip("Harmonics to use: '1-10', '1,3,5'; empty = all")
        self.sbSlice = QSpinBox()
        self.sbSlice.setMinimum(1)
        self.sbSlice.setPrefix('slice ')
        row.addWidget(self.eHarmonics, 1)
        row.addWidget(self.sbSlice)
        f.addRow('Harmonics', row)
        self.lInfo = QLabel('-')
        self.lInfo.setStyleSheet('color: #606060;')
        self.lInfo.setWordWrap(True)
        f.addRow(self.lInfo)
        v.addWidget(box)

        box = QGroupBox('Phase, deg:  harmonic h is rotated by Phase + Slope (h - 1)')
        g = QGridLayout(box)
        self.PhaseSpinner = SciSpinBox(0.0, 1.0, -720, 720)
        self.SlopeSpinner = SciSpinBox(0.0, 1.0, -720, 720)
        self.btnUsePhase = QPushButton('Use')
        self.btnUsePhase.setCheckable(True)
        self.ddPhaseFit = QComboBox()
        for label, key in PHASE_FITS:
            self.ddPhaseFit.addItem(label, key)
        self.btnFitPhase = QPushButton('Fit')
        self.btnFitPhase.setToolTip('Find Phase and Slope from the I/Q data')
        g.addWidget(QLabel('Phase'), 0, 0)
        g.addWidget(self.PhaseSpinner, 0, 1)
        g.addWidget(QLabel('Slope'), 0, 2)
        g.addWidget(self.SlopeSpinner, 0, 3)
        g.addWidget(self.btnUsePhase, 0, 4)
        g.addWidget(self.btnFitPhase, 1, 4)
        g.addWidget(self.ddPhaseFit, 1, 1, 1, 3)
        g.addWidget(QLabel('Fit by'), 1, 0)
        self.ddSigns = QComboBox()
        for label, key in SIGNS:
            self.ddSigns.addItem(label, key)
        self.ddSigns.setToolTip(
            'Harmonic signs. Alternate flips every second harmonic: a lock-in phase slope\n'
            '180 deg off (e.g. ModPhSlope -70 instead of 110). Auto compares H2 with the\n'
            'H2 predicted from H1 and flips when it is inverted. Works for I-only data.')
        g.addWidget(QLabel('Signs'), 2, 0)
        g.addWidget(self.ddSigns, 2, 1, 1, 3)
        self.lSigns = QLabel('')
        self.lSigns.setStyleSheet('color: #606060;')
        g.addWidget(self.lSigns, 2, 4)
        v.addWidget(box)

        box = QGroupBox('Method')
        f = QFormLayout(box)
        self.DropDown2 = QComboBox()
        self.DropDown2.addItems(MODES)
        f.addRow('Mode', self.DropDown2)
        self.sbBm = SciSpinBox(0.1, 0.01, 0, 1e3)
        self.sbBm.setToolTip('Modulation amplitude, G peak-to-peak (true field; start value of '
                             'the joint fit)')
        f.addRow('Bm, G', self.sbBm)
        self.sbBmOut = SciSpinBox(0.01, 0.001, 0, 1e3)
        self.sbBmOut.setToolTip('Bm of the pseudo 1st harmonic (e.g. the dBpp of the line)')
        f.addRow('Bm out, G', self.sbBmOut)
        self.sbMu = SciSpinBox(1e-3, 1e-4, 0, 1)
        self.sbMu.setToolTip('Tikhonov regularisation: features broader than ~Bm/sqrt(mu) are lost')
        f.addRow('mu', self.sbMu)
        self.ddShow = QComboBox()
        for label, key in SHOW:
            self.ddShow.addItem(label, key)
        f.addRow('Show', self.ddShow)
        self.cbGauss = QCheckBox('Voigt (Gaussian part); off: Lorentzian')
        self.cbGauss.setChecked(True)
        f.addRow('Line', self.cbGauss)
        self._method_rows = f
        v.addWidget(box)

        self.Reports = QPlainTextEdit()
        self.Reports.setReadOnly(True)
        self.Reports.setMinimumHeight(160)
        v.addWidget(self.Reports, 1)
        row = QHBoxLayout()
        self.cbUpdate = QCheckBox('Update when file changes')
        self.cbUpdate.setChecked(True)
        self.CalculateButton = QPushButton('Calculate')
        self.CalculateButton.setMinimumHeight(30)
        row.addWidget(self.cbUpdate)
        row.addWidget(self.CalculateButton, 1)
        v.addLayout(row)

        self.CalculateButton.clicked.connect(self.calculate)
        self.btnFitPhase.clicked.connect(self.fit_phase)
        self.DropDown2.currentIndexChanged.connect(self._update_enabled)
        self.ddShow.currentIndexChanged.connect(self.calculate)
        self.SourceDropDown.currentIndexChanged.connect(self._source_changed)
        self.btnUsePhase.toggled.connect(self.calculate)
        self.ddSigns.currentIndexChanged.connect(self.calculate)
        self._update_enabled()

    def _update_enabled(self, *_):
        mode = self.DropDown2.currentText()
        f = self._method_rows
        for wdg, on in ((self.sbBm, mode.startswith('MH')),
                        (self.sbBmOut, mode == 'MH reconstruction'),
                        (self.sbMu, mode == 'MH reconstruction'),
                        (self.ddShow, mode == 'MH reconstruction'),
                        (self.cbGauss, mode == 'MH joint fit')):
            f.setRowVisible(wdg, on)

    def _source_changed(self, *_):
        self._read_source()
        self.calculate()

    # ---------------------------------------------------------------- host
    def file_update(self):
        if not self.cbUpdate.isChecked():
            return
        src = self.host.get_data('source')
        bm = device_value(src.dsc, 'ModAmplitude')
        if bm is not None:
            self.sbBm.setValue(getvalue(str(bm))[0])
            self.sbBmOut.setValue(round(self.sbBm.value() / 10, 6))
        if self._read_source():
            self.calculate()

    def _read_source(self) -> bool:
        """Split the source channels into harmonics; the info line says what was found."""
        self.src = self.host.get_data('source')
        raw = self.src.ax.get('raw')
        names = self.src.ax.get('raw_names')
        origin = 'lock-in channels (ax.raw)'
        self.hs = []
        if raw is None or np.ndim(raw) < 2:
            # other files: the source columns are the channels (complex columns: re, im pairs)
            y = np.asarray(self.src.y)
            if y.size == 0 or y.ndim != 2 or y.shape[1] < 2 and not np.iscomplexobj(y):
                self.lInfo.setText('No channels: the source needs ax.raw or several columns')
                return False
            raw = (np.stack([y.real, y.imag], axis=2).reshape(y.shape[0], -1)
                   if np.iscomplexobj(y) else y)[:, None, :]
            names = self.src.ax.get('streams')
            origin = 'source columns' + (' (re, im of each: use Pairs)' if np.iscomplexobj(y) else '')
        try:
            hs, hh, has_q, note = split_harmonics(raw, self.SourceDropDown.currentData(), names)
        except ValueError as e:
            self.lInfo.setText(str(e))
            return False
        self.hs, self.hh, self.has_q = hs, hh, has_q
        self.sbSlice.setMaximum(hh.shape[2])
        dev = []
        for prop in ('LinMode', 'ScanAmplitude', 'ModAmplitude', 'ModPhase', 'ModPhSlope'):
            val = device_value(self.src.dsc, prop)
            if val is not None:
                dev.append(f'{prop} {val}')
        self.lInfo.setText(f"{origin}: {len(hs)} harmonics ({'I + Q' if has_q else 'I only'}), "
                           f"{hh.shape[1]} points, {hh.shape[2]} slice(s)"
                           + (f'; {note}' if note else '') + ('\n' + ', '.join(dev) if dev else ''))
        self.btnFitPhase.setEnabled(has_q)
        self.btnFitPhase.setToolTip(
            'Find Phase and Slope from the I/Q data' if has_q else
            'Needs I and Q channels: this source has only in-phase (I) harmonics, '
            'so the phase cannot be found afterwards.\nSet Phase/Slope by hand or record with LinMode CH1-IQ.')
        return True

    # ---------------------------------------------------------------- pieces
    def _selected(self):
        """(harmonic numbers, H (n_h, N, m)) of the selection, phased when *Use* is on."""
        want = parse_harmonics(self.eHarmonics.text())
        idx = [i for i, h in enumerate(self.hs) if want is None or h in want]
        if not idx:
            raise ValueError('none of the selected harmonics is in the data')
        hs = [self.hs[i] for i in idx]
        hh = self.hh[idx]
        if self.btnUsePhase.isChecked() and self.has_q:
            ph = self.PhaseSpinner.value() + self.SlopeSpinner.value() * (np.asarray(hs) - 1)
            hh = hh * np.exp(-1j * np.radians(ph))[:, None, None]
        return hs, hh

    def _slice(self) -> int:
        return min(self.sbSlice.value(), self.hh.shape[2]) - 1

    def fit_phase(self):
        """Phase and Slope from the I/Q data of the current slice."""
        try:
            if not self._read_source() or not self.has_q:
                raise ValueError('phase fit needs I and Q channels')
            want = parse_harmonics(self.eHarmonics.text())
            idx = [i for i, h in enumerate(self.hs) if want is None or h in want]
            hs = [self.hs[i] for i in idx]
            hc = self.hh[idx][:, :, self._slice()]
            if self.ddPhaseFit.currentData() == 'axis':
                phi = mh.harmonic_phase_offsets(hc)
                snr = np.array([s['snr'] for s in mh.harmonic_snr(np.abs(hc))])
                r = mh.fit_phase_line(hs, phi, weights=snr ** 2)
                phase1, slope = r['phase1'], r['slope']
                text = ('phase per harmonic (deg, mod 180): '
                        + ', '.join(f'H{h} {p:.1f}' for h, p in zip(hs, phi))
                        + f"\nline fit rms {r['rms']:.1f} deg")
            else:
                ph0, slope = find_lin_phase(list(hc))
                phase1, text = ph0, 'Kazan3 min. imaginary fit'
            # rotation of harmonic h = phase1 + slope (h - 1) refers to harmonic hs[0]
            phase1 -= slope * (hs[0] - 1)
            self.PhaseSpinner.setValue(round(phase1, 2))
            self.SlopeSpinner.setValue(round(slope, 2))
            self.Reports.setPlainText(f'Phase {phase1:.2f}, Slope {slope:.2f} deg\n{text}')
            self.btnUsePhase.setChecked(True)
        except Exception as e:  # noqa: BLE001
            self.host.set('message', f'CWMH: {e}')

    # ---------------------------------------------------------------- calculate
    def calculate(self, *_):
        try:
            if not getattr(self, 'hs', None) and not self._read_source():
                return
            self._calculate()
        except Exception as e:  # noqa: BLE001 - report like a MATLAB error
            self.host.set('message', f'CWMH: {e}')

    def _trace(self, x, data, title, color=None, xlabel='', **ax):
        a = Struct(x=np.asarray(x), xlabel=xlabel, **ax)
        if color is not None:
            a.Color = color
        data = np.asarray(data)
        return KzData(y=data.reshape(len(a.x), -1) if data.ndim < 2 else data, ax=a, dsc=self.src.dsc,
                      filename=self.src.filename, title=title)

    def _calculate(self):
        mode = self.DropDown2.currentText()
        if mode == 'Power saturation':
            return self._power_saturation()
        hs, hh = self._selected()
        k = self._slice()
        n = hh.shape[1]
        field, flabel = field_axis(self.src, n)
        data = hh[:, :, k] * self._signs(hs, hh[:, :, k].real, field)[:, None]
        if mode in ('As Is', 'Harmonics 2D'):
            y = mh.debase(data.real) + (1j * mh.debase(data.imag) if self.has_q else 0)
            if mode == 'As Is':
                out = [self._trace(field, y[i], f'H{h}', COLORS[i % len(COLORS)], flabel)
                       for i, h in enumerate(hs)]
            else:
                out = [self._trace(field, y.T, 'harmonics', None, flabel,
                                   y=np.asarray(hs, float), ylabel='Harmonic, #')]
            snr = mh.harmonic_snr(data.real)
            self.Reports.setPlainText('SNR (p-p / edge rms):\n' + '  '.join(
                f"H{h} {s['snr']:.0f}" for h, s in zip(hs, snr)))
        elif mode == 'MH reconstruction':
            out = self._reconstruction(field, flabel, hs, data.real)
        else:
            out = self._joint_fit(field, flabel, hs, data.real)
        self.host.set_data('output', out)

    def _signs(self, hs, h, field) -> np.ndarray:
        """Sign factor of each harmonic from the Signs selection (Auto: H2 vs H1)."""
        kind = self.ddSigns.currentData()
        note = ''
        if kind == 'auto':
            bm = self.sbBm.value()
            kind, c = mh.auto_signs(h, field, bm if bm > 0 else 0.1, hs)
            note = (f'auto: {"alternate" if kind == "alt" else "as recorded"}'
                    + (f' (H2/model {c[1]:+.2f})' if np.isfinite(c[1]) else ' (needs H1, H2)'))
        self.signs = kind
        self.lSigns.setText(note)
        return mh.sign_pattern(hs, kind)

    def _reconstruction(self, field, flabel, hs, h):
        bm, bm_out = self.sbBm.value(), self.sbBmOut.value()
        if bm <= 0:
            raise ValueError('set Bm (true G peak-to-peak)')
        r = mh.reconstruct(h, field, bm, hs, mu=self.sbMu.value(), bm_out=bm_out or None)
        show = self.ddShow.currentData()
        h1 = [i for i, hh in enumerate(hs) if hh == 1]
        if show == 'abs':
            out = [self._trace(field, r['S'], 'MH absorption', 'b', flabel)]
        elif show == 'd1':
            out = [self._trace(field, r['d1'], f"pseudo H1, Bm {r['bm_out']:g} G", 'r', flabel)]
        elif show == 'cmp':
            out = [self._trace(field, r['d1'], f"pseudo H1, Bm {r['bm_out']:g} G", 'r', flabel)]
            if h1:
                out.insert(0, self._trace(field, r['data'][h1[0]], f'measured H1, Bm {bm:g} G', 'b', flabel))
        else:
            ys = np.asarray(hs, float)
            out = [self._trace(field, r['data'].T, 'harmonics', 'b', flabel, y=ys, ylabel='Harmonic, #'),
                   self._trace(field, r['model'].T, 'model', 'r', flabel, y=ys, ylabel='Harmonic, #')]
        res = mh.resolution(bm, hs)
        d1 = mh.snr_pp(r['d1'])
        lines = [f"absorption SNR {mh.snr_peak(r['S'])['snr']:.0f}; pseudo H1 (Bm {r['bm_out']:g} G) "
                 f"SNR {d1['snr']:.0f}, p-p {d1['pp']:.4g}",
                 f"band limit: lines narrower than HWHM {res['w_min'] * 1e3:.1f} mG are smoothed",
                 'harmonic  SNR  weight  resid/sigma  data/H1-model']
        snr = mh.harmonic_snr(h)
        scale = mh.harmonic_scales(h, field, bm, hs)
        for i, hh in enumerate(hs):
            lines.append(f"H{hh:<3d} {snr[i]['snr']:7.1f} {r['w'][i]:7.3f} {r['resid'][i] / r['sigma'][i]:8.2f}"
                         f"     {scale[i]:+7.2f}")
        lines.append('data/H1-model: each harmonic against the one predicted from H1 alone; '
                     '~+1 is right, <0 inverted, <1 phase or Bm off (meaningless at low SNR)')
        if self.signs == 'alt':
            lines.append('signs: every second harmonic flipped (lock-in phase slope 180 deg off)')
        if h1:
            lines.insert(1, f"measured H1 SNR {snr[h1[0]]['snr']:.0f} (at Bm {bm:g} G)")
        bad = [hh for i, hh in enumerate(hs) if r['resid'][i] / r['sigma'][i] > 1.5]
        if bad:
            lines.append('WARNING: resid/sigma > 1.5 for ' + ', '.join(f'H{x}' for x in bad)
                         + ': Bm, the harmonic phases or the field axis do not match the data')
        if not self.has_q:
            lines.append('I only: the harmonic phases must be right on the instrument '
                         '(a wrong phase scales or flips a harmonic)')
        self.Reports.setPlainText('\n'.join(lines))
        return out

    def _joint_fit(self, field, flabel, hs, h):
        bm0 = self.sbBm.value()
        if bm0 <= 0:
            raise ValueError('set Bm (start value, G peak-to-peak)')
        self.host.set('message', 'CWMH: joint fit ...')
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            r = mh.fit_harmonics(h, field, hs, bm0, gauss=self.cbGauss.isChecked())
        finally:
            QApplication.restoreOverrideCursor()
        warn = []
        if r['Bm'] < 2 * r['dBpp']:
            warn.append(f"Bm < 2 dBpp: Bm is not defined by the harmonics (use Bm >= 2 dBpp)")
        if r['chi2'] > 3:
            warn.append('chi2 > 3: one line does not describe the data (several lines? '
                        'harmonic phases? Bm above the band limit?)')
        ys = np.asarray(hs, float)
        out = [self._trace(field, r['data'].T, 'harmonics', 'b', flabel, y=ys, ylabel='Harmonic, #'),
               self._trace(field, r['model'].T, 'joint fit', 'r', flabel, y=ys, ylabel='Harmonic, #')]
        self.Reports.setPlainText('\n'.join([
            f"B0 {r['B0']:.4f} G   dBpp {r['dBpp'] * 1e3:.1f} mG",
            f"Lorentz HWHM {r['gamma'] * 1e3:.1f} mG   Gauss sd {r['sigma'] * 1e3:.1f} mG",
            f"Bm {r['Bm']:.4f} +- {r['Bm_err']:.4f} G  (set {bm0:g} G, ratio {r['Bm'] / bm0:.4f})",
            f"chi2/dof {r['chi2']:.2f}",
            'resid/sigma: ' + '  '.join(f'H{hh} {v:.2f}' for hh, v in zip(hs, r['resid_sigma']))]
            + ['WARNING: ' + x for x in warn]))
        return out

    def _power_saturation(self):
        hs, hh = self._selected()
        y = hh[0].real                       # first selected harmonic, every slice
        att = -np.ravel(self.src.ax.get('y', np.zeros(y.shape[1])))   # ax.y: attenuation, dB
        if att.size != y.shape[1] or y.shape[1] < 3:
            raise ValueError('power saturation needs slices with the attenuation in ax.y')
        amp = np.ptp(mh.debase(y.T), axis=1)
        order = np.argsort(att)
        att, amp = att[order], amp[order]
        xfit, fit = saturation_fit(att, amp)
        px = dict(xlabel='Power, dBm')
        out = [self._trace(att + P_REF, 20 * np.log10(amp), f'H{hs[0]} p-p', 'r', **px),
               self._trace(att + P_REF, 20 * np.log10(fit), 'fit', 'g', **px)]
        ps = abs(xfit[1])
        self.Reports.setPlainText(
            f'Pref={P_REF:.1f}dBm\nPs={ps * 1e3:.1f}mW ({10 * np.log10(ps * 1e3):.1f}dBm) '
            f'e={min(max(xfit[2], 0.5), 1.5):.3f}')
        self.host.set_data('output', out)
