"""Kazan data structure: Python port of the MATLAB ``src``/``out`` struct and ``Verify()``.

Conventions (differences from MATLAB are deliberate and minimal):

* ``y`` is always a 2-D numpy array of shape ``(n1, n2)``; a 1-D trace is ``(n, 1)``
  (MATLAB column vector).
* ``ax.x`` and ``ax.y`` are 1-D numpy arrays (MATLAB column vectors ``(:)``).
* ``ax`` and ``dsc`` are open-ended :class:`Struct` objects, so plugin code such as
  ``d.ax.Color = 'r'`` ports unchanged.
* MATLAB structs are copied on assignment, Python objects are shared. Use
  :meth:`KzData.copy` before changing data you did not create.
"""
from __future__ import annotations

import copy as _copy
from dataclasses import dataclass, field

import numpy as np


class Struct(dict):
    """dict with MATLAB-struct style attribute access.

    Missing fields read as ``None`` (like ``kv3_safeget`` with an empty default),
    so ``d.ax.Color or 'b'`` works. Use ``d.ax.get('tc', 5)`` for other defaults.
    """

    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError(key)
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key) from None

    def copy(self) -> Struct:
        """Deep copy (MATLAB value semantics)."""
        return _copy.deepcopy(self)


@dataclass
class KzData:
    """One data set: the MATLAB ``src`` / ``out{k}`` struct."""

    y: np.ndarray = field(default_factory=lambda: np.zeros((0, 1)))
    ax: Struct = field(default_factory=Struct)
    dsc: Struct = field(default_factory=Struct)
    filename: str = ''
    script: str = ''
    title: str = ''

    def copy(self) -> KzData:
        """Deep copy (MATLAB value semantics)."""
        return _copy.deepcopy(self)

    @property
    def is_empty(self) -> bool:
        return self.y.size == 0

    @property
    def is_2d(self) -> bool:
        return self.y.ndim == 2 and self.y.shape[1] > 1


def verify(d: KzData) -> KzData:
    """Port of ``kazan3.Verify``: normalise shapes and fill in default fields.

    Modifies ``d`` in place and returns it.
    """
    if not isinstance(d.ax, Struct):
        d.ax = Struct(d.ax or {})
    if not isinstance(d.dsc, Struct):
        d.dsc = Struct(d.dsc or {})

    y = np.asarray(d.y)
    if y.ndim == 0:
        y = y.reshape(1, 1)
    elif y.ndim == 1:
        y = y[:, None]
    elif y.ndim == 2 and y.shape[0] == 1 and y.shape[1] > 1:
        y = y.T  # MATLAB: a row vector becomes a column
    d.y = y

    n1 = y.shape[0]
    n2 = y.shape[1] if y.ndim > 1 else 1
    for key, n in (('x', n1), ('y', n2)):
        v = d.ax.get(key)
        d.ax[key] = np.arange(1.0, n + 1.0) if v is None else np.asarray(v).ravel()
    d.ax.setdefault('xlabel', 'unknown, pnt')
    d.ax.setdefault('ylabel', 'unknown, pnt')
    d.ax.setdefault('filt', 'none')
    d.ax.setdefault('diff', 'normal')
    d.ax.setdefault('filtpar1', 'auto')

    d.filename = d.filename or ''
    d.script = d.script or ''
    d.title = d.title or ''
    return d
