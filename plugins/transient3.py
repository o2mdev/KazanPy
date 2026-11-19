"""Transient plugin: port of transient3.mlapp.

2D transient data (field x time). The dark signal (mean over the *Dark* time points) is
subtracted from every transient, the data are optionally smoothed in time
(Savitzky-Golay) and inverted.

* **Field domain** - the mean over the *Signal* time points against field, with a
  polynomial baseline (order No/0..3) fitted to the field *Range* (add / remove with the
  cross buttons). *Show Fit* draws the baseline instead of subtracting it.
* **Time domain** - the transient at the field marked with the cross next to *Switch to
  Time*, minus the mean transient of the off-resonance range, with the signal and dark
  regions (pick them with the cross buttons).

Differences from MATLAB (see Documentation/plugins.md):
* The baseline is fitted only when the range has more than 3 points (MATLAB tested the
  length of the mask, so a near-empty range gave NaN).
* Time-domain outputs are all labelled with the time axis (MATLAB kept the field label
  on two of them).
* The cross buttons are enabled for the current domain from the start.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QWidget)
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


def _cross(tooltip=''):
    b = QPushButton()
    b.setIcon(QIcon(str(RESOURCES / 'pbCross.png')))
    b.setIconSize(QSize(14, 14))
    b.setToolTip(tooltip)
    b.setSizePolicy(b.sizePolicy().horizontalPolicy(), b.sizePolicy().Policy.Expanding)
    return b


def _state(text, checked=False):
    b = QPushButton(text)
    b.setCheckable(True)
    b.setChecked(checked)
    return b


def _label(text, center=True):
    lab = QLabel(text)
    lab.setWordWrap(True)
    if center:
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lab


class transient3(KazanPlugin):  # noqa: N801 - MATLAB name
    menu_name = 'TRANSIENT3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('transient')
        self.resize(455, 292)
        self.area_fit: np.ndarray | None = None
        self.time_field = 1             # 1 field domain, 0 time domain
        self.show_field_position = 0    # 0-based field index of the time-domain trace
        self._build_ui()
        self._update_enabled()
        self.file_update()

    # ================================================================ UI
    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(5, 5, 5, 5)
        g.setSpacing(2)
        for c, s in enumerate((10, 10, 6, 10, 20, 10, 10, 10, 10, 10)):
            g.setColumnStretch(c, s)
        for r in range(11):
            g.setRowStretch(r, 1)

        self.pbTimeField = _state('Switch to Time')
        g.addWidget(self.pbTimeField, 0, 0, 2, 3)
        self.pbMarkField = _cross('Mark Field for Trace')
        g.addWidget(self.pbMarkField, 0, 3, 2, 1)
        self.cbFileUpdate = QCheckBox('Update when file changes')
        self.cbFileUpdate.setChecked(True)
        g.addWidget(self.cbFileUpdate, 0, 5, 1, 5)

        g.addWidget(_label('Smooth'), 1, 4)
        self.smooth_group = QButtonGroup(self)
        self.tbS0, self.tbS1, self.tbS2, self.tbS3 = (
            _state('No', True), _state('3'), _state('5'), _state('10'))
        for c, b in enumerate((self.tbS0, self.tbS1, self.tbS2, self.tbS3), start=5):
            self.smooth_group.addButton(b)
            g.addWidget(b, 1, c, 2, 1)

        self.eInfo = QPlainTextEdit('-')
        self.eInfo.setReadOnly(True)
        g.addWidget(self.eInfo, 2, 0, 2, 4)
        self.cbShowSrc = QCheckBox('Show src')
        g.addWidget(self.cbShowSrc, 2, 4)
        self.ShowFitHint = _label('Show Fit: baseline is drawn, NOT subtracted')
        self.ShowFitHint.setStyleSheet('color: #d90000; font-weight: bold;')
        self.ShowFitHint.setVisible(False)
        g.addWidget(self.ShowFitHint, 3, 4, 1, 6)

        self.pbTrans = QCheckBox('Transpose')
        self.pbTrans.setChecked(True)
        g.addWidget(self.pbTrans, 4, 0, 1, 2)
        self.cbInvert = QCheckBox('Inv')
        g.addWidget(self.cbInvert, 4, 2, 1, 2)
        g.addWidget(_label('BL'), 4, 4)
        self.bl_group = QButtonGroup(self)
        self.tbFno, self.tbF0, self.tbF1, self.tbF2, self.tbF3 = (
            _state('No', True), _state('0'), _state('1'), _state('2'), _state('3'))
        for c, b in enumerate((self.tbFno, self.tbF0, self.tbF1, self.tbF2, self.tbF3), start=5):
            self.bl_group.addButton(b)
            g.addWidget(b, 4, c, 2, 1)

        self.text2 = _label('Signal, pts', False)
        g.addWidget(self.text2, 5, 0, 1, 4)
        self.cbShowFit = QCheckBox('Show Fit')
        self.cbShowFit.setToolTip('Show the fit area and baseline curve; the baseline is NOT '
                                  'subtracted while checked')
        g.addWidget(self.cbShowFit, 5, 4)

        self.eSstart, self.eSend = QLineEdit('200'), QLineEdit('600')
        self.eBLstart, self.eBLend = QLineEdit('1'), QLineEdit('10')
        for e in (self.eSstart, self.eSend, self.eBLstart, self.eBLend):
            e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        g.addWidget(_label('Start', False), 6, 0)
        g.addWidget(self.eSstart, 6, 1, 1, 2)
        g.addWidget(_label('End', False), 7, 0)
        g.addWidget(self.eSend, 7, 1, 1, 2)
        self.pbSelectSignal = _cross('Select the signal time range')
        g.addWidget(self.pbSelectSignal, 6, 3, 2, 1)
        g.addWidget(_label('Range'), 6, 4, 2, 1)
        self.pbAddRange = _cross('Add a field range to the baseline area')
        g.addWidget(self.pbAddRange, 6, 5, 2, 1)
        g.addWidget(_label('Add'), 6, 6, 2, 1)
        self.pbRemoveRange = _cross('Remove a field range from the baseline area')
        g.addWidget(self.pbRemoveRange, 6, 7, 2, 1)
        g.addWidget(_label('Remv'), 6, 8, 2, 1)

        self.text1 = _label('Dark signal, pts', False)
        g.addWidget(self.text1, 8, 0, 1, 4)
        g.addWidget(_label('Start', False), 9, 0)
        g.addWidget(self.eBLstart, 9, 1, 1, 2)
        g.addWidget(_label('End', False), 10, 0)
        g.addWidget(self.eBLend, 10, 1, 1, 2)
        self.pbSelectDark = _cross('Select the dark signal time range')
        g.addWidget(self.pbSelectDark, 9, 3, 2, 1)
        self.pbCalculate = QPushButton('Calculate')
        self.pbCalculate.setSizePolicy(self.pbCalculate.sizePolicy().horizontalPolicy(),
                                       self.pbCalculate.sizePolicy().Policy.Expanding)
        g.addWidget(self.pbCalculate, 9, 5, 2, 5)

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
            self.eInfo.setPlainText(f'field {y.shape[0]} pts\n time {y.shape[1]} pts')
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
            pos = self.show_field_position = max(0, min(self.show_field_position, y.shape[0] - 1))
            ysmout, yout = ysm[pos], y[pos]
            if areafit.any():
                ysmout = ysmout - ysm[areafit].mean(axis=0)
                yout = yout - y[areafit].mean(axis=0)
            trace = dict(xl=tlabel, ylabel=xlabel, y=np.array([x[pos]]) if len(x) else None)
            out = []
            if self.cbShowSrc.isChecked():
                out.append(data(time, yout, 'original', [1, 0, 0], **trace))
            out.append(data(time, ysmout, 'smoothed', **trace))
            out.append(data(time[sig], ysmout[sig], 'signal', [0, 1, 0], xl=tlabel))
            if len(dark):
                out.append(data(time[dark], ysmout[dark], 'dark', [0, 0, 0], xl=tlabel))
        self.host.set_data('output', out)

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

        def text(name, idx):
            if not len(idx) or not t.size or idx.max() >= t.size:
                return name
            s = f'{name} ({t[idx.min()] * scale:.4g} to {t[idx.max()] * scale:.4g}'
            return s + (f' {unit})' if unit else ')')
        self.text2.setText(text('Signal, pts', sig))
        self.text1.setText(text('Dark signal, pts', dark))

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
