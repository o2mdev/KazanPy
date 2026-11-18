"""File loaders: port of ``kv3_ScriptLoad``.

Every loader has the MATLAB signature ``ax, y, dsc = loader(filename, **options)``.
The extension / subtype lists mirror the MATLAB ones so the dropdowns look the same;
subtypes without a Python loader yet raise :class:`NotImplementedError`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import numpy as np

from ..core.data import Struct
from . import bruker, specman

EXTENSIONS = ['*.', '*.aqs', '*.img', '*.jpg', '*.dat', '*.d00', '*.d01', '*.d02', '*.dsc',
              '*.exp', '*.par', '*.rmn', '*.tdms', '*.txt', '*']

SUBTYPES = {
    '*': ['ASCII', 'ASCII2D', 'UofC_bin', 'RMN_1D', 'RMN_2D', 'TecMag', 'XWINNMR', 'WINNMR',
          'WEBMOSS', 'OPUS_FTIR', 'image'],
    '*.': ['ASCII', 'ASCII2D', 'RMN_1D', 'RMN_2D', 'Spinsight', 'TecMag', 'XWINNMR', 'WINNMR'],
    '*.aqs': ['WINNMR'],
    '*.dat': ['ASCII', 'ASCII2D', 'XEPR', 'RMNdat', 'RMNdat2D', 'transient'],
    '*.img': ['UofC_img'],
    '*.tdms': ['SpecMan'],
    '*.txt': ['ASCII', 'ASCII2D'],
    '*.exp': ['SpecMan'],
    '*.par': ['XEPR', 'XEPR_JSS', 'ASTASHKIN'],
    '*.dsc': ['XEPR', 'XEPR_JSS', 'ASTASHKIN'],
    '*.rmn': ['RMN_1D', 'RMN_2D'],
    '*.d01': ['SpecMan', 'SpecManNIST', 'SpecManFLD'],
    '*.d02': ['SpecManRAW'],
    '*.jpg': ['image'],
}


def subtypes(ext: str) -> list[str]:
    return SUBTYPES.get(ext, ['---'])


_NUM_SPLIT = re.compile(r'[\s,;]+')


def ascii_read(filename: str, first_column_x: bool = True):
    """Port of ``kv3_asciiread``: numeric rows become data, other lines go to dsc."""
    rows, text = [], []
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            parts = [p for p in _NUM_SPLIT.split(line.strip()) if p]
            try:
                values = [float(p) for p in parts]
            except ValueError:
                values = []
            if values and (not rows or len(values) == len(rows[0])):
                rows.append(values)
            elif line.strip():
                text.append(line.rstrip('\n'))
    if not rows:
        raise ValueError('No numeric data found')
    data = np.array(rows)

    ax = Struct(type='data', xlabel='?', ylabel='Intensity', unit='a.u.')
    if first_column_x and data.shape[1] > 1:
        ax.x = data[:, 0]
        y = data[:, 1:]
    else:
        ax.x = np.arange(1.0, data.shape[0] + 1.0)
        y = data
    dsc = Struct(ASCII='ASCII loader for KAZAN viewer')
    for i, s in enumerate(text, 1):
        dsc[f'c{i}'] = s
    return ax, y, dsc


# (extension, subtype) -> loader; (None, subtype) applies to any extension
LOADERS: dict[tuple, Callable] = {
    (None, 'ASCII'): ascii_read,
    (None, 'XEPR'): bruker.brukerread,
    ('*.tdms', 'SpecMan'): specman.smtdmsread,
    ('*.exp', 'SpecMan'): specman.d01read,
    ('*.d01', 'SpecMan'): specman.d01read,
}


def load(filename: str, ext: str, subtype: str, **options):
    """Run the loader for ``ext`` + ``subtype``; returns ``(ax, y, dsc)``."""
    loader = LOADERS.get((ext, subtype)) or LOADERS.get((None, subtype))
    if loader is None:
        raise NotImplementedError(f"Loader '{subtype}' ({ext}) is not ported yet")
    return loader(str(Path(filename)), **options)
