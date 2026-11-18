"""Port of ``kv_autofit``: fit a small script such as ``['f = a*x + b', 'a = 0', 'b = 0']``.

Script lines:
  ``f = <expression of x and parameters>``  - the model (MATLAB syntax is accepted)
  ``name = value``                          - a parameter and its start value
  ``MaxIter = n``                           - iteration limit (default 500)
  ``FitRng ...``                            - kept as is
  ``polN = ...``                            - result lines of a previous polyfit (ignored)

``f = polyfit(x, y, n)`` / ``f = exppolyfit(x, y, n)`` fit a polynomial of order ``n``
(the first parameter); everything else is minimized with Nelder-Mead, as MATLAB
``fminsearch``. The model is evaluated with numpy; scripts are the user's own input.
"""
from __future__ import annotations

import re

import numpy as np
from scipy.optimize import minimize

from .lineshapes import gaussian, lorentzian, lshape, voigtian

_NAMESPACE = {
    'exp': np.exp, 'log': np.log, 'cos': np.cos, 'sin': np.sin, 'abs': np.abs,
    'sqrt': np.sqrt, 'pi': np.pi, 'gaussian': gaussian, 'lorentzian': lorentzian,
    'lshape': lshape, 'voigtian': voigtian,
    'kv3_lshape': lambda x, x0, fg, fl: voigtian(x, x0, [fg, fl]),
}


def matlab_to_python(expr: str) -> str:
    expr = expr.replace('.*', '*').replace('./', '/').replace('.^', '**')
    return re.sub(r'(?<!\*)\^', '**', expr)


def evaluate(expr: str, x, params: dict):
    ns = dict(_NAMESPACE)
    ns.update(params)
    ns['x'] = x
    return eval(matlab_to_python(expr), {'__builtins__': {}}, ns)


def _fmt(v: float) -> str:
    return f'{v:.5g}'


def autofit(script: list[str], x, y, rangeidx=None) -> tuple[list[str], np.ndarray]:
    """Returns the updated script and the fitted curve evaluated on all of ``x``."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    y2 = y.reshape(len(y), -1)
    idx = np.ones(len(x), bool) if rangeidx is None else np.asarray(rangeidx, bool)

    fun, keep, names, start, max_iter = None, [], [], [], 500
    for line in script:
        s = line.strip().replace('f=', 'f =', 1) if line.strip().startswith('f=') else line.strip()
        if not s:
            continue
        if s.startswith('f ='):
            fun = s
            keep.append(s)
        elif s.startswith('FitRng'):
            keep.append(s)
        elif s.startswith('MaxIter'):
            max_iter = int(float(s.split('=', 1)[1]))
        elif s.startswith('pol'):
            continue
        else:
            name, _, value = s.partition('=')
            names.append(name.strip())
            start.append(float(eval(matlab_to_python(value), {'__builtins__': {}}, dict(_NAMESPACE))))
    if fun is None:
        raise ValueError('can not find function')
    expr = fun[3:].strip()

    extra, sim = [], np.zeros((len(x), y2.shape[1]))
    if 'polyfit' in expr:
        order = int(start[0]) if start else 1
        for k in range(y2.shape[1]):
            if 'exppolyfit' in expr:
                col = y2[:, k]
                shift = col.min() - 1e-4 * abs(col.max() - col.min())
                pol = np.polyfit(x[idx], np.log(col[idx] - shift), order)
                sim[:, k] = np.exp(np.polyval(pol, x)) + shift
            else:
                pol = np.polyfit(x[idx], y2[idx, k], order)
                sim[:, k] = np.polyval(pol, x)
        extra = [f'pol{i + 1} = {_fmt(v)}' for i, v in enumerate(pol)]
        values = start
    else:
        values = list(start)
        for k in range(y2.shape[1]):
            def chi2(p, xx=x[idx], yy=y2[idx, k]):
                return float(np.sum((np.real(evaluate(expr, xx, dict(zip(names, p)))) - yy) ** 2))
            res = minimize(chi2, np.array(values, float) if values else np.zeros(0),
                           method='Nelder-Mead',
                           options={'maxiter': max_iter, 'xatol': 1e-9, 'fatol': 1e-12})
            values = list(res.x)
            sim[:, k] = np.broadcast_to(np.real(evaluate(expr, x, dict(zip(names, values)))), len(x))
    out = keep + [f'{n} = {_fmt(v)}' for n, v in zip(names, values)] + extra
    return out, sim[:, 0] if y.ndim == 1 else sim
