"""Noise plugin: port of Noise3.mlapp.

Signal amplitude, noise and signal-to-noise ratio of the source, for the real and
imaginary parts and for every extra SpecMan channel (``ax.data``). With a reference set
(*Set Reference*, same size as the source), the noise is the source minus the reference
and the signal is the reference.

* **Signal** - none, a fitted sinusoid subtracted, or a moving average.
* **Noise** - as is, a fitted sinusoid subtracted, trace 2 subtracted from every trace,
  or an FFT low-pass / high-pass filter.
* **Range** - the part of each trace used for the noise (all, or the last 95/90/80/20%).

Signal is the peak-to-peak amplitude, reported in mV; noise is the standard deviation,
reported in uV (the data are taken to be in volts).

Differences from MATLAB (see Documentation/plugins.md):
* *Mov.average x7* and *x11* were swapped.
* *Sinus fit* (signal and noise) and *- Trace2* changed copies that were not used, so
  they had no effect; they work now. The fit starts from the strongest FFT frequency
  (MATLAB assumed 5 periods per trace and needed a second trace).
* The noise uses the selected range of every trace (MATLAB used the first trace only),
  and 2D data report the mean amplitude over the traces.
* *Set Reference* / *Clear Ref* report in the text box (MATLAB wrote to a missing
  label and failed).
"""
from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QLabel, QPlainTextEdit,
                               QPushButton, QWidget)
from scipy.ndimage import uniform_filter1d
from scipy.optimize import minimize

from kazan.core import KazanPlugin

SIGNAL_OPTIONS = [('No fit', 'no_fit'), ('Sinus fit', 'sinus_fit'),
                  ('Mov.average x7', 7), ('Mov.average x11', 11), ('Mov.average x21', 21),
                  ('Mov.average x31', 31), ('Mov.average x51', 51)]
NOISE_OPTIONS = [('As is / Ref', 'as_is'), ('Sinus fit', 'sinus_fit'),
                 ('- Trace2', 'minus_trace2'), ('LP Filter 0.5', 'filter_LP_0p5'),
                 ('HP Filter 0.75', 'filter_HP_0p75')]
RANGE_OPTIONS = [('As is', 0.0), ('Last 95%', 0.05), ('Last 90%', 0.1), ('Last 80%', 0.2),
                 ('Last 20%', 0.8)]


def movmean(y, k: int):
    """MATLAB ``movmean(y, k)`` along the first dimension (shrinking window at the ends)."""
    n = y.shape[0]
    out = np.empty_like(y, dtype=float)
    lo, hi = (k - 1) // 2, k // 2
    c = np.vstack([np.zeros((1,) + y.shape[1:]), np.cumsum(y, axis=0)])
    i = np.arange(n)
    a, b = np.maximum(i - lo, 0), np.minimum(i + hi + 1, n)
    out[:] = (c[b] - c[a]) / (b - a).reshape((-1,) + (1,) * (y.ndim - 1))
    return out


def _sine(p, x):
    return p[0] * np.sin(p[1] * x + p[2]) + p[3]


def _fminsearch(y, x, p0):
    return minimize(lambda p: np.sum((y - _sine(p, x)) ** 2), p0, method='Nelder-Mead',
                    options={'maxiter': 800, 'maxfev': 800, 'xatol': 1e-4, 'fatol': 1e-4}).x


def subtract_sine(y: np.ndarray) -> np.ndarray:
    """Subtract a fitted ``a sin(w x + phi) + c`` from every column (real data)."""
    x = np.arange(1, y.shape[0] + 1, dtype=float)
    guide = y[:, 1] if y.shape[1] > 1 else y[:, 0]
    spec = np.abs(np.fft.rfft(guide - guide.mean()))
    k = int(np.argmax(spec[1:])) + 1 if len(spec) > 1 else 5
    w0 = 2 * np.pi * k / len(x)                     # dominant frequency, rad/point
    starts = [np.array([(guide.max() - guide.min()) / 2, w0, ph, guide.mean()])
              for ph in np.arange(4) * np.pi / 2]
    p0 = min((_fminsearch(guide, x, s) for s in starts),
             key=lambda p: np.sum((guide - _sine(p, x)) ** 2))
    p0 = _fminsearch(guide, x, p0)
    return np.column_stack([col - _sine(_fminsearch(col, x, p0), x) for col in y.T])


def fft_filter(y: np.ndarray, kind: str) -> np.ndarray:
    """MATLAB filter_LP_0p5 / filter_HP_0p75: zero FFT bins along the first dimension."""
    t = np.fft.fft(y, axis=0)
    sz = t.shape[0]
    if kind == 'filter_LP_0p5':
        c = int(np.floor(sz * 0.875 / 2))
        lo, hi = int(np.ceil(sz / 2 - c)), int(np.floor(sz / 2 + c))   # 1-based
        t[max(lo, 1) - 1:hi] = 0
    else:
        c = int(np.floor(sz * 0.25 / 2))
        t[:c] = 0
        t[max(sz - c, 1) - 1:] = 0
    return np.fft.ifft(t, axis=0).real


class Noise3(KazanPlugin):
    menu_name = 'NOISE3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('noiseplugin')
        self.resize(361, 316)
        self.reference = None
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(5, 5, 5, 5)
        g.setSpacing(5)
        self.cbFileUpdate = QCheckBox('Update')
        self.set_update_checkbox(self.cbFileUpdate)
        g.addWidget(self.cbFileUpdate, 0, 1)
        self.ClearRefButton = QPushButton('Clear Ref')
        self.pbSetReference = QPushButton('Set Reference')
        for c, b in enumerate((self.ClearRefButton, self.pbSetReference)):
            b.setMinimumHeight(36)
            g.addWidget(b, 1, c)
        g.addWidget(QLabel('Signal'), 2, 0)
        g.addWidget(QLabel('Noise'), 2, 1)
        self.ddFitOptions, self.ddNoiseOptions, self.ddRangeOptions = (QComboBox() for _ in range(3))
        for dd, items in ((self.ddFitOptions, SIGNAL_OPTIONS), (self.ddNoiseOptions, NOISE_OPTIONS),
                          (self.ddRangeOptions, RANGE_OPTIONS)):
            for text, data in items:
                dd.addItem(text, data)
        g.addWidget(self.ddFitOptions, 3, 0)
        g.addWidget(self.ddNoiseOptions, 3, 1)
        g.addWidget(QLabel('Range'), 4, 1)
        g.addWidget(self.ddRangeOptions, 5, 1)
        self.TextArea = QPlainTextEdit()
        self.TextArea.setReadOnly(True)
        g.addWidget(self.TextArea, 6, 0, 1, 2)
        g.setRowStretch(6, 1)
        self.pbCalculate = QPushButton('Calculate')
        self.pbCalculate.setMinimumHeight(36)
        g.addWidget(self.pbCalculate, 7, 1)

        self.pbSetReference.clicked.connect(self.set_reference)
        self.ClearRefButton.clicked.connect(self.clear_reference)
        self.pbCalculate.clicked.connect(self.calculate)

    def file_update(self):
        if self.cbFileUpdate.isChecked():
            self.calculate()

    def set_reference(self):
        self.reference = self.host.get_data('source')
        self.TextArea.setPlainText('Reference is added')

    def clear_reference(self):
        self.reference = None
        self.TextArea.setPlainText('Reference is cleared')

    def calculate(self):
        try:
            self._calculate()
        except Exception as e:  # noqa: BLE001 - report like a MATLAB error
            self.host.set('message', f'Noise: {e}')

    def _calculate(self):
        noise = self.host.get_data('source')
        ref = self.reference
        if ref is not None and ref.y.shape == noise.y.shape:
            signal = ref
            noise.y = noise.y - signal.y
        else:
            signal = noise.copy()

        extra = [np.real(np.asarray(d)).reshape(signal.y.shape[0], -1)
                 for d in (signal.ax.get('data') or [])]
        extra_noise = [np.real(np.asarray(d)).reshape(noise.y.shape[0], -1)
                       for d in (noise.ax.get('data') or [])]
        if len(extra_noise) != len(extra):
            extra_noise = extra
        stats = [{'data': signal.y.real.copy(), 'noise': noise.y.real.copy()},
                 {'data': signal.y.imag.copy(), 'noise': noise.y.imag.copy()}]
        stats += [{'data': d.copy(), 'noise': n.copy()} for d, n in zip(extra, extra_noise)]

        sig_opt = self.ddFitOptions.currentData()
        noise_opt = self.ddNoiseOptions.currentData()
        frac = self.ddRangeOptions.currentData()
        for s in stats:
            if sig_opt == 'sinus_fit':
                s['data'] = subtract_sine(s['data'])
            elif isinstance(sig_opt, int):
                s['data'] = movmean(s['data'], sig_opt)
            if noise_opt == 'sinus_fit':
                s['noise'] = subtract_sine(s['noise'])
            elif noise_opt == 'minus_trace2':
                if s['noise'].shape[1] < 2:
                    raise ValueError('- Trace2 needs 2D data')
                s['noise'] = s['noise'] - s['noise'][:, 1:2]
            elif noise_opt in ('filter_LP_0p5', 'filter_HP_0p75'):
                s['noise'] = fft_filter(s['noise'], noise_opt)
            n = s['noise'].shape[0]
            s['idx'] = slice(max(int(np.floor(n * frac)), 1) - 1, n)
            s['signal'] = float(np.mean(s['data'].max(axis=0) - s['data'].min(axis=0)))
            s['std'] = float(np.std(s['noise'][s['idx']], ddof=1))
            s['snr'] = s['signal'] / s['std'] if s['std'] else np.inf

        def row(key, scale, fmt):
            return ''.join(f' {s[key] * scale:{fmt}} |' for s in stats)
        self.TextArea.setPlainText('signal_mV=' + row('signal', 1e3, '.3f') + '\n'
                                   + 'noise_uV=' + row('std', 1e6, '.3f') + '\n'
                                   + 'snr=' + row('snr', 1, '.2f'))

        out_s = signal.copy()
        out_s.y = stats[0]['data'] + 1j * stats[1]['data']
        out_s.title, out_s.ax.Color = 'signal', 'b'
        out_n = noise.copy()
        idx = stats[1]['idx']
        out_n.y = stats[0]['noise'][idx] + 1j * stats[1]['noise'][idx]
        out_n.ax.x = np.asarray(out_n.ax.x)[idx]
        out_n.title, out_n.ax.Color = 'noise', 'r'
        for d in (out_s, out_n):
            d.ax.pop('data', None)
            d.ax.pop('raw', None)
        self.host.set_data('output', [out_s, out_n])
