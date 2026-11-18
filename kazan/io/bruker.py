"""Bruker XEPR (.DSC/.DTA) and ESP/WinEPR (.par/.spc) loader.

Ports of ``kv3_brukerread``, ``kv3_XEPRdsc`` and ``kv3_XEPRpar``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..core.data import Struct

_FORBIDDEN = set('~!@#$%^&*()./\\')


def _num(par, key, default='nan') -> float:
    try:
        return float(str(par.get(key, default)).split()[0])
    except (ValueError, IndexError):
        return float('nan')


def read_dsc(filename) -> Struct:
    """Port of ``kv3_XEPRdsc``: 'KEY value' lines; lines starting with a digit
    continue the previous key; comment/section lines are skipped."""
    par = Struct()
    last = ''
    with open(filename, 'r', encoding='latin-1') as f:
        for line in f:
            parts = line.strip().split(None, 1)
            if not parts or parts[0][0] in _FORBIDDEN:
                continue
            key, value = parts[0], (parts[1].strip() if len(parts) > 1 else '')
            if key[0].isdigit():
                if last:
                    par[last] = (par[last] + line.strip()).strip()
                continue
            last = key
            if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
                value = value[1:-1]
            par[key] = value
    return par


def _axis(par: Struct, letter: str) -> tuple[np.ndarray, str]:
    """Port of ``getrespar321`` (one axis of ``kv3_XEPRpar``)."""
    L = letter.upper()
    dim, sf, step, label = 1, 0.0, 1.0, '?'
    unit = str(par.get(f'{L}UNI', 'a.u.')).replace("'", '') or 'a.u.'
    factor = 1.0
    if 'ns' in unit:
        unit, factor = 's', 1e-9

    if 'JSS' not in par and ('RES' in par or 'RRES' in par) and 'HCF' in par:
        par = Struct(par, JSS='2', RES=par.get('RES', par.get('RRES', '1024')))

    if 'JSS' in par:
        jss = int(_num(par, 'JSS'))
        if jss == 2 and L != 'Y':
            dim = int(_num(par, 'RES', '1024'))
            if 'GST' in par and 'GSI' in par:
                sf, step = _num(par, 'GST'), _num(par, 'GSI') / (dim - 1)
            elif 'HCF' in par and 'HSW' in par:
                c, w = _num(par, 'HCF'), _num(par, 'HSW')
                step, sf = w / (dim - 1), c - w / 2
            else:
                c = _num(par, 'HCF')
                w = 2 * abs(c - _num(par, 'GST'))
                step, sf = w / (dim - 1), c - w / 2
            label = 'Magnetic Field, G'
        elif jss in (4128, 4144):
            dim = int(_num(par, f'SS{L}'))
            sw = _num(par, f'X{L}WI', str(dim))
            step = sw / (dim - 1)
            label = 'Time, ' + str(par.get(f'X{L}UN', '?')).replace("'", '')
        elif jss not in (2, 32) and par.get(f'{L}TYP', 'NODATA') != 'NODATA':
            dim = int(_num(par, f'{L}PTS'))
            sf, w = _num(par, f'{L}MIN'), _num(par, f'{L}WID')
            step = w / (dim - 1)
            label = f"{par.get(f'{L}NAM', '?')}, {unit}"
        # JSS 32 (ESP pulse) is not ported: falls back to point numbers
    elif 'JEX' in par:
        if L != 'Y':
            dim = int(_num(par, 'RES', '1024'))
            if par.JEX == 'ENDOR':
                sf, w = _num(par, 'ESF'), _num(par, 'ESW')
                step, label = w / (dim - 1), 'Frequency, MHz'
    elif par.get(f'{L}TYP', 'NODATA') != 'NODATA':
        dim = int(_num(par, f'{L}PTS'))
        sf = _num(par, f'{L}MIN') * factor
        w = _num(par, f'{L}WID') * factor
        step = w / (dim - 1) if dim > 1 else 1.0
        label = f"{par.get(f'{L}NAM', '?')}, {unit}"
        if f'{L}AxisQuant' in par:
            label = f"{par[f'{L}AxisQuant']}, {unit}"
    return sf + step * np.arange(dim), label


def brukerread(filename):
    """Port of ``kv3_brukerread``: ``ax, y, dsc``."""
    p = Path(filename)
    ext = p.suffix.upper()
    if ext in ('.DSC', '.DTA'):
        dscname, fname = _sibling(p, '.dsc'), _sibling(p, '.dta')
    else:
        dscname, fname = _sibling(p, '.par'), _sibling(p, '.spc')
    dsc = read_dsc(dscname)
    dsc.KAZANformat = 'BRUKERDSC'
    ax = Struct()
    ax.x, ax.xlabel = _axis(dsc, 'x')
    ax.y, ax.ylabel = _axis(dsc, 'y')
    ax.unit = str(dsc.get('IRUNI', '')).replace("'", '') or 'a.u.'
    if ax.ylabel == '?':
        ax.ylabel = 'Intensity'

    nx, ny = len(ax.x), len(ax.y)
    if 'IKKF' in dsc:
        is_complex = dsc.IKKF == 'CPLX'
    elif 'XQAD' in dsc:
        is_complex = dsc.XQAD == 'ON'
    else:
        is_complex = False

    if ext in ('.DSC', '.DTA'):
        e = '>' if dsc.get('BSEQ', 'BIG') == 'BIG' else '<'
        fmt = {'I': 'i4', 'F': 'f4'}.get(dsc.get('IRFMT', 'D'), 'f8')
        y = _read_matrix(fname, nx, ny, e + fmt, is_complex)
    else:
        # WinEPR writes little-endian and sets DOS; ESP (no DOS key) is big-endian
        e = '<' if 'DOS' in dsc else '>'
        if is_complex:
            raw = _read_matrix(fname, 2 * nx, ny, e + 'i4', False)
            y = raw[:nx] + 1j * raw[nx:]
        else:
            fmt = 'f4' if _num(dsc, 'VERS', '0') == 769 else 'i4'
            if 'DOS' in dsc and fname.stat().st_size == 4 * nx * ny:
                fmt = 'f4'  # WinEPR stores float32
            y = _read_matrix(fname, nx, ny, e + fmt, False)

    for letter in ('X', 'Y'):
        if dsc.get(f'{letter}TYP') == 'IGD':
            try:
                vals = np.fromfile(_sibling(p, f'.{letter}GF'), dtype=e + 'f8',
                                   count=len(ax[letter.lower()]))
                ax[letter.lower()] = vals.astype(float)
            except OSError:
                print('Error during the reading of the axis file')
    if len(ax.x) != y.shape[0]:
        ax.x = np.arange(1.0, y.shape[0] + 1)
    if len(ax.y) != y.shape[1]:
        ax.y = np.arange(1.0, y.shape[1] + 1)
    return ax, y, dsc


def _sibling(p: Path, ext: str) -> Path:
    """Same name with another extension, matching existing upper/lower case."""
    for e in (ext, ext.upper(), ext.lower()):
        q = p.with_suffix(e)
        if q.exists():
            return q
    return p.with_suffix(ext.upper() if p.suffix.isupper() else ext)


def _read_matrix(fname: Path, nx: int, ny: int, dtype: str, is_complex: bool) -> np.ndarray:
    n = (2 if is_complex else 1) * nx * ny
    x = np.fromfile(fname, dtype=dtype, count=n)
    if x.size < n:
        raise ValueError('Unable to read all expected data.')
    x = x.astype(float)
    if is_complex:
        x = x[0::2] + 1j * x[1::2]
    return x.reshape((nx, ny), order='F')
