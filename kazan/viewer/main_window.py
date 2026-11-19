"""Kazan viewer main window: port of kazan3.mlapp, and the in-process KazanHost."""
from __future__ import annotations

import fnmatch
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEventLoop, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QFileDialog,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollBar, QSizePolicy, QVBoxLayout, QWidget)

from ..core.data import KzData, Struct, verify
from ..core.ini import KazanIni
from ..core.plugin import KazanPlugin, PluginInfo, discover_plugins
from ..core.processing import process
from ..io import loaders
from ..io.params import parameter_reader
from .plot import COLOR_ORDER, KazanPlot

RESOURCES = Path(__file__).resolve().parent.parent / 'resources'
DEFAULT_PLUGIN_PATH = Path(__file__).resolve().parents[2] / 'plugins'

MATLAB_STYLE = """
QMainWindow { background: #f0f0f0; }
QPushButton { background: #fdfdfd; border: 1px solid #adadad; border-radius: 3px;
              padding: 3px 8px; }
QPushButton:hover { border-color: #0078d7; }
QPushButton:pressed { background: #d6d6d6; }
QPushButton:checkable { background: #f5f5f5; }
/* kazan3 UpdateStateButtons: high-contrast "on" look, onColor = [1 0.65 0.2] */
QPushButton:checked { background: #ffa633; border-color: #c27a1a; }
QPushButton:checked:hover { border-color: #0078d7; }
QListWidget::item:selected { background: #c0c0c0; color: black; }
"""


@dataclass
class View:
    """Port of ``app.View`` (only the fields used so far)."""
    data_src_out: int = 1        # 1 source, 2 output
    part: str = 'real'           # 'real' | 'reim' | 'magn'
    plot_type: str = '1D'        # '1D' | 'Stack' | 'Contour' | 'Density'
    position: int = 0            # current slice, 0-based
    range: str = 'tight'         # 'tight' | 'auto' | 'manual'
    grid: bool = False
    default_font: int = 12
    font: int = 12


class KazanViewer(QMainWindow):
    """The viewer window. Implements :class:`kazan.core.plugin.KazanHost`."""

    sourceChanged = Signal()
    sliceChanged = Signal(int)

    def __init__(self, plugin_path: Path | None = None, ini: KazanIni | None = None):
        super().__init__()
        self.ini = ini or KazanIni()
        self.plugin_path = Path(plugin_path or self.ini.get(
            'KazanViewer', 'plugin_path', str(DEFAULT_PLUGIN_PATH)))
        self.src: KzData = verify(KzData())
        self.out: list[KzData] = []
        self.plugins: list[KazanPlugin] = []
        self.plugin_infos: list[PluginInfo] = []
        self.view = View()
        self.view.default_font = self.view.font = QApplication.font().pointSize()
        self._message = ''
        self._message_until = 0.0
        self._ginput: dict | None = None
        self._dir_entries: list[tuple[str, bool]] = []   # (name, is_dir)

        self.setWindowTitle('KAZAN3')
        self.setWindowIcon(QIcon(str(RESOURCES / 'pbZoom.png')))
        QApplication.instance().setStyleSheet(MATLAB_STYLE)   # plugins share the look
        self.resize(1165, 860)
        self._build_ui()
        self._build_menus()

        self.make_plugins('search')
        self._load_logo()
        self.load_directory(self.ini.get('KazanViewer', 'last_path', str(Path.home())))
        self.set('message', 'Welcome !')

    # ================================================================ UI
    def _build_ui(self):
        central = QWidget(objectName='central')
        self.setCentralWidget(central)
        h = QHBoxLayout(central)
        h.setContentsMargins(8, 6, 8, 6)

        # ---- left: directory browser + results
        left = QWidget()
        left.setFixedWidth(310)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.ePath = QLineEdit()
        self.ePath.returnPressed.connect(lambda: self.load_directory(self.ePath.text()))
        lv.addWidget(self.ePath)
        row = QHBoxLayout()
        self.ddExt = QComboBox()
        self.ddExt.addItems(loaders.EXTENSIONS)
        self.ddExt.setCurrentText(self.ini.get('KazanViewer', 'ext', '*'))
        self.ddExt.currentTextChanged.connect(self._on_ext_changed)
        self.ddDataType = QComboBox()
        self.ddDataType.currentTextChanged.connect(
            lambda t: t and self.ini.set('KazanViewer', 'datatype', t))
        self.bUp = QPushButton('Up')
        self.bUp.setFixedWidth(46)
        self.bUp.clicked.connect(lambda: self.load_directory(str(Path(self.ePath.text()).parent)))
        row.addWidget(self.ddDataType, 1)
        row.addWidget(self.ddExt, 1)
        row.addWidget(self.bUp)
        lv.addLayout(row)
        self.lbDirlist = QListWidget()
        self.lbDirlist.currentRowChanged.connect(self._on_dirlist_selected)
        self.lbDirlist.itemActivated.connect(lambda _: self._on_dirlist_activated())
        lv.addWidget(self.lbDirlist, 1)
        lv.addWidget(QLabel('Results'))
        self.TextArea = QPlainTextEdit(readOnly=True)
        self.TextArea.setFixedHeight(90)
        lv.addWidget(self.TextArea)
        h.addWidget(left)
        self._on_ext_changed(self.ddExt.currentText())
        self.ddDataType.setCurrentText(self.ini.get('KazanViewer', 'datatype', ''))

        # ---- right: view buttons, parameter row, plot, slice slider
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)

        row1 = QHBoxLayout()
        self.bSource, self.bOutput = QPushButton('Source'), QPushButton('Output')
        self.bTransfer = QPushButton('<<')
        self.bTransfer.setFixedWidth(30)
        self.bTransfer.setToolTip('Transfer an output trace to the source')
        self.bTransfer.clicked.connect(self._on_transfer)
        self._group(row1, [(self.bSource, 1), (self.bTransfer, None), (self.bOutput, 2)],
                    self._on_src_out)
        row1.addSpacing(30)
        self.part_buttons = self._group(
            row1, [(QPushButton(t), v) for t, v in
                   (('Real', 'real'), ('Re/Im', 'reim'), ('Magn', 'magn'))], self._on_part)
        row1.addSpacing(30)
        self.type_buttons = self._group(
            row1, [(QPushButton(t), t) for t in ('1D', 'Stack', 'Contour', 'Density')],
            self._on_plot_type)
        row1.addStretch(1)
        rv.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(3)
        self.ddSelParameter = QComboBox()
        self.ddSelParameter.setMinimumWidth(200)
        self.ddSelParameter.currentTextChanged.connect(self._on_parameter_selected)
        self.eParameter = QLineEdit()
        self.eParameter.returnPressed.connect(self._on_parameter_set)
        bEq = QPushButton('=')
        bEq.setFixedWidth(26)
        bEq.setToolTip('Set parameter value')
        bEq.clicked.connect(self._on_parameter_set)
        row2.addWidget(self.ddSelParameter)
        row2.addWidget(self.eParameter, 1)
        row2.addWidget(bEq)
        self.bMeasure = self._tool(row2, 'pbCross.png', 'Measure', checkable=True)
        self.bZoom = self._tool(row2, 'pbZoom.png', 'Zoom', checkable=True)
        self.bMeasure.toggled.connect(self._on_measure_toggled)
        self.bZoom.toggled.connect(self._on_zoom_toggled)
        self._tool(row2, 'pbXExpand.png', 'Zoom on X').clicked.connect(
            lambda: self.plot.scale(0.5, 1))
        self._tool(row2, 'pbXCollapse.png', 'Expand X').clicked.connect(
            lambda: self.plot.scale(2, 1))
        self._tool(row2, 'pbYExpand.png', 'Zoom on Y').clicked.connect(
            lambda: self.plot.scale(1, 0.5))
        self._tool(row2, 'pbYCollapse.png', 'Expand Y').clicked.connect(
            lambda: self.plot.scale(1, 2))
        rv.addLayout(row2)

        self.plot = KazanPlot()
        self.plot.set_font_size(self.view.font)
        self.plot.clicked.connect(self._on_plot_clicked)
        self.plot.contextMenuRequested.connect(self._on_plot_context_menu)
        rv.addWidget(self.plot, 1)

        self.sl2Dplot = QScrollBar(Qt.Orientation.Horizontal)
        self.sl2Dplot.valueChanged.connect(lambda v: self.set('slice', v))
        self.lSlice = QLabel()
        srow = QHBoxLayout()
        srow.addWidget(self.sl2Dplot, 1)
        srow.addWidget(self.lSlice)
        self.slice_row = QWidget()
        self.slice_row.setLayout(srow)
        srow.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.slice_row)
        h.addWidget(right, 1)

        self.bSource.setChecked(True)
        self.part_buttons['real'].setChecked(True)
        self.type_buttons['1D'].setChecked(True)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._ginput_cancel)

    @staticmethod
    def _group(layout, buttons, callback) -> dict:
        grp = QButtonGroup(layout)
        grp.setExclusive(True)
        out = {}
        row = QHBoxLayout()
        row.setSpacing(2)
        for b, value in buttons:
            row.addWidget(b)
            if value is None:
                continue
            b.setCheckable(True)
            b.setMinimumWidth(64)
            grp.addButton(b)
            b.clicked.connect(lambda _=False, v=value: callback(v))
            out[value] = b
        layout.addLayout(row)
        return out

    @staticmethod
    def _tool(layout, icon, tip, checkable=False) -> QPushButton:
        b = QPushButton()
        b.setIcon(QIcon(str(RESOURCES / icon)))
        b.setIconSize(QSize(14, 14))
        b.setFixedSize(38, 24)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        layout.addWidget(b)
        return b

    def _build_menus(self):
        mb = self.menuBar()
        todo = []  # menu items kept for the original look but not ported yet

        m = mb.addMenu('File')
        m.addAction('Open Directory', self._menu_open_directory)
        self.mFavoriteDirectories = m.addMenu('Favorite Directories')
        self._fill_favorite_dirs()
        m.addSeparator()
        m.addAction('Save Source', lambda: self._menu_save(False))
        m.addAction('Save Source with Processing', lambda: self._menu_save(True))
        todo += [m.addAction('Convert Folder to ASCII (dat)'),
                 m.addAction('Convert Folder to ASCII (txt)')]
        m.addSeparator()
        todo += [m.addAction('Export Src to Workspace'), m.addAction('Export Out to Workspace'),
                 m.addAction('Load Src from Workspace')]

        m = mb.addMenu('View')
        fm = m.addMenu('Font')
        g = QActionGroup(self)
        for d in range(-4, 5):
            a = fm.addAction('Default' if d == 0 else f'{d:+d}')
            a.setCheckable(True)
            a.setChecked(d == 0)
            g.addAction(a)
            a.triggered.connect(lambda _=False, d=d: self.set('font', self.view.default_font + d))
        m.addSeparator()
        g = QActionGroup(self)
        for text, mode in (('Axis Tight', 'tight'), ('Axis Auto', 'auto'), ('Axis Manual', 'manual')):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setChecked(mode == self.view.range)
            g.addAction(a)
            a.triggered.connect(lambda _=False, mode=mode: self._set_range(mode))
        todo.append(m.addAction('Select View Area'))
        m.addAction('Zoom', self.bZoom.toggle)
        m.addSeparator()
        a = m.addAction('Show Grid')
        a.setCheckable(True)
        a.toggled.connect(self._set_grid)
        todo += [m.addAction('Show Minor Grid'), m.addAction('Aspect Normal'),
                 m.addAction('Aspect Square'), m.addAction('Axis Equal')]
        m.addSeparator()
        for text, key, fn in (
                ('Next File', 'Ctrl+Down', lambda: self._step_file(1)),
                ('Previous File', 'Ctrl+Up', lambda: self._step_file(-1)),
                ('Next Slice', 'Ctrl+Right', lambda: self.set('slice', self.view.position + 1)),
                ('Previous Slice', 'Ctrl+Left', lambda: self.set('slice', self.view.position - 1))):
            a = m.addAction(text)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(fn)

        m = mb.addMenu('Tools')
        m.addAction('Clear Source', self._menu_clear_source)
        todo += [m.addAction('Fix Source Processing'), m.addAction('Cut Slice')]
        m.addAction('Show Load Script', lambda: self.set('log', self.src.script or '(none)'))

        self.mPluginsMain = mb.addMenu('Plugins')

        m = mb.addMenu('Window')
        todo += [m.addAction('New Window'), m.addAction('Show in Window'),
                 m.addAction('Plot 1D'), m.addAction('Plot 2D')]

        m = mb.addMenu('Help')
        m.addAction('How to Start', self._menu_how_to_start)
        m.addAction('About Kazan Viewer', lambda: QMessageBox.about(
            self, 'About', 'KAZAN data viewer and plugins\nPython port of Kazan Viewer 3.0\n'
                           'by Boris Epel, 2003-2026'))
        for a in todo:
            a.setEnabled(False)
            a.setToolTip('Not ported yet')

    # ================================================================ KazanHost API
    def get_data(self, mode):
        if mode == 'source':
            return verify(self.src.copy())
        if mode == 'psource':
            d, _ = process(verify(self.src.copy()))
            return verify(d)
        if mode == 'output':
            return [d.copy() for d in self.out]
        raise ValueError(f'get_data: unknown mode {mode!r}')

    def set_data(self, mode, data):
        if mode == 'source':
            self.src = verify(data.copy())
            self.src_control_update()
        elif mode == 'output':
            items = data if isinstance(data, (list, tuple)) else [data]
            self.out = [verify(d.copy()) for d in items]
            self.update_slider()
        else:
            raise ValueError(f'set_data: unknown mode {mode!r}')
        self.view.data_src_out = 2
        self.bOutput.setChecked(True)
        self.plot_data()

    def get(self, key):
        if key == 'font':
            return self.view.font
        if key == 'slice':
            return min(self.view.position, max(self.src.y.shape[1] - 1, 0))
        return None

    def set(self, key, value=None):
        if key == 'font':
            self.view.font = int(value)
            f = QApplication.font()
            f.setPointSize(self.view.font)
            QApplication.setFont(f)      # applies to plugin windows too
            self.plot.set_font_size(self.view.font)
            self.plot_data()
        elif key == 'slice':
            n = self._n_slices()
            value = int(np.clip(int(value), 0, max(n - 1, 0)))
            if value != self.view.position:
                self.view.position = value
                self.sl2Dplot.blockSignals(True)
                self.sl2Dplot.setValue(value)
                self.sl2Dplot.blockSignals(False)
                self.plot_data()
                self.sliceChanged.emit(value)
        elif key == 'cursor':
            self.plot.set_title(str(value))
        elif key == 'message':
            self._message = str(value)
            self._message_until = time.monotonic() + 3.0
            self.plot.set_title(self._message)
        elif key == 'log':
            lines = value if isinstance(value, (list, tuple)) else [value]
            if self.TextArea.blockCount() > 4:
                self.TextArea.clear()
            self._log_prepend([str(v) for v in lines])
        elif key == 'log_all':
            lines = value if isinstance(value, (list, tuple)) else [value]
            self._log_prepend([str(v) for v in lines])
        elif key == 'log_clear':
            self.TextArea.clear()

    def ginput(self, n: int) -> np.ndarray:
        """Blocking selection of n points; runs a local event loop like MATLAB ginput."""
        if self._ginput is not None:
            return np.zeros((0, 2))
        loop = QEventLoop()
        self._ginput = {'n': int(n), 'points': [], 'loop': loop}
        self.plot.setCursor(Qt.CursorShape.CrossCursor)
        self.activateWindow()
        try:
            loop.exec()
        finally:
            pts = self._ginput['points']
            self._ginput = None
            self._message_until = 0.0   # the selection prompt is done
            self.plot.unsetCursor()
        return np.array(pts, dtype=float).reshape(-1, 2)

    def plugin_closed(self, plugin):
        self.plugins = [p for p in self.plugins if p is not plugin]
        print(f'Plugin removed. {len(self.plugins)} left.')

    # ================================================================ data
    def _load_logo(self):
        """The KAZAN logo shown at start (from kazan3 startupFcn)."""
        sz = 0.3
        kx = np.array([-.15, 0, 0, 0, 1, 0, 1]) * 1.3
        ky = [1, 1, 0, .5, 1, .5, 0]
        ax_ = np.array([0, .5, .75, .25, .75, 1])
        ay = [0, 1, .5, .5, .5, 0]
        zx = np.array([0, 1, 0, 0, 0, 1, 0, 1, 1, 1])
        zy = [0, 1, 1, .92, 1, 1, 0, 0, .08, 0]
        nx = np.array([0, 0, 1, 1, 1 + .15]) * 1.4
        ny = [0, 1, 0, 1, 1]
        x = np.concatenate([[8, 8, -2, -2], kx - .3, ax_ + 1.2, zx + 2.4, ax_ + 3.6, nx + 4.8,
                            [8, 8, 6.2, 8, 8, -2, -2, -0.3, -2, -2]]) * sz
        y = np.concatenate([[1, 2, 2, 1], ky, ay, zy, ay, ny, [1, 0, 0, 0, -1, -1, 0, 0, 0, 1]])
        self.src = verify(KzData(y=y, ax=Struct(x=x, y=np.array([1.0]), type='data',
                                                xlabel='KAZAN viewer logo,', ylabel='a.u.')))
        self.src_control_update()

    def load_file(self, filename: str):
        """Port of LoadFile."""
        size = Path(filename).stat().st_size if Path(filename).exists() else 0
        if size >= 2 ** 20:
            answer = QMessageBox.question(
                self, f'File size {size / 2 ** 20:10.2f}Mb', 'Do you want to continue reading?')
            if answer != QMessageBox.StandardButton.Yes:
                return
        ext, subtype = self.ddExt.currentText(), self.ddDataType.currentText()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ax, y, dsc = loaders.load(filename, ext, subtype)
        except Exception as e:
            traceback.print_exc()
            self.set('message', f'Load error: {e}')
            self.set('log', f'{Path(filename).name}: {e}')
            return
        finally:
            QApplication.restoreOverrideCursor()
        ax, dsc = Struct(ax), Struct(dsc)
        y = np.asarray(y)
        while y.ndim > 2 and y.shape[-1] == 1:   # MATLAB size() drops trailing singletons
            y = y[..., 0]
        if y.ndim > 2:   # MATLAB: data dimension is reduced to 2D
            self.set('log', 'Data dimension is reduced.')
            y = y.reshape((y.shape[0], -1), order='F')
            ax.y = np.arange(1.0, y.shape[1] + 1)
        ax = parameter_reader(ax, dsc)
        ax.dx = 0
        ax.Datatype = ext + subtype
        if dsc.get('KAZANwarning'):
            self.set('log', dsc.KAZANwarning)
        self._message_until = 0.0   # a new file replaces any pending message
        self.ini.set('KazanViewer', 'last_file', filename)
        self.src = verify(KzData(y=y, ax=ax, dsc=dsc, filename=filename,
                                 script=f"loaders.load({filename!r}, {ext!r}, {subtype!r})"))
        self.src_control_update()

    def src_control_update(self):
        """Port of SrcControlUpdate: refresh controls, notify plugins, replot."""
        title = self.src.ax.get('title') or ''
        name = self.src.filename or ''
        self.setWindowTitle(f'KAZAN3 - {name} [{title}]' if name else 'KAZAN3')
        self._fill_parameter_list()
        self.update_slider()
        self.sourceChanged.emit()
        self.plot_data()

    def _n_slices(self) -> int:
        n = self.src.y.shape[1] if not self.src.is_empty else 1
        for d in self.out:
            n = max(n, d.y.shape[1])
        return n

    def update_slider(self):
        n = self._n_slices()
        self.view.position = min(self.view.position, n - 1)
        self.sl2Dplot.blockSignals(True)
        self.sl2Dplot.setRange(0, max(n - 1, 0))
        self.sl2Dplot.setValue(self.view.position)
        self.sl2Dplot.blockSignals(False)
        self.slice_row.setVisible(n > 1 and self.view.plot_type == '1D')

    def _current_target(self) -> KzData | None:
        """Data the processing context menu acts on (MATLAB: src or out{1})."""
        if self.view.data_src_out == 1:
            return self.src
        return self.out[0] if self.out else None

    # ================================================================ plotting
    def plot_data(self):
        """Port of PlotData (subset: 1D / Stack / Contour / Density)."""
        try:
            self._plot_data()
        except Exception:
            traceback.print_exc()
            self.set('message', 'Plot error, see console')

    @staticmethod
    def _plot_axis(d: KzData) -> KzData:
        """Axis corrections ax.dx / ax.dy (MATLAB getplotaxis, linear representation)."""
        for axis, key in (('x', 'dx'), ('y', 'dy')):
            try:
                shift = float(d.ax.get(key) or 0)
            except (TypeError, ValueError):
                shift = 0.0
            if shift and d.ax.get(axis) is not None:
                d.ax[axis] = np.asarray(d.ax[axis], float) + shift
            d.ax[key] = 0
        return d

    def _datasets(self) -> list[tuple[KzData, str]]:
        if self.view.data_src_out == 1:
            d, warnings = process(self.src.copy())
            for w in warnings:
                self.set('log', w)
            return [(self._plot_axis(d), 'b')]
        sets = []
        for i, o in enumerate(self.out):
            d, _ = process(o.copy())
            d = self._plot_axis(d)
            c = o.ax.get('Color')
            if c is None or (isinstance(c, str) and not c):
                c = COLOR_ORDER[i % len(COLOR_ORDER)]
            sets.append((d, c))
        return sets

    @staticmethod
    def _style(d: KzData) -> dict:
        """Line style fields of a data set (MATLAB SuperPlot)."""
        lw = d.ax.get('LineWidth', 1)
        try:
            lw = float(lw)
        except (TypeError, ValueError):
            lw = 1.0
        return dict(width=lw, style=d.ax.get('LineStyle') or '-', marker=d.ax.get('Marker') or 'none')

    def _part(self, y):
        if self.view.part == 'magn':
            return np.abs(y), None
        return np.real(y), (np.imag(y) if self.view.part == 'reim' else None)

    def _plot_data(self):
        p = self.plot
        p.clear_plots()
        p.show_imag(self.view.part == 'reim')
        self.slice_row.setVisible(self._n_slices() > 1 and self.view.plot_type == '1D')
        sets = [(d, c) for d, c in self._datasets() if not d.is_empty]
        if not sets:
            p.set_title('No data')
            return
        ref = sets[0][0]

        if self.view.plot_type in ('Contour', 'Density') and ref.is_2d:
            re, im = self._part(ref.y)
            draw = p.density if self.view.plot_type == 'Density' else p.contour
            draw(p.real, ref.ax.x, ref.ax.y, re)
            if im is not None:
                draw(p.imag, ref.ax.x, ref.ax.y, im)
            ylabel = ref.ax.ylabel
        else:
            for d, color in sets:
                re, im = self._part(d.y)
                if self.view.plot_type == 'Stack' and d.is_2d:
                    step = np.nanmax(np.abs(re)) or 1.0
                    for k in range(re.shape[1]):
                        p.line(p.real, d.ax.x, re[:, k] + k * step, color, **self._style(d))
                        if im is not None:
                            p.line(p.imag, d.ax.x, im[:, k] + k * step, color, **self._style(d))
                else:
                    k = min(self.view.position, re.shape[1] - 1)
                    p.line(p.real, d.ax.x, re[:, k], color, **self._style(d))
                    if im is not None:
                        p.line(p.imag, d.ax.x, im[:, k], color, **self._style(d))
            ylabel = ref.ax.get('unit') or 'a.u.'
        p.set_labels(ref.ax.xlabel, ylabel)

        if ref.is_2d:
            yv = ref.ax.y[min(self.view.position, len(ref.ax.y) - 1)]
            self.lSlice.setText(f'{ref.ax.ylabel}: {yv:g}  [{self.view.position + 1}/{len(ref.ax.y)}]')

        if time.monotonic() < self._message_until:
            p.set_title(self._message)
        else:
            src = self.src if self.view.data_src_out == 1 else ref
            p.set_title(Path(src.filename).name if src.filename else (src.title or ''))
        if self.view.range != 'manual':
            p.set_range_mode(self.view.range)

    # ================================================================ plugins
    def make_plugins(self, mode: str):
        """Port of MakePlugins: 'search' builds the menu, 'closeall' closes plugins."""
        if mode == 'closeall':
            for p in list(self.plugins):
                p.close()
            return
        if mode != 'search':
            return
        self.plugin_infos, errors = discover_plugins(self.plugin_path)
        for e in errors:
            self.set('log_all', f'Plugin load error: {e}')
            print(e)

        m = self.mPluginsMain
        m.clear()
        fav = {i.name for i in self.plugin_infos
               if self.ini.get(i.name, 'favorite', '0') == '1'}
        for info in self.plugin_infos:
            if info.name in fav:
                m.addAction(info.label, lambda i=info: self.launch_plugin(i))
        other = m.addMenu('Other plugins')
        m.addSeparator()
        add_fav = m.addMenu('Add to Favorites')
        rem_fav = m.addMenu('Remove from Favorites')
        for info in self.plugin_infos:
            if info.name in fav:
                rem_fav.addAction(info.label, lambda i=info: self._set_favorite(i, False))
            else:
                other.addAction(info.label, lambda i=info: self.launch_plugin(i))
                add_fav.addAction(info.label, lambda i=info: self._set_favorite(i, True))
        m.addSeparator()
        m.addAction('Arrange plugins', self._arrange_plugins)
        m.addAction('Reload plugins', lambda: self.make_plugins('search'))

    def launch_plugin(self, info: PluginInfo):
        try:
            plugin = info.cls(self, uuid.uuid4().hex)
        except Exception:
            traceback.print_exc()
            self.set('message', f'Plugin {info.label} failed to start, see console')
            return
        if not plugin.windowTitle():
            plugin.setWindowTitle(info.label)
        self.plugins.append(plugin)
        plugin.show()
        print(f'Plugin is added. Overall {len(self.plugins)}')

    def _set_favorite(self, info: PluginInfo, on: bool):
        self.ini.set(info.name, 'favorite', '1' if on else '0')
        self.ini.save()
        self.make_plugins('search')

    def _arrange_plugins(self):
        g = self.frameGeometry()
        x, y = g.right() + 4, g.top()
        for p in self.plugins:
            p.move(x, y)
            p.raise_()
            y += 40

    # ================================================================ directory list
    def load_directory(self, path: str):
        path = Path(path)
        if not path.is_dir():
            path = path.parent if path.parent.is_dir() else Path.home()
        self.ePath.setText(str(path))
        pattern = self.ddExt.currentText()
        try:
            entries = list(path.iterdir())
        except OSError as e:
            self.set('log', str(e))
            entries = []
        dirs = sorted((e.name for e in entries if e.is_dir()), key=str.lower)
        if pattern == '*.':
            match = lambda n: '.' not in n
        else:
            match = lambda n: fnmatch.fnmatch(n.lower(), pattern.lower())
        files = sorted((e.name for e in entries if e.is_file() and match(e.name)), key=str.lower)
        self._dir_entries = [(d, True) for d in dirs] + [(f, False) for f in files]
        self.lbDirlist.blockSignals(True)
        self.lbDirlist.clear()
        self.lbDirlist.addItems([f'[{d}]' for d in dirs] + files)
        self.lbDirlist.blockSignals(False)
        self.ini.set('KazanViewer', 'last_path', str(path))

    def _on_dirlist_selected(self, row: int):
        if 0 <= row < len(self._dir_entries):
            name, is_dir = self._dir_entries[row]
            if not is_dir:
                self.load_file(str(Path(self.ePath.text()) / name))

    def _on_dirlist_activated(self):
        row = self.lbDirlist.currentRow()
        if 0 <= row < len(self._dir_entries):
            name, is_dir = self._dir_entries[row]
            if is_dir:
                self.load_directory(str(Path(self.ePath.text()) / name))

    def _step_file(self, step: int):
        row = self.lbDirlist.currentRow() + step
        if 0 <= row < self.lbDirlist.count():
            self.lbDirlist.setCurrentRow(row)

    def _on_ext_changed(self, ext: str):
        self.ini.set('KazanViewer', 'ext', ext)
        self.ddDataType.clear()
        self.ddDataType.addItems(loaders.subtypes(ext))
        if self.ePath.text():
            self.load_directory(self.ePath.text())

    # ================================================================ parameters
    #: port of kv3_ParameterReader('options'): (name, default, description)
    DATA_PARAMETERS = [('title', '', 'Title'), ('sample', '', 'Sample'), ('comment', '', 'Comment'),
                       ('formula', '', 'Formula'), ('freq1', 0.0, 'EPR frequency'),
                       ('reference', 0.0, 'Reference frequency'), ('cf', 0.0, 'Central Field'),
                       ('xunit', '', 'X axis unit'), ('yunit', '', 'Y axis unit (2D only)'),
                       ('unit', '', 'Signal unit')]

    def _fill_parameter_list(self):
        keep = self.ddSelParameter.currentText()
        self.ddSelParameter.blockSignals(True)
        self.ddSelParameter.clear()
        for i, (name, _default, about) in enumerate(self.DATA_PARAMETERS):
            self.ddSelParameter.addItem(name)
            self.ddSelParameter.setItemData(i, about, Qt.ItemDataRole.ToolTipRole)
        if keep:
            self.ddSelParameter.setCurrentText(keep)
        self.ddSelParameter.blockSignals(False)
        self._on_parameter_selected(self.ddSelParameter.currentText())

    def _on_parameter_selected(self, key: str):
        default = dict((n, d) for n, d, _ in self.DATA_PARAMETERS).get(key, '')
        value = self.src.ax.get(key, default) if key else ''
        self.eParameter.setText(f'{value:g}' if isinstance(value, float) else str(value))

    def _on_parameter_set(self):
        key, text = self.ddSelParameter.currentText(), self.eParameter.text()
        if not key:
            return
        default = dict((n, d) for n, d, _ in self.DATA_PARAMETERS).get(key, '')
        try:
            value = float(text) if isinstance(default, float) else text
        except ValueError:
            self.set('message', f'{key}: a number is expected')
            return
        self.src.ax[key] = value
        self.plot_data()

    # ================================================================ callbacks
    def _on_src_out(self, value: int):
        self.view.data_src_out = value
        self.plot_data()

    def _on_transfer(self):
        if not self.out:
            self.bSource.setChecked(self.view.data_src_out == 1)
            return
        if len(self.out) == 1:
            n = 0
        else:
            names = [f'{i + 1}: {d.title or "trace"}' for i, d in enumerate(self.out)]
            item, ok = QInputDialog.getItem(self, 'Transfer', 'Select trace', names, 0, False)
            if not ok:
                return
            n = names.index(item)
        src = verify(self.out[n].copy())
        if not src.filename:
            src.filename = self.out[n].title or 'transfer'
        self.src = src
        self.view.data_src_out = 1
        self.bSource.setChecked(True)
        self.src_control_update()

    def _on_part(self, value: str):
        self.view.part = value
        self.plot_data()

    def _on_plot_type(self, value: str):
        self.view.plot_type = value
        self.plot_data()

    def _set_range(self, mode: str):
        self.view.range = mode
        self.plot_data()

    def _set_grid(self, on: bool):
        self.view.grid = on
        self.plot.set_grid(on)

    def _on_zoom_toggled(self, on: bool):
        if on:
            self.bMeasure.setChecked(False)
        self.plot.set_zoom_mode(on)

    def _on_measure_toggled(self, on: bool):
        if on:
            self.bZoom.setChecked(False)

    def _on_plot_clicked(self, x: float, y: float):
        if self._ginput is not None:
            g = self._ginput
            g['points'].append((x, y))
            self.set('cursor', f'Point {len(g["points"])} of {g["n"]}: x = {x:g}, y = {y:g}')
            if len(g['points']) >= g['n']:
                g['loop'].quit()
        elif self.bMeasure.isChecked():
            self.set('cursor', f'x = {x:g}, y = {y:g}')

    def _ginput_cancel(self):
        if self._ginput is not None:
            self._ginput['loop'].quit()

    def _on_plot_context_menu(self, pos):
        if self._ginput is not None:       # right click ends ginput, as in MATLAB
            self._ginput_cancel()
            return
        target = self._current_target()
        if target is None:
            return
        menu = QMenu(self)

        def add(menu_, text, field, value):
            a = menu_.addAction(text)
            a.setCheckable(True)
            a.setChecked((target.ax.get(field) or '') == value)
            a.triggered.connect(lambda: (target.ax.__setitem__(field, value), self.plot_data()))

        for text, value in (('Normal', 'normal'), ('PS,mod', 'psmod'), ('Integrate', 'integrate')):
            add(menu, text, 'diff', value)
        menu.addSeparator()
        for text, value in (('Not Filtered', 'none'), ('RC', 'rc'), ('M.aver.', 'mvgaver'),
                            ('Sav.gol.', 'savgol')):
            add(menu, text, 'filt', value)
        sub = menu.addMenu('Apply to')
        for text, value in (('Auto', 'auto'), ('First Dim', '1D'), ('Second Dim', '2D'),
                            ('Both', 'both')):
            add(sub, text, 'filtpar1', value)
        menu.exec(pos)

    # ================================================================ menus
    def _fill_favorite_dirs(self):
        m = self.mFavoriteDirectories
        m.clear()
        dirs = self.ini.get_list('KazanViewer', 'favorite_dir')
        for d in dirs:
            m.addAction(d, lambda d=d: self.load_directory(d))
        if dirs:
            m.addSeparator()
        m.addAction('Add Current', self._fav_add)
        m.addAction('Remove Current', self._fav_remove)
        m.addAction('Remove All', lambda: self._fav_store([]))

    def _fav_store(self, dirs):
        self.ini.set_list('KazanViewer', 'favorite_dir', dirs)
        self.ini.save()
        self._fill_favorite_dirs()

    def _fav_add(self):
        dirs = self.ini.get_list('KazanViewer', 'favorite_dir')
        if self.ePath.text() not in dirs:
            self._fav_store(dirs + [self.ePath.text()])

    def _fav_remove(self):
        self._fav_store([d for d in self.ini.get_list('KazanViewer', 'favorite_dir')
                         if d != self.ePath.text()])

    def _menu_open_directory(self):
        d = QFileDialog.getExistingDirectory(self, 'Select directory', self.ePath.text())
        if d:
            self.load_directory(d)

    def _menu_save(self, processed: bool):
        d = self.get_data('psource' if processed else 'source')
        default = str(Path(d.filename).with_suffix('.dat')) if d.filename else ''
        fname, _ = QFileDialog.getSaveFileName(self, 'Save Source', default,
                                               'ASCII (*.dat *.txt)')
        if not fname:
            return
        y = d.y
        cols = [d.ax.x[:, None]]
        cols += [y.real, y.imag] if np.iscomplexobj(y) else [y]
        np.savetxt(fname, np.hstack(cols), fmt='%.10g', delimiter='\t')
        self.set('log', f'Saved {Path(fname).name}')

    def _menu_clear_source(self):
        self.src = verify(KzData())
        self.src_control_update()

    def _menu_how_to_start(self):
        QMessageBox.information(self, 'How to Start', '\n'.join([
            '1: Select a directory (type the path, use Up, or double-click a [folder])',
            '2: Select the file extension and data type, then click a file',
            '3: Process the data: start a plugin from the Plugins menu']))

    # ================================================================ close
    def _log_prepend(self, lines: list[str]):
        old = self.TextArea.toPlainText()
        self.TextArea.setPlainText('\n'.join(lines) + ('\n' + old if old else ''))

    def closeEvent(self, event):
        self.make_plugins('closeall')
        try:
            self.ini.save()
        except OSError:
            pass
        super().closeEvent(event)
