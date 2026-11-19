"""MATLAB ``fminsearch`` / ``fminsearchbnd`` (J. D'Errico) on top of SciPy Nelder-Mead.

MATLAB stops when both the simplex size (TolX) and the spread of function values
(TolFun) are small; SciPy's ``xatol`` / ``fatol`` have the same meaning.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


def fminsearch(fun, x0, max_iter=None, max_fun_evals=None, tol_x=1e-4, tol_fun=1e-4):
    """Unbounded Nelder-Mead; returns ``(x, fval)``."""
    x0 = np.asarray(x0, float)
    n = len(x0)
    res = minimize(fun, x0, method='Nelder-Mead',
                   options={'maxiter': max_iter or 200 * n, 'maxfev': max_fun_evals or 200 * n,
                            'xatol': tol_x, 'fatol': tol_fun})
    return res.x, float(res.fun)


def fminsearchbnd(fun, x0, lb, ub, **kw):
    """Nelder-Mead with bounds by the sin transform of ``fminsearchbnd``.

    Each variable with both bounds maps to ``lb + (ub - lb) (sin z + 1) / 2``; with only
    one bound to ``lb + z^2`` / ``ub - z^2``; ``lb == ub`` fixes the variable.
    Returns ``(x, fval)``.
    """
    x0 = np.asarray(x0, float)
    lb = np.asarray(lb, float)
    ub = np.asarray(ub, float)
    lo, hi = np.minimum(lb, ub), np.maximum(lb, ub)
    has_lo, has_hi = np.isfinite(lo), np.isfinite(hi)
    fixed = has_lo & has_hi & (lo == hi)

    def to_x(z):
        x = np.empty_like(x0)
        k = 0
        for i in range(len(x0)):
            if fixed[i]:
                x[i] = lo[i]
                continue
            v = z[k]
            k += 1
            if has_lo[i] and has_hi[i]:
                x[i] = min(max(lo[i] + (hi[i] - lo[i]) * (np.sin(v) + 1) / 2, lo[i]), hi[i])
            elif has_lo[i]:
                x[i] = lo[i] + v * v
            elif has_hi[i]:
                x[i] = hi[i] - v * v
            else:
                x[i] = v
        return x

    z0 = []
    for i in range(len(x0)):
        if fixed[i]:
            continue
        if has_lo[i] and has_hi[i]:
            s = 2 * (min(max(x0[i], lo[i]), hi[i]) - lo[i]) / (hi[i] - lo[i]) - 1
            z0.append(2 * np.pi + np.arcsin(min(max(s, -1.0), 1.0)))
        elif has_lo[i]:
            z0.append(np.sqrt(max(x0[i] - lo[i], 0.0)))
        elif has_hi[i]:
            z0.append(np.sqrt(max(hi[i] - x0[i], 0.0)))
        else:
            z0.append(x0[i])
    if not z0:
        return to_x(np.zeros(0)), float(fun(to_x(np.zeros(0))))
    z, fval = fminsearch(lambda z: fun(to_x(z)), z0, **kw)
    return to_x(z), fval
