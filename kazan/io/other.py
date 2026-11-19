"""Other loaders: ports of ``opus_read`` (Bruker OPUS FT-IR), the ``image`` script
(``imread`` + ``rgb2gray``) and ``kv3_astashkinread``.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from ..core.data import Struct

#: OPUS data part (MATLAB option 1): label -> code
OPUS_PARTS = [('Interferogram', 1), ('Baseline (fft)', 2), ('Data-Baseline(fft)', 3)]


def opus_read(filename: str, datapart: int = 2):
    """``opus_read``: blocks are found by their 3-letter tags; values follow 8 bytes
    after a tag (MATLAB ``fseek(tag + 7)`` with 1-based positions)."""
    b = Path(filename).read_bytes()
    text = b.decode('latin-1')

    def tags(name):
        out, i = [], text.find(name)
        while i >= 0:
            out.append(i)
            i = text.find(name, i + 1)
        return out

    def f64(pos):
        return struct.unpack_from('<d', b, pos + 8)[0]

    def i32(pos):
        return struct.unpack_from('<i', b, pos + 8)[0]

    hfl, lfl = f64(tags('HFL')[0]), f64(tags('LFL')[0])
    fxv, lxv, npt = tags('FXV'), tags('LXV'), tags('NPT')
    first = [f64(p) for p in fxv]
    last = [f64(p) for p in lxv]
    npts = [i32(p) for p in npt[:len(fxv)]]
    nbg = i32(tags('ARS')[0]) if tags('ARS') else 0
    nscans = i32(tags('ASS')[0]) if tags('ASS') else 0
    ends = [p + 1 + 3 for p in tags('END')]                 # MATLAB 1-based strfind + 3
    starts = [max(e for e in ends if e < p + 1) for p in fxv]

    ax = Struct(type='data', y=np.array([1.0]), HFL=hfl, LFL=lfl)
    part = datapart
    if len(fxv) > 2:
        part = min(len(fxv), datapart)
        ax.xlabel, ax.title = (('Mirror steps, pnts', 'Interferogram') if part == 1 else
                               ('Wavenumber, cm^{-1}', 'FT-IR spectrum'))
    elif len(fxv) == 2:
        part = min(len(fxv), datapart)
        if part == 2:
            ax.xlabel, ax.title, part = 'Wavenumber, cm^{-1}', 'FT-IR spectrum', 1
        else:
            ax.xlabel, ax.title, part = 'Mirror steps, pnts', 'Interferogram', 2
    k = part - 1
    n = npts[k]
    first_float = (starts[k] + 3) // 4 + 1                 # 0-based float index of point 1
    y = np.frombuffer(b, '<f4', count=n, offset=4 * first_float).astype(float)
    ax.x = np.linspace(first[k], last[k], n)
    dsc = Struct(HighFoldingLimit=f'{hfl:g} cm-1', LowFoldingLimit=f'{lfl:g} cm-1',
                 NumberOfBGScans=str(nbg), NumberOfSampleScans=str(nscans))
    return ax, y, dsc


def image_read(filename: str):
    """``imread`` + ``rgb2gray``: a grey-level image (rows x columns)."""
    from PySide6.QtGui import QImage   # Qt reads jpg / png / bmp / tif without extra packages
    img = QImage(str(filename))
    if img.isNull():
        raise ValueError('Unable to read the image')
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    a = np.frombuffer(img.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)[:, :3 * w]
    rgb = a.reshape(h, w, 3).astype(float)
    y = np.round(rgb @ np.array([0.2989, 0.5870, 0.1140]))   # MATLAB rgb2gray (uint8)
    ax = Struct(type='image', xlabel='Image width, pixels')
    return ax, y, Struct(comment='no info')


def astashkin_read(filename: str):
    """``kv3_astashkinread``: ``name.par`` ('key: value') + ``name.dat`` (8-byte header,
    float32)."""
    p = Path(filename)
    dsc = Struct()
    for line in p.with_suffix('.par').read_text(errors='replace').splitlines():
        if ';' in line or ':' not in line:
            continue
        key, value = line.rsplit(':', 1)
        key = key.strip().replace(' ', '_')
        for ch in '[].':
            key = key.replace(ch, '')
        dsc[key] = value.strip()
    dsc.KAZANformat = 'ASTASHKINPAR'
    nx = int(float(dsc.get('X_Axis_Resolution_pts', '0')))
    ny = int(float(dsc.get('Y_Axis_Resolution_pts', '1')))
    y = np.fromfile(p.with_suffix('.dat'), '<f4', offset=8).astype(float)
    if nx > 0 and ny > 0 and y.size == nx * ny:
        y = y.reshape((nx, ny), order='F')
    ax = Struct(type='data', xlabel='?, a.u.', ylabel='?, a.u.', unit='a.u.')
    ax.x = np.arange(1.0, (nx or y.shape[0]) + 1)
    ax.y = np.arange(1.0, ny + 1)
    if dsc.get('Field_Sweep_Coordinate') != 'Y' and dsc.get('RF1_Sweep_Coordinate') != 'Y':
        try:
            ax.x = (float(dsc.Initial_delay) + float(dsc.Delay_step_X) * np.arange(nx)) * 1e-9
            ax.xlabel = 'Time, s'
        except (TypeError, ValueError):
            pass
    return ax, y, dsc
