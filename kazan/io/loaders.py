"""File loaders: port of ``kv3_ScriptLoad``.

Every loader has the MATLAB signature ``ax, y, dsc = loader(filename, **options)``.
The extension / subtype lists mirror the MATLAB ones so the dropdowns look the same;
subtypes without a Python loader (RMNdat2D, transient, UofC_bin, UofC_img, WEBMOSS: no
MATLAB source or helpers available) raise :class:`NotImplementedError`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import ascii, bruker, nmr, other, specman

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


@dataclass
class LoadOption:
    """One loader option control (MATLAB ``kv3_ScriptLoad('options')``): a drop-down
    (``items`` = (label, value) pairs) or, with ``items=None``, a text field."""
    items: list | None
    default: object = None
    tooltip: str = ''


_ASCII_OPTIONS = [LoadOption(ascii.DELIMITERS, '	', 'Column delimiter'),
                  LoadOption(ascii.LAYOUTS, 3, 'Column layout'),
                  LoadOption(None, 'Time, s', 'X axis label (when the file has none)')]

#: subtype -> option controls (index 0, 1: drop-downs, 2: text field)
OPTIONS: dict[str, list[LoadOption]] = {
    'ASCII': _ASCII_OPTIONS,
    'ASCII2D': [LoadOption([('complex (re, im)', True), ('real', False)], True, 'Values'),
                LoadOption([('Not used', 1)], 1),
                LoadOption(None, '128 64 1e-6 1e-6 0', 'xsize ysize [xdwell ydwell cfreq]')],
    'RMN_2D': [LoadOption(nmr.RMN2D_TYPES, '2DTT', 'Axis types'),
               LoadOption([('Not used', 1)], 1), LoadOption(None, '')],
    'SpecMan': [LoadOption(specman.STREAM_MODES, 'complex',
                           'Re + i Im: the first two streams as one complex signal; '
                           'All streams: every stream as a real trace (2D)')],
    'OPUS_FTIR': [LoadOption(other.OPUS_PARTS, 1, 'Data part'),
                  LoadOption([('Not used', 1)], 1), LoadOption(None, '')],
}


def options(subtype: str) -> list[LoadOption]:
    return OPTIONS.get(subtype, [])


def _opt(values, k, default):
    return values[k] if values and len(values) > k and values[k] is not None else default


def _ascii(f, o):
    return ascii.ascii_load(f, _opt(o, 0, '	'), int(_opt(o, 1, 3)), str(_opt(o, 2, '')))


# (extension, subtype) -> loader(filename, option values); (None, subtype) for any extension
LOADERS: dict[tuple, Callable] = {
    (None, 'ASCII'): _ascii,
    (None, 'ASCII2D'): lambda f, o: ascii.ascii2d_load(f, str(_opt(o, 2, '')), bool(_opt(o, 0, True))),
    (None, 'XEPR'): lambda f, o: bruker.brukerread(f),
    (None, 'XEPR_JSS'): lambda f, o: bruker.brukerread_jss(f),
    (None, 'ASTASHKIN'): lambda f, o: other.astashkin_read(f),
    ('*.tdms', 'SpecMan'): lambda f, o: specman.smtdmsread(f, _opt(o, 0, 'complex')),
    ('*.exp', 'SpecMan'): lambda f, o: specman.d01read(f, _opt(o, 0, 'complex')),
    ('*.d01', 'SpecMan'): lambda f, o: specman.d01read(f, _opt(o, 0, 'complex')),
    (None, 'SpecManNIST'): lambda f, o: specman.nist_d01read(f),
    (None, 'SpecManFLD'): lambda f, o: specman.d01read_field(f),
    (None, 'SpecManRAW'): lambda f, o: specman.d02read(f),
    (None, 'RMN_1D'): lambda f, o: nmr.rmnread(f, '1D'),
    (None, 'RMN_2D'): lambda f, o: nmr.rmnread(f, '2D', str(_opt(o, 0, '2DTT'))),
    (None, 'RMNdat'): lambda f, o: nmr.rmnread(f, '1dtxt'),
    (None, 'XWINNMR'): lambda f, o: nmr.xwinnmr(f),
    (None, 'WINNMR'): lambda f, o: nmr.winnmr(f),
    (None, 'TecMag'): lambda f, o: nmr.tecmag_read(f),
    (None, 'Spinsight'): lambda f, o: nmr.spinsight_read(f),
    (None, 'OPUS_FTIR'): lambda f, o: other.opus_read(f, int(_opt(o, 0, 1))),
    (None, 'image'): lambda f, o: other.image_read(f),
}


def load(filename: str, ext: str, subtype: str, option_values: list | None = None):
    """Run the loader for ``ext`` + ``subtype``; returns ``(ax, y, dsc)``.

    ``option_values`` are the values of the :func:`options` controls (defaults if None).
    """
    loader = LOADERS.get((ext, subtype)) or LOADERS.get((None, subtype))
    if loader is None:
        raise NotImplementedError(f"Loader '{subtype}' ({ext}) is not ported yet")
    if option_values is None:
        option_values = [o.default for o in options(subtype)]
    return loader(str(Path(filename)), option_values)
