"""Kazan viewer main window: port of kazan3.mlapp, and the in-process KazanHost."""
from __future__ import annotations

import fnmatch
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shiboken6
from PySide6.QtCore import QEvent, QEventLoop, QObject, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (QAction, QActionGroup, QDesktopServices, QFont, QFontMetrics, QIcon,
                           QKeySequence, QShortcut)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QFileDialog, QSlider,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMenu, QMenuBar, QMessageBox, QPlainTextEdit,
                               QPushButton, QStyleFactory,
                               QScrollBar, QSizePolicy, QVBoxLayout, QWidget)

from ..core.data import KzData, Struct, verify
from ..core.ini import KazanIni
from ..core.plugin import KazanPlugin, PluginInfo, discover_plugins
from ..core.processing import process
from ..io import loaders
from ..io import writers
from ..io.ascii import ascii_write
from ..io.params import parameter_reader
from . import console, figures
from .plot import COLOR_ORDER, KazanPlot

RESOURCES = Path(__file__).resolve().parent.parent / 'resources'
DOCS = Path(__file__).resolve().parents[2] / 'Documentation'
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
BASE_FONT = 10   # point size the fixed widget sizes below are designed for

#: Help menu texts (MATLAB KazanViewerHelp), adapted to the Python port
HELP = {
    'How to Start': [
        '1: Load data: select the directory, the file extension and the data type,',
        '   change the loader options (if present), then click a file',
        '2: Adjust the view: right-click on the plot, select options',
        '3: Process the data: start a plugin from the Plugins menu',
        '4: Copy processed data from Output to Source (<<)',
        '5: Print the plot: Window > Show in Window, then save it from the figure toolbar'],
    'Data Load Routines': [
        'File extensions, data types and loader options are listed in',
        '    kazan/io/loaders.py   (EXTENSIONS, OPTIONS, LOADERS)',
        'Common parameters (title, freq1, ...) are read by',
        '    kazan/io/params.py    (parameter_reader)',
        '(MATLAB: kv3_ScriptLoad and kv3_ParameterReader)', '',
        "Developer's corner:",
        "    ax, y, dsc = loaders.load(filename, '*.dsc', 'XEPR', option_values)",
        '    loaders.options(subtype)  - the options of a data type', '',
        'Supported formats: Documentation/loaders.md'],
    'Axis Data Structure': [
        'Parameters (fields of ax) that affect visualization:',
        'title     - data title',
        'x / y     - 1D axis arrays   REQUIRED',
        'xlabel / ylabel - axis labels',
        'Color     - colour of the trace b/g/r/c/m/y/k or [r g b], rgb = 0..1',
        'LineStyle - style of the line - / : / -. / --',
        'LineWidth - width of the line 0..inf',
        'Marker    - style of dots none/./o/x/+/*/s/d/v/^/</>/p/h',
        'contour   - for 2D plots - contour levels', '',
        'Plot type related:',
        'reference - for the ppm plot',
        'freq1     - for the g-factor plot', '',
        'Data processing:',
        'dx, s           - shift of abscissa / ordinate',
        'diff, ps_mod    - pseudo-modulation parameters, derivative / integral',
        'filt, tc, pol   - filter rc / mvgaver / savgol, 1..inf, 1..inf', '',
        'Fields of ax are accessible through the list and the edit field',
        'above the plot.'],
    'Plugins': [
        'Plugins are windows with access to the viewer data. A plugin is a',
        'KazanPlugin subclass in a .py file in the plugins folder:',
        "    menu_name = 'MYPLUGIN'      - name in the Plugins menu",
        '    __init__(self, host, guid)   - initialization',
        '    file_update(self)            - called when data are loaded', '',
        'Plugins use:',
        "    src = self.host.get_data('source')    - data (a copy)",
        "    src = self.host.get_data('psource')   - processed data",
        "    self.host.set_data('output', [out])   - set output data",
        "    font = self.host.get('font')          - font size",
        "    self.host.set('slice', k)             - change the slice (0-based)", '',
        'Details: Documentation/plugin-api.md'],
    'How to Print': [
        'Select Window > Show in Window: the plot opens in a matplotlib figure.',
        'Its toolbar zooms and saves the image (PNG, PDF, SVG, ...).', '',
        'To put several plots on one figure use Window > Plot 1D > Axis k / [r,c].'],
}

#: open viewers (Window > New Window), kept alive here
VIEWERS: list = []


class _MenuStyle(QObject):
    """The Windows 11 style draws menu bars and menus in a fixed font, so the Font menu
    could not scale them; menus of every window (plugins too) get the Fusion style,
    which follows the font."""

    def __init__(self, parent):
        super().__init__(parent)
        self._style = None

    def style(self):
        """The shared Fusion style, owned by this filter (recreated if Qt deleted it)."""
        if self._style is None or not shiboken6.isValid(self._style):
            self._style = QStyleFactory.create('Fusion')
            self._style.setParent(self)
        return self._style

    def eventFilter(self, obj, ev):
        try:
            if (ev.type() == QEvent.Type.Polish and isinstance(obj, (QMenuBar, QMenu))
                    and not obj.property('kzMenuStyle')):
                obj.setProperty('kzMenuStyle', True)
                obj.setStyle(self.style())
        except RuntimeError:     # never let a style problem break event delivery
            pass
        return False


def _install_menu_style():
    app = QApplication.instance()
    if app is not None and app.property('kzMenuStyle') is None:
        app.setProperty('kzMenuStyle', True)
        app._kz_menu_style = _MenuStyle(app)
        app.installEventFilter(app._kz_menu_style)


@dataclass
class View:
    """Port of ``app.View`` (only the fields used so far)."""
    data_src_out: int = 1        # 1 source, 2 output
    part: str = 'real'           # 'real' | 'reim' | 'magn'
    plot_type: str = '1D'        # '1D' | 'Stack' | 'Contour' | 'Density'
    position: int = 0            # current slice, 0-based
    abscissa: int = 1            # 1: slices are columns (X abscissa), 2: rows (Y abscissa)
    range: str = 'tight'         # 'tight' | 'auto' | 'manual'
    grid: bool = False
    minor_grid: bool = False     # MATLAB MinAxisGrid (X only)
    aspect: str = 'normal'       # 'normal' | 'square' | 'equal'
    default_font: int = 12
    font: int = 12
    xtype: str = 'plot'          # 'plot' | 'pnt' | 'semilog' | 'reverse' | 'gspace' | 'ppm' | 'ppm-1'
    ytype: str = 'plot'          # 'plot' | 'pnt' | 'semilog' | 'reverse'
    par: dict = field(default_factory=dict)      # view parameter values (MATLAB View.Par)
    locked: list = field(default_factory=list)   # parameters kept on file load (View.LockedPar)


def matlab_vector(text, default=None) -> np.ndarray:
    """Numbers of a MATLAB vector expression: '.2:.1:.6', '[.1 .3 .5]', '0.5'."""
    try:
        out = []
        for part in str(text).strip().strip('[]').replace(',', ' ').split():
            nums = [float(v) for v in part.split(':')]
            if len(nums) == 1:
                out.append(nums[0])
            else:
                a, st, b = (nums[0], 1.0, nums[1]) if len(nums) == 2 else nums
                if st:
                    out.extend(a + st * np.arange(int(np.floor((b - a) / st + 1e-9)) + 1))
        if out:
            return np.array(out)
    except (ValueError, TypeError):
        pass
    return np.asarray(default if default is not None else [], float)


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
        self.view.default_font = QApplication.font().pointSize()
        try:     # MATLAB ini.KazanViewer.Font
            self.view.font = int(float(self.ini.get('KazanViewer', 'Font', str(self.view.default_font))))
        except ValueError:
            self.view.font = self.view.default_font
        self.view.font = int(np.clip(self.view.font, self.view.default_font - 4, self.view.default_font + 4))
        self._scaled: list = []      # (widget, sizes at BASE_FONT), see _scale
        self._message = ''
        self._message_until = 0.0
        self._ginput: dict | None = None
        self._dir_entries: list[tuple[str, bool]] = []   # (name, is_dir)

        self.setWindowTitle('KAZAN3')
        self.setWindowIcon(QIcon(str(RESOURCES / 'pbZoom.png')))
        self.resize(1165, 860)
        _install_menu_style()
        self._build_ui()
        self._build_menus()
        self._apply_font()
        VIEWERS.append(self)

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
        self._scale(left, w=310)
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
        self.ddDataType.currentTextChanged.connect(self._on_datatype_changed)
        self.bUp = QPushButton('Up')
        self._scale(self.bUp, w=46)
        self.bUp.clicked.connect(lambda: self.load_directory(str(Path(self.ePath.text()).parent)))
        row.addWidget(self.ddDataType, 1)
        row.addWidget(self.ddExt, 1)
        row.addWidget(self.bUp)
        lv.addLayout(row)
        self.lbDirlist = QListWidget()
        self.lbDirlist.currentRowChanged.connect(self._on_dirlist_selected)
        self.lbDirlist.itemActivated.connect(lambda _: self._on_dirlist_activated())
        self.lbDirlist.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lbDirlist.customContextMenuRequested.connect(self._dirlist_menu)
        self._select_source = True       # MATLAB cmSelectSource (checked by default)
        lv.addWidget(self.lbDirlist, 1)
        # loader options (MATLAB eLoadOption, ddLoadOption1/2)
        self.eLoadOption = QLineEdit()
        self.eLoadOption.editingFinished.connect(self._save_load_options)
        lv.addWidget(self.eLoadOption)
        row = QHBoxLayout()
        self.ddLoadOption1, self.ddLoadOption2 = QComboBox(), QComboBox()
        for dd in (self.ddLoadOption1, self.ddLoadOption2):
            dd.currentIndexChanged.connect(self._save_load_options)
            row.addWidget(dd, 1)
        lv.addLayout(row)
        lv.addWidget(QLabel('Results'))
        self.TextArea = QPlainTextEdit(readOnly=True)
        self._scale(self.TextArea, h=90)
        self.TextArea.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.TextArea.customContextMenuRequested.connect(self._results_menu)
        lv.addWidget(self.TextArea)
        h.addWidget(left)
        self._on_ext_changed(self.ddExt.currentText())
        self.ddDataType.setCurrentText(self.ini.get('KazanViewer', 'datatype', ''))
        self._on_datatype_changed(self.ddDataType.currentText())

        # ---- right: view buttons, parameter row, plot, slice slider
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)

        row1 = QHBoxLayout()
        self.bSource, self.bOutput = QPushButton('Source'), QPushButton('Output')
        self.bTransfer = QPushButton('<<')
        self._scale(self.bTransfer, w=30)
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
        self._scale(self.ddSelParameter, minw=200)
        self.ddSelParameter.currentTextChanged.connect(self._on_parameter_selected)
        self.eParameter = QLineEdit()
        self.eParameter.returnPressed.connect(self._on_parameter_set)
        for w in (self.ddSelParameter, self.eParameter):   # MATLAB ParMenu: lock parameters
            w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            w.customContextMenuRequested.connect(
                lambda pos, w=w: self._parameter_menu(w.mapToGlobal(pos)))
        bEq = QPushButton('=')
        self._scale(bEq, w=26)
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
        self.plot.doubleClicked.connect(self.full_scale)
        self.plot.moved.connect(self._on_plot_moved)
        self.plot.contextMenuRequested.connect(self._on_plot_context_menu)
        prow = QHBoxLayout()
        prow.setSpacing(2)
        prow.addWidget(self.plot, 1)
        # MATLAB sl2Dplot (vertical slider right of the axes) and b2D (slice direction)
        self.slice_col = QWidget()
        self._scale(self.slice_col, w=50)
        sv = QVBoxLayout(self.slice_col)
        sv.setContentsMargins(0, 0, 0, 0)
        self.sl2Dplot = QSlider(Qt.Orientation.Vertical)
        self.sl2Dplot.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self.sl2Dplot.valueChanged.connect(lambda v: self.set('slice', v))
        sv.addWidget(self.sl2Dplot, 1, Qt.AlignmentFlag.AlignHCenter)
        self.b2D = QPushButton('X')
        self.b2D.setToolTip('Slice direction: X - traces along X (columns), Y - along Y (rows)')
        self.b2D.clicked.connect(self._on_b2d)
        sv.addWidget(self.b2D)
        prow.addWidget(self.slice_col)
        rv.addLayout(prow, 1)
        self.plot.viewport().installEventFilter(self)   # wheel steps through slices
        self.lSlice = QLabel()
        self.lSlice.setAlignment(Qt.AlignmentFlag.AlignRight)
        rv.addWidget(self.lSlice)
        h.addWidget(right, 1)

        self.bSource.setChecked(True)
        self.part_buttons['real'].setChecked(True)
        self.type_buttons['1D'].setChecked(True)

        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._ginput_cancel)

    def _group(self, layout, buttons, callback) -> dict:
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
            self._scale(b, minw=64)
            grp.addButton(b)
            b.clicked.connect(lambda _=False, v=value: callback(v))
            out[value] = b
        layout.addLayout(row)
        return out

    def _tool(self, layout, icon, tip, checkable=False) -> QPushButton:
        b = QPushButton()
        b.setIcon(QIcon(str(RESOURCES / icon)))
        self._scale(b, w=38, h=24, icon=14)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        layout.addWidget(b)
        return b

    def _scale(self, widget, **sizes):
        """Register a fixed size (pixels at BASE_FONT points) that follows the font."""
        self._scaled.append((widget, sizes))
        self._apply_sizes(widget, sizes, self.view.font / BASE_FONT)

    @staticmethod
    def _apply_sizes(widget, sizes, k):
        px = {n: max(1, round(v * k)) for n, v in sizes.items()}
        if isinstance(widget, QPushButton) and widget.text() and 'w' in px:
            f = QFont(QApplication.font())          # never narrower than the text
            f.setPointSizeF(BASE_FONT * k)
            px['w'] = max(px['w'], QFontMetrics(f).horizontalAdvance(widget.text())
                          + 2 * round(8 * k) + 4)
        if 'w' in px:
            widget.setFixedWidth(px['w'])
        if 'h' in px:
            widget.setFixedHeight(px['h'])
        if 'minw' in px:
            widget.setMinimumWidth(px['minw'])
        if 'icon' in px:
            widget.setIconSize(QSize(px['icon'], px['icon']))

    def _apply_font(self):
        """MATLAB UIFigureSizeChanged font part: every control uses the View font. The
        size goes into the application style sheet (a style sheet masks
        QApplication.setFont), so plugin windows follow too; fixed sizes scale with it."""
        pt = self.view.font
        k = pt / BASE_FONT
        QApplication.instance().setStyleSheet(
            MATLAB_STYLE + f'* {{ font-size: {pt}pt; }}\n'
            f'QPushButton {{ padding: {round(3 * k)}px {round(8 * k)}px; }}\n'
            f'*[fontScale="big"] {{ font-size: {round(pt * 1.6)}pt; font-weight: bold; }}\n')
        f = QApplication.font()
        f.setPointSize(pt)
        QApplication.setFont(f)
        for widget, sizes in self._scaled:
            self._apply_sizes(widget, sizes, k)
        mb = self.menuBar()      # QMenuBar keeps its item layout until told the font changed
        QApplication.sendEvent(mb, QEvent(QEvent.Type.FontChange))
        mb.updateGeometry()
        self.plot.set_font_size(pt)
        for a in getattr(self, '_font_actions', {}).values():
            a.setChecked(False)
        a = getattr(self, '_font_actions', {}).get(pt - self.view.default_font)
        if a is not None:
            a.setChecked(True)

    def _build_menus(self):
        mb = self.menuBar()

        m = mb.addMenu('File')
        m.addAction('Open Directory', self._menu_open_directory)
        self.mFavoriteDirectories = m.addMenu('Favorite Directories')
        self._fill_favorite_dirs()
        m.addSeparator()
        m.addAction('Save Source', lambda: self._menu_save(False))
        m.addAction('Save Source with Processing', lambda: self._menu_save(True))
        m.addAction('Convert Folder to ASCII (dat)', lambda: self._menu_convert_folder('.dat'))
        m.addAction('Convert Folder to ASCII (txt)', lambda: self._menu_convert_folder('.txt'))
        m.addSeparator()
        m.addAction('Export Src to Workspace', lambda: self._menu_workspace('export_src'))
        m.addAction('Export Out to Workspace', lambda: self._menu_workspace('export_out'))
        m.addAction('Load Src from Workspace', lambda: self._menu_workspace('load_src'))
        m.addAction('Workspace Console', lambda: self._menu_workspace('console'))

        m = mb.addMenu('View')
        fm = m.addMenu('Font')
        g = QActionGroup(self)
        self._font_actions = {}
        for d in range(-4, 5):
            a = fm.addAction('Default' if d == 0 else f'{d:+d}')
            a.setCheckable(True)
            g.addAction(a)
            a.triggered.connect(lambda _=False, d=d: self.set('font', self.view.default_font + d))
            self._font_actions[d] = a
        m.addSeparator()
        g = QActionGroup(self)
        self._range_actions = {}
        for text, mode in (('Axis Tight', 'tight'), ('Axis Auto', 'auto'), ('Axis Manual', 'manual')):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setChecked(mode == self.view.range)
            g.addAction(a)
            a.triggered.connect(lambda _=False, mode=mode: self._set_range(mode))
            self._range_actions[mode] = a
        m.addAction('Select View Area', self._menu_select_view_area)
        m.addAction('Zoom', self.bZoom.toggle)
        a = m.addAction('Full Scale', self.full_scale)
        a.setShortcut(QKeySequence('Ctrl+A'))
        m.addSeparator()
        a = m.addAction('Show Grid')
        a.setCheckable(True)
        a.toggled.connect(self._set_grid)
        a = m.addAction('Show Minor Grid')
        a.setCheckable(True)
        a.toggled.connect(self._set_minor_grid)
        g = QActionGroup(self)
        for text, mode in (('Aspect Normal', 'normal'), ('Aspect Square', 'square'),
                           ('Axis Equal', 'equal')):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setChecked(mode == self.view.aspect)
            g.addAction(a)
            a.triggered.connect(lambda _=False, mode=mode: self._set_aspect(mode))
        m.addSeparator()
        for text, key, fn in (
                ('Next File', 'Ctrl+Down', lambda: self._step_file(1)),
                ('Previous File', 'Ctrl+Up', lambda: self._step_file(-1)),
                ('Next Slice', 'Ctrl+U;Ctrl+Right', lambda: self.set('slice', self.view.position + 1)),
                ('Previous Slice', 'Ctrl+D;Ctrl+Left', lambda: self.set('slice', self.view.position - 1))):
            a = m.addAction(text)
            a.setShortcuts([QKeySequence(k) for k in key.split(';')])
            a.triggered.connect(fn)

        m = mb.addMenu('Tools')
        m.addAction('Clear Source', self._menu_clear_source)
        m.addAction('Fix Source Processing', self._menu_fix_processing)
        m.addAction('Cut Slice', self._menu_cut_slice)
        m.addAction('Show Load Script', lambda: self.set('log', self.src.script or '(none)'))

        self.mPluginsMain = mb.addMenu('Plugins')

        m = mb.addMenu('Window')
        m.addAction('New Window', self._menu_new_window)
        m.addAction('Show in Window', lambda: self._menu_figure('show'))
        m.addSeparator()
        sm = m.addMenu('Plot 1D')
        for text, key in (('Open figure', 'open'), ('Empty figure', 'empty'),
                          ('Axis 1 / [1,2]', (1, 2, 1)), ('Axis 2 / [1,2]', (1, 2, 2)),
                          ('Axis 1 / [2,1]', (2, 1, 1)), ('Axis 2 / [2,1]', (2, 1, 2))):
            sm.addAction(text, lambda key=key: self._menu_figure(key))
        sm = m.addMenu('Plot 2D')
        for text, key in (('Surf', 'surf'), ('Scatter3', 'scatter3'), ('Surface', 'surface')):
            sm.addAction(text, lambda key=key: self._menu_plot_2d(key))

        m = mb.addMenu('Help')
        for text in HELP:
            m.addAction(text, lambda text=text: self._menu_help(text))
        m.addAction('Documentation', self._menu_documentation)
        m.addSeparator()
        m.addAction('About Kazan Viewer', lambda: QMessageBox.about(
            self, 'About', 'KAZAN data viewer and plugins\nPython port of Kazan Viewer 3.0\n'
                           'by Boris Epel, 2003-2026'))

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
        else:
            raise ValueError(f'set_data: unknown mode {mode!r}')
        self.view.data_src_out = 2
        self.bOutput.setChecked(True)
        self.update_slider()     # after the switch: the slider follows the shown data
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
            self.ini.set('KazanViewer', 'Font', str(self.view.font))
            self._apply_font()           # applies to plugin windows too
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
        self.plot.set_crosshair(True)
        self.plot.clear_marks()
        self.activateWindow()
        try:
            loop.exec()
        finally:
            pts = self._ginput['points']
            self._ginput = None
            self._message_until = 0.0   # the selection prompt is done
            self.plot.unsetCursor()
            self.plot.set_crosshair(self.bMeasure.isChecked())
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
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            d = self.read_file(filename)
        except Exception as e:
            traceback.print_exc()
            self.set('message', f'Load error: {e}')
            self.set('log', f'{Path(filename).name}: {e}')
            return
        finally:
            QApplication.restoreOverrideCursor()
        if d.dsc.get('KAZANwarning'):
            self.set('log', d.dsc.KAZANwarning)
        if getattr(d, '_reduced', False):
            self.set('log', 'Data dimension is reduced.')
        self._message_until = 0.0   # a new file replaces any pending message
        self.ini.set('KazanViewer', 'last_file', filename)
        self.src = d
        self.src_control_update()

    def read_file(self, filename: str) -> KzData:
        """Load a file with the selected data type and options (MATLAB ScriptLoad +
        eval + ParameterReader('load'))."""
        ext, subtype = self.ddExt.currentText(), self.ddDataType.currentText()
        opts = self.load_option_values()
        ax, y, dsc = loaders.load(filename, ext, subtype, opts)
        ax, dsc = Struct(ax), Struct(dsc)
        y = np.asarray(y)
        while y.ndim > 2 and y.shape[-1] == 1:   # MATLAB size() drops trailing singletons
            y = y[..., 0]
        reduced = y.ndim > 2
        if reduced:   # MATLAB: data dimension is reduced to 2D
            y = y.reshape((y.shape[0], -1), order='F')
            ax.y = np.arange(1.0, y.shape[1] + 1)
        ax = parameter_reader(ax, dsc)
        ax.dx = 0
        ax.Datatype = ext + subtype
        d = verify(KzData(y=y, ax=ax, dsc=dsc, filename=filename,
                          script=f"loaders.load({filename!r}, {ext!r}, {subtype!r}, {opts!r})"))
        d._reduced = reduced
        return d

    def src_control_update(self):
        """Port of SrcControlUpdate: refresh controls, notify plugins, replot."""
        title = self.src.ax.get('title') or ''
        name = self.src.filename or ''
        self.setWindowTitle(f'KAZAN3 - {name} [{title}]' if name else 'KAZAN3')
        self._load_parameters(getattr(self, '_previous_parameters', {}))
        self._snapshot_parameters()
        self._fill_parameter_list()
        self.update_slider()
        self.sourceChanged.emit()
        self.plot_data()

    def _n_slices(self) -> int:
        """Slices along the ordinate (MATLAB UpdateSlider: size(y, OrdinateXorY))."""
        dim = 1 if self.view.abscissa == 1 else 0
        sets = [self.src] if self.view.data_src_out == 1 else (self.out or [self.src])
        return max([d.y.shape[dim] for d in sets if not d.is_empty] or [1])

    def _shown_sets(self) -> list:
        """The data sets on display: the source, or the output traces."""
        return [self.src] if self.view.data_src_out == 1 else (self.out or [self.src])

    def update_slider(self):
        two_d = any(d.is_2d for d in self._shown_sets() if not d.is_empty)
        if not two_d:
            self.view.abscissa = 1        # 1D data have no slice direction
        n = self._n_slices()
        self.view.position = min(self.view.position, n - 1)
        self.sl2Dplot.blockSignals(True)
        self.sl2Dplot.setRange(0, max(n - 1, 0))
        step = 1
        while n / step > 40:
            step *= 2
        self.sl2Dplot.setTickInterval(step)
        self.sl2Dplot.setPageStep(step)
        self.sl2Dplot.setValue(self.view.position)
        self.sl2Dplot.blockSignals(False)
        self.slice_col.setVisible(two_d)    # slider and X / Y button only for 2D data
        self.b2D.setText('XY'[self.view.abscissa - 1])

    def _on_b2d(self):
        """MATLAB b2DValueChanged: switch the slice direction of 2D data."""
        two_d = any(d.is_2d for d in self._shown_sets() if not d.is_empty)
        self.view.abscissa = 1 if (self.view.abscissa == 2 or not two_d) else 2
        self.view.position = 0
        self.update_slider()
        self.plot_data()

    @staticmethod
    def get_slice(d: KzData, dim: int, sel: int) -> KzData:
        """MATLAB GetSlice: column ``sel`` (dim 1), or row ``sel`` as a trace along Y (dim 2)."""
        rs = d.copy()
        y = np.asarray(d.y)
        xs = np.ravel(d.ax.get('x', np.arange(1.0, y.shape[0] + 1)))
        ys = np.ravel(d.ax.get('y', np.arange(1.0, y.shape[1] + 1)))
        if dim == 1:
            k = min(sel, y.shape[1] - 1)
            rs.y = y[:, k:k + 1]
            rs.ax.y = ys[min(k, len(ys) - 1):][:1]
        else:
            k = min(sel, y.shape[0] - 1)
            rs.y = y[k:k + 1, :].T
            rs.ax.x = ys
            rs.ax.y = xs[min(k, len(xs) - 1):][:1]
            rs.ax.xlabel = d.ax.get('ylabel') or 'a.u.'
            rs.ax.ylabel = d.ax.get('xlabel') or 'a.u.'
        return rs

    def eventFilter(self, obj, event):
        """Mouse wheel over the plot steps through slices (MATLAB WindowScrollWheel),
        unless Zoom or Measure is active."""
        if (event.type() == QEvent.Type.Wheel and self._n_slices() > 1
                and not self.bZoom.isChecked() and not self.bMeasure.isChecked()):
            dy = event.angleDelta().y()
            steps = dy // 120 or (1 if dy > 0 else -1)
            self.set('slice', self.view.position + steps)
            return True
        return super().eventFilter(obj, event)

    def _menu_cut_slice(self):
        """MATLAB mCutSlice: the current slice becomes the source."""
        if self.src.is_empty:
            return
        self.src = verify(self.get_slice(self.src, self.view.abscissa, self.view.position))
        self.view.abscissa, self.view.position = 1, 0
        self.src_control_update()

    def _menu_fix_processing(self):
        """MATLAB mFixSourceProcessing: apply the display processing to the source."""
        d, warnings = process(self.src.copy())
        for w in warnings:
            self.set('log', w)
        d.ax.filtpar1 = ''
        self.src = verify(d)
        self.plot_data()

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

    GAMMA = 1.3996e6   # electron gyromagnetic ratio, Hz/G (MATLAB app.gamma)

    def _plot_axis(self, d: KzData) -> KzData:
        """MATLAB getplotaxis: ax.dx / ax.dy corrections, then the X / Y representation
        (points, g-factor from freq1, ppm of the reference)."""
        for axis, key in (('x', 'dx'), ('y', 'dy')):
            try:
                shift = float(d.ax.get(key) or 0)
            except (TypeError, ValueError):
                shift = 0.0
            if shift and d.ax.get(axis) is not None:
                d.ax[axis] = np.asarray(d.ax[axis], float) + shift
            d.ax[key] = 0

        def var(label):
            label = str(label or '')
            return label[:label.index(',') + 1] if ',' in label else 'a.u.'

        def num(key, default):
            try:
                v = float(d.ax.get(key, default) or 0)
            except (TypeError, ValueError):
                v = default
            return v or 1.0

        x = np.asarray(d.ax.x, float)
        xt = self.view.xtype
        if xt == 'gspace':
            with np.errstate(divide='ignore'):
                d.ax.x = num('freq1', 34e9) / self.GAMMA / x
            d.ax.xlabel = 'g-factor,'
        elif xt == 'ppm-1':
            d.ax.x = (x / num('reference', 34e9) - 1) * 1e6
            d.ax.xlabel = var(d.ax.xlabel) + 'ppm'
        elif xt == 'ppm':
            d.ax.x = x / num('reference', 34e9) * 1e6
            d.ax.xlabel = var(d.ax.xlabel) + 'ppm'
        elif xt == 'pnt':
            d.ax.x = np.arange(1.0, len(x) + 1)
            d.ax.xlabel = var(d.ax.xlabel) + 'pts'
        if self.view.ytype == 'pnt' and d.ax.get('y') is not None:
            d.ax.y = np.arange(1.0, len(np.ravel(d.ax.y)) + 1)
            d.ax.ylabel = var(d.ax.ylabel) + 'pts'
        return d

    def _datasets(self) -> list[tuple[KzData, str]]:
        if self.view.data_src_out == 1:
            d, warnings = process(self.src.copy())
            for w in warnings:
                self.set('log', w)
            return [(self._plot_axis(d), self.src.ax.get('Color') or 'b')]
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

    def _plot_data(self, p=None):
        """Draw into the viewer plot, or into ``p`` (a figure, MATLAB PlotData(rAxis, iAxis))."""
        main = p is None
        p = p or self.plot
        p.clear_plots()
        p.show_imag(self.view.part == 'reim')
        sets = [(d, c) for d, c in self._datasets() if not d.is_empty]
        if not sets:
            p.set_title('No data')
            return
        ref = sets[0][0]

        if self.view.plot_type in ('Contour', 'Density') and ref.is_2d:
            re, im = self._part(ref.y)
            cc = matlab_vector(ref.ax.get('contour'), default=np.arange(1, 7) / 10)
            for item, z in ((p.real, re), (p.imag, im)):
                if z is None:
                    continue
                zmax, zmin = np.nanmax(z), np.nanmin(z)
                sh = zmin if zmax < 0 else 0.0       # MATLAB: levels cc*max (+min if all < 0)
                span = zmax - zmin if self.view.part == 'reim' else zmax
                levels = cc * span + sh
                if self.view.plot_type == 'Density':
                    p.density(item, ref.ax.x, ref.ax.y, z, (levels.min(), levels.max()))
                else:
                    p.contour(item, ref.ax.x, ref.ax.y, z, levels=levels)
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
                    t = self.get_slice(d, self.view.abscissa, self.view.position)
                    tre, tim = self._part(t.y)
                    p.line(p.real, t.ax.x, tre[:, 0], color, **self._style(d))
                    if tim is not None:
                        p.line(p.imag, t.ax.x, tim[:, 0], color, **self._style(d))
            ylabel = ref.ax.get('unit') or 'a.u.'
        xlabel = ref.ax.xlabel
        if self.view.abscissa == 2 and self.view.plot_type == '1D':
            xlabel = ref.ax.get('ylabel') or 'a.u.'
        p.set_labels(xlabel, ylabel)
        image = self.view.plot_type in ('Contour', 'Density') and ref.is_2d
        for item in (p.real, p.imag):    # MATLAB SuperPlot XScale / XDir / YScale / YDir
            if item is not None:
                p.axis_modes(item, logx=self.view.xtype == 'semilog' and not image,
                             logy=self.view.ytype == 'semilog' and not image,
                             invx=self.view.xtype in ('reverse', 'gspace'),
                             invy=self.view.ytype == 'reverse')

        if not main:
            src = self.src if self.view.data_src_out == 1 else ref
            p.set_title(Path(src.filename).name if src.filename else (src.title or ''))
            p.set_range_mode(self.view.range if self.view.range != 'manual' else 'tight')
            return
        n = self._n_slices()
        if n > 1 and self.view.plot_type == '1D':
            vals, lab = ((ref.ax.y, ref.ax.ylabel) if self.view.abscissa == 1 else
                         (ref.ax.x, ref.ax.xlabel))
            vals = np.ravel(vals)
            v = vals[min(self.view.position, len(vals) - 1)] if len(vals) else self.view.position + 1
            names = ref.ax.get('streams') if self.view.abscissa == 1 else None
            if names and self.view.position < len(names):     # SpecMan 'All streams'
                self.lSlice.setText(f'{names[self.view.position]}  [{self.view.position + 1}/{n}]')
            else:
                self.lSlice.setText(f'{lab}: {v:g}  [{self.view.position + 1}/{n}]')
        else:
            self.lSlice.setText('')

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
                if self._select_source:      # MATLAB cmSelectSource: show the new file
                    self.view.data_src_out = 1
                    self.bSource.setChecked(True)
                self.load_file(str(Path(self.ePath.text()) / name))

    def _dirlist_menu(self, pos):
        self._build_dirlist_menu().exec(self.lbDirlist.mapToGlobal(pos))

    def _build_dirlist_menu(self) -> QMenu:
        """MATLAB ContextMenu2 of the file list."""
        m = QMenu(self)
        m.addAction('Reload Data', lambda: self._on_dirlist_selected(self.lbDirlist.currentRow()))
        m.addAction('Reload Folder', lambda: self.load_directory(self.ePath.text()))
        m.addAction('Convert', lambda: self._menu_save(False))
        a = m.addAction('Select Source')
        a.setCheckable(True)
        a.setChecked(self._select_source)
        a.setToolTip('Show the Source when a file is loaded')
        a.toggled.connect(lambda on: setattr(self, '_select_source', on))
        m.addSeparator()
        m.addAction('Copy Full Path', self.copy_full_path)
        return m

    def copy_full_path(self) -> str:
        """Put the full path of the current file-list entry on the clipboard."""
        row = self.lbDirlist.currentRow()
        if not 0 <= row < len(self._dir_entries):
            return ''
        path = str((Path(self.ePath.text()) / self._dir_entries[row][0]).resolve())
        QApplication.clipboard().setText(path)
        self.set('message', f'Copied: {path}')
        return path

    def _results_menu(self, pos):
        m = self._build_results_menu()
        m.exec(self.TextArea.mapToGlobal(pos))
        m.deleteLater()

    def _build_results_menu(self) -> QMenu:
        """MATLAB ContextMenu3 of the Results box (Clear), plus Copy / Select All."""
        m = self.TextArea.createStandardContextMenu()
        m.addSeparator()
        m.addAction('Clear', self.TextArea.clear)
        return m

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

    # ================================================================ loader options
    def _on_datatype_changed(self, subtype: str):
        """Port of ddDataTypeValueChanged: show the loader's option controls."""
        if subtype:
            self.ini.set('KazanViewer', 'datatype', subtype)
        opts = loaders.options(subtype)
        saved = self.ini.get('LoadOptions', subtype, '').split('|') if subtype else []
        self._loading_options = True
        for k, dd in enumerate((self.ddLoadOption1, self.ddLoadOption2)):
            dd.blockSignals(True)
            dd.clear()
            if k < len(opts) and opts[k].items:
                for label, value in opts[k].items:
                    dd.addItem(label, value)
                labels = [label for label, _ in opts[k].items]
                values = [value for _, value in opts[k].items]
                pick = saved[k] if k < len(saved) and saved[k] in labels else None
                dd.setCurrentIndex(labels.index(pick) if pick else
                                   values.index(opts[k].default) if opts[k].default in values else 0)
                dd.setToolTip(opts[k].tooltip)
            dd.setVisible(k < len(opts) and bool(opts[k].items))
            dd.blockSignals(False)
        has_edit = len(opts) > 2
        self.eLoadOption.setVisible(has_edit)
        if has_edit:
            self.eLoadOption.setText(saved[2] if len(saved) > 2 else str(opts[2].default or ''))
            self.eLoadOption.setToolTip(opts[2].tooltip)
        self._loading_options = False

    def load_option_values(self) -> list:
        opts = loaders.options(self.ddDataType.currentText())
        if not opts:
            return []
        values = [dd.currentData() for dd in (self.ddLoadOption1, self.ddLoadOption2)]
        return values[:min(len(opts), 2)] + ([self.eLoadOption.text()] if len(opts) > 2 else [])

    def _save_load_options(self, *_):
        subtype = self.ddDataType.currentText()
        if getattr(self, '_loading_options', False) or not loaders.options(subtype):
            return
        self.ini.set('LoadOptions', subtype, '|'.join(
            (self.ddLoadOption1.currentText(), self.ddLoadOption2.currentText(),
             self.eLoadOption.text())))

    def _on_ext_changed(self, ext: str):
        self.ini.set('KazanViewer', 'ext', ext)
        self.ddDataType.clear()
        self.ddDataType.addItems(loaders.subtypes(ext))
        if self.ePath.text():
            self.load_directory(self.ePath.text())

    # ================================================================ parameters
    #: MATLAB View.Par: (name, default, description); kept across file loads
    VIEW_PARAMETERS = [('xlabel', '', 'X axis label'), ('ylabel', '', 'Y axis label'),
                       ('Color', 'b', 'Trace colour'), ('LineStyle', '-', 'Line style'),
                       ('LineWidth', 1.0, 'Line width'), ('Marker', 'none', 'Marker'),
                       ('dx', 0.0, 'X axis correction'), ('s', 0.0, 'Y shift'),
                       ('ps_mod', 1.0, 'Pseudo-modulation amplitude, points (PS,mod)'),
                       ('tc', 2.0, 'Filter time constant, points'),
                       ('contour', '.2:.1:.6', 'Contour levels, fraction of the maximum'),
                       ('yslicelabel', '', 'Slice label format')]
    #: port of kv3_ParameterReader('options'): read from each new file
    DATA_PARAMETERS = [('title', '', 'Title'), ('sample', '', 'Sample'), ('comment', '', 'Comment'),
                       ('formula', '', 'Formula'), ('freq1', 0.0, 'EPR frequency'),
                       ('reference', 0.0, 'Reference frequency'), ('cf', 0.0, 'Central Field'),
                       ('xunit', '', 'X axis unit'), ('yunit', '', 'Y axis unit (2D only)'),
                       ('unit', '', 'Signal unit')]

    def _par_defaults(self) -> dict:
        return {n: (d, a) for n, d, a in self.VIEW_PARAMETERS + self.DATA_PARAMETERS}

    def _par_value(self, key):
        """Value shown in the editor: the source's field, else the stored view value."""
        default = self._par_defaults().get(key, ('', ''))[0]
        if key in self.src.ax and self.src.ax[key] is not None:
            return self.src.ax[key]
        return self.view.par.get(key, default)

    def _snapshot_parameters(self):
        """Values a locked parameter returns to on the next source change."""
        self._previous_parameters = {k: self._par_value(k) for k in self._par_defaults()}

    def _load_parameters(self, previous: dict):
        """MATLAB MakeParameters('load'): view parameters follow the file where it has
        them; locked parameters keep their previous value and are written into src.ax."""
        for name, _, _ in self.VIEW_PARAMETERS:
            if name in self.src.ax and self.src.ax[name] is not None:
                self.view.par[name] = self.src.ax[name]
        for key in self.view.locked:
            if key in previous:
                self.src.ax[key] = previous[key]
                if key in dict((n, 0) for n, _, _ in self.VIEW_PARAMETERS):
                    self.view.par[key] = previous[key]

    def _fill_parameter_list(self):
        keep = self.ddSelParameter.currentData() or self.ddSelParameter.currentText()
        self.ddSelParameter.blockSignals(True)
        self.ddSelParameter.clear()
        for i, (name, _default, about) in enumerate(self.VIEW_PARAMETERS + self.DATA_PARAMETERS):
            self.ddSelParameter.addItem(f'* {name}' if name in self.view.locked else name, name)
            self.ddSelParameter.setItemData(i, about, Qt.ItemDataRole.ToolTipRole)
        idx = self.ddSelParameter.findData(keep) if keep else -1
        self.ddSelParameter.setCurrentIndex(idx if idx >= 0 else
                                            self.ddSelParameter.findData('title'))
        self.ddSelParameter.blockSignals(False)
        self._on_parameter_selected()

    def _on_parameter_selected(self, *_):
        key = self.ddSelParameter.currentData()
        value = self._par_value(key) if key else ''
        if isinstance(value, np.ndarray):
            value = ' '.join(f'{v:g}' for v in np.ravel(value))
        self.eParameter.setText(f'{value:g}' if isinstance(value, float) else str(value))
        about = self._par_defaults().get(key, ('', ''))[1] if key else ''
        locked = key in self.view.locked
        self.eParameter.setToolTip((about + ' [locked: kept on file load]' if locked else about).strip())
        self.eParameter.setStyleSheet('background: #ffffbf;' if locked else '')

    def _on_parameter_set(self):
        key, text = self.ddSelParameter.currentData(), self.eParameter.text()
        if not key:
            return
        default = self._par_defaults().get(key, ('', ''))[0]
        try:
            value = float(text) if isinstance(default, float) else text
        except ValueError:
            self.set('message', f'{key}: a number is expected')
            return
        self.src.ax[key] = value
        if key in dict((n, 0) for n, _, _ in self.VIEW_PARAMETERS):
            self.view.par[key] = value
        self._snapshot_parameters()
        self.plot_data()

    def _parameter_menu(self, pos):
        key = self.ddSelParameter.currentData()
        if not key:
            return
        menu = QMenu(self)
        a = menu.addAction(f"Lock '{key}'")
        a.setCheckable(True)
        a.setChecked(key in self.view.locked)
        a.setToolTip('Keep this parameter when another file is loaded')
        a.triggered.connect(lambda on: self._lock_parameter(key, on))
        b = menu.addAction('Unlock all')
        b.setEnabled(bool(self.view.locked))
        b.triggered.connect(lambda: self._lock_parameter(None, False))
        menu.exec(pos)

    def _lock_parameter(self, key, on: bool):
        if key is None:
            self.view.locked.clear()
        elif on and key not in self.view.locked:
            self.view.locked.append(key)
        elif not on and key in self.view.locked:
            self.view.locked.remove(key)
        self._snapshot_parameters()
        self._fill_parameter_list()

    # ================================================================ callbacks
    def _on_src_out(self, value: int):
        self.view.data_src_out = value
        self.update_slider()
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
        self._range_actions[mode].setChecked(True)
        self.plot_data()

    def full_scale(self):
        """Show all data (MATLAB zoom out / double-click): tight or auto as set in the View
        menu; Axis Manual goes back to Axis Tight."""
        if self.view.range == 'manual':
            self._set_range('tight')
        else:
            self.plot.set_range_mode(self.view.range)

    def _menu_select_view_area(self):
        """Type the axis limits; the range becomes manual."""
        cur = ' '.join(f'{v:g}' for v in self.plot.view_area())
        text, ok = QInputDialog.getText(self, 'Select View Area', 'xmin xmax ymin ymax', text=cur)
        if not ok:
            return
        try:
            x0, x1, y0, y1 = [float(v) for v in text.replace(',', ' ').split()]
        except ValueError:
            self.set('message', 'Four numbers are needed: xmin xmax ymin ymax')
            return
        self._set_range('manual')
        self.plot.set_view_area(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1))

    def _set_grid(self, on: bool):
        self.view.grid = on
        self.plot.set_grid(on, self.view.minor_grid)

    def _set_minor_grid(self, on: bool):
        self.view.minor_grid = on
        self.plot.set_grid(self.view.grid, on)

    def _set_aspect(self, mode: str):
        self.view.aspect = mode
        self.plot.set_aspect(mode)
        self.plot_data()

    def _on_zoom_toggled(self, on: bool):
        if on:
            self.bMeasure.setChecked(False)
        self.plot.set_zoom_mode(on)

    def _on_measure_toggled(self, on: bool):
        if on:
            self.bZoom.setChecked(False)
        self._measure_points = []
        if self._ginput is None:
            self.plot.set_crosshair(on)

    def _g_factor(self, x: float):
        """g at field x (G or mT) from freq1, or None (MATLAB getGfactor)."""
        d = self._current_target()
        if d is None or self.view.xtype == 'gspace':
            return None
        try:
            f = float(d.ax.get('freq1') or 0)
        except (TypeError, ValueError):
            return None
        unit = str(d.ax.get('xlabel') or '').rpartition(',')[2].strip()
        scale = {'G': 1.0, 'mT': 10.0, 'T': 1e4}.get(unit)
        if not f or not scale or not x:
            return None
        return f / self.GAMMA / (x * scale)

    def _on_plot_moved(self, x: float, y: float):
        """MATLAB WindowButtonMotion: coordinates (and g) in the title while the crosshair
        is on and no message is shown."""
        if not self.plot._crosshair or time.monotonic() < self._message_until:
            return
        g = self._g_factor(x)
        gtext = f' g={g:.5f}' if g else ''
        n = self._n_slices()
        dim = f' ({self.view.position + 1})' if n > 1 else ''
        pts = getattr(self, '_measure_points', [])
        if self._ginput is None and len(pts) == 1:
            self.plot.set_title(f'dx= {x - pts[0][0]:g},    dy= {y - pts[0][1]:g}{dim}')
        else:
            self.plot.set_title(f'x: {x:.6g}{gtext}  y: {y:.4g}{dim}')

    def _on_plot_clicked(self, x: float, y: float):
        if self._ginput is not None:
            g = self._ginput
            g['points'].append((x, y))
            self.plot.add_mark(x, y)
            self.set('cursor', f'Point {len(g["points"])} of {g["n"]}: x = {x:g}, y = {y:g}')
            if len(g['points']) >= g['n']:
                g['loop'].quit()
        elif self.bMeasure.isChecked():
            # MATLAB Measure: first click reads x, y (and g); the second gives dx, dy
            pts = self._measure_points = getattr(self, '_measure_points', [])
            if len(pts) >= 2:
                pts.clear()
                self.plot.clear_marks()
            pts.append((x, y))
            self.plot.add_mark(x, y)
            if len(pts) == 1:
                g = self._g_factor(x)
                self.set('log', f'x:{x:6.6g} y:{y:6.4g}' + (f' g={g:.5f}' if g else ''))
            else:
                (x0, y0), (x1, y1) = pts
                g0, g1 = self._g_factor(x0), self._g_factor(x1)
                self.set('log', f'dx= {x1 - x0:g},    dy= {y1 - y0:g}'
                         + (f',    dg= {g1 - g0:.5f}' if g0 and g1 else ''))

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

        def rep(menu_, text, axis, value):
            a = menu_.addAction(text)
            a.setCheckable(True)
            a.setChecked(getattr(self.view, axis) == value)
            a.triggered.connect(lambda: (setattr(self.view, axis, value), self.plot_data()))

        menu.addSeparator()
        a = menu.addAction('x-y')
        a.setCheckable(True)
        a.setChecked(self.view.xtype == 'plot' and self.view.ytype == 'plot')
        a.triggered.connect(lambda: (setattr(self.view, 'xtype', 'plot'),
                                     setattr(self.view, 'ytype', 'plot'), self.plot_data()))
        sub = menu.addMenu('X')
        for text, value in (('X', 'plot'), ('X pnts', 'pnt'), ('Reverse X', 'reverse'),
                            ('X Log', 'semilog'), ('X g-space (freq1)', 'gspace'),
                            ('X ppm (reference)', 'ppm'), ('X ppm - 1 (reference)', 'ppm-1')):
            rep(sub, text, 'xtype', value)
        sub = menu.addMenu('Y')
        for text, value in (('Y', 'plot'), ('Y pnts', 'pnt'), ('Reverse Y', 'reverse'),
                            ('Y Log', 'semilog')):
            rep(sub, text, 'ytype', value)
        menu.addSeparator()
        reload_ = menu.addAction('Reload Data')
        reload_.setEnabled(bool(self.src.filename) and Path(self.src.filename).exists())
        reload_.triggered.connect(lambda: self.load_file(self.src.filename))
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

    def _save_data(self, processed: bool) -> KzData:
        """MATLAB ExportSaveConvert (save): dx applied to x, optionally processed."""
        d = verify(self.src.copy())
        try:
            dx = float(d.ax.get('dx') or 0)
        except (TypeError, ValueError):
            dx = 0.0
        d.ax.x = np.asarray(d.ax.x, float) + dx
        d.ax.dx = 0
        if processed:
            d, _ = process(d)
            d = verify(d)
        return d

    def _menu_save(self, processed: bool):
        """MATLAB Save Source: ASCII (txt / dat), SpecMan d01, Bruker dsc / par, WinSIM lmb."""
        d = self._save_data(processed)
        default = str(Path(d.filename).with_suffix('')) if d.filename else ''
        filters = [f for f, _ in writers.FORMATS]
        fname, flt = QFileDialog.getSaveFileName(self, 'Select file format', default,
                                                 ';;'.join(filters))
        if not fname:
            return
        kind = dict(writers.FORMATS).get(flt, 'txt')
        if not Path(fname).suffix:
            fname += '.' + kind
        try:
            writers.save(fname, d, kind, parameters=[n for n, _, _ in self.DATA_PARAMETERS])
        except Exception as e:
            traceback.print_exc()
            self.set('message', f'Save error: {e}')
            return
        self.set('log', f'{Path(fname).name} saved in format "{kind}"')

    def _menu_convert_folder(self, ext: str):
        """MATLAB Convert Folder to ASCII: every file of the current extension is loaded
        with the current data type and written next to it as ``name.dat`` / ``name.txt``."""
        box = QMessageBox(QMessageBox.Icon.Question, 'ASCII file conversion',
                          'Converting all files to ASCII?', parent=self)
        yes = box.addButton('Yes', QMessageBox.ButtonRole.YesRole)
        missing = box.addButton('Only missing', QMessageBox.ButtonRole.YesRole)
        box.addButton('No', QMessageBox.ButtonRole.NoRole)
        box.exec()
        if box.clickedButton() not in (yes, missing):
            return
        self.convert_folder(ext, only_missing=box.clickedButton() is missing)

    def convert_folder(self, ext: str, only_missing: bool = False) -> int:
        folder = Path(self.ePath.text())
        pattern = self.ddExt.currentText()
        self.set('log_clear')
        n = 0
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for f in sorted(folder.iterdir()):
                if f.is_dir() or not fnmatch.fnmatch(f.name.lower(), pattern.lower()):
                    continue
                dest = f.with_suffix(ext)
                if dest == f or (only_missing and dest.exists()):
                    continue
                try:
                    d = self.read_file(str(f))
                    ascii_write(str(dest), d, origin=f.name,
                                parameters=[n_ for n_, _, _ in self.DATA_PARAMETERS])
                except Exception as e:      # MATLAB: try ... catch, end
                    print(f'{f.name}: {e}')
                    continue
                self.set('log_all', f'{f.stem} -> {ext}')
                n += 1
        finally:
            QApplication.restoreOverrideCursor()
        return n

    def _menu_workspace(self, what: str):
        """MATLAB Export Src / Out to Workspace, Load Src from Workspace; the workspace is a
        Python namespace with its own console (File > Workspace Console)."""
        con = console.WorkspaceConsole.instance()
        console.WORKSPACE['viewer'] = self
        if what == 'export_src':
            console.assign('exp_src', self.src.copy())
            con.write("Variable 'exp_src' is created in the workspace\n")
        elif what == 'export_out':
            console.assign('exp_out', [d.copy() for d in self.out])
            con.write(f"Variable 'exp_out' is created in the workspace ({len(self.out)} traces)\n")
        elif what == 'load_src':
            v = console.lookup('exp_src')
            if v is None:
                con.write("Variable 'exp_src' was not found in the workspace\n")
            else:
                if not isinstance(v, KzData):
                    v = KzData(y=np.asarray(v))
                self.src = verify(v.copy())
                self.view.data_src_out = 1
                self.bSource.setChecked(True)
                self.src_control_update()
                con.write("Variable 'exp_src' was loaded from workspace\n")
        con.show()
        con.raise_()

    def _menu_new_window(self):
        w = KazanViewer(plugin_path=self.plugin_path)
        w.show()

    def _figure_plot(self, fig, real, imag=None):
        t = figures.MplPlot(real, imag, self.view.font)
        self._plot_data(t)
        t.set_grid(self.view.grid, self.view.minor_grid)
        t.set_aspect(self.view.aspect)
        fig.canvas.draw_idle()
        fig.show()

    def _menu_figure(self, key):
        """MATLAB Window menu: Show in Window, Plot 1D > Open / Empty figure, Axis k / [r,c]
        (a subplot of the current figure)."""
        try:
            plt = figures.pyplot()
        except ImportError:
            self.set('message', 'matplotlib is needed for figures: pip install matplotlib')
            return
        if key == 'empty':
            plt.figure().show()
        elif key == 'show':
            fig = plt.figure()
            self._figure_plot(fig, fig.add_subplot())
        elif key == 'open':
            fig = plt.figure()
            if self.view.part == 'reim':
                self._figure_plot(fig, fig.add_subplot(2, 1, 1), fig.add_subplot(2, 1, 2))
            else:
                self._figure_plot(fig, fig.add_subplot())
        else:
            fig = plt.gcf()
            self._figure_plot(fig, plt.subplot(*key))

    def _menu_plot_2d(self, kind: str):
        if self.src.is_empty:
            return
        try:
            figures.plot_2d(kind, self.src)
        except ImportError:
            self.set('message', 'matplotlib is needed for figures: pip install matplotlib')

    def _menu_clear_source(self):
        self.src = verify(KzData())
        self.src_control_update()

    def _menu_help(self, text: str):
        """MATLAB KazanViewerHelp message boxes."""
        box = QMessageBox(QMessageBox.Icon.Information, text, '\n'.join(HELP[text]), parent=self)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if text in ('Axis Data Structure', 'Data Load Routines', 'Plugins'):
            box.setStyleSheet('QLabel { font-family: Consolas, monospace; }')
        box.exec()

    def _menu_documentation(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DOCS)))

    # ================================================================ close
    def _log_prepend(self, lines: list[str]):
        old = self.TextArea.toPlainText()
        self.TextArea.setPlainText('\n'.join(lines) + ('\n' + old if old else ''))

    def closeEvent(self, event):
        if self in VIEWERS:
            VIEWERS.remove(self)
        self.make_plugins('closeall')
        try:
            self.ini.save()
        except OSError:
            pass
        super().closeEvent(event)
