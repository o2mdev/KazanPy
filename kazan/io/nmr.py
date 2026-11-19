"""NMR loaders: ports of ``rmnread``, ``XWINNMR`` / ``XWINNMRpar``, ``kv3_WINNMR``,
``TecMagread`` and ``kv_read_spinsight``.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

import numpy as np

from ..core.data import Struct
from .units import getvalue

#: RMN 2D axis types (MATLAB option 1): label -> code
RMN2D_TYPES = [('D1:Time D2:Time', '2DTT'), ('D1:Time D2:Freq', '2DTF'),
               ('D1:Freq D2:Time', '2DFT'), ('D1:Freq D2:Freq', '2DFF')]


def _num(s, default=0.0) -> float:
    try:
        return float(str(s).split()[0])
    except (ValueError, IndexError):
        return default


# ===================================================================== RMN

def rmnread(filename: str, kind: str = '1D', subtype: str = '2DTT'):
    """``rmnread`` types '1D', '2D' (binary, big-endian) and '1dtxt' (RMNdat)."""
    kind = kind.lower()
    ax, opt = Struct(type='data'), Struct()
    if kind == '1dtxt':
        with open(filename, 'r', encoding='utf-8', errors='replace') as f:
            p = np.array([float(s) for s in f.read().split()])
        n = len(p) // 2
        y = p[0:2 * n:2] + 1j * p[1:2 * n:2]
        ax.x = 10e-6 * np.arange(1, n + 1)
        ax.xlabel = 'Time, s'
        return ax, y, opt
    b = Path(filename).read_bytes()
    if kind == '1d':
        version = b[0]
        n = struct.unpack_from('>i', b, 1)[0]
        dwell, init, freq, offset = struct.unpack_from('>4d', b, 5)
        comment = b[37:37 + 1024]
        p = np.frombuffer(b, '>f4', count=2 * n, offset=37 + 1024).astype(float)
        y = p[0::2] + 1j * p[1::2]
        ax.update(ncomplex=n, dwelltime=dwell, inittime=init, freq1=freq, freqoffset=offset)
        ax.x = init + dwell * np.arange(1, n + 1)
        ax.xlabel = '?'
        opt.update(version=str(version), ncomplex=str(n), dwelltime=str(dwell),
                   inittime=str(init), freq=str(freq), freqoffset=str(offset),
                   comment=comment.split(b'\0')[0].decode('latin-1'))
        return ax, y, opt
    # 2D
    version = b[0]
    if version != 4:
        raise ValueError('Not supported rmn file version.')
    n2d = struct.unpack_from('>i', b, 1)[0]
    dwell2d, init2d, freq2d, offset2d = struct.unpack_from('>4d', b, 5)
    n1d = struct.unpack_from('>i', b, 37)[0]
    dwell1d, init1d, freq1d, offset1d = struct.unpack_from('>4d', b, 41)
    comment = b[73:73 + 1024]
    ax.update(n2d=n2d, dwell2d=dwell2d, init2d=init2d, freq2d=freq2d, offset2d=offset2d,
              n1d=n1d, dwell1d=dwell1d, init1d=init1d, freq1d=freq1d, offset1d=offset1d)
    sub = (subtype + 'TTTT')[:4]
    if sub[2] == 'T':
        ax.x, ax.xlabel = (init1d + dwell1d * np.arange(n1d + 1)) * 1e3, 'T2, ms'
    else:
        ax.x, ax.xlabel = 1 / dwell1d / 2 / n1d * np.arange(-n1d, n1d + 1, 2) * 1e-3, 'F2, kHz'
    if sub[3] == 'T':
        ax.y, ax.ylabel = (init2d + dwell2d * np.arange(n2d + 1)) * 1e3, 'T1, ms'
    else:
        ax.y, ax.ylabel = 1 / dwell2d / 2 / n2d * np.arange(-n2d, n2d + 1, 2) * 1e-3, 'F1, kHz'
    n = (n1d + 1) * (n2d + 1)
    p = np.frombuffer(b, '>f4', count=2 * n, offset=73 + 1024).astype(float)
    y = (p[0::2] + 1j * p[1::2]).reshape((n1d + 1, n2d + 1), order='F')
    opt.update(version=str(version), n1d=str(n1d), n2d=str(n2d), dwell1d=str(dwell1d),
               dwell2d=str(dwell2d), subtype=subtype,
               comment=comment.split(b'\0')[0].decode('latin-1'))
    return ax, y, opt


# ===================================================================== Bruker NMR

def xwinnmr_par(filename) -> Struct:
    """``XWINNMRpar``: JCAMP-DX ``##$KEY= value`` files (acqus, procs, ...);
    continuation lines are appended with '; '."""
    par, fld = Struct(), None
    with open(filename, 'r', encoding='latin-1') as f:
        for line in f:
            s = line.rstrip('\r\n')
            if '##' in s:
                if '$$' in s:
                    continue
                s = s.replace('#', ' ').strip()
                name, _, value = s.partition('=')
                fld = name.replace('$', '').strip() or None
                if fld:
                    par[fld] = value.strip()
            elif fld:
                par[fld] = f'{par[fld]}; {s.strip()}'
    return par


def _byteorder(par, key) -> str:
    return '>' if _num(par.get(key, '0')) > 0.5 else '<'


def xwinnmr(filename: str):
    """``XWINNMR``: Bruker NMR experiment folder (``fid``, ``ser`` or processed ``1r``/``1i``)."""
    folder = Path(filename).parent
    ax, dsc = Struct(type='data', dx=0), Struct()
    if (folder / 'fid').exists() and (folder / 'acqus').exists():
        dsc = xwinnmr_par(folder / 'acqus')
        td = int(_num(dsc.TD))
        dw = 1 / (2 * _num(dsc.SW_h))
        p = np.fromfile(folder / 'fid', _byteorder(dsc, 'BYTORDA') + 'i4', count=td).astype(float)
        data = p[0::2] + 1j * p[1::2]
        ax.x, ax.xlabel = 1e6 * dw * np.arange(1, len(data) + 1), 'Time, us'
        ax.reference = _num(dsc.get('BF1', '0')) * 1e6
    elif (folder / 'ser').exists():
        dsc = xwinnmr_par(folder / 'acqus')
        dsc2 = xwinnmr_par(folder / 'acqu2s')
        td1 = int(_num(dsc.TD)) + 45 * 2          # MATLAB: TD + 90 (digital filter)
        td2 = int(_num(dsc2.TD))
        dw = 1 / (2 * _num(dsc.SW_h))
        p = np.fromfile(folder / 'ser', _byteorder(dsc, 'BYTORDA') + 'i4', count=td1 * td2).astype(float)
        data = (p[0::2] + 1j * p[1::2]).reshape((td1 // 2, -1), order='F')
        ax.x, ax.xlabel = 1e6 * dw * np.arange(1, td1 // 2 + 1), 'Time, us'
        if dsc2.get('VDLIST', '<>') != '<>' and (folder / 'vdlist').exists():
            vals = [getvalue(l.strip() + 's')[0] for l in
                    (folder / 'vdlist').read_text(errors='replace').splitlines() if l.strip()]
            ax.y, ax.ylabel = np.array(vals[:data.shape[1]]), 'Time, s'
        else:
            ax.y, ax.ylabel = np.arange(1.0, data.shape[1] + 1), 'Points, pts'
        ax.reference = _num(dsc.get('BF1', '0')) * 1e6
    elif (folder / 'procs').exists():
        dsc = xwinnmr_par(folder / 'procs')
        si = int(_num(dsc.SI))
        sw, sf = _num(dsc.SW_p), _num(dsc.SF)
        ax.x = _num(dsc.OFFSET) * sf - sw * np.arange(si) / (si - 1)
        ax.xlabel = 'Frequency, Hz'
        ax.reference = _num(dsc.get('SF', '0')) * 1e6
        e = _byteorder(dsc, 'BYTORDP') + 'i4'
        r = np.fromfile(folder / '1r', e, count=si).astype(float)
        i = np.fromfile(folder / '1i', e, count=si).astype(float)
        data = (r + 1j * i) * 2.0 ** _num(dsc.get('NC_proc', '0'))
    else:
        raise ValueError('XWINNMR: no fid, ser or procs file in the folder')
    ax.freq1 = _num(dsc.get('BF1', '0')) * 1e6
    if (folder / 'title').exists():
        lines = (folder / 'title').read_text(errors='replace').splitlines()
        ax.title = lines[0] if lines else ''
    return ax, data, dsc


def winnmr(filename: str):
    """``kv3_WINNMR``: WIN-NMR spectrum (``name.aqs`` parameters, ``name.1r`` / ``.1i``)."""
    p = Path(filename)
    dsc = xwinnmr_par(p)
    seq = int(_num(dsc.AQ_mod)) & 2 > 0
    td1 = int(_num(dsc.TD) / (1 + (not seq)))
    sw = _num(dsc.SW_h)
    ax = Struct(type='data', dx=0, xlabel='Frequency, Hz', ylabel='Intensity', unit='a.u.')
    ax.x = sw * np.arange(-td1 / 2, td1 / 2) / td1 + _num(dsc.get('O1', '0'))
    ax.reference = _num(dsc.get('SFO1', '0')) * 1e6
    ax.freq1 = _num(dsc.get('BF1', '0')) * 1e6
    e = _byteorder(dsc, 'BYTORDA') + 'f4'
    r = np.fromfile(p.with_suffix('.1r'), e, count=td1).astype(float)
    i = np.fromfile(p.with_suffix('.1i'), e, count=td1).astype(float)
    return ax, r + 1j * i, dsc


# ===================================================================== TecMag / Spinsight

def tecmag_read(filename: str):
    """``TecMagread``: TecMag binary (big-endian header, float pairs imag/real)."""
    b = Path(filename).read_bytes()
    dsc = Struct()
    nrecords = struct.unpack_from('>i', b, 0)[0]
    dsc.nrecords = str(nrecords)
    dsc.dtype = 'Frequency, Hz' if b[4] else 'Time, us'
    npoints = struct.unpack_from('>i', b, 50)[0]
    dsc.npoints1D = str(npoints)
    dsc.sample = b[58:90].split(b'\0')[0].decode('latin-1')
    dsc.sequence = b[90:122].split(b'\0')[0].decode('latin-1')
    mfield, freq1, swidth, dw, acqtime, _, freq2 = struct.unpack_from('>7d', b, 154)
    dw *= 1e6
    dsc.update(mfield=f'{mfield:g} T', frequency1=f'{freq1:g} MHz', spwidth=f'{swidth:g} Hz',
               dw=f'{dw:g} us', acqtime=f'{acqtime:g} s', frequency2=f'{freq2:g} MHz')
    comment = b[1024:2048].replace(b'\0', b'').decode('latin-1')
    for k, line in enumerate((s.strip() for s in re.split(r'[\r\n]+', comment) if s.strip()), 1):
        dsc[f'c{k}'] = line
    data = np.frombuffer(b, '>f4', count=2 * nrecords * npoints, offset=2048).astype(float)
    data = data.reshape((2, npoints, nrecords), order='F')
    spec = data[1] + 1j * data[0]
    ax = Struct(type='data', freq1=freq1, freq2=freq2, xlabel=dsc.dtype)
    ax.x = dw * np.arange(1, npoints + 1)
    return ax, spec, dsc


def spinsight_read(filename: str):
    """``kv_read_spinsight``: Spinsight experiment folder (``acq`` parameters, ``data``)."""
    folder = Path(filename).parent
    dsc = Struct()
    for line in (folder / 'acq').read_text(errors='replace').splitlines():
        if '=' in line and not line.lstrip().startswith(('[', ';', '#')):
            k, v = line.split('=', 1)
            dsc[k.strip()] = v.strip()
    npoints = int(_num(dsc.get('al', '0')))
    m = re.match(r'\s*([-+0-9.eE]+)\s*([a-zA-Z]*)', dsc.get('dw', '0'))
    dw, unit = (float(m.group(1)), m.group(2)) if m else (0.0, '')
    if unit in ('u', 'm', 'n', 'k', 'p'):                   # Spinsight: '2u' = 2 us
        dw *= {'u': 1e-6, 'm': 1e-3, 'n': 1e-9, 'k': 1e3, 'p': 1e-12}[unit]
        unit = 's'
    elif unit:
        dw, unit = getvalue(dsc.get('dw', '0'))[:2]
    p = np.fromfile(folder / 'data', '>f4', count=2 * npoints).astype(float)
    ax = Struct(type='data', xlabel=f'Time, {unit or "s"}')
    ax.x = np.arange(1, npoints + 1) * dw
    return ax, p[:npoints] + 1j * p[npoints:], dsc
