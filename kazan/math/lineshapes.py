"""Area-normalized EPR line shapes (EasySpin conventions, written from the analytic forms).

``diff=0`` absorption, ``diff=1`` first derivative. Widths are FWHM.
"""
from __future__ import annotations

import numpy as np
from scipy.special import wofz

_LN2 = np.log(2.0)


def gaussian(x, x0, fwhm, diff=0):
    x = np.asarray(x, float)
    s = fwhm / (2 * np.sqrt(2 * _LN2))
    g = np.exp(-0.5 * ((x - x0) / s) ** 2) / (s * np.sqrt(2 * np.pi))
    return g if diff == 0 else -(x - x0) / s ** 2 * g


def lorentzian(x, x0, fwhm, diff=0):
    x = np.asarray(x, float)
    gam = fwhm / 2
    d = (x - x0) ** 2 + gam ** 2
    return gam / np.pi / d if diff == 0 else -2 * gam * (x - x0) / np.pi / d ** 2


def lshape(x, x0, fwhm, diff=0, alpha=1.0):
    """EasySpin ``lshape``: ``alpha*Gaussian + (1-alpha)*Lorentzian`` (default Gaussian)."""
    fw = np.atleast_1d(np.asarray(fwhm, float))
    fg, fl = (fw[0], fw[0]) if fw.size == 1 else (fw[0], fw[1])
    y = 0.0
    if alpha != 0:
        y = y + alpha * gaussian(x, x0, fg, diff)
    if alpha != 1:
        y = y + (1 - alpha) * lorentzian(x, x0, fl, diff)
    return y


def voigtian(x, x0, fwhm, diff=0):
    """Convolution of a Gaussian and a Lorentzian, ``fwhm = [fwhmGauss, fwhmLorentz]``."""
    fg, fl = (abs(float(v)) for v in fwhm)
    if fg == 0:
        return lorentzian(x, x0, fl, diff)
    if fl == 0:
        return gaussian(x, x0, fg, diff)
    x = np.asarray(x, float)
    s = fg / (2 * np.sqrt(2 * _LN2))
    z = ((x - x0) + 1j * fl / 2) / (s * np.sqrt(2))
    w = wofz(z)
    norm = s * np.sqrt(2 * np.pi)
    if diff == 0:
        return w.real / norm
    dw = -2 * z * w + 2j / np.sqrt(np.pi)
    return dw.real / norm / (s * np.sqrt(2))
