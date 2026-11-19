"""Sinusoidal rapid-scan deconvolution: port of ``sinDecoBG.m`` (M. Tseytlin, University
of Denver, version 2014_2) and its helpers ``InterleavingCycles``, ``fftM``,
``H_amplit``, ``mygaussian``, ``zeroLine``, ``min_max``, plus MATLAB ``interpft``.

MATLAB indexing / rounding conventions are kept (``conv(...,'same')`` centring,
round-half-away-from-zero), so the results match the MATLAB code point by point.
"""
from __future__ import annotations

import numpy as np

GAMMA = 1.7608e7            # rad/(s G)
G2F = GAMMA / (2 * np.pi)   # Hz/G


def mround(x):
    """MATLAB round (half away from zero)."""
    return np.sign(x) * np.floor(np.abs(x) + 0.5)


def fft_m(t, a):
    """``fftM``: centred spectrum and its frequency axis."""
    dt = t[1] - t[0] if np.size(t) > 1 else float(np.ravel(t)[0])
    n = len(a)
    w = (np.arange(n) - n / 2) / (dt * n)
    return w, np.fft.fftshift(np.fft.fft(a))


def conv_same(a, k):
    """MATLAB ``conv(a, k, 'same')``."""
    full = np.convolve(a, k)
    start = len(k) // 2
    return full[start:start + len(a)]


def mygaussian(h, fwhm):
    """Area-normalised Gaussian of full width at half height ``fwhm``."""
    hpp = fwhm / np.sqrt(2 * np.log(2))
    return np.sqrt(2 / np.pi) / hpp * np.exp(-2 * (h / hpp) ** 2)


def zero_line(spectrum, extent):
    """``zeroLine``: subtract the straight line through the mean of both edges."""
    n = len(spectrum)
    edge = int(mround(extent * n)) or 1
    left = spectrum[:edge].sum() / edge
    right = spectrum[n - edge:].sum() / edge
    return spectrum - (left + (right - left) / n * np.arange(1, n + 1))


def interpft(x, ny):
    """MATLAB ``interpft`` (FFT interpolation to ``ny`` points)."""
    m = len(x)
    a = np.fft.fft(x)
    nyq = int(np.ceil((m + 1) / 2))
    b = np.concatenate([a[:nyq], np.zeros(ny - m, complex), a[nyq:]])
    if m % 2 == 0:
        b[nyq - 1] /= 2
        b[nyq - 1 + ny - m] = b[nyq - 1]
    y = np.fft.ifft(b)
    if np.isrealobj(x):
        y = y.real
    return y * ny / m


def min_max(h, a):
    """``min_max``: field of the centre between the minimum and the maximum."""
    return (h[np.argmin(a)] + h[np.argmax(a)]) / 2


def h_amplit(xi, yi, fm):
    """``H_amplit``: background ``[sin x, sin 2x, cos x, cos 2x, const]`` from one half
    cycle, separating its symmetric and antisymmetric parts."""
    t = 2 * np.pi * fm * xi
    fs = (yi + yi[::-1]) / 2
    fa = (yi - yi[::-1]) / 2
    vs = np.array([np.sin(t), np.cos(2 * t), np.ones_like(t)])
    xs = np.linalg.solve(vs @ vs.T, vs @ fs)
    va = np.array([np.sin(2 * t), np.cos(t)])
    xa = np.linalg.solve(va @ va.T, va @ fa)
    return np.array([xs[0], xa[0], xa[1], xs[1], xs[2]])


def _background(t, part, fm, x):
    r = h_amplit(t, part, fm)
    return (r[0] * np.sin(x) + r[1] * np.sin(2 * x) + r[2] * np.cos(x)
            + r[3] * np.cos(2 * x) + r[4])


def interleaving_cycles(t, ts, rs, scan_freq, nfc, ns, wm, method='fast'):
    """``InterleavingCycles``: average all full cycles onto ``ns`` points of one."""
    p = 1 / scan_freq
    tb = t[1]
    sel = t < nfc * p
    k = np.arange(-ns // 2, ns // 2)
    rs_i, t_i = rs[sel], t[sel]
    m = len(rs_i)
    if method == 'slow':
        spec = np.array([rs_i @ np.exp(-1j * kk * wm * t_i).conj() for kk in k])
        return np.fft.fft(np.fft.fftshift(spec)) * tb / ts[1] / nfc / ns
    v, spec = fft_m(t_i, np.concatenate([rs_i, rs_i]))
    spec_i = np.interp(k / p, v, spec, left=0, right=0)
    return np.fft.ifft(np.fft.fftshift(spec_i)) / m * ns / 2


def sin_deco_bg(rs, dt, hm, vm, up=1, ph=0.0, fp=0.0, fwhm=None, n_iter=2, method='fast'):
    """Deconvolve a sinusoidal rapid-scan signal (``sinDecoBG``).

    rs     complex signal with at least one full scan cycle
    dt     sampling period [s];  hm  peak-to-peak scan amplitude [G];  vm  scan frequency [Hz]
    up     1 if the first half-scan goes up, -1 for down
    ph     RF phase correction [deg];  fp  first point of the cycle [deg, 0..360]
    fwhm   narrowest expected line [G] (post-filter width fwhm/10); default hm/25
    n_iter >1 estimates the scan phase (fp) correction iteratively

    Returns ``h, A, B, fp_corr_total, rs_out, bg_out, out``; ``A``/``B`` are the up/down
    spectra on field ``h`` [G], ``out`` holds the intermediate cycles ``rs_i``,
    ``rs_ii``, ``rs_iii``.
    """
    fwhm = hm / 25 if fwhm is None else fwhm
    rs0 = np.ravel(np.asarray(rs)).astype(complex)
    fp_corr_total = 0.0
    out = {}
    for _ in range(max(int(n_iter), 1)):
        m = len(rs0)
        t = np.arange(m) * dt
        vmax = G2F * hm
        ns = int(2 * np.ceil(vmax / vm))
        p = 1 / vm
        ts = np.arange(ns) * (p / ns)
        wm = 2 * np.pi * vm
        nc = int(mround(1 / (dt * vm)))
        nfc = m // nc
        if nfc == 0:
            raise ValueError('RS signal must have at least one full cycle')

        rs_i = interleaving_cycles(t, ts, rs0, vm, nfc, ns, wm, method)
        rs_ii = rs_i * np.exp(1j * ph / 180 * np.pi)
        rs_iii = np.roll(rs_ii, int(mround(fp / 360 * len(rs_ii))))
        out = {'rs_i': rs_i, 'rs_ii': rs_ii, 'rs_iii': rs_iii}
        rs_out = rs_iii

        # driving function over one cycle
        t, tb = ts, ts[1]
        w = GAMMA * hm / 2 * (-up * np.cos(2 * np.pi * vm * t))
        dr = np.exp(-1j * np.cumsum(w) * tb)

        # separate up from down scan
        v, spec = fft_m(t, rs_iii)
        pos, neg = (v > 0, v < 0) if up > 0 else (v < 0, v > 0)
        a = np.fft.ifft(np.fft.ifftshift(spec * pos))
        b = np.fft.ifft(np.fft.ifftshift(spec * neg))
        half = ns // 2
        aa, bb, bga, bgb = a[:half], b[half:], a[half:], b[:half]
        t1, t2 = t[:half], t[half:]

        # background removal: each half from the other half's background
        x1, x2 = 2 * np.pi * vm * t1, 2 * np.pi * vm * t2
        bg_a = _background(t2, bga.real, vm, x1) + 1j * _background(t2, bga.imag, vm, x1)
        bg_b = _background(t1, bgb.real, vm, x2) + 1j * _background(t1, bgb.imag, vm, x2)
        aaa, bbb = aa - bg_a, bb - bg_b
        bg_out = rs_iii - np.concatenate([aaa, bbb])

        # deconvolution
        dr_a, dr_b = dr[:half], dr[half:]
        v, spec_a = fft_m(t, aaa * dr_a)
        _, d_a = fft_m(t, dr_a)
        _, spec_b = fft_m(t, bbb * dr_b)
        _, d_b = fft_m(t, dr_b)
        A, B = spec_a / d_a, spec_b / d_b
        h = v * 2 * np.pi / GAMMA
        sel = np.abs(h) < hm / 2
        A, B, h = A[sel], B[sel], h[sel]

        # post-filtering
        filt = mygaussian(h, fwhm / 10)
        if filt.sum() > 0:
            filt = filt / filt.sum()
            A, B = conv_same(A, filt), conv_same(B, filt)
        A = np.imag(zero_line(A, 0.05)[::-1])
        B = np.imag(zero_line(B, 0.05)[::-1])

        # scan phase (first point) correction estimate
        if n_iter > 1:
            af, bf = interpft(A, len(A) * 4), interpft(B, len(B) * 4)
            hi = np.linspace(h[0], h[-1], len(af))
            filt_i = mygaussian(hi, fwhm)
            filt_i = filt_i / filt_i.sum()
            a1 = np.gradient(conv_same(af, filt_i))
            b1 = np.gradient(conv_same(bf, filt_i))
            mid = np.array([min_max(hi, a1), min_max(hi, b1)])
            dh = mid - mid.mean()
            fp_corr = dh / (np.pi * hm * vm) * vm * 360
            fp_corr_total += fp_corr[0]
            fp -= fp_corr[0]
    return h, A, B, fp_corr_total, rs_out, bg_out, out
