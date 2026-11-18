"""Value/unit string helpers: ports of ``kv3_getvalue`` and the SpecMan ``get_array``.

``getvalue('4.6245 T')`` -> ``(4.6245, 'T', '', 1)``;
``getvalue('800 ps')`` -> ``(8e-10, 's', 'p', 1e-12)``.
A leading SI prefix is removed only when the unit has more than one character,
so 'T' (tesla) and 'G' (gauss) survive, exactly as in MATLAB.
"""
from __future__ import annotations

import re

import numpy as np

PREFIX = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'M': 1e6, 'G': 1e9, 'T': 1e12}

_VALUE = re.compile(r'(?P<number>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(?P<unit>\w+)?')


def getvalue(s) -> tuple[float, str, str, float]:
    """Returns ``(value_in_base_units, unit, prefix, prefix_factor)``; NaN if no number."""
    if not isinstance(s, str):
        try:
            return float(s), '', '', 1.0
        except (TypeError, ValueError):
            return float('nan'), '', '', 1.0
    m = _VALUE.search(s)
    if not m:
        return float('nan'), '', '', 1.0
    val = float(m.group('number'))
    unit = m.group('unit') or ''
    if unit in ('to', 'logto', 'step'):   # '4.6 to 4.7 T': keyword, not a unit
        unit = ''
    pref, pref_val = '', 1.0
    if len(unit) > 1 and unit[0] in PREFIX:
        pref, pref_val = unit[0], PREFIX[unit[0]]
        val *= pref_val
        unit = unit[1:]
    return val, unit, pref, pref_val


def get_val(s: str) -> tuple[float, str]:
    """Value and unit of the part before the first ';'."""
    s = s.split(';', 1)[0]
    v, unit, _, _ = getvalue(s)
    if not unit:   # '4.6 to 4.7 T': the unit follows the last value
        for kw in ('logto', 'to', 'step'):
            if kw in s:
                unit = getvalue(s.split(kw, 1)[1])[1]
                break
    return v, unit


def get_array(s: str, n: int | None = None) -> np.ndarray:
    """SpecMan parameter string to array.

    Forms: 'a logto b', 'a to b', 'a step d', 'v1, v2, ...' (anything after ';' ignored).
    """
    s = s.split(';', 1)[0]
    if 'logto' in s:
        a, b = s.split('logto', 1)
        return np.logspace(np.log10(getvalue(a)[0]), np.log10(getvalue(b)[0]), int(n))
    if 'to' in s:
        a, b = s.split('to', 1)
        return np.linspace(getvalue(a)[0], getvalue(b)[0], int(n))
    if 'step' in s:
        a, b = s.split('step', 1)
        return getvalue(a)[0] + np.arange(int(n)) * getvalue(b)[0]
    vals = [getvalue(t)[0] for t in s.split(',') if t.strip()]
    return np.array([v for v in vals if v == v], dtype=float)


def valid_field(name: str) -> str:
    """Port of ``validMLfield``: the field names MATLAB used for TDMS/BIP objects."""
    for ch in "/.[]?@#$():'-":
        name = name.replace(ch, '')
    name = name.replace(' ', '_')
    if not name:
        return 'Fempty'
    if name[0].isdigit():
        name = 'F' + name
    return name
