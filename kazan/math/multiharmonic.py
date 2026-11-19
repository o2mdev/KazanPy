"""Multiharmonic CW EPR: reconstruction of the absorption from field-modulation harmonics,
joint line fit over all harmonics, harmonic phases.

From the SpecMan *multiharmonic* skill (``multiharmonic.py``), data-only: no SpecMan or
file access here; the harmonics come in as arrays.

Lock-in convention (FeMi LIN1 / FEMICWRS boards): the field is B + (Bm/2) cos(theta) and
harmonic h is the cos(h theta) Fourier coefficient,
    H_h(B) = (2/pi) int_0^pi S(B + a cos t) cos(h t) dt,     a = Bm/2.
Along the field, in the Fourier domain (Jacobi-Anger),
    H^_h(k) = G_h(k) S^(k),     G_h(k) = 2 i^h J_h(k a)
(Kalin, Gromov, Schweiger, J. Magn. Reson. 160, 166 (2003)): every harmonic sees the same
absorption through its own Bessel window. ``reconstruct`` combines them per k by
noise-weighted least squares with a Tikhonov term (all J_h vanish at k -> 0: the area of
the absorption is not measured and comes from the edges).
"""
from __future__ import annotations

import numpy as np
from scipy.special import jv

SNR_EDGE = 0.15                 # baseline: first and last 15 % of the points


# ---------------------------------------------------------------- baseline, noise, SNR
def edge_mask(n: int, edge: float = SNR_EDGE) -> np.ndarray:
    m = np.zeros(n, bool)
    e = max(2, int(round(edge * n)))
    m[:e] = m[-e:] = True
    return m


def debase(y, edge: float = SNR_EDGE) -> np.ndarray:
    """Remove a straight line fitted to the edges (last axis)."""
    y = np.asarray(y, float)
    x = np.arange(y.shape[-1])
    m = edge_mask(y.shape[-1], edge)
    a = np.vstack([np.ones(m.sum()), x[m]]).T
    flat = y.reshape(-1, y.shape[-1])
    coef = np.linalg.lstsq(a, flat[:, m].T, rcond=None)[0]
    return (flat - (coef[0][:, None] + coef[1][:, None] * x)).reshape(y.shape)


def noise(h, edge: float = SNR_EDGE) -> np.ndarray:
    """rms of each trace on its edges after a straight-line baseline (last axis)."""
    return debase(h, edge)[..., edge_mask(np.shape(h)[-1], edge)].std(axis=-1)


def snr_pp(y, edge: float = SNR_EDGE) -> dict:
    """Peak-to-peak / rms of the 15 % edges (each edge minus its own mean)."""
    y = np.asarray(y, float)
    e = max(2, int(round(edge * y.size)))
    left, right = y[:e] - y[:e].mean(), y[-e:] - y[-e:].mean()
    rms = np.sqrt(np.mean(np.concatenate([left, right]) ** 2))
    return {'pp': float(np.ptp(y)), 'rms': float(rms), 'snr': float(np.ptp(y) / rms) if rms else np.inf}


def snr_peak(s, edge: float = SNR_EDGE) -> dict:
    """Absorption SNR: maximum above the edge baseline / rms of the edges."""
    s = debase(s, edge)
    rms = s[edge_mask(s.size, edge)].std()
    return {'peak': float(s.max()), 'rms': float(rms), 'snr': float(s.max() / rms) if rms else np.inf}


def harmonic_snr(h, edge: float = SNR_EDGE) -> list[dict]:
    """Per-harmonic p-p / edge rms after a straight-line baseline."""
    return [snr_pp(y, edge) for y in debase(h, edge)]


# ---------------------------------------------------------------- model
def kernel(k, a, h):
    """G_h(k) = 2 i^h J_h(k a): transfer from the absorption to harmonic h (a = Bm/2)."""
    return 2.0 * (1j ** h) * jv(h, k * a)


def _k(n: int, step: float) -> np.ndarray:
    return 2 * np.pi * np.fft.fftfreq(n, step)


def forward(s, step: float, bm: float, hs, pad: float = 2) -> np.ndarray:
    """Harmonics (n_h, N) of an absorption s sampled at ``step`` G, zero outside the trace."""
    s = np.asarray(s, float)
    n = s.size
    npad = int(pad * n)
    k = _k(npad, step)
    sf = np.fft.fft(s, npad)
    return np.array([np.fft.ifft(kernel(k, bm / 2, h) * sf).real[:n] for h in hs])


def pseudo_mod(s, step: float, bm: float, h: int = 1, pad: float = 2) -> np.ndarray:
    """Harmonic h of the absorption s at modulation bm (G p-p), without overmodulation noise."""
    return forward(s, step, bm, [h], pad)[0]


def lorentz_abs(b, b0, w, amp=1.0):
    """Lorentzian absorption, HWHM w, peak amp."""
    return amp / (1 + ((np.asarray(b) - b0) / w) ** 2)


def simulate(b, bm, hs, b0=0.0, w=0.05, amp=1.0, sigma=0.0, seed=None):
    """Harmonics of a Lorentzian absorption plus white noise sigma on every harmonic."""
    b = np.asarray(b, float)
    s = lorentz_abs(b, b0, w, amp)
    h = forward(s, b[1] - b[0], bm, hs, pad=4)
    if sigma:
        h = h + np.random.default_rng(seed).normal(0, sigma, h.shape)
    return s, h


# ---------------------------------------------------------------- reconstruction
def band_window(k, a, zcut, taper=3.0):
    """1 for |k| a <= zcut, cos^2 roll-off to 0 at zcut + taper (z = |k| a)."""
    z = np.abs(k) * a
    x = np.clip((z - zcut) / taper, 0, 1)
    return np.cos(0.5 * np.pi * x) ** 2


def resolution(bm: float, hs, taper: float = 3.0) -> dict:
    """Band limit: k_max (rad/G) at the window's half point and the narrowest Lorentzian
    HWHM rendered within ~1 %."""
    kmax = (max(hs) + taper / 2) / (bm / 2)
    return {'kmax': kmax, 'w_min': 4.6 / kmax}


def bm_max(w: float, hs, taper: float = 3.0) -> float:
    """Largest Bm (G p-p) whose reconstruction still renders a Lorentzian of HWHM w (~1 %)."""
    return 2 * (max(hs) + taper / 2) * w / 4.6


def reconstruct(h, field, bm: float, hs, sigma=None, mu: float = 1e-3, pad: float = 2,
                edge: float = SNR_EDGE, bm_out: float | None = None, zcut=None,
                taper: float = 3.0) -> dict:
    """Absorption from harmonics by noise-weighted Tikhonov least squares (Kalin 2003):
        S^(k) = W(k) sum_h w_h conj(G_h) H^_h / (sum_h w_h |G_h|^2 + lambda),  w_h = 1/sigma_h^2,
    lambda = mu max_k sum_h w_h |G_h|^2. ``h`` (n_h, N), ``field`` (N) G, ``bm`` G p-p (the
    true field), ``hs`` harmonic numbers. W is the band window at z = k a = max(hs). Each
    harmonic is debased on the edges: the absorption must vanish there. ``bm_out``: Bm of
    the pseudo 1st harmonic ``d1`` (default bm/10).
    Returns S, d1, model, residual rms and noise per harmonic, weights."""
    h = np.atleast_2d(np.asarray(h, float))
    b = np.asarray(field, float)
    step = b[1] - b[0]
    n = b.size
    if len(hs) != h.shape[0]:
        raise ValueError(f'{len(hs)} harmonics named, {h.shape[0]} traces')
    hd = debase(h, edge)
    sig = noise(h, edge) if sigma is None else np.broadcast_to(np.asarray(sigma, float), (len(hs),))
    sig = np.where(sig > 0, sig, sig[sig > 0].min() if np.any(sig > 0) else 1.0)
    w = 1 / sig ** 2
    npad = int(pad * n)
    k = _k(npad, step)
    g = np.array([kernel(k, bm / 2, hh) for hh in hs])
    hf = np.fft.fft(hd, npad, axis=-1)
    num = (w[:, None] * np.conj(g) * hf).sum(0)
    den = (w[:, None] * np.abs(g) ** 2).sum(0)
    lam = mu * den.max()
    win = band_window(k, bm / 2, max(hs) if zcut is None else zcut, taper)
    s = debase(np.fft.ifft(win * num / (den + lam)).real[:n], edge)
    model = forward(s, step, bm, hs, pad)
    resid = (hd - model)[:, ~edge_mask(n, edge)].std(axis=1)
    bm1 = bm / 10 if bm_out is None else bm_out
    return {'S': s, 'd1': pseudo_mod(s, step, bm1, 1, pad), 'bm_out': bm1, 'model': model,
            'data': hd, 'resid': resid, 'sigma': sig, 'w': w / w.sum(), 'mu': mu}


# ---------------------------------------------------------------- joint line fit
_KERNELS: dict = {}


def _kernels(n2: int, step: float, bm: float, hs) -> np.ndarray:
    """G_h(k) on the non-negative frequencies of a 2N real FFT, cached per Bm (a fit
    changes Bm in one Jacobian column only; the Bessel functions dominate the cost)."""
    key = (n2, float(step), float(bm), tuple(hs))
    g = _KERNELS.get(key)
    if g is None:
        if len(_KERNELS) > 64:
            _KERNELS.clear()
        k = 2 * np.pi * np.fft.rfftfreq(n2, step)
        g = _KERNELS[key] = np.array([kernel(k, bm / 2, hh) for hh in hs])
    return g


def voigt_harmonics(b, hs, b0, gamma, sigma, area, bm) -> np.ndarray:
    """Harmonics (n_h, N) of a Voigt absorption (Lorentz HWHM gamma, Gauss sd sigma,
    integral ``area``) at modulation bm, analytically in the Fourier domain."""
    b = np.asarray(b, float)
    n, step = b.size, b[1] - b[0]
    k = 2 * np.pi * np.fft.rfftfreq(2 * n, step)
    arg = np.minimum(gamma * k + 0.5 * (sigma * k) ** 2, 700.0)     # no overflow for wild trials
    env = area * np.exp(-arg - 1j * k * (b0 - b[0]))
    return np.fft.irfft(_kernels(2 * n, step, bm, hs) * env, 2 * n, axis=-1)[:, :n] / step


def fit_harmonics(h, field, hs, bm0: float, sigma_n=None, edge: float = SNR_EDGE,
                  gauss: bool = True, window: float | None = None) -> dict:
    """Least-squares fit of one Voigt (or Lorentzian, ``gauss=False``) line to all harmonics
    at once, Bm free. The harmonic ratios fix Bm independently of the line shape. Each
    harmonic is weighted by 1/its edge noise; only |B - B0| < window (default bm0 + 1 G) is
    fitted. Returns B0, gamma, sigma, area, Bm (+ error), dBpp, chi2/dof, residual/sigma per
    harmonic and the model."""
    from scipy.optimize import least_squares
    h = np.atleast_2d(np.asarray(h, float))
    b = np.asarray(field, float)
    hd = debase(h, edge)
    sig = noise(h, edge) if sigma_n is None else np.asarray(sigma_n, float)
    sig = np.where(sig > 0, sig, 1.0)
    b0s = b[np.argmax(np.abs(np.cumsum(hd[0])))]
    win = (bm0 + 1.0) if window is None else window
    sel = np.abs(b - b0s) < win

    # parameters: B0, ln gamma, [ln sigma], area, Bm  (no Gaussian width for a Lorentzian)
    def unpack(p):
        lw = np.exp(np.clip(p[1:3] if gauss else p[1:2], -30.0, 10.0))   # widths, no overflow
        if gauss:
            return p[0], lw[0], lw[1], p[3], p[4]
        return p[0], lw[0], 0.0, p[2], p[3]

    def model(p):
        return debase(voigt_harmonics(b, hs, *unpack(p)), edge)

    def resid(p):
        return ((model(p) - hd)[:, sel] / sig[:, None]).ravel()

    starts = []
    for g0 in (0.02, 0.05, 0.2):
        p0 = [b0s, np.log(g0)] + ([np.log(0.03)] if gauss else []) + [1.0, bm0]
        p0[-2] = np.ptp(hd[0]) / (np.ptp(model(p0)[0]) or 1)     # amplitude matched to H1
        starts.append((float(np.sum(resid(p0) ** 2)), p0))
    best = None
    for _, p0 in sorted(starts, key=lambda s: s[0])[:2]:        # optimise from the 2 best starts
        try:
            r = least_squares(resid, p0, x_scale='jac', max_nfev=150)
        except ValueError:
            continue
        if best is None or r.cost < best.cost:
            best = r
    if best is None:
        raise ValueError('the joint fit did not converge')
    p = best.x
    dof = max(1, best.fun.size - p.size)
    chi2 = 2 * best.cost / dof
    try:
        err = np.sqrt(np.diag(np.linalg.inv(best.jac.T @ best.jac) * chi2))
    except np.linalg.LinAlgError:
        err = np.full(p.size, np.nan)
    b0, gamma, sg, area, bm = unpack(p)
    m = model(p)
    x = np.linspace(-1, 1, 20001) * max(10 * (gamma + sg), 0.05)
    k = 2 * np.pi * np.fft.fftfreq(x.size, x[1] - x[0])
    s = np.fft.ifft(np.exp(-gamma * np.abs(k) - 0.5 * (sg * k) ** 2) * np.exp(-1j * k * x[0])).real
    ds = np.gradient(s, x)
    dbpp = abs(x[np.argmax(ds)] - x[np.argmin(ds)])
    rh = ((m - hd)[:, sel]).std(axis=1) / sig
    return {'B0': b0, 'gamma': gamma, 'sigma': sg, 'area': area, 'Bm': bm, 'Bm_err': err[-1],
            'dBpp': dbpp, 'chi2': chi2, 'resid_sigma': rh, 'model': m, 'data': hd, 'sel': sel,
            'converged': bool(best.success)}


# ---------------------------------------------------------------- harmonic phases (need I and Q)
def harmonic_phase_offsets(hc, edge: float = SNR_EDGE) -> np.ndarray:
    """Per-harmonic phase (deg, mod 180) of complex harmonics I + jQ (n_h, N): the rotation
    that puts the signal into I (principal axis)."""
    hc = np.atleast_2d(hc)
    i, q = debase(hc.real, edge), debase(hc.imag, edge)
    out = []
    for a, c in zip(i, q):
        sxx, syy, sxy = (a * a).sum(), (c * c).sum(), (a * c).sum()
        out.append(0.5 * np.degrees(np.arctan2(2 * sxy, sxx - syy)))
    return np.array(out)


def fit_phase_line(hs, phi, weights=None) -> dict:
    """Fit phi_h = c + h p (mod 180). Returns the phase of harmonic 1 (c + p, the
    ModPhase-like constant) and the slope p per harmonic (ModPhSlope-like), rms, residuals.
    weights: e.g. SNR^2 per harmonic."""
    hs, phi = np.asarray(hs, float), np.asarray(phi, float)
    wt = np.ones_like(phi) if weights is None else np.asarray(weights, float)
    best = None
    for p in np.arange(-90, 90, 0.05):
        r = (phi - p * hs + 90) % 180 - 90
        c = np.degrees(np.angle((wt * np.exp(2j * np.radians(r))).sum())) / 2
        e = (r - c + 90) % 180 - 90
        cost = (wt * e ** 2).sum()
        if best is None or cost < best[0]:
            best = (cost, c, p, e)
    _, c, p, e = best
    return {'phase1': float(c + p), 'slope': float(p), 'rms': float(np.sqrt((e ** 2).mean())),
            'residual': e}
