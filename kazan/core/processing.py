"""Display processing: port of ``kazan3.Process`` (ax.filt, ax.diff, ax.s).

Ported: mvgaver (binomial), savgol, integrate, shift.
Not yet ported (data passes through unchanged, a warning is returned): rc, psmod.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import convolve1d
from scipy.signal import savgol_filter

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
        warnings.append('RC filter is not ported yet')

    diff = d.ax.get('diff') or 'normal'
    if diff == 'integrate':
        x = d.ax.x
        dx = (x[1] - x[0]) if len(x) > 1 else 1.0
        y = np.cumsum(y - y.mean(axis=0, keepdims=True), axis=0) * dx / 2
    elif diff == 'psmod':
        warnings.append('Pseudo-modulation is not ported yet')

    d.y = y + float(d.ax.get('s', 0) or 0)
    d.ax.filt = ''
    d.ax.diff = ''
    return d, warnings
