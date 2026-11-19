"""Transient plugin: port of transient3.mlapp.

2D transient data (field x time). The dark signal (mean over the *Dark* time points) is
subtracted from every transient, the data are optionally smoothed in time
(Savitzky-Golay) and inverted.

* **Field domain** - the mean over the *Signal* time points against field, with a
  polynomial baseline (order No/0..3) fitted to the field *Range* (add / remove with the
  cross buttons). *Show Fit* draws the baseline instead of subtracting it.
* **Time domain** - all transients (time x field), minus the mean transient of the
  off-resonance range, shown at the field marked with *Mark field*; the viewer slider
  steps through the field. The signal and dark regions are marked (*Pick* buttons).

Differences from MATLAB (see Documentation/plugins.md):
* The baseline is fitted only when the range has more than 3 points (MATLAB tested the
  length of the mask, so a near-empty range gave NaN).
* Time-domain outputs are all labelled with the time axis (MATLAB kept the field label
  on two of them).
* The cross buttons are enabled for the current domain from the start.
* The time domain outputs every field (MATLAB: only the marked one), so the viewer
  slider steps through the transients.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)
from scipy.signal import savgol_filter

from kazan.core import KazanPlugin, KzData, Struct
from kazan.viewer.main_window import RESOURCES

SMOOTH_TIME = {'tbS1': 5, 'tbS2': 10, 'tbS3': 20}      # datasmooth(y, m, 'savgol', 2)
SMOOTH_FIELD = {'tbS1': 1, 'tbS2': 3, 'tbS3': 5}       # datasmooth(y, m, 'savgol', 1)
BL_ORDER = {'tbF0': 0, 'tbF1': 1, 'tbF2': 2, 'tbF3': 3}


def datasmooth(y, m: int, pol: int, axis: int = 0):
    """EasySpin ``datasmooth(y, m, 'savgol', pol)``: window 2m+1, ends padded with the
    end values."""
    def f(a):
        return savgol_filter(a, 2 * m + 1, min(pol, 2 * m), axis=axis, mode='nearest')
    return f(y.real) + 1j * f(y.imag) if np.iscomplexobj(y) else f(y)


def _range(first: str, last: str, n: int) -> np.ndarray:
    """MATLAB ``str2double(a):str2double(b)`` limited to 1..n, as 0-based indices."""
    try:
        a, b = float(first), float(last)
    except ValueError:
        return np.zeros(0, int)
    idx = np.arange(a, b + 1e-9)
    idx = idx[(idx > 0) & (idx <= n) & (idx == np.round(idx))]
    return idx.astype(int) - 1


def _cross(tooltip='', text=''):
    """Pick button with the cross icon (MATLAB ginput buttons)."""
    b = QPushButton(text)
    b.setIcon(QIcon(str(RESOURCES / 'pbCross.png')))
    b.setIconSize(QSize(14, 14))
    b.setToolTip(tooltip)
    return b


def _state(text, checked=False):
    b = QPushButton(text)
    b.setCheckable(True)
    b.setChecked(checked)
    return b


def _segments(group: QButtonGroup, buttons) -> QHBoxLayout:
    """A row of exclusive state buttons."""
    row = QHBoxLayout()
    row.setSpacing(2)
    for b in buttons:
        group.addButton(b)
        b.setMinimumWidth(34)
        row.addWidget(b)
    row.addStretch(1)
    return row


def _hint(text=''):
    lab = QLabel(text)
    lab.setStyleSheet('color: #606060;')
    return lab


class transient3(KazanPlugin):  # noqa: N801 - MATLAB name
    menu_name = 'TRANSIENT3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('transient')
        self.resize(430, 420)
        self.area_fit: np.ndarray | None = None
        self.time_field = 1             # 1 field domain, 0 time domain
        self.show_field_position = 0    # 0-based field index of the time-domain trace
        self._build_ui()
        self._update_enabled()
        host.sliceChanged.connect(self._on_slice)
        self.file_update()

    def _on_slice(self, k: int):
        """Stepping through the field in the viewer (time domain) moves the marked field."""
        if self.time_field == 0:
            self.show_field_position = int(k)

    # ================================================================ UI
    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # ---- domain switch, field marker, update
        top = QHBoxLayout()
        self.pbTimeField = _state('Switch to Time')
        self.pbTimeField.setToolTip('Field domain: the signal against field; '
                                    'time domain: the transient at the marked field')
        self.pbMarkField = _cross('Mark the field of the time-domain trace', 'Mark field')
        self.cbFileUpdate = QCheckBox('Update when file changes')
        self.cbFileUpdate.setChecked(True)
        top.addWidget(self.pbTimeField)
        top.addWidget(self.pbMarkField)
        top.addStretch(1)
        top.addWidget(self.cbFileUpdate)
        v.addLayout(top)
        self.eInfo = _hint('-')
        v.addWidget(self.eInfo)

        # ---- data
        box = QGroupBox('Data')
        g = QGridLayout(box)
        self.pbTrans = QCheckBox('Transpose')
        self.pbTrans.setChecked(True)
        self.pbTrans.setToolTip('Rows of the source are the field')
        self.cbInvert = QCheckBox('Invert')
        self.cbShowSrc = QCheckBox('Show src')
        row = QHBoxLayout()
        for cb in (self.pbTrans, self.cbInvert, self.cbShowSrc):
            row.addWidget(cb)
        row.addStretch(1)
        g.addLayout(row, 0, 0, 1, 2)
        g.addWidget(QLabel('Smooth'), 1, 0)
        self.smooth_group = QButtonGroup(self)
        self.tbS0, self.tbS1, self.tbS2, self.tbS3 = (
            _state('No', True), _state('3'), _state('5'), _state('10'))
        g.addLayout(_segments(self.smooth_group, (self.tbS0, self.tbS1, self.tbS2, self.tbS3)), 1, 1)
        g.setColumnStretch(1, 1)
        v.addWidget(box)

        # ---- field domain: baseline
        box = QGroupBox('Field domain: baseline')
        g = QGridLayout(box)
        g.addWidget(QLabel('Order'), 0, 0)
        self.bl_group = QButtonGroup(self)
        self.tbFno, self.tbF0, self.tbF1, self.tbF2, self.tbF3 = (
            _state('No', True), _state('0'), _state('1'), _state('2'), _state('3'))
        g.addLayout(_segments(self.bl_group, (self.tbFno, self.tbF0, self.tbF1, self.tbF2, self.tbF3)), 0, 1)
        g.addWidget(QLabel('Range'), 1, 0)
        self.pbAddRange = _cross('Add a field range to the baseline area', 'Add')
        self.pbRemoveRange = _cross('Remove a field range from the baseline area', 'Remove')
        self.cbShowFit = QCheckBox('Show Fit')
        self.cbShowFit.setToolTip('Show the fit area and baseline curve; the baseline is NOT '
                                  'subtracted while checked')
        row = QHBoxLayout()
        row.addWidget(self.pbAddRange)
        row.addWidget(self.pbRemoveRange)
        row.addStretch(1)
        row.addWidget(self.cbShowFit)
        g.addLayout(row, 1, 1)
        self.ShowFitHint = QLabel('Show Fit: baseline is drawn, NOT subtracted')
        self.ShowFitHint.setStyleSheet('color: #d90000; font-weight: bold;')
        self.ShowFitHint.setVisible(False)
        g.addWidget(self.ShowFitHint, 2, 0, 1, 2)
        g.setColumnStretch(1, 1)
        v.addWidget(box)

        # ---- time domain: signal and dark ranges
        box = QGroupBox('Time domain, points')
        g = QGridLayout(box)
        self.eSstart, self.eSend = QLineEdit('200'), QLineEdit('600')
        self.eBLstart, self.eBLend = QLineEdit('1'), QLineEdit('10')
        self.pbSelectSignal = _cross('Select the signal time range on the plot', 'Pick')
        self.pbSelectDark = _cross('Select the dark signal time range on the plot', 'Pick')
        self.text2, self.text1 = _hint(), _hint()
        for r, (name, a, b, pick, span) in enumerate((
                ('Signal', self.eSstart, self.eSend, self.pbSelectSignal, self.text2),
                ('Dark', self.eBLstart, self.eBLend, self.pbSelectDark, self.text1))):
            for e in (a, b):
                e.setAlignment(Qt.AlignmentFlag.AlignCenter)
                e.setMaximumWidth(70)
            g.addWidget(QLabel(name), r, 0)
            g.addWidget(a, r, 1)
            g.addWidget(QLabel('to'), r, 2)
            g.addWidget(b, r, 3)
            g.addWidget(pick, r, 4)
            g.addWidget(span, r, 5)
        g.setColumnStretch(5, 1)
        v.addWidget(box)

        v.addStretch(1)
        self.pbCalculate = QPushButton('Calculate')
        self.pbCalculate.setMinimumHeight(32)
        v.addWidget(self.pbCalculate)

        # wiring
        self.pbTimeField.clicked.connect(self.time_field_changed)
        self.pbMarkField.clicked.connect(self.mark_field)
        self.pbAddRange.clicked.connect(lambda: self.range_changed(True))
        self.pbRemoveRange.clicked.connect(lambda: self.range_changed(False))
        self.pbSelectSignal.clicked.connect(lambda: self.select_time_range(self.eSstart, self.eSend))
        self.pbSelectDark.clicked.connect(lambda: self.select_time_range(self.eBLstart, self.eBLend))
        self.smooth_group.buttonClicked.connect(self.draw_all)
        self.bl_group.buttonClicked.connect(self.draw_all)
        self.cbShowFit.toggled.connect(self.draw_all)
        for cb in (self.cbInvert, self.cbShowSrc, self.pbTrans):
            cb.toggled.connect(self.recalculate)
        self.pbCalculate.clicked.connect(self.recalculate)

    def _update_enabled(self):
        field = self.time_field == 1
        for b in (self.pbMarkField, self.pbRemoveRange, self.pbAddRange):
            b.setEnabled(field)
        for b in (self.pbSelectSignal, self.pbSelectDark):
            b.setEnabled(not field)

    # ================================================================ host
    def file_update(self):
        if self.cbFileUpdate.isChecked():
            try:
                _, y, _ = self.raw_data()
            except Exception:  # noqa: BLE001 - no usable source
                return
            self.eInfo.setText(f'field {y.shape[0]} pts, time {y.shape[1]} pts')
            self.draw_all()

    def recalculate(self, *_):
        """MATLAB Update: FileUpdate + DrawAll."""
        if self.cbFileUpdate.isChecked():
            self.file_update()
        else:
            self.draw_all()

    # ================================================================ data
    def raw_data(self):
        """MATLAB GetRawData: (ax, y, areafit); transposed so rows are the field."""
        src = self.host.get_data('source')
        ax, y = src.ax, np.asarray(src.y)
        if self.pbTrans.isChecked():
            y = y.T
            ax.x, ax.y = ax.y, ax.x
            ax.xlabel, ax.ylabel = ax.get('ylabel', ''), ax.get('xlabel', '')
        n = y.shape[0]
        if self.area_fit is None:
            self.area_fit = np.zeros(n, bool)
            self.area_fit[:10] = True
            self.area_fit[max(n - 11, 0):] = True
        if len(self.area_fit) > n:
            self.area_fit = self.area_fit[:n]
        elif len(self.area_fit) < n:
            self.area_fit = np.concatenate([self.area_fit, np.zeros(n - len(self.area_fit), bool)])
            self.area_fit[-1] = True
        return ax, y, self.area_fit.copy()

    def _smooth_key(self):
        return next((k for k in SMOOTH_TIME if getattr(self, k).isChecked()), None)

    def draw_all(self, *_):
        try:
            self._draw_all()
        except Exception as e:  # noqa: BLE001 - report like a MATLAB error
            self.host.set('message', f'transient: {e}')

    def _draw_all(self):
        ax, y, areafit = self.raw_data()
        sig = _range(self.eSstart.text(), self.eSend.text(), y.shape[1])
        dark = _range(self.eBLstart.text(), self.eBLend.text(), y.shape[1])
        self.update_range_labels(ax, sig, dark)
        self.ShowFitHint.setVisible(self.cbShowFit.isChecked() and self.time_field == 1)

        if len(dark):
            y = y - y[:, dark].mean(axis=1, keepdims=True)
        else:
            y = y * 1.0   # MATLAB mean of nothing is NaN; keep the data instead
        key = self._smooth_key()
        ysm = datasmooth(y, SMOOTH_TIME[key], 2, axis=1) if key else y
        if self.cbInvert.isChecked():
            y, ysm = -y, -ysm
        x = np.asarray(ax.x, float)
        time = np.asarray(ax.y, float)
        xlabel, tlabel = ax.get('xlabel', ''), ax.get('ylabel', '')

        def data(xx, yy, title, color=None, xl=xlabel, **extra):
            a = Struct(x=np.asarray(xx), xlabel=xl, **extra)
            if color is not None:
                a.Color = color
            return KzData(y=np.asarray(yy).reshape(len(a.x), -1), ax=a, title=title)

        if self.time_field == 1:
            if not len(sig):
                self.host.set_data('output', [KzData(y=ysm, ax=ax, title='original')])
                return
            yout = y[:, sig].mean(axis=1)
            ysmout = ysm[:, sig].mean(axis=1)
            if key:
                ysmout = datasmooth(ysmout, SMOOTH_FIELD[key], 1)
            bl = np.zeros(len(x))
            af = areafit[:len(x)]
            order = next((o for k, o in BL_ORDER.items() if getattr(self, k).isChecked()), None)
            if order is not None and np.count_nonzero(af) > 3:
                if order == 0:
                    bl = np.full(len(x), ysmout[af].mean())
                else:
                    bl = np.polyval(np.polyfit(x[af], ysmout[af], order), x)
            fit_area = dict(Marker='o', LineStyle='none', s=0)
            if self.cbShowFit.isChecked():
                out = [data(x, ysmout, 'smoothed (baseline NOT subtracted)')]
                if self.cbShowSrc.isChecked():
                    out.append(data(x, yout, 'original', [1, 0, 0]))
                out.append(data(x[af], ysmout[af], 'fit area', [0, 0, 0], **fit_area))
                out.append(data(x, bl, 'baseline', [0, 1, 0], s=0, LineStyle='-'))
            else:
                out = [data(x, ysmout - bl, 'baseline corrected')]
                if self.cbShowSrc.isChecked():
                    out.append(data(x, yout - bl, 'original', [1, 0, 0]))
                out.append(data(x[af], ysmout[af] - bl[af], 'fit area', [0, 0, 0], **fit_area))
        else:
            # all transients (time x field), minus the mean off-resonance transient; the
            # viewer shows the marked field and its slider steps through the field
            # (MATLAB output only the transient at the marked field)
            pos = self.show_field_position = max(0, min(self.show_field_position, y.shape[0] - 1))
            ysmout, yout = ysm, y
            if areafit.any():
                ysmout = ysmout - ysm[areafit].mean(axis=0)
                yout = yout - y[areafit].mean(axis=0)
            ysmout, yout = ysmout.T, yout.T
            trace = dict(xl=tlabel, ylabel=xlabel, y=x)
            out = []
            if self.cbShowSrc.isChecked():
                out.append(data(time, yout, 'original', [1, 0, 0], **trace))
            out.append(data(time, ysmout, 'smoothed', **trace))
            out.append(data(time[sig], ysmout[sig], 'signal', [0, 1, 0], **trace))
            if len(dark):
                out.append(data(time[dark], ysmout[dark], 'dark', [0, 0, 0], **trace))
        self.host.set_data('output', out)
        if self.time_field == 0:
            self.host.set('slice', self.show_field_position)

    def update_range_labels(self, ax, sig, dark):
        """Signal / dark ranges in time units next to their labels."""
        t = np.ravel(np.asarray(ax.get('y', []), float))
        yl = str(ax.get('ylabel', ''))
        unit = yl.split(',', 1)[1].strip() if ',' in yl else ''
        scale = 1.0
        if unit == 's' and t.size:
            tmax = np.abs(t).max()
            for lim, sc, u in ((1e-5, 1e9, 'ns'), (1e-2, 1e6, 'us'), (10, 1e3, 'ms')):
                if tmax < lim:
                    scale, unit = sc, u
                    break

        def text(idx):
            """The time span of a point range, e.g. '3.98 to 11.98 us'."""
            if not len(idx) or not t.size or idx.max() >= t.size:
                return ''
            s = f'{t[idx.min()] * scale:.4g} to {t[idx.max()] * scale:.4g}'
            return s + (f' {unit}' if unit else '')
        self.text2.setText(text(sig))
        self.text1.setText(text(dark))

    # ================================================================ callbacks
    def time_field_changed(self):
        self.time_field = 0 if self.time_field == 1 else 1
        self.pbTimeField.setText(('Switch to Field', 'Switch to Time')[self.time_field])
        self.pbTimeField.setChecked(self.time_field == 0)
        self.setWindowTitle('TRANSIENT: ' + ('Time Domain', 'Field Domain')[self.time_field])
        self._update_enabled()
        self.draw_all()

    def range_changed(self, add: bool):
        self.host.set('message', 'Select the beginning and the end of the range')
        pos = self.host.ginput(2)
        if len(pos) < 2:
            return
        lo, hi = np.sort(pos[:, 0])
        ax, _, areafit = self.raw_data()
        x = np.asarray(ax.x, float)
        areafit[(x > lo) & (x < hi)] = add
        self.area_fit = areafit
        self.draw_all()

    def mark_field(self):
        pos = self.host.ginput(1)
        if len(pos) < 1:
            return
        ax, _, _ = self.raw_data()
        self.show_field_position = int(np.argmin(np.abs(np.asarray(ax.x, float) - pos[0, 0])))

    def select_time_range(self, first: QLineEdit, last: QLineEdit):
        if self.time_field != 0:
            return
        self.host.set('message', 'Select the beginning and the end of the range')
        pos = self.host.ginput(2)
        if len(pos) < 2:
            return
        lo, hi = np.sort(pos[:, 0])
        ax, _, _ = self.raw_data()
        t = np.asarray(ax.y, float)
        first.setText(str(int(np.argmin(np.abs(t - lo))) + 1))
        last.setText(str(int(np.argmin(np.abs(t - hi))) + 1))
        self.draw_all()
