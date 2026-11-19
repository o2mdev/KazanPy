"""SpecMan4EPR loaders.

Ports of ``kv3_d01read`` (+ ``kv3_SpecMandsc``, ``kv3_SpecManpar``, ``kv3_LoadBIP``)
and ``kv3_smtdmsread`` (+ ``kv3_LoadTDMS``, ``kv3_SpecManTDMSpar``).

Field names in ``ax`` and ``dsc`` are kept identical to MATLAB, because plugins
read them (``ax.raw``, ``ax.data``, ``dsc.RS_Frequency``, ...).
"""
from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..core.data import Struct
from .units import get_array, get_val, getvalue, valid_field

# =====================================================================  .exp / .d01


def read_exp(filename) -> Struct:
    """Port of ``kv3_SpecMandsc``: '[section]' + 'key = value' to ``section_key``."""
    par = Struct()
    section = ''
    text = prg = 1
    with open(filename, 'r', encoding='latin-1') as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith('[') and s.count('[') + s.count(']') == 2 and s.endswith(']'):
                section = s[1:-1]
                continue
            if section == 'text':
                par[f'text{text}'] = s
                text += 1
            elif section == 'program':
                par[f'prg{prg}'] = s
                prg += 1
            else:
                key, _, value = s.partition('=')
                key = key.strip()
                for ch in '/\\ .':
                    key = key.replace(ch, '_')
                sec = 'f' + section if section[:1].isdigit() else section
                par[f'{sec}_{key}'] = value.strip()
    return par


def read_bip(filename) -> Struct:
    """Port of ``kv3_LoadBIP``: binary parameter arrays sidecar (.bip)."""
    res = Struct()
    p = Path(filename)
    if not p.exists():
        return res
    b = p.read_bytes()
    if b[:4] != b'BIP1':
        return res
    pos = 4
    (count,) = struct.unpack_from('<I', b, pos)
    pos += 4
    try:
        for _ in range(count):
            (n,) = struct.unpack_from('<I', b, pos); pos += 4
            if n > 256:
                break
            name = b[pos:pos + n].decode('latin-1'); pos += n
            (n,) = struct.unpack_from('<I', b, pos); pos += 4
            if n > 64:
                break
            unit = b[pos:pos + n].decode('latin-1'); pos += n
            sig_digit, dtype, count_el = struct.unpack_from('<III', b, pos); pos += 12
            fmt, size = ('<f8', 8) if dtype == 0 else ('<f4', 4)
            data = np.frombuffer(b, dtype=fmt, count=count_el, offset=pos).astype(float)
            pos += size * count_el
            res[valid_field(name)] = Struct(data=[data], unit=unit, sig_digit=float(sig_digit))
    except struct.error:
        pass
    return res


def _sm_field(par: Struct, name: str) -> str:
    """Port of ``getSMfield``: values continued over ``name_0``, ``name_1``, ... lines."""
    s = par[name]
    if '*****' not in s:
        return s
    out, i = '', 0
    while f'{name}_{i}' in par:
        s1 = par[f'{name}_{i}']
        if '*****' in s1:
            break
        a, b = s1.find('*'), s1.rfind('*')
        out += s1[a + 1:b]
        i += 1
    return out


def _sm_time(par: Struct):
    """Port of ``GetSMTime``: start, finish (datevec-like lists) and duration in min."""
    def parse(s):
        return datetime.strptime(' '.join(s.split()), '%a %b %d %H:%M:%S %Y')
    try:
        t0, t1 = parse(par['general_starttime']), parse(par['general_finishtime'])
    except (KeyError, ValueError):
        now = datetime.now()
        t0 = t1 = now
    vec = lambda t: [t.year, t.month, t.day, t.hour, t.minute, t.second]
    return vec(t0), vec(t1), (t1 - t0).total_seconds() / 60.0


def _split_sweep(s: str):
    """'X,341,1,Field' -> type, dim, reps, [vars] (MATLAB strtok semantics)."""
    parts = [p for p in s.split(',') if p != '']
    t = parts[0].strip()[:1]
    dim = float(parts[1])
    reps = float(parts[2]) if len(parts) > 2 else 1.0
    return t, dim, reps, parts[3:]


def specman_par(par: Struct) -> Struct:
    """Port of ``kv3_SpecManpar``: sweep description -> axes."""
    res = Struct(title=par.get('general_name', '?'))
    sweepax = []
    key = 'sweep_transient'
    idx = 0
    triggers = float(par.get('streams_triggers', '1').split(',')[0] or 1)
    scans = [float(v) for v in par.get('streams_scans', '1').split(',') if v.strip()] or [1.0]
    shots = 1.0
    while key in par:
        t, dim, reps, var = _split_sweep(par[key])
        ax = Struct(t=t, dim=dim, size=dim if t in 'XYZT' else 1, reps=reps, var=var, triggers=1)
        shots *= dim * reps if t == 'S' else reps
        sweepax.append(ax)
        key = f'sweep_sweep{idx}'
        idx += 1
    if sweepax:
        sweepax[0].triggers = triggers
    res.sweepax = sweepax
    res.shots = shots
    res.scans = scans[0]

    labels = 'xyzijkl'
    counter = 0
    for sa in [a for a in sweepax if a.size > 1 or a.triggers > 1]:
        asize = int(sa.size)
        name = labels[counter]
        if sa.t in ('I', 'A'):
            res[name] = np.arange(1.0, sa.triggers + 1)
            res[name + 'label'] = 'triggers'
        elif sa.t == 'T':
            if sa.triggers > 1:
                res[name] = np.arange(1.0, sa.triggers + 1)
                res[name + 'label'] = 'triggers'
                if asize > 1:
                    counter += 1
                    name = labels[counter]
            if asize > 1:
                dwell = par.get('streams_dwelltime', '1 ns').split(',')[0].strip()
                res[name] = get_array(f'0 ns step {dwell};', asize)
                res[name + 'label'] = 'transient, s'
        else:
            pname = sa.var[0].replace(' ', '_') if sa.var else ''
            if f'params_{pname}' in par:
                s = _sm_field(par, f'params_{pname}')
                unit = ''
                if s.startswith('@bip'):
                    pa = par.get(f'param_arrays_{pname}')
                    values = np.asarray(pa.data[0], float) if pa and pa.get('data') else np.array([])
                    unit = (pa or {}).get('unit', '')
                else:
                    values = get_array(s, asize)
                    unit = get_val(s)[1]
                res[name] = values
                res[name + 'label'] = f'{pname}, {unit or "a.u."}'
        counter += 1
    res.StartTime, res.FinishTime, res.ExpTime = _sm_time(par)
    return res


def d01read(filename):
    """Port of ``kv3_d01read``: ``ax, y, dsc`` from ``name.d01`` + ``name.exp``."""
    p = Path(filename)
    fname, dscname = p.with_suffix('.d01'), p.with_suffix('.exp')
    b = fname.read_bytes()
    ndim1, dformat = struct.unpack_from('<II', b, 0)
    if ndim1 == 0:
        raise ValueError('No data present')
    pos = 8
    streams, ntotal = [], 0
    for _ in range(ndim1):
        ndim2 = struct.unpack_from('<i', b, pos)[0]
        dims = list(struct.unpack_from('<4i', b, pos + 4))
        total = struct.unpack_from('<i', b, pos + 20)[0]
        pos += 24
        dims[ndim2:] = [1] * (4 - ndim2)
        if int(np.prod(dims)) != total:   # inconsistent header: keep the data as 1D
            dims = [total, 1, 1, 1]
        streams.append(Struct(dim=dims, first=ntotal, total=total))
        ntotal += total
    dt = '<f4' if dformat == 1 else '<f8'
    tmp = np.frombuffer(b, dtype=dt, count=ntotal, offset=pos).astype(float)

    def stream(k):
        s = streams[k]
        return tmp[s.first:s.first + s.total].reshape(s.dim, order='F')

    dsc = read_exp(dscname)
    for name, v in read_bip(p.with_suffix('.bip')).items():
        dsc[f'param_arrays_{name}'] = v
    ax = specman_par(dsc)
    if not ax.get('ylabel'):
        ax.ylabel = 'Intensity'
    try:
        d0 = streams[0].dim
        ax.raw = tmp.reshape((d0[0], d0[1], ndim1), order='F')
    except ValueError:
        pass

    if ndim1 > 1 and streams[1].dim == streams[0].dim:
        spec = stream(0) + 1j * stream(1)
        ax.data = [stream(k) / ax.scans for k in range(2, ndim1)]
    elif ndim1 > 1:
        spec = stream(0)
        ax.data = [stream(k) / ax.scans for k in range(1, ndim1)]
    else:
        spec = stream(0)

    n = spec.shape[0]
    x = ax.get('x')
    ax.x = np.arange(1.0, n + 1) if x is None or len(x) < n else np.asarray(x)[:n]
    ax.type = 'data'
    ax.RepTime = getvalue(dsc.get('params_RepTime', '1 us'))[0]
    ax.unit = dsc.get('streams_units', '').split(',')[0].strip() or 'a.u.'
    scans = getvalue(dsc.get('streams_scans', '1,1,1,1'))[0]
    if scans and scans == scans:   # 0 / missing scans: leave the data unscaled
        spec = spec / scans
    dsc.KAZANformat = 'SPECMAND01'
    return ax, spec, dsc


# =====================================================================  .tdms

_TDMS_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)
_TDMS_SCALAR = {1: 'i1', 2: 'i2', 3: 'i4', 4: 'i8', 5: 'u1', 6: 'u2', 7: 'u4', 8: 'u8',
                9: 'f4', 10: 'f8', 25: 'f4', 26: 'f8'}


def _tdms_time(b: bytes, pos: int, e: str) -> datetime:
    frac, sec = struct.unpack_from(e + 'Qq', b, pos)
    return (_TDMS_EPOCH + timedelta(seconds=sec + frac / 2 ** 64)).astimezone()


def load_tdms(filename) -> Struct:
    """Port of ``kv3_LoadTDMS``.

    Result: ``tdms.root`` (file properties), ``tdms.<group>`` (group properties plus
    one Struct per channel); every raw-data chunk of a channel is appended to the
    channel's ``data`` list, as in MATLAB (the stream assembly depends on it).
    """
    b = Path(filename).read_bytes()
    tdms = Struct(root=Struct())
    pos, end = 0, len(b)
    last_index: dict[tuple, tuple] = {}

    def get_string(p, e):
        (n,) = struct.unpack_from(e + 'I', b, p)
        if n > 4_000_000:
            raise ValueError('Too long string (suspicious).')
        return b[p + 4:p + 4 + n].decode('utf-8', errors='replace'), p + 4 + n

    def get_obj(t1, t2):
        grp = tdms.setdefault(t1, Struct())
        return grp if not t2 else grp.setdefault(t2, Struct())

    while pos < end - 4:
        if b[pos:pos + 4] != b'TDSm':
            raise ValueError(f'TDMS tag is not recognized at position {pos}')
        (toc,) = struct.unpack_from('<I', b, pos + 4)
        e = '>' if toc & (1 << 6) else '<'
        seg_len, _raw_len = struct.unpack_from(e + 'QQ', b, pos + 12)
        next_seg = pos + 28 + seg_len
        p = pos + 28
        raw_idx = []
        if toc & (1 << 1):          # kTocMetaData
            (nobj,) = struct.unpack_from(e + 'I', b, p); p += 4
            for _ in range(nobj):
                path, p = get_string(p, e)
                parts = [valid_field(s) for s in path.split('/')[1:] if s != ''] if path != '/' else []
                t1, t2 = (parts + ['', ''])[:2] if parts else ('root', '')
                (desc_len,) = struct.unpack_from(e + 'I', b, p); p += 4
                if desc_len == 20:
                    dtype, _dim, n = struct.unpack_from(e + 'IIQ', b, p)
                    p += 16
                    last_index[(t1, t2)] = (dtype, n)
                    raw_idx.append((t1, t2, dtype, n))
                elif desc_len == 0 and (t1, t2) in last_index:   # same as previous segment
                    raw_idx.append((t1, t2) + last_index[(t1, t2)])
                else:
                    p += 0 if desc_len in (0, 0xFFFFFFFF) else desc_len - 4
                obj = get_obj(t1, t2)
                (nprop,) = struct.unpack_from(e + 'I', b, p); p += 4
                for _ in range(nprop):
                    name, p = get_string(p, e)
                    (ptype,) = struct.unpack_from(e + 'i', b, p); p += 4
                    if ptype in _TDMS_SCALAR:
                        dt = np.dtype(_TDMS_SCALAR[ptype]).newbyteorder(e)
                        value = np.frombuffer(b, dt, 1, p)[0].item()
                        p += dt.itemsize
                    elif ptype == 32:
                        value, p = get_string(p, e)
                    elif ptype == 33:
                        value = b[p] != 0
                        p += 1
                    elif ptype == 68:
                        value = _tdms_time(b, p, e)
                        p += 16
                    else:
                        raise ValueError(f'Unknown TDMS property type {ptype}')
                    obj[valid_field(name)] = value
        if toc & (1 << 3) and toc & (1 << 5) and raw_idx and all(r[2] in _TDMS_SCALAR for r in raw_idx):
            # kTocInterleavedData: values of all channels alternate (MATLAB did not support this)
            rec = np.dtype([(f'c{i}', np.dtype(_TDMS_SCALAR[r[2]]).newbyteorder(e))
                            for i, r in enumerate(raw_idx)])
            n = min(r[3] for r in raw_idx)
            table = np.frombuffer(b, rec, n, p)
            for i, (t1, t2, dtype, _n) in enumerate(raw_idx):
                obj = get_obj(t1, t2)
                obj.setdefault('data', [])
                if n:
                    obj.data.append(table[f'c{i}'].astype(float))
        elif toc & (1 << 3):        # kTocRawData
            for t1, t2, dtype, n in raw_idx:
                if dtype in _TDMS_SCALAR:
                    dt = np.dtype(_TDMS_SCALAR[dtype]).newbyteorder(e)
                    data = np.frombuffer(b, dt, n, p).astype(float if dtype >= 9 else dt.newbyteorder('='))
                    p += dt.itemsize * n
                elif dtype == 33:
                    data = np.frombuffer(b, 'u1', n, p) != 0
                    p += n
                elif dtype == 68:
                    data = [_tdms_time(b, p + 16 * i, e) for i in range(n)]
                    p += 16 * n
                else:
                    raise ValueError(f'Unknown TDMS data type {dtype}')
                obj = get_obj(t1, t2)
                obj.setdefault('data', [])
                if len(data):
                    obj.data.append(data)
        pos = next_seg
    return tdms


def _stream_to_array(ch: Struct) -> tuple[np.ndarray, bool]:
    """Port of ``TDMS_StreamToArray``. Returns the array and whether it was complete."""
    dims = [int(ch.get(f'dim{i}', 1) or 1) for i in range(1, 5)]
    total = int(np.prod(dims))
    chunks = ch.get('data') or []
    if not chunks:
        return np.zeros(dims), False
    size = len(chunks[0])
    one_set = max(total // size, 1)
    n_rep = len(chunks) // one_set
    data = np.zeros((size, one_set))
    for i in range(min(one_set, len(chunks))):
        data[:, i] = chunks[i]
    complete = len(chunks) >= one_set
    if n_rep > 1:
        # MATLAB divided only the last column by n_rep; all columns are averaged here
        for j in range(1, n_rep):
            for i in range(one_set):
                data[:, i] += chunks[i + one_set * j]
        data /= n_rep
    return data.reshape(dims, order='F'), complete


def specman_tdms_par(tdms: Struct) -> Struct:
    """Port of ``kv3_SpecManTDMSpar``."""
    prefix = ['n', 'u', 'm', 'k', 'M', 'G']
    koeff = [1e-9, 1e-6, 1e-3, 1e3, 1e6, 1e9]
    root, axis = tdms.root, tdms.get('axis') or Struct()
    params = Struct(tdms.get('params') or {})
    ref = tdms.streams.Re
    res = Struct(title=root.get('name', '?'))
    triggers = float(ref.get('triggers', 1) or 1)

    sweepax, shots, key, idx = [], 1.0, 'transient', 0
    while key in axis:
        t, dim, reps, var = _split_sweep(axis[key])
        size = 1.0 if t in 'SIAR' else dim
        shots *= dim * reps if t == 'S' else reps
        sweepax.append(Struct(t=t, dim=dim, size=size, reps=reps, var=var))
        key = f'sweep{idx}'
        idx += 1
    if sweepax:
        sweepax[0].size *= triggers
    res.sweepax = sweepax
    res.shots = shots

    labels = 'xyzabc'
    counter = 0
    for sa in sweepax:
        asize = int(sa.size)
        if asize <= 1:
            continue
        if sa.t in ('I', 'A'):
            pname = 'trans'
            params.trans = '1sl step 1sl;'
        elif sa.t == 'T':
            pname = 'trans'
            params.trans = f"0 ns step {float(ref.get('dwelltime', 1e-9)) * 1e9:f} ns"
        else:
            pname = sa.var[0].replace(' ', '_')
        unit, arr, label_unit = '', np.array([]), None
        if pname in params:
            s = str(params[pname])
            if s.startswith('@bip'):
                pa = (tdms.get('param_arrays') or {}).get(pname)
                if pa and pa.get('data'):
                    arr = np.asarray(pa.data[0], float)
                    unit = pa.get('unit', '')
            elif 'step' in s:
                a, rest = s.split('step', 1)
                minval, unit, _, _ = getvalue(a)
                arr = minval + np.arange(asize) * getvalue(rest.split(';')[0])[0]
            elif 'logto' in s:
                a, rest = s.split('logto', 1)
                minval, unit, _, _ = getvalue(a)
                arr = np.logspace(np.log10(minval), np.log10(getvalue(rest.split(';')[0])[0]), asize)
            elif 'to' in s:
                a, rest = s.split('to', 1)
                minval, unit, _, _ = getvalue(a)
                arr = np.linspace(minval, getvalue(rest.split(';')[0])[0], asize)
            elif ':' in s.split(';')[0]:
                # 'mm:0,-50,50;p;X@STAGE' - unit-prefixed list (MATLAB textscan stops at ';')
                list_unit, values = s.split(';')[0].split(':', 1)
                arr = np.array([getvalue(v)[0] for v in values.split(',') if v.strip()])
                label_unit = list_unit.strip()
            else:
                vals = []
                for tok in s.split(';')[0].split(','):
                    if tok.strip():
                        v, unit, _, _ = getvalue(tok)
                        vals.append(v)
                arr = np.array(vals)
        else:
            arr = np.arange(float(asize))
            unit = 's'
        if unit not in ('G', 'K', 's', '') and arr.size:
            umax = np.max(np.abs(arr))
            for kk in range(len(koeff) - 1, -1, -1):
                if umax > koeff[kk]:
                    unit = prefix[kk] + unit
                    arr = arr / koeff[kk]
                    break
        arr = arr[:asize]
        res[labels[counter]] = arr
        res[labels[counter] + 'label'] = f'{sa.var[0] if sa.var else pname}, {label_unit or unit}'
        counter += 1
    res.StartTime = root.get('starttime')
    res.FinishTime = root.get('finishtime')
    res.ExpTime = root.get('totaltime')
    res.RepTime = get_val(str(params.get('RepTime', '15 us')))[0]
    return res


def smtdmsread(filename):
    """Port of ``kv3_smtdmsread``: ``ax, y, dsc`` from a SpecMan4EPR .tdms file."""
    tdms = load_tdms(filename)
    streams = tdms.get('streams')
    if not streams or 'Re' not in streams:
        raise ValueError('No SpecMan streams in this TDMS file')
    re_, ok_re = _stream_to_array(streams.Re)
    im_, ok_im = _stream_to_array(streams.Im) if 'Im' in streams else (np.zeros_like(re_), True)
    spec = re_ + 1j * im_
    ax = specman_tdms_par(tdms)
    if not ax.get('ylabel'):
        ax.ylabel = 'Intensity'
    channel_names = [k for k, v in streams.items() if isinstance(v, Struct) and 'data' in v]
    ax.raw = [_stream_to_array(streams[k])[0] for k in channel_names]
    x = ax.get('x')
    if x is None or len(x) != spec.shape[0]:
        ax.x = np.arange(1.0, spec.shape[0] + 1)
    ax.type = 'data'
    if 'freq1' in tdms.root:
        ax.freq1 = getvalue(tdms.root.freq1)[0]
    ax.unit = streams.Re.get('unit') or 'a.u.'

    # dsc = root properties + flattened sections, as MATLAB 'case 2'
    dsc = Struct(tdms.root)
    for sec in ('axis', 'params', 'exp_info', 'sample_info', 'devices', 'param_arrays'):
        for k, v in (tdms.get(sec) or {}).items():
            dsc[f'{sec}_{k}'] = v
    for dev, props in (tdms.get('devices') or {}).items():
        if isinstance(props, Struct):
            for k, v in props.items():
                dsc[f'{dev}_{k}'] = v
    if not (ok_re and ok_im):
        dsc.KAZANwarning = 'Incomplete data: missing scans are zero'
    dsc.KAZANformat = 'SPECMANTDMS'
    return ax, spec, dsc


# =====================================================================  .d01 variants / .d02

def _d01_streams(fname: Path) -> list[np.ndarray]:
    """Raw streams of a ``.d01`` file (column-major, header dimensions)."""
    b = Path(fname).read_bytes()
    ndim1, dformat = struct.unpack_from('<II', b, 0)
    pos, heads = 8, []
    for _ in range(ndim1):
        ndim2 = struct.unpack_from('<i', b, pos)[0]
        dims = list(struct.unpack_from('<4i', b, pos + 4))
        total = struct.unpack_from('<i', b, pos + 20)[0]
        dims[ndim2:] = [1] * (4 - ndim2)
        heads.append((dims, total))
        pos += 24
    dt = '<f4' if dformat == 1 else '<f8'
    out = []
    for dims, total in heads:
        a = np.frombuffer(b, dtype=dt, count=total, offset=pos).astype(float)
        pos += total * np.dtype(dt).itemsize
        out.append(a.reshape(dims, order='F') if int(np.prod(dims)) == total else a)
    return out


def _resample_field(ax, spec, field):
    """Put the data on an even field axis from the measured field values."""
    field = np.ravel(field)
    ax.x = np.linspace(field.min(), field.max(), len(field))
    f, idx = np.unique(field, return_index=True)
    s = spec.reshape(spec.shape[0], -1)[idx]
    cols = [np.interp(ax.x, f, c.real) + (1j * np.interp(ax.x, f, c.imag) if np.iscomplexobj(c) else 0)
            for c in s.T]
    return np.column_stack(cols)


def d01read_field(filename):
    """Port of ``kv3_d01read_field`` (SpecManFLD): ``.d01`` with the field measured by
    a field meter (first extra stream) when ``sweep1`` sweeps ``FieldM``; the data are
    resampled onto an even field axis."""
    ax, spec, dsc = d01read(filename)
    data = ax.get('data') or []
    if 'aquisition_FieldM' in dsc and 'FieldM' in dsc.get('sweep_sweep1', '') and data:
        print('kv_d01read_field: resampling field axis.')
        spec = _resample_field(ax, spec, np.asarray(data[0]) * ax.scans)
    return ax, spec, dsc


def nist_d01read(filename):
    """Port of ``kv_nistd01read`` (SpecManNIST): extra streams are divided by their own
    scan counts; with ``aquisition_FieldM`` the data are resampled on the field from
    stream 3."""
    ax, spec, dsc = d01read(filename)
    dsc.KAZANformat = 'SPECMANNISTD01'
    streams = _d01_streams(Path(filename).with_suffix('.d01'))
    scans = [float(v) for v in dsc.get('streams_scans', '1').split(',') if v.strip()] or [1.0]
    first = 2 if len(streams) > 1 and streams[1].shape == streams[0].shape else 1
    ax.data = [streams[k] / (scans[k] if k < len(scans) and scans[k] else 1.0)
               for k in range(first, len(streams))]
    if 'aquisition_FieldM' in dsc and len(streams) >= 3:
        print('kv_nistd01read: resampling field axis.')
        spec = _resample_field(ax, spec, streams[2])
    return ax, spec, dsc


def d02read(filename):
    """Port of ``kv_d02read`` (SpecManRAW): ``.d02`` pairs (uint32 index, float32 value)
    of every scan; output is one column per scan."""
    p = Path(filename)
    dsc = read_exp(p.with_suffix('.exp'))
    ax = specman_par(dsc)
    sweepax = ax.sweepax
    sz = int(np.prod([a.size for a in sweepax])) if sweepax else 1
    hidden = int(np.prod([a.dim for a in sweepax if a.t == 'S'])) if sweepax else 1
    channels = len(sweepax[0].var) if sweepax and sweepax[0].var else 1
    x = np.asarray(ax.get('x', np.arange(1.0, sz + 1)), float)
    if hidden > 1:
        span = x.max() - x.min()
        ax.x = np.concatenate([x + k * span * 1.1 for k in range(hidden)])
    raw = np.fromfile(p.with_suffix('.d02'), dtype=np.dtype([('i', '<u4'), ('v', '<f4')]))
    points = len(raw)
    full_size = sz * hidden
    full_scans = points // (sz * channels * hidden)
    n = channels * full_size * full_scans
    idx = raw['i'][:n].astype(np.int64)
    if hidden > 1:
        idx = idx + (np.arange(n) % hidden) * sz
    idx = idx.reshape((channels * full_size, full_scans), order='F')
    idx = idx + np.arange(full_scans)[None, :] * channels * full_size
    buf = np.zeros(n)
    buf[idx.ravel(order='F')] = raw['v'][:n]
    buf = buf.reshape((full_size, channels, full_scans), order='F')
    spec = buf[:, 0, :] + (1j * buf[:, 1, :] if channels == 2 else 0)
    if len(np.ravel(ax.get('x', []))) != full_size:
        ax.x = np.arange(1.0, full_size + 1)
    ax.y, ax.ylabel = np.arange(1.0, full_scans + 1), 'scans'
    ax.type = 'data'
    dsc.KAZANformat = 'SPECMAND01'
    return ax, spec, dsc
