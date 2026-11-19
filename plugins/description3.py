"""Description plugin: port of Description3.mlapp.

Lists the source description (``dsc``) fields; *Sequence* draws the pulse sequence of
Bruker XEPR (``Psd1..36``) or ESP (``XPD1..16``) files in a separate window.

Differences from MATLAB (see README):
* Values are printed as ``name   value`` (MATLAB's sprintf printed numeric values as
  characters).
* Each channel of the sequence plot has one colour (MATLAB cycled colours per segment),
  and channels without pulses get no (empty) row.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QGridLayout, QMainWindow, QPlainTextEdit, QPushButton, QWidget)

from kazan.core import KazanPlugin
from kazan.viewer.plot import COLOR_ORDER, KazanPlot, to_qcolor

CHANNELS = ['1', '2', 'TWT', '4', 'detect', '+X', '7', '8', '9', '10', '11', '12', '13', '14',
            '15', '16', '17', '10', '19', 'RFGate', '21', '22', '23', '24', '25', '26', '27',
            '28', '29', 'RF1', '31', '32', '33', '34', '35', '36']


def _numbers(value) -> np.ndarray:
    if isinstance(value, str):
        value = value[value.find('}') + 1:] if '}' in value else value
        return np.array([float(v) for v in re.split(r'[,;\s]+', value.strip()) if v], float)
    return np.ravel(np.asarray(value, float))


def psd_sequence(dsc, n: int) -> np.ndarray:
    """MATLAB getsequencestring: Psd<n> as a (k, 4) table [position, length, ...]."""
    val = _numbers(dsc.get(f'Psd{n}', '') or '')
    if val.size == 0 or val.size % 4:
        return np.zeros((0, 4))
    return val.reshape(4, -1).T  # MATLAB reshape(val, len/4, 4), column-major


def format_description(dsc) -> list[str]:
    lines = []
    for name, val in (dsc or {}).items():
        if isinstance(val, dict):
            for sub, sval in val.items():
                lines.append(f'{name + "-" + str(sub):<16s}   {sval}')
        else:
            lines.append(f'{name + ":":<16s}   {val}')
    return lines or ['(no description)']


class SequenceWindow(QMainWindow):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title or 'Sequence')
        self.resize(640, 420)
        self.plot = KazanPlot()
        self.setCentralWidget(self.plot)
        self.p = self.plot.real

    def pulse(self, x0, x1, level, color):
        """Rectangular pulse from x0 to x1 at channel level (MATLAB: _ up - dn)."""
        pen = pg.mkPen(color, width=1.5)
        self.p.plot([x0, x0, x1, x1], level + np.array([0, 0.5, 0.5, 0]), pen=pen)

    def line(self, x0, x1, level, color):
        self.p.plot([x0, x1], [level, level], pen=pg.mkPen(color, width=1.5))

    def text(self, x, y, s):
        t = pg.TextItem(s, color='k', anchor=(0, 1))
        t.setFont(QFont('', 8))
        t.setPos(x, y)
        self.p.addItem(t)

    def finish(self, title=''):
        self.plot.set_labels('Sequence, ns', 'Channels')
        if title:
            self.plot.set_title(title)
        vb = self.p.getViewBox()
        vb.autoRange(padding=0.02)
        y0, y1 = vb.viewRange()[1]
        vb.setYRange(y0 - 0.2, y1 + 0.5, padding=0)  # room for the pulse length labels


class Description3(KazanPlugin):
    menu_name = 'DESCRIPTION3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.resize(370, 480)
        self.sequence_windows: list[SequenceWindow] = []
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(2, 2, 2, 2)
        g.setSpacing(2)
        self.txtDescription = QPlainTextEdit()
        self.txtDescription.setReadOnly(True)
        self.txtDescription.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.txtDescription.setFont(QFont('Consolas'))
        g.addWidget(self.txtDescription, 0, 0, 1, 2)
        self.SequenceButton = QPushButton('Sequence')
        self.SequenceButton.setMinimumHeight(36)
        self.SequenceButton.clicked.connect(self.show_sequence)
        g.addWidget(self.SequenceButton, 1, 1)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        self.file_update()

    def file_update(self):
        src = self.host.get_data('source')
        self.setWindowTitle(src.filename or 'Description')
        self.txtDescription.setPlainText('\n'.join(format_description(src.dsc)))

    def closeEvent(self, ev):
        for win in self.sequence_windows:
            try:
                win.close()
            except RuntimeError:  # already closed and deleted
                pass
        super().closeEvent(ev)

    def show_sequence(self):
        src = self.host.get_data('source')
        dsc = src.dsc or {}
        if 'Psd1' not in dsc and 'XPD1' not in dsc:
            self.host.set('message', 'No pulse sequence in the data description.')
            return
        win = SequenceWindow(Path(src.filename).name if src.filename else 'Sequence')
        if 'Psd1' in dsc:
            self._draw_psd(win, dsc)
            win.finish()
        else:
            self._draw_xpd(win, dsc)
            win.finish(src.filename)
        self.sequence_windows.append(win)
        win.show()

    @staticmethod
    def _draw_psd(win: SequenceWindow, dsc):
        det = psd_sequence(dsc, 5)
        maxval = (det[:, 0] + det[:, 1]).max() + 50 if len(det) else 0
        istep = 1
        for ii in range(1, 37):
            val = psd_sequence(dsc, ii)
            if not ((val[:, 0] > 0) & (val[:, 1] > 0)).any():
                continue  # no pulses on this channel
            color = to_qcolor(COLOR_ORDER[(istep - 1) % len(COLOR_ORDER)])
            last = 0.0
            for pos, length in val[:, :2]:
                if pos > 0 and length > 0:
                    win.line(last, pos, istep, color)
                    win.pulse(pos, pos + length, istep, color)
                    win.text(pos, istep + 0.7, f'{length:g}ns')
                    last = pos + length
            win.text(10, istep + 0.3, CHANNELS[ii - 1])
            if last > 0:
                win.line(last, max(maxval, last), istep, color)
            istep += 1

    @staticmethod
    def _draw_xpd(win: SequenceWindow, dsc):
        for ii in range(1, 17):
            if f'XPD{ii}' not in dsc:
                continue
            val = _numbers(dsc[f'XPD{ii}'])
            if len(val) <= 4:
                continue
            color = to_qcolor(COLOR_ORDER[(ii - 1) % len(COLOR_ORDER)])
            npulse = (len(val) + 3) // 4 - 1
            val = np.concatenate([val, np.zeros(4)])
            start = 0.0
            for j in range(1, npulse + 1):
                start1 = val[j * 4] * 8
                win.line(start, start1, ii, color)
                win.text(start + 10, ii + 0.2, f'{start1 - start:g}ns')
                start = start1
                start1 = 8 * (val[1 + j * 4] - 1) + start
                win.pulse(start, start1, ii, color)
                win.text(start, ii + 0.7, f'{start1 - start:g}ns')
                start = start1
