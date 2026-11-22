"""Comparison box: port of CompBox3.mlapp.

Collects snapshots of the viewer source as traces and shows them together in Output,
each with its own colour, X/Y shift, X/Y zoom (linear or dB) and sign. Processing menu:
normalisation, fit to the first trace, waterfall, join traces into 2D, ungroup 2D,
sort, add all.

Differences from MATLAB (see Documentation/plugins.md):
* *Join Traces*, *Ungroup Data*, *Add Current To Output* and *Normalize Current 2D*
  work (in MATLAB they called undefined functions/fields and failed).
* *Add All* and *Join Traces* also apply Zoom X and dB zoom, as the plot does.
* *Change* keeps the colour of the trace; *Delete* / *Delete All* refresh the Output.
* The second-dimension field is editable: it sets the trace's Y axis values
  (used by *Sort By Y Value* and *Join Traces*).
* The trace list shows the file name without the folder.
* *Add* / *Change* are *Add Source* / *Change from Source*; *Add Output* and *Change from
  Output* (new) take the viewer output. *Inverse Y*, *Delete All* and *Combine All
  Traces to 2D* (a check box: Output shows the traces combined, the traces are kept)
  are in the *Options* button menu.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QGridLayout, QInputDialog, QLabel,
                               QLineEdit, QMenu, QPushButton, QWidget)
from scipy.interpolate import CubicSpline

from kazan.core import KazanPlugin, KzData, Struct
from kazan.core.processing import process
from kazan.viewer.plot import to_qcolor
from kazan.viewer.widgets import SciSpinBox

PALETTE = [(0, 0, 1), (1, 0, 0), (0, 1, 0), (0, 0, 0), (1, 0, 1), (0, 1, 1), (1, 1, 0)]
SHIFT_STEPS = ['1e-7', '1e-6', '1e-5', '1e-4', '0.001', '0.01', '0.1', '1', '10', '100', '1000',
               '1e4', '1e5', '1e6', '1e7', '1e8']
ZOOM_STEPS = ['1e-5', '1e-4', '1e-3', '0.001', '0.01', '0.1', '1', '10', '100', '1000', '1e4',
              '1e5', '1e6']


def _pp(y) -> tuple[float, float]:
    r = np.real(y)
    return float(np.nanmin(r)), float(np.nanmax(r))


def _interp(x, y, xq):
    """interp1 column-wise, NaN outside."""
    order = np.argsort(x)
    xs = np.asarray(x)[order]
    y = np.asarray(y)[order].reshape(len(xs), -1)
    out = np.empty((len(xq), y.shape[1]), dtype=complex if np.iscomplexobj(y) else float)
    for k in range(y.shape[1]):
        f = (lambda c: np.interp(xq, xs, c, left=np.nan, right=np.nan))
        col = y[:, k]
        out[:, k] = f(col.real) + 1j * f(col.imag) if np.iscomplexobj(col) else f(col)
    return out


class CompBox3(KazanPlugin):
    menu_name = 'COMPBOX3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('Comp. Box')
        self.resize(300, 420)
        self.traces: list[dict] = []
        self._build_menus()
        self._build_ui()
        self.update_list()
        self.update_interface()

    # ================================================================ UI
    def _build_menus(self):
        m = self.menuBar().addMenu('Processing')
        m.addAction('Fit All to 1st').triggered.connect(self.fit_all_to_first)
        m.addAction('Normalize Current 2D').triggered.connect(self.normalize_slices)
        m.addAction('Normalize All Traces').triggered.connect(self.normalize_all)
        m.addSeparator()
        self.mPreserveZero = QAction('Preserve Zero', self, checkable=True)
        self.mPreserveZero.triggered.connect(self.plot_this)
        m.addAction(self.mPreserveZero)
        m.addSeparator()
        m.addAction('Waterfall').triggered.connect(lambda: self.waterfall(False))
        m.addAction('Waterfall 2D').triggered.connect(lambda: self.waterfall(True))
        m.addSeparator()
        m.addAction('Add Current To Output').triggered.connect(self.add_current_to_output)
        m.addAction('Join Traces').triggered.connect(self.join_traces)
        m.addAction('Ungroup Data').triggered.connect(self.ungroup)
        m.addAction('Sort By Y Value').triggered.connect(self.sort_by_y)
        m.addAction('Add All').triggered.connect(self.add_all)
        self.mDisChanges = m.addAction('Discard ..2D')
        self.mDisChanges.triggered.connect(self.discard_2d)
        self.mDisChanges.setVisible(False)
        m = self.menuBar().addMenu('Load Options')
        self.mProcessSource = QAction('Source processing', self, checkable=True)
        self.mProcessSource.triggered.connect(self.plot_this)
        m.addAction(self.mProcessSource)

    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(4, 4, 4, 4)
        g.setSpacing(3)
        for c in range(4):
            g.setColumnStretch(c, 1)

        self.ddTraces = QComboBox()
        self.ddTraces.currentIndexChanged.connect(lambda _i: self.update_interface())
        g.addWidget(self.ddTraces, 0, 0, 1, 4)
        self.txtColor = QLabel()
        self.txtColor.setFixedHeight(10)
        g.addWidget(self.txtColor, 1, 0, 1, 4)

        for c, (text, fn) in enumerate((('Norm', self.normalize_current),
                                        ('-> 1st', self.to_first), ('Color', self.change_color),
                                        ('Title', self.change_title))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            if c == 0:
                b.setToolTip('Set p-p to 1')
            g.addWidget(b, 2, c)

        self.spin = {}
        for row, (text, key, steps, default) in enumerate(
                (('Shift X', 'shift_x', SHIFT_STEPS, '0.1'), ('Shift Y', 'shift_y', SHIFT_STEPS, '0.1'),
                 (None, None, None, None),
                 ('Zoom X', 'zoom_x', ZOOM_STEPS, '1'), ('Zoom Y', 'zoom_y', ZOOM_STEPS, '1')), start=3):
            if text is None:
                g.setRowMinimumHeight(row, 6)
                continue
            g.addWidget(QLabel(text), row, 0)
            sp = SciSpinBox(step=float(default))
            dd = QComboBox()
            dd.addItems(steps)
            dd.setCurrentText(default)
            dd.currentTextChanged.connect(lambda t, s=sp: s.setSingleStep(float(t)))
            sp.valueChanged.connect(lambda v, k=key: self.value_changed(k, v))
            g.addWidget(dd, row, 2)
            g.addWidget(sp, row, 3)
            self.spin[key] = sp
        for row, what in ((4, 'shift'), (7, 'zoom')):
            b = QPushButton('Clear')
            b.clicked.connect(lambda _=False, k=what: self.value_changed(k))
            g.addWidget(b, row, 1)

        g.addWidget(QLabel('Y Units'), 8, 1)
        self.ddUnits = QComboBox()
        self.ddUnits.addItems(['linear', 'dB'])
        self.ddUnits.currentTextChanged.connect(self.units_changed)
        g.addWidget(self.ddUnits, 8, 2, 1, 2)
        self.eSecondDim = QLineEdit()
        self.eSecondDim.setPlaceholderText('2nd dimension (Y) value(s) of the trace')
        self.eSecondDim.setToolTip(
            'Second-dimension (Y axis) value of the current trace: one number per column,\n'
            'separated by spaces or commas; press Enter to apply.\n'
            'Used by Sort By Y Value and as the 2nd axis when traces are combined to 2D.')
        self.eSecondDim.editingFinished.connect(self._on_second_dim)
        g.addWidget(self.eSecondDim, 9, 0, 1, 4)

        self.bAdd = QPushButton('Add Source')
        self.bAdd.setToolTip('Add the viewer source as a new trace')
        self.bAdd.clicked.connect(self.add)
        g.addWidget(self.bAdd, 10, 0, 1, 2)
        self.bAddOutput = QPushButton('Add Output')
        self.bAddOutput.setToolTip('Add every trace of the viewer output (e.g. a fit from '
                                   'another plugin) as new traces, keeping their shifts')
        self.bAddOutput.clicked.connect(self.add_output)
        g.addWidget(self.bAddOutput, 10, 2, 1, 2)
        self.bChange = QPushButton('Change from Source')
        self.bChange.setToolTip('Replace the current trace with the viewer source')
        self.bChange.clicked.connect(self.change)
        g.addWidget(self.bChange, 11, 0, 1, 2)
        self.bChangeOutput = QPushButton('Change from Output')
        self.bChangeOutput.setToolTip('Replace the current trace with the viewer output '
                                      '(its first trace if there are several)')
        self.bChangeOutput.clicked.connect(self.change_output)
        g.addWidget(self.bChangeOutput, 11, 2, 1, 2)
        b = QPushButton('Delete Current')
        b.clicked.connect(self.delete_current)
        g.addWidget(b, 12, 0, 1, 2)

        self.mOptions = QMenu(self)
        self.mOptions.addAction('Inverse Y').triggered.connect(
            lambda: self.value_changed('invert'))
        self.mCombine = QAction('Combine All Traces to 2D', self, checkable=True)
        self.mCombine.setToolTip('Show all traces as one 2D set in Output; the traces '
                                 'themselves are not changed')
        self.mCombine.toggled.connect(self.plot_this)
        self.mOptions.addAction(self.mCombine)
        self.mOptions.addSeparator()
        self.mOptions.addAction('Delete All').triggered.connect(self.delete_all)
        self.bOptions = QPushButton('Options')
        self.bOptions.setMenu(self.mOptions)
        g.addWidget(self.bOptions, 12, 2, 1, 2)

    # ================================================================ helpers
    @property
    def num(self) -> int:
        return max(self.ddTraces.currentIndex(), 0)

    def _zoom(self, t: dict) -> float:
        return t['zoom_y'] if self.ddUnits.currentText() == 'linear' else 10 ** (t['zoom_y'] / 10)

    def _zoom_value(self, factor: float) -> float:
        return factor if self.ddUnits.currentText() == 'linear' else 10 * np.log10(factor)

    def _scaled_y(self, t: dict, y=None):
        y = t['data'].y if y is None else y
        y = y * self._zoom(t) * t['ysign']
        if t.get('change2d'):
            y = (y - t.get('shift_y2d', 0)) * t.get('zoom_y2d', 1)
        return y

    @staticmethod
    def _new_trace(data: KzData, name: str) -> dict:
        return dict(name=name, data=data, shift_x=0.0, shift_y=0.0, zoom_x=1.0, zoom_y=1.0,
                    ysign=1)

    def update_list(self):
        self.ddTraces.blockSignals(True)
        cur = self.ddTraces.currentIndex()
        self.ddTraces.clear()
        if self.traces:
            self.ddTraces.addItems([f'{i + 1}:{Path(t["name"]).name if t["name"] else ""}'
                                    for i, t in enumerate(self.traces)])
            self.ddTraces.setCurrentIndex(min(max(cur, 0), len(self.traces) - 1))
        else:
            self.ddTraces.addItem('-------')
        self.ddTraces.blockSignals(False)

    def update_interface(self):
        vals = dict(shift_x=0.0, shift_y=0.0, zoom_x=1.0, zoom_y=1.0)
        color, second = (0.75, 0.75, 0.75), '-'
        if self.traces:
            t = self.traces[self.num]
            vals = {k: t[k] for k in vals}
            color = t['data'].ax.Color
            second = ' '.join(f'{v:g}' for v in np.ravel(np.real(t['data'].ax.y)))
        for k, v in vals.items():
            self.spin[k].blockSignals(True)
            self.spin[k].setValue(float(v))
            self.spin[k].blockSignals(False)
        self.txtColor.setStyleSheet(f'background-color: {to_qcolor(color).name()};')
        self.eSecondDim.setText(second)

    # ================================================================ plotting
    def plot_this(self):
        if self.mCombine.isChecked() and self.traces:
            d = self._combine()
            if d is not None:
                self.host.set_data('output', [d])
                return
        out = []
        for kk, t in enumerate(self.traces):
            d = t['data'].copy()
            if not self.mProcessSource.isChecked():
                d.ax.filt = ''
                d.ax.diff = ''
            d.ax.x = np.asarray(d.ax.x) * t['zoom_x']
            d.y = self._scaled_y(t)
            d.ax.s = t['shift_y']
            d.ax.dx = t['shift_x']
            d.title = f'Trace{kk + 1}'
            out.append(d)
        self.host.set_data('output', out)

    def preprocess(self, t: dict):
        d = t['data'].copy()
        if self.mProcessSource.isChecked():
            d.ax.s = 0
            d, _ = process(d)
        xx = np.asarray(d.ax.x) * t['zoom_x'] + t['shift_x']
        return xx, self._scaled_y(t, d.y) + t['shift_y']

    # ================================================================ trace list
    def add(self):
        """Add Source: the viewer source becomes a new trace."""
        src = self.host.get_data('source')
        if src.is_empty:
            return
        self._append(src)
        self._added()

    def add_output(self):
        """Add Output: every trace shown in the viewer output becomes a new trace.

        Output traces are already processed, so their filter / derivative settings are
        cleared; their Y shift (ax.s) and X shift (ax.dx) become the trace's shifts.
        """
        out = self._output()
        for d in out:
            shifts = self._from_output(d)
            self._append(d, d.title or d.filename or '').update(shifts)
        if out:
            self._added()

    def _output(self) -> list[KzData]:
        out = [d for d in self.host.get_data('output') if not d.is_empty]
        if not out:
            self.host.set('message', 'Comp. Box: the output is empty')
        return out

    @staticmethod
    def _from_output(d: KzData) -> dict:
        """Take the plot shifts off an output trace (they become the trace's
        Shift X / Shift Y) and clear its processing (output is already processed)."""
        shifts = {}
        for key, v in (('shift_y', d.ax.s), ('shift_x', d.ax.dx)):
            v = np.ravel(np.real(v if v is not None else 0))
            shifts[key] = float(v[0]) if v.size else 0.0
        d.ax.s = d.ax.dx = 0
        d.ax.filt = d.ax.diff = ''
        return shifts

    def _append(self, d: KzData, name: str | None = None) -> dict:
        counter = len(self.traces)
        d.ax.Color = PALETTE[counter % 7]
        y = np.ravel(d.ax.y)
        if y.size == 1 and y[0] == 0:
            d.ax.y = np.array([float(counter)])
        t = self._new_trace(d, (d.filename or d.title or '') if name is None else name)
        self.traces.append(t)
        return t

    def _added(self):
        self.update_list()
        self.ddTraces.setCurrentIndex(len(self.traces) - 1)
        self.update_interface()
        self.plot_this()

    def change(self):
        """Change from Source: the current trace gets the viewer source."""
        if not self.traces:
            self.add()
            return
        src = self.host.get_data('source')
        t = self.traces[self.num]
        src.ax.Color = t['data'].ax.Color
        t['data'] = src
        t['name'] = src.filename
        self.update_list()
        self.update_interface()
        self.plot_this()

    def change_output(self):
        """Change from Output: the current trace gets the (first) viewer output trace,
        keeping its colour; the output's shifts become the trace's shifts."""
        if not self.traces:
            self.add_output()
            return
        out = self._output()
        if not out:
            return
        if len(out) > 1:
            self.host.set('message', f'Comp. Box: the output has {len(out)} traces, '
                                     'the first one is used')
        d = out[0]
        t = self.traces[self.num]
        t.update(self._from_output(d))
        d.ax.Color = t['data'].ax.Color
        d.ax.y = t['data'].ax.y if np.size(t['data'].ax.y) == d.y.shape[1] else d.ax.y
        t['data'] = d
        t['name'] = d.title or d.filename or ''
        self.update_list()
        self.update_interface()
        self.plot_this()

    def delete_current(self):
        if self.traces:
            del self.traces[self.num]
        self.update_list()
        self.update_interface()
        self.plot_this()

    def delete_all(self):
        self.traces = []
        self.update_list()
        self.update_interface()
        self.plot_this()

    def change_title(self):
        if not self.traces:
            return
        t = self.traces[self.num]
        text, ok = QInputDialog.getText(self, 'Data Title', 'Change Data Title', text=t['name'])
        if ok:
            t['name'] = text
            self.update_list()

    def change_color(self):
        if not self.traces:
            return
        t = self.traces[self.num]
        c = QColorDialog.getColor(to_qcolor(t['data'].ax.Color), self, 'Trace colour')
        if c.isValid():
            t['data'].ax.Color = (c.redF(), c.greenF(), c.blueF())
            self.update_interface()
            self.plot_this()

    def _on_second_dim(self):
        if not self.traces or not self.eSecondDim.isModified():
            return
        self.eSecondDim.setModified(False)
        t = self.traces[self.num]
        try:
            vals = np.array([float(v) for v in self.eSecondDim.text().replace(',', ' ').split()])
        except ValueError:
            vals = np.zeros(0)
        if vals.size == t['data'].y.shape[1]:
            t['data'].ax.y = vals
        else:
            self.host.set('message', f'Need {t["data"].y.shape[1]} value(s) for the 2nd dimension')
        self.update_interface()

    # ================================================================ shift / zoom
    def value_changed(self, key: str, value: float | None = None):
        if not self.traces:
            return
        t = self.traces[self.num]
        if key == 'shift':
            t['shift_x'] = t['shift_y'] = 0.0
        elif key == 'zoom':
            t['zoom_x'] = 1.0
            t['zoom_y'] = 1.0 if self.ddUnits.currentText() == 'linear' else 0.0
        elif key == 'invert':
            t['ysign'] = -t['ysign']
        else:
            t[key] = float(value)
        self.update_interface()
        self.plot_this()

    def units_changed(self, units: str):
        for t in self.traces:
            t['zoom_y'] = 10 ** (t['zoom_y'] / 10) if units == 'linear' else 10 * np.log10(t['zoom_y'])
        self.update_interface()
        self.plot_this()

    # ================================================================ processing menu
    def normalize_current(self):
        if self.traces:
            self._normalize(self.traces[self.num])
            self.update_interface()
            self.plot_this()

    def normalize_all(self):
        for t in self.traces:
            self._normalize(t)
        self.update_interface()
        self.plot_this()

    def _normalize(self, t: dict):
        miny, maxy = _pp(t['data'].y)
        zmy = 1 / (maxy - miny) if maxy > miny else 1.0
        t['shift_y'] = 0.0 if self.mPreserveZero.isChecked() else -miny * zmy
        t['zoom_y'] = self._zoom_value(zmy)

    def to_first(self):
        num = self.num
        if num == 0 or len(self.traces) < 2:
            return
        t = self.traces[num]
        t['zoom_x'], t['shift_x'] = 1.0, 0.0
        (mn, mx), (mn1, mx1) = _pp(self.traces[0]['data'].y), _pp(t['data'].y)
        zmy = (mx - mn) / (mx1 - mn1) if mx1 > mn1 else 1.0
        t['shift_y'] = mn - mn1 * zmy if zmy > 0 else mn - mx1 * zmy
        t['zoom_y'] = self._zoom_value(zmy)
        self.update_interface()
        self.plot_this()

    def fit_all_to_first(self):
        if len(self.traces) < 2:
            return
        mn, mx = _pp(self.traces[0]['data'].y)
        for t in self.traces[1:]:
            t['zoom_x'], t['shift_x'] = 1.0, 0.0
            mn1, mx1 = _pp(t['data'].y)
            if self.mPreserveZero.isChecked():
                zmy = (mx - mn) / (mx1 - mn1) if mx1 > mn1 else 1.0
                t['shift_y'] = 0.0
            else:
                zmy = mx / mx1 if mx1 else 1.0
                t['shift_y'] = mn - min(mn1 * zmy, mx1 * zmy)
            t['zoom_y'] = self._zoom_value(zmy)
        self.update_interface()
        self.plot_this()

    def normalize_slices(self):
        if not self.traces:
            return
        t = self.traces[self.num]
        y = np.real(t['data'].y)
        miny, maxy = y.min(axis=0), y.max(axis=0)
        if self.mPreserveZero.isChecked():
            miny = np.where((maxy > 0) & (miny > 0), 0, miny)
            maxy = np.where((maxy < 0) & (miny < 0), 0, maxy)
        span = np.where(maxy > miny, maxy - miny, 1.0)
        t['zoom_y'] = 1.0 if self.ddUnits.currentText() == 'linear' else 0.0
        t['shift_y'] = 0.0
        t['zoom_y2d'] = np.broadcast_to(1 / span, y.shape).copy()
        t['shift_y2d'] = np.broadcast_to(miny, y.shape).copy()
        t['change2d'] = True
        self.mDisChanges.setVisible(True)
        self.update_interface()
        self.plot_this()

    def discard_2d(self):
        for t in self.traces:
            t['shift_y2d'], t['zoom_y2d'], t['change2d'] = 0, 1, False
        self.mDisChanges.setVisible(False)
        self.plot_this()

    def waterfall(self, two_d: bool):
        if not self.traces:
            return
        wfc, ok = QInputDialog.getDouble(self, 'wf', 'Enter the Waterfall parameter', 1.0,
                                         -1e9, 1e9, 4)
        if not ok:
            return
        lo, hi = np.inf, -np.inf
        for t in self.traces:
            mn, mx = _pp(t['data'].y * self._zoom(t) + t['shift_y'])
            lo, hi = min(lo, mn), max(hi, mx)
        wf = (hi - lo) * wfc
        for kk, t in enumerate(self.traces):
            if two_d:
                n1, n2 = t['data'].y.shape
                t['shift_y2d'] = np.broadcast_to(np.arange(n2) * wf, (n1, n2)).copy()
                t.setdefault('zoom_y2d', 1)
                t['change2d'] = True
            else:
                t['shift_y'] -= kk * wf
        if two_d:
            self.mDisChanges.setVisible(True)
        self.update_interface()
        self.plot_this()

    def add_current_to_output(self):
        if not self.traces:
            return
        kk = self.num
        t = self.traces[kk]
        d = t['data'].copy()
        if self.mProcessSource.isChecked():
            d, _ = process(d)
        else:
            d.ax.filt = ''
            d.ax.diff = ''
        d.ax.x = np.asarray(d.ax.x) * t['zoom_x']
        d.y = d.y * self._zoom(t) * t['ysign']
        d.ax.s = t['shift_y']
        d.ax.dx = t['shift_x']
        d.title = f'Trace{kk + 1}'
        self.host.set_data('output', [d])

    def join_traces(self):
        """Processing > Join Traces: replace all traces with their 2D combination."""
        if not self.traces:
            return
        d = self._combine()
        if d is None:
            return
        self.traces = [self._new_trace(d, self.traces[0]['name'])]
        self.update_list()
        self.ddTraces.setItemText(0, 'Group')
        self.update_interface()
        self.plot_this()

    def _combine(self) -> KzData | None:
        """All traces as one 2D set: every column (shifts, zoom and sign applied) is
        splined onto a common X axis over the range where all traces overlap. The
        second axis is the traces' Y values. None (with a message) if they don't
        overlap."""
        axes = [np.asarray(t['data'].ax.x) * t['zoom_x'] + t['shift_x'] for t in self.traces]
        lo = max(a.min() for a in axes)
        hi = min(a.max() for a in axes)
        if hi <= lo:
            self.host.set('message', 'Comp. Box: the traces do not overlap')
            return None
        same = all(len(a) == len(axes[0]) and np.allclose(a, axes[0]) for a in axes)
        if same:
            newax = axes[0]
        else:
            dx = (axes[0].max() - axes[0].min()) / len(axes[0])
            newax = np.linspace(lo, hi, max(int(np.floor((hi - lo) / dx + 0.5)), 2))
        cols, dim2 = [], []
        for t, x in zip(self.traces, axes):
            _, y = self.preprocess(t)
            y = y.reshape(len(x), -1)
            yv = np.ravel(np.real(t['data'].ax.y))
            order = np.argsort(x)
            xs, keep = np.unique(x[order], return_index=True)
            for k in range(y.shape[1]):
                cols.append(CubicSpline(xs, y[order][keep, k])(newax))
                dim2.append(float(yv[k]) if k < yv.size else float(len(dim2)))
        first = self.traces[0]
        ax = first['data'].ax.copy()
        ax.update(x=newax, y=np.array(dim2), ylabel='trace,', s=0, dx=0, filt='', diff='',
                  Color=PALETTE[0])
        return KzData(y=np.stack(cols, axis=1), ax=ax, dsc=first['data'].dsc.copy(),
                      filename=first['data'].filename, title='Out')

    def ungroup(self):
        if not self.traces:
            return
        num = self.num
        t = self.traces.pop(num)
        d = t['data']
        yax = np.ravel(d.ax.y)
        for ii in range(d.y.shape[1]):
            nd = d.copy()
            nd.y = d.y[:, ii:ii + 1]
            nd.ax.y = np.array([yax[ii] if ii < len(yax) else ii])
            nd.title = f'{d.title}::{ii + 1}'
            nd.ax.Color = PALETTE[(ii + 1) % 7]
            nt = self._new_trace(nd, f'{Path(t["name"]).name if t["name"] else d.title}::{ii + 1}')
            nt.update({k: t[k] for k in ('shift_x', 'shift_y', 'zoom_x', 'zoom_y', 'ysign')})
            self.traces.append(nt)
        self.update_list()
        self.update_interface()
        self.plot_this()

    def sort_by_y(self):
        if len(self.traces) < 2:
            return
        self.traces.sort(key=lambda t: float(np.ravel(np.real(t['data'].ax.y))[0]))
        self.update_list()
        self.update_interface()
        self.plot_this()

    def add_all(self):
        if len(self.traces) < 2:
            return
        xx, yy = self.preprocess(self.traces[0])
        for t in self.traces[1:]:
            x1, y1 = self.preprocess(t)
            yy = yy + _interp(x1, y1, xx)[:, :yy.shape[1]]
        ax = Struct(x=xx, xlabel=self.traces[0]['data'].ax.xlabel)
        self.host.set_data('output', [KzData(y=yy, ax=ax, dsc=Struct(),
                                             title=f'Trace{len(self.traces)}')])
