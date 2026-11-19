"""ASCII loaders: ports of ``kv3_asciiread`` (with the column layouts of
``kv3_ScriptLoad``) and of ``rmnread`` type ``2dtxt`` (ASCII2D).
"""
from __future__ import annotations

import re

import numpy as np

from ..core.data import Struct

_NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[-+]?(?:inf|nan)', re.I)

#: column layouts of the ASCII loader (MATLAB option 2): label -> code
LAYOUTS = [('Y', 1), ('rY, iY', 2), ('X,Y', 3), ('X,(rY,iY)n', 4), ('X,(rY)n,(iY)n', 8),
           ('idx, X, Y', 5), ('idx, X, rY, iY', 6), ('X,Y1,Y2,Y3..', 7)]
DELIMITERS = [('tab', '\t'), ('space', ' '), (',', ','), (';', ';')]


def _scan(line: str, delimiter: str) -> list[float]:
    """MATLAB ``sscanf(line, ['%f' delimiter])``: numbers from the start of the line, each
    followed by the delimiter (any whitespace for tab / space); stops at the first
    mismatch."""
    values, pos, n = [], 0, len(line)
    ws_delim = delimiter.strip() == ''
    while True:
        while pos < n and line[pos].isspace():
            pos += 1
        m = _NUMBER.match(line, pos)
        if not m:
            return values
        values.append(float(m.group()))
        pos = m.end()
        if not ws_delim:
            while pos < n and line[pos].isspace():
                pos += 1
            if pos < n and line[pos] == delimiter:
                pos += 1
            else:
                return values


def ascii_read(filename: str, delimiter: str = '\t', first_column_x: bool = True):
    """Port of ``kv3_asciiread``: rows with as many numbers as the first numeric row are
    data, other lines go to ``dsc.c1, c2, ...``. The footer written by Kazan Viewer 3.0
    (``; created by Kazan Viewer 3.0`` followed by ``key: value`` lines) restores
    ``ax`` fields."""
    rows, text = [], []
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            values = _scan(line, delimiter)
            if values and (not rows or len(values) == len(rows[0])):
                rows.append(values)
            else:
                text.append(line.rstrip('\r\n'))
    if not rows:
        raise ValueError('No numeric data found')
    data = np.array(rows)

    ax = Struct()
    if first_column_x and data.shape[1] > 1:
        ax.x, y = data[:, 0], data[:, 1:]
    else:
        ax.x, y = np.arange(1.0, data.shape[0] + 1.0), data
    ax.type, ax.xlabel, ax.ylabel, ax.unit = 'data', '?', 'Intensity', 'a.u.'
    dsc = Struct(ASCII='ASCII loader for KAZAN viewer', Delimiter=delimiter,
                 FirstColumn='Treated as ' + ('X' if first_column_x else 'Y'),
                 size_x=str(y.shape[0]), size_y=str(y.shape[1]))
    for i, s in enumerate(text, 1):
        dsc[f'c{i}'] = s
    _read_footer(text, ax, y.shape[1])
    return ax, y, dsc


def _read_footer(lines, ax, ncols):
    in_footer = False
    for line in lines:
        body = line[1:].strip() if line.startswith(';') else line.strip()
        if not body:
            continue
        if 'created by Kazan Viewer 3.0' in body:
            in_footer = True
            continue
        if not in_footer or ':' not in body:
            continue
        key, val = (s.strip() for s in body.split(':', 1))
        if key.lower() in ('original', 'script'):
            continue
        if key.startswith('ax.'):
            key = key[3:]
        if not key.isidentifier():
            continue
        if key == 'y':
            vec = [float(v) for v in _NUMBER.findall(val)]
            if vec and len(vec) in (ncols / 2, ncols):
                ax.y = np.array(vec)
            continue
        try:
            ax[key] = float(val)
        except ValueError:
            ax[key] = val


def ascii_load(filename: str, delimiter: str = '\t', layout: int = 3, xlabel: str = ''):
    """``kv3_ScriptLoad`` ASCII script: read, then apply the column layout."""
    ax, y, dsc = ascii_read(filename, delimiter, layout > 2)
    if layout in (5, 6):                 # idx, X, ...: the idx column was taken as x
        ax.x, y = y[:, 0], y[:, 1:]
    n = y.shape[1]
    if layout in (2, 5, 6, 8) and n % 2 == 0 and n:
        y = y[:, :n // 2] + 1j * y[:, n // 2:]
    elif layout == 4 and n % 2 == 0 and n:
        y = y[:, 0::2] + 1j * y[:, 1::2]
    if ax.xlabel == '?':
        ax.xlabel = xlabel
    if len(np.ravel(ax.get('y', []))) != y.shape[1]:
        ax.pop('y', None)
    return ax, y, dsc


def ascii2d_load(filename: str, sizes: str = '', is_complex: bool = True):
    """ASCII2D (``rmnread`` type ``2dtxt``): one number per value (re, im interleaved when
    complex), reshaped to xsize x ysize. ``sizes`` is ``'xsize ysize [xdwell ydwell
    cfreq]'``; odd sizes give centred frequency axes, even sizes time axes."""
    v = [float(s) for s in _NUMBER.findall(sizes or '')]
    if len(v) < 2:
        raise ValueError("ASCII2D: enter 'xsize ysize [xdwell ydwell cfreq]' in the option field")
    xsize, ysize = int(v[0]), int(v[1])
    xdwell = v[2] if len(v) > 2 else 10e-6
    ydwell = v[3] if len(v) > 3 else 10e-6
    cfreq = v[4] if len(v) > 4 else 0.0
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        p = np.array([float(s) for s in _NUMBER.findall(f.read())])
    y = p[0::2] + 1j * p[1::2] if is_complex else p
    if xsize * ysize > len(y):
        raise ValueError(f'Specified sizes {xsize}x{ysize}={xsize * ysize} not equal to '
                         f'array size {len(y)}')
    y = y[:xsize * ysize].reshape((xsize, ysize), order='F')
    ax = Struct(type='data', reference=cfreq)
    if xsize % 2 and ysize % 2:
        ax.x = 1 / xdwell / (xsize - 1) * np.arange(-(xsize - 1) / 2, (xsize - 1) / 2 + 1)
        ax.y = 1 / ydwell / (ysize - 1) * np.arange(-(ysize - 1) / 2, (ysize - 1) / 2 + 1)
    else:
        ax.x = xdwell * np.arange(1, xsize + 1)
        ax.y = ydwell * np.arange(1, ysize + 1)
    dsc = Struct(ASCII2D='ASCII 2D loader for KAZAN viewer', size=f'{xsize}x{ysize}')
    return ax, y, dsc


def ascii_write(filename: str, d, origin: str = '', parameters=None, footer: bool = True):
    """Port of ``kv3_asciiwrite`` (``usefooter``): columns ``x, real(y) [, imag(y)]`` as
    MATLAB ``save -ascii`` writes them, then the Kazan Viewer 3.0 footer that
    :func:`ascii_read` reads back. ``parameters``: data-parameter names written when the
    axis has them (MATLAB ``DataParameters``)."""
    y = np.asarray(d.y)
    if y.ndim == 1:
        y = y[:, None]
    yr, yi = np.real(y), np.imag(y)
    x = np.ravel(d.ax.x)[:, None]
    p = np.hstack([x, yr, yi] if np.any(yi) else [x, yr])
    lines = ['   '.join(f'{v:15.8e}' for v in row) for row in p]
    if footer:
        ax = d.ax
        lines.append(';--- created by Kazan Viewer 3.0 ---')
        lines.append(f'; original: {origin}')
        for key in ('type', 'xlabel', 'ylabel'):
            if ax.get(key) is not None:
                lines.append(f'; ax.{key}: {ax[key]}')
        ay = ax.get('y')
        if yr.shape[1] > 1 and ay is not None and np.size(ay) == yr.shape[1]:
            lines.append('; ax.y: ' + ' '.join(f'{v:.15g}' for v in np.ravel(ay)))
        if ax.get('filt'):
            lines.append(f"; ax.filt: {ax.filt}")
            for key, fmt in (('tc', '{:f}'), ('pol', '{:d}')):
                if ax.get(key) is not None:
                    try:
                        lines.append(f'; ax.{key}: ' + fmt.format(int(ax[key]) if key == 'pol' else float(ax[key])))
                    except (TypeError, ValueError):
                        pass
        if ax.get('diff'):
            lines.append(f"; ax.diff: {ax['diff']}")
            if ax.get('ps_mod') is not None:
                lines.append(f'; ax.ps_mod: {float(ax.ps_mod):f}')
        for key in ('dx', 'dy', 's'):
            try:
                if ax.get(key) is not None:
                    lines.append(f'; ax.{key}: {float(ax[key]):f}')
            except (TypeError, ValueError):
                pass
        script = getattr(d, 'script', '') or ''
        if script:
            lines.append(f'; Script: {script}')
        for name in parameters or []:
            v = ax.get(name)
            if v is None or (isinstance(v, str) and not v) or name in ('xlabel', 'ylabel'):
                continue
            if isinstance(v, str):
                lines.append(f'; {name}: {v}')
            else:
                try:
                    lines.append(f'; {name}: {float(v):f}')
                except (TypeError, ValueError):
                    pass
    with open(filename, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
