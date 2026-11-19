"""Display processing: port of ``kazan3.Process`` (ax.filt, ax.diff, ax.s).

Filters (ax.filt): rc, mvgaver (binomial), savgol; derivative (ax.diff): psmod
(pseudo-modulation), integrate; shift ax.s. EasySpin's ``rcfilt`` and ``fieldmod``
are re-implemented here (the EasySpin copies are p-coded).
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import convolve1d
from scipy.signal import lfilter, savgol_filter
from scipy.special import jv

from .data import KzData


def _per_part(f, y: np.ndarray) -> np.ndarray:
    """Apply a real filter to real and imaginary parts separately."""
    if np.iscomplexobj(y):
        return f(y.real) + 1j * f(y.imag)
    return f(y)


def _binomial_kernel(n: int) -> np.ndarray:
    k = np.array([1.0])
    for _ in range(max(n, 1) - 1):
        k = np.convolve(k, [1.0, 1.0])
    return k / k.sum()


def _dims(d: KzData) -> tuple[bool, bool]:
    fpar = str(d.ax.get('filtpar1', 'auto'))
    if fpar == 'auto':
        return True, d.y.shape[1] > 5
    return '1D' in fpar or fpar == 'both', '2D' in fpar or fpar == 'both'


def rcfilt(y: np.ndarray, samp_time: float, time_const: float) -> np.ndarray:
    """EasySpin ``rcfilt``: RC low-pass filter along the first dimension,
    ``y_k = e y_(k-1) + (1-e) x_k`` with ``e = exp(-samp_time / time_const)``."""
    if time_const <= 0:
        return y
    e = np.exp(-samp_time / time_const)
    return _per_part(lambda a: lfilter([1 - e], [1, -e], a, axis=0), y)


def fieldmod(x: np.ndarray, y: np.ndarray, mod_ampl: float, harmonic: int = 1) -> np.ndarray:
    """EasySpin ``fieldmod``: pseudo-modulation of an absorption spectrum with
    peak-to-peak amplitude ``mod_ampl`` (x units); ``harmonic`` of the lock-in signal.
    Small amplitudes give the derivative times ``mod_ampl / 2``."""
    y = np.asarray(y, float)
    n = len(y)
    if n < 2 or mod_ampl <= 0:
        return y
    dx = x[1] - x[0]
    f = np.fft.fftfreq(2 * n, dx)                       # zero-padded, 1/x units
    s = 2 * (1j) ** harmonic * jv(harmonic, 2 * np.pi * (mod_ampl / 2) * f)
    return np.real(np.fft.ifft(np.fft.fft(y, 2 * n) * s))[:n]


def process(d: KzData) -> tuple[KzData, list[str]]:
    """Return processed data (modifies ``d``) and a list of warnings."""
    warnings: list[str] = []
    if d.is_empty:
        return d, warnings
    y = d.y.astype(complex if np.iscomplexobj(d.y) else float)
    filt = d.ax.get('filt') or 'none'
    tc = int(float(d.ax.get('tc', 5)))

    if filt == 'mvgaver':
        fx, fy = _dims(d)
        k = _binomial_kernel(tc)
        if fx:
            y = _per_part(lambda a: convolve1d(a, k, axis=0, mode='nearest'), y)
        if fy:
            y = _per_part(lambda a: convolve1d(a, k, axis=1, mode='nearest'), y)
    elif filt == 'savgol':
        fx, fy = _dims(d)
        pol = int(float(d.ax.get('pol', 2)))
        win = tc if tc % 2 else tc + 1
        if fx and y.shape[0] > win:
            y = _per_part(lambda a: savgol_filter(a, win, min(pol, win - 1), axis=0), y)
        if fy and y.shape[1] > win:
            y = _per_part(lambda a: savgol_filter(a, win, min(pol, win - 1), axis=1), y)
    elif filt == 'rc':
        y = rcfilt(y, 1, float(d.ax.get('tc', 5)))

    diff = d.ax.get('diff') or 'normal'
    if diff == 'integrate':
        x = d.ax.x
        dx = (x[1] - x[0]) if len(x) > 1 else 1.0
        y = np.cumsum(y - y.mean(axis=0, keepdims=True), axis=0) * dx / 2
    elif diff == 'psmod':
        amp = float(d.ax.get('ps_mod', 5) or 0)
        bl = np.concatenate([y[:4], y[-4:]]).sum(axis=0) / 8
        pts = np.arange(1.0, y.shape[0] + 1)
        y = np.column_stack([fieldmod(pts, np.real(y[:, k] - bl[k]), amp)
                             for k in range(y.shape[1])])

    d.y = y + float(d.ax.get('s', 0) or 0)
    d.ax.filt = ''
    d.ax.diff = ''
    return d, warnings
