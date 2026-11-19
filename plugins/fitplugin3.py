"""Fitting plugin: port of FitPlugin3.mlapp.

Fits a user script (``f = a*exp(-x/t)``, ``a = 1``, ``t = 2e-6``) to the current slice
or, with *Fit -> Fit All*, a separate script per slice. Source (blue or chosen
colour), ignored points (grey dots), fit (red) and difference (green) go to Output.

Differences from MATLAB (see README):
* *Fit Function ...* opens a plain script editor (MATLAB used the external
  ``fittingbox_func`` dialog, not part of Kazan3).
* Single-slice mode plots the current viewer slice with its fit (MATLAB fitted the
  viewer slice but plotted all slices and their difference against that one fit).
* *Enter Expression* asks for an expression (MATLAB inserted the constant 125).
* The source shown honours *Source processing* (MATLAB always plotted the raw source).
"""
from __future__ import annotations

import time

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QGridLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QMenu, QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from kazan.core import KazanPlugin, KzData
from kazan.viewer.widgets import SciSpinBox
from kazan.math.autofit import autofit, evaluate_script, tokens, _value

STEPS = ['1e-7', '1e-6', '1e-5', '1e-4', '1e-3', '0.01', '0.1', '1', '10', '100', '1000',
         '1e+4', '1e+5', '1e+6']

FUNCTIONS = {
    'EPR/MRI': [
        ('T2*: exp(-x/t)', ['f = a*exp(-x/t)', 'a = 1', 't = 2e-6']),
        ('T2*: exp(-2x/t)', ['f = a*exp(-2*x/t)', 'a = 1', 't = 2e-6']),
        ('T1: 1-2*exp(-x/t)', ['f = a-b*exp(-x/t)', 'a = 1', 'b = 1', 't = 2e-6']),
        ('T2* mod: cos*exp', ['f = a*exp(-x/t).*cos(x*2*pi*F+Ph)', 'a = 1', 't = 2e-6',
                              'F = 1e6', 'Ph = 0']),
    ],
    'Lineshape': [
        ('Voigtian', ['f = a*kv3_lshape(x,x0,lwG,lwL)', 'a = 1', 'x0 = 0', 'lwG = 1', 'lwL = 1']),
        ('Lorentzian', ['f = a*lorentzian(x,x0,lwL)', 'a = 1', 'x0 = 0', 'lwL = 1']),
        ('Gaussian', ['f = a*gaussian(x,x0,lwG)', 'a = 1', 'x0 = 0', 'lwG = 1']),
    ],
    'Polynomial': [
        ('x0', ['f = x0', 'x0 = 0']),
        ('x1,x0', ['f = x*x1 + x0', 'x0 = 0', 'x1 = 0']),
        ('x2,x1,x0', ['f = x.*x*x2 + x*x1 + x0', 'x0 = 0', 'x1 = 0', 'x2 = 0']),
    ],
}


def _num2str(v) -> str:
    """MATLAB num2str: 4 significant digits after the point (%.4g-like, max 5 sig.)."""
    return f'{float(v):.5g}'


class FitPlugin3(KazanPlugin):
    menu_name = 'FITPLUGIN3'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        self.setWindowTitle('Fitting')
        self.resize(265, 420)
        self.color = (0, 0, 255)
        self.editor_mode = 'value'
        self.area_fit = np.zeros(0, bool)
        self.fits: list[dict] = [{'script': ['f = a*exp(-x/t)', 'a = 1', 't = 2e-6'], 'y': None}]
        self._build_menus()
        self._build_ui()
        self.update_fit_list()
        self.update_script_list()
        host.sliceChanged.connect(self._on_viewer_slice)

    # ================================================================ UI
    def _build_menus(self):
        m = self.menuBar().addMenu('Simulation')
        m.addAction('Fit Function ...').triggered.connect(self._edit_function)
        for title, items in FUNCTIONS.items():
            sub = m.addMenu(title)
            for text, script in items:
                sub.addAction(text).triggered.connect(lambda _=False, s=script: self.select_function(s))
        m.addSeparator()
        self.mSimUseProcessing = self._check(m, 'Source processing', True)
        self.mShowDifference = self._check(m, 'Show Difference', True)
        self.mShowRange = self._check(m, 'Show Range', True)
        m = self.menuBar().addMenu('Fit')
        self.mFitAll = QAction('Fit All', self, checkable=True)
        self.mFitAll.triggered.connect(self.fit_one_or_all_changed)
        m.addAction(self.mFitAll)

    def _check(self, menu, text, checked):
        a = QAction(text, self, checkable=True)
        a.setChecked(checked)
        a.triggered.connect(self.plot_this)
        menu.addAction(a)
        return a

    def _build_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        g = QGridLayout(w)
        g.setContentsMargins(4, 4, 4, 4)
        g.setSpacing(4)
        for c in range(5):
            g.setColumnStretch(c, 1)

        self.ddSliceSelector = QComboBox()
        self.ddSliceSelector.currentIndexChanged.connect(self._on_slice_selector)
        g.addWidget(self.ddSliceSelector, 0, 0, 1, 4)
        self.bChangeColor = QPushButton()
        self.bChangeColor.setToolTip('Source colour')
        self.bChangeColor.clicked.connect(self._change_color)
        g.addWidget(self.bChangeColor, 0, 4)
        self._show_color()

        self.lScript = QListWidget()
        self.lScript.currentRowChanged.connect(self._on_script_row)
        self.lScript.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lScript.customContextMenuRequested.connect(self._script_menu)
        g.addWidget(self.lScript, 1, 0, 3, 5)
        g.setRowStretch(1, 1)

        self.ddParameterStep = QComboBox()
        self.ddParameterStep.addItems(STEPS)
        self.ddParameterStep.setCurrentText('1')
        self.ddParameterStep.currentTextChanged.connect(
            lambda t: self.eNumValue.setSingleStep(float(t)))
        g.addWidget(self.ddParameterStep, 4, 0, 1, 2)
        self.eNumValue = SciSpinBox()
        self.eNumValue.valueChanged.connect(lambda _v: self.edit_value_changed())
        g.addWidget(self.eNumValue, 4, 2, 1, 3)

        self.LLabel = QLabel('L')
        g.addWidget(self.LLabel, 5, 0)
        self.eStringValue = QLineEdit()
        self.eStringValue.editingFinished.connect(self._on_string_edited)
        g.addWidget(self.eStringValue, 5, 1, 1, 4)

        self.txtRange = QLabel('Fitting range')
        g.addWidget(self.txtRange, 6, 0, 1, 3)
        self.bClearRange = QPushButton('Clear')
        self.bClearRange.clicked.connect(lambda: self.range_changed('clear'))
        g.addWidget(self.bClearRange, 7, 0, 1, 2)
        for col, (text, color, tip, mode) in enumerate(
                (('+', '#0000ff', 'Add Range', 'add'), ('-', '#ff0000', 'Delete Range', 'remove')),
                start=3):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setStyleSheet(f'QPushButton {{ color: {color}; font-weight: bold; font-size: 16pt; }}')
            b.clicked.connect(lambda _=False, m=mode: self.range_changed(m))
            g.addWidget(b, 7, col)

        self.bFitOnce = QPushButton('Fit Slice')
        self.bFitOnce.clicked.connect(self.fit_once)
        g.addWidget(self.bFitOnce, 9, 0, 1, 5)
        self.butFitAll = QPushButton('Fit All Slices')
        self.butFitAll.clicked.connect(self.fit_all)
        g.addWidget(self.butFitAll, 10, 0, 1, 5)
        g.setRowMinimumHeight(8, 6)

    def _show_color(self):
        self.bChangeColor.setStyleSheet(
            'QPushButton {{ background-color: rgb({}, {}, {}); }}'.format(*self.color))

    def _script_menu(self, pos):
        m = QMenu(self)
        m.addAction('ReloadValue').triggered.connect(lambda: self._on_script_row(self.lScript.currentRow()))
        m.addSeparator()
        m.addAction('Enter Expression').triggered.connect(lambda: self.edit_value_changed('expression'))
        m.addAction('Convert to String').triggered.connect(lambda: self.edit_value_changed('to_string'))
        m.addAction('Convert to Number').triggered.connect(lambda: self.edit_value_changed('to_number'))
        m.addSeparator()
        m.addAction('Copy To All Slices').triggered.connect(self.copy_to_all_slices)
        m.exec(self.lScript.mapToGlobal(pos))

    # ================================================================ helpers
    @property
    def selected_set(self) -> int:
        return max(self.ddSliceSelector.currentIndex(), 0) if self.mFitAll.isChecked() else 0

    def _source(self) -> KzData:
        return self.host.get_data('psource' if self.mSimUseProcessing.isChecked() else 'source')

    def _ensure_area(self, n: int):
        if len(self.area_fit) > n:
            self.area_fit = self.area_fit[:n]
        elif len(self.area_fit) < n:
            self.area_fit = np.concatenate([self.area_fit, np.ones(n - len(self.area_fit), bool)])

    def update_fit_list(self):
        self.ddSliceSelector.blockSignals(True)
        self.ddSliceSelector.clear()
        self.ddSliceSelector.addItems([str(i + 1) for i in range(len(self.fits))])
        self.ddSliceSelector.blockSignals(False)

    def update_script_list(self):
        row = self.lScript.currentRow()
        self.lScript.blockSignals(True)
        self.lScript.clear()
        self.lScript.addItems(self.fits[self.selected_set]['script'])
        self.lScript.blockSignals(False)
        if 0 <= row < self.lScript.count():
            self.lScript.setCurrentRow(row)

    # ================================================================ host
    def file_update(self):
        return  # as in MATLAB

    def _on_viewer_slice(self, value: int):
        if self.mFitAll.isChecked() and value != self.ddSliceSelector.currentIndex() \
                and value < self.ddSliceSelector.count():
            self.ddSliceSelector.setCurrentIndex(value)

    # ================================================================ plotting
    def plot_this(self):
        src = self._source()
        if src.is_empty:
            return
        self._ensure_area(len(src.ax.x))
        fit_all = self.mFitAll.isChecked()
        if fit_all:
            columns = slice(None)
        else:
            k = min(self.host.get('slice'), src.y.shape[1] - 1)
            columns = slice(k, k + 1)
        y = src.y[:, columns]

        s = src.copy()
        s.y = y
        s.ax.Color = self.color
        s.ax.s = 0
        s.title = 'Src'
        out = [s]

        if self.mShowRange.isChecked() and (~self.area_fit).any():
            r = src.copy()
            r.ax.x = src.ax.x[~self.area_fit]
            r.y = y[~self.area_fit, :]
            r.ax.Marker = '.'
            r.ax.LineStyle = 'none'
            r.ax.Color = (0.75, 0.75, 0.75)
            r.ax.s = 0
            r.title = 'Ignore'
            out.append(r)

        if fit_all:
            fit_y = np.zeros(y.shape)
            have = False
            for ii, f in enumerate(self.fits[:y.shape[1]]):
                if f['y'] is not None and len(f['y']) == y.shape[0]:
                    fit_y[:, ii] = f['y']
                    have = True
        else:
            f = self.fits[0]['y']
            have = f is not None and len(f) == y.shape[0]
            fit_y = f.reshape(-1, 1) if have else None
        if have:
            r = src.copy()
            r.y = fit_y
            r.ax.Color = 'r'
            r.ax.s = 0
            r.title = 'Fit'
            out.append(r)
            if self.mShowDifference.isChecked():
                r = src.copy()
                r.y = np.real(y) - fit_y
                r.ax.Color = 'g'
                r.ax.s = 0
                r.title = 'Diff'
                out.append(r)
        self.host.set_data('output', out)

    # ================================================================ fitting
    def _fit_set(self, n: int, column: int, src: KzData) -> float:
        self._ensure_area(len(src.ax.x))
        t0 = time.perf_counter()
        script, sim = autofit(self.fits[n]['script'], src.ax.x, np.real(src.y[:, column]),
                              self.area_fit)
        self.fits[n]['script'] = script
        self.fits[n]['y'] = np.asarray(sim, float)
        self.fits[n]['slice'] = column
        return time.perf_counter() - t0

    def _run(self, fn):
        try:
            fn()
        except Exception as e:  # a script error must not kill the plugin
            self.host.set('message', f'Fit error: {e}')

    def fit_once(self):
        def go():
            src = self._source()
            if src.is_empty:
                return
            if self.mFitAll.isChecked():
                n = column = self.selected_set
            else:
                n, column = 0, self.host.get('slice')
            dt = self._fit_set(n, min(column, src.y.shape[1] - 1), src)
            self.host.set('message', f'Computations: {dt:f} sec')
            self.update_script_list()
            self.plot_this()
        self._run(go)

    def fit_all(self):
        if not self.mFitAll.isChecked():
            self.host.set('message', 'Select: Fit -> FitAll')
            return

        def go():
            src = self._source()
            for ii in range(min(len(self.fits), src.y.shape[1])):
                dt = self._fit_set(ii, ii, src)
                self.host.set('message', f'Computations: slide {ii + 1} {dt:f} sec')
            self.update_script_list()
            self.plot_this()
        self._run(go)

    def fit_one_or_all_changed(self):
        n = self.host.get_data('source').y.shape[1]
        if self.mFitAll.isChecked():
            if len(self.fits) != n:
                first = self.fits[0]
                self.fits = [{'script': list(first['script']), 'y': None, 'slice': ii}
                             for ii in range(n)]
        elif len(self.fits) != 1:
            self.fits = self.fits[:1]
        self.update_fit_list()
        if self.mFitAll.isChecked():
            self.ddSliceSelector.setCurrentIndex(min(self.host.get('slice'), n - 1))
        self.update_script_list()
        self.plot_this()

    # ================================================================ script editing
    def select_function(self, script: list[str]):
        for f in self.fits:
            f['script'] = list(script)
            f['y'] = None
        self.update_script_list()

    def _edit_function(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('Fit Function')
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("One line each: 'f = model', then 'parameter = start value'"))
        ed = QPlainTextEdit('\n'.join(self.fits[self.selected_set]['script']))
        lay.addWidget(ed)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(380, 260)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        script = [s.strip() for s in ed.toPlainText().splitlines() if s.strip()]
        if not script:
            return
        old = self.fits[self.selected_set]['script']
        script += [s for s in old if s.startswith('FitRng') and s not in script]
        self.select_function(script)

    def _on_script_row(self, row: int):
        if row < 0 or row >= self.lScript.count():
            return
        name, _, rhs = self.lScript.item(row).text().partition('=')
        rhs = rhs.strip()
        self.eNumValue.blockSignals(True)
        if name.strip() == 'f':
            self.eStringValue.setEnabled(True)
            self.eStringValue.setText(rhs)
            self.eNumValue.setEnabled(False)
            self.editor_mode, label = 'function', 'F'
        elif rhs.startswith("'"):
            self.eStringValue.setEnabled(True)
            end = rhs.find("'", 1)
            self.eStringValue.setText(rhs[1:end if end > 0 else len(rhs)])
            self.eNumValue.setEnabled(False)
            self.editor_mode, label = 'string', 'S'
        else:
            self.eNumValue.setEnabled(True)
            try:
                self.eNumValue.setValue(float(_value(rhs)))
            except Exception:
                self.eNumValue.setValue(0.0)
            self.eStringValue.setEnabled(False)
            self.editor_mode, label = 'value', 'V'
        self.eNumValue.blockSignals(False)
        self.LLabel.setText(label)

    def _on_string_edited(self):
        if self.eStringValue.isModified():
            self.eStringValue.setModified(False)
            self.edit_value_changed()

    def edit_value_changed(self, action: str | None = None):
        row = self.lScript.currentRow()
        if row < 0:
            return
        script = [self.lScript.item(i).text() for i in range(self.lScript.count())]
        name = script[row].partition('=')[0].strip()
        if action == 'to_number':
            script[row] = f'{name} = 0.0'
        elif action == 'to_string':
            script[row] = f"{name} = 'string'"
        elif action == 'expression':
            text, ok = QInputDialog.getText(self, 'Enter Expression', f'{name} =',
                                            text=script[row].partition('=')[2].strip())
            if not ok:
                return
            script[row] = f'{name} = {text}'
        elif self.editor_mode == 'function':
            script[row] = 'f = ' + self.eStringValue.text().strip()
        elif self.editor_mode == 'string':
            script[row] = f"{name} = '{self.eStringValue.text().strip()}'"
        else:
            script[row] = f'{name} = {_num2str(self.eNumValue.value())}'

        # re-evaluate all parameters, keep those the model uses, add missing ones as 0
        values, model, extra = {}, None, []
        for line in script:
            n, eq, rhs = line.partition('=')
            if not eq:
                continue
            if n.strip() == 'f':
                model = line
            elif n.strip().startswith(('FitRng', 'MaxIter')) or n.strip().startswith('pol'):
                extra.append(line)
            else:
                try:
                    values[n.strip()] = _value(rhs, values)
                except Exception:
                    values[n.strip()] = rhs.strip()
        if model is None:
            self.host.set('message', 'can not find function')
            return
        new = [model]
        for tok in tokens(model) if 'polyfit' not in model else list(values):
            v = values.get(tok, 0.0)
            new.append(f"{tok} = '{v}'" if isinstance(v, str) else f'{tok} = {_num2str(v)}')
        new += extra
        n = self.selected_set
        self.fits[n]['script'] = new
        self.update_script_list()
        self._on_script_row(self.lScript.currentRow())

        src = self.host.get_data('source')
        try:
            self.fits[n]['y'] = evaluate_script(new, src.ax.x)
        except Exception as e:
            self.fits[n]['y'] = None
            self.host.set('message', f'Evaluation error: {e}')
        if not self.mFitAll.isChecked():
            self.fits[0]['slice'] = self.host.get('slice')
        self.plot_this()

    def copy_to_all_slices(self):
        if self.mFitAll.isChecked():
            script = self.fits[self.selected_set]['script']
            for f in self.fits:
                f['script'] = list(script)

    # ================================================================ ranges / slices
    def range_changed(self, mode: str):
        src = self.host.get_data('source')
        x = src.ax.x
        self._ensure_area(len(x))
        if mode == 'clear':
            self.area_fit = np.ones(len(x), bool)
        else:
            self.host.set('message', 'Select the beginning and the end of the range')
            pos = self.host.ginput(2)
            if len(pos) < 2:
                return
            lo, hi = np.sort(pos[:, 0])
            self.area_fit[(x > lo) & (x < hi)] = mode == 'add'
        self.plot_this()

    def _on_slice_selector(self, index: int):
        if index < 0:
            return
        if self.mFitAll.isChecked():
            self.host.set('slice', index)
        self.update_script_list()
        self.plot_this()

    def _change_color(self):
        c = QColorDialog.getColor(QColor(*self.color), self, 'Source colour')
        if c.isValid():
            self.color = (c.red(), c.green(), c.blue())
            self._show_color()
            self.plot_this()
