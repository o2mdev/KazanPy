"""pyqtgraph plot area styled after the MATLAB Kazan3 axes.

White background, black box axes with inward ticks, bold title, MATLAB letter
colours. Two axes: Real (always) and Imag (shown in Re/Im mode), as in kazan3
(``haReal`` / ``haImag``).
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QTransform

pg.setConfigOptions(background='w', foreground='k', antialias=True, imageAxisOrder='col-major')

MATLAB_COLORS = {
    'b': (0, 0, 255), 'g': (0, 255, 0), 'r': (255, 0, 0), 'c': (0, 255, 255),
    'm': (255, 0, 255), 'y': (255, 255, 0), 'k': (0, 0, 0), 'w': (255, 255, 255),
}
COLOR_ORDER = ['b', 'g', 'r', 'c', 'm', 'y', 'k']  # classic MATLAB plot order
_LINESTYLE = {'-': Qt.PenStyle.SolidLine, '--': Qt.PenStyle.DashLine, ':': Qt.PenStyle.DotLine,
              '-.': Qt.PenStyle.DashDotLine}
_MARKER = {'o': 'o', '+': '+', '*': 'star', '.': 'o', 'x': 'x', 's': 's', 'square': 's',
           'd': 'd', 'diamond': 'd', '^': 't1', 'v': 't', '>': 't2', '<': 't3', 'p': 'p', 'h': 'h'}


def to_qcolor(c, default='b') -> QColor:
    """MATLAB colour spec ('r', [1 0 0], (255, 0, 0), '#ff0000') -> QColor."""
    if c is None or (isinstance(c, str) and not c):
        c = default
    if isinstance(c, str):
        if c in MATLAB_COLORS:
            return QColor(*MATLAB_COLORS[c])
        return QColor(c)
    v = np.asarray(c, dtype=float).ravel()[:3]
    if v.max() <= 1.0:
        v = v * 255
    return QColor(*[int(round(a)) for a in v])


class _KazanViewBox(pg.ViewBox):
    """ViewBox whose right-click opens Kazan's own context menu."""

    def __init__(self, menu_callback):
        super().__init__()
        self._menu_callback = menu_callback

    def raiseContextMenu(self, ev):
        self._menu_callback(ev.screenPos().toPoint())


class KazanPlot(pg.GraphicsLayoutWidget):
    #: (x, y) data coordinates of a left click on the Real axes
    clicked = Signal(float, float)
    #: global position for the processing context menu
    contextMenuRequested = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.real = pg.PlotItem(viewBox=_KazanViewBox(self.contextMenuRequested.emit))
        self.imag = pg.PlotItem(viewBox=_KazanViewBox(self.contextMenuRequested.emit))
        for p in (self.real, self.imag):
            self._style(p)
        self.imag.setXLink(self.real)
        self.addItem(self.real, row=0, col=0)
        self._imag_shown = False
        self.font_size = 12
        self.scene().sigMouseClicked.connect(self._on_scene_click)

    # ------------------------------------------------------------------ style
    def _style(self, p: pg.PlotItem):
        p.hideButtons()
        for name in ('top', 'right'):
            p.showAxis(name)
            p.getAxis(name).setStyle(showValues=False)
        for name in ('left', 'bottom', 'top', 'right'):
            a = p.getAxis(name)
            a.setPen(pg.mkPen('k', width=1))
            a.setTextPen(pg.mkPen('k'))
            a.setStyle(tickLength=6)  # positive = inward ticks, as in MATLAB
            a.enableAutoSIPrefix(False)

    def set_font_size(self, size: int):
        self.font_size = size
        f = QFont()
        f.setPointSize(max(size - 1, 6))
        for p in (self.real, self.imag):
            for name in ('left', 'bottom'):
                p.getAxis(name).setStyle(tickFont=f)

    # ------------------------------------------------------------------ layout
    def show_imag(self, show: bool):
        if show and not self._imag_shown:
            self.addItem(self.imag, row=1, col=0)
        elif not show and self._imag_shown:
            self.removeItem(self.imag)
        self._imag_shown = show

    def clear_plots(self):
        for p in (self.real, self.imag):
            p.clear()

    def set_title(self, text: str):
        self.real.setTitle(f'<b>{text}</b>', size=f'{self.font_size}pt', color='k')

    def set_labels(self, xlabel: str, ylabel: str, imag_ylabel: str | None = None):
        css = {'font-size': f'{self.font_size}pt', 'color': '#000'}
        target = self.imag if self._imag_shown else self.real
        target.setLabel('bottom', xlabel, **css)
        if self._imag_shown:
            self.real.setLabel('bottom', '')
        self.real.setLabel('left', ylabel, **css)
        self.imag.setLabel('left', imag_ylabel or ylabel, **css)

    # ------------------------------------------------------------------ drawing
    @staticmethod
    def line(p: pg.PlotItem, x, y, color='b', width=1.0, style='-', marker='none'):
        """MATLAB plot(x, y, 'Color', c, 'LineStyle', style, 'LineWidth', w, 'Marker', m)."""
        c = to_qcolor(color)
        pen = None if style == 'none' else pg.mkPen(c, width=float(width), style=_LINESTYLE.get(style, Qt.PenStyle.SolidLine))
        symbol = _MARKER.get(marker)
        kw = {}
        if symbol:
            kw = dict(symbol=symbol, symbolPen=pg.mkPen(c), symbolBrush=None, symbolSize=6)
        p.plot(np.asarray(x), np.asarray(y), pen=pen, **kw)

    @staticmethod
    def density(p: pg.PlotItem, x, y, z):
        img = pg.ImageItem(np.asarray(z, dtype=float))
        x0, x1, y0, y1 = float(x[0]), float(x[-1]), float(y[0]), float(y[-1])
        img.setRect(QRectF(x0, y0, (x1 - x0) or 1.0, (y1 - y0) or 1.0))
        img.setColorMap(pg.colormap.get('viridis'))
        p.addItem(img)

    @staticmethod
    def contour(p: pg.PlotItem, x, y, z, nlevels: int = 10):
        z = np.asarray(z, dtype=float)
        nx, ny = z.shape
        tr = QTransform()
        tr.translate(float(x[0]), float(y[0]))
        tr.scale((float(x[-1]) - float(x[0])) / max(nx - 1, 1) or 1.0,
                 (float(y[-1]) - float(y[0])) / max(ny - 1, 1) or 1.0)
        cmap = pg.colormap.get('viridis')
        zmin, zmax = np.nanmin(z), np.nanmax(z)
        for i, level in enumerate(np.linspace(zmin, zmax, nlevels + 2)[1:-1]):
            c = cmap.map((i + 0.5) / nlevels, mode='qcolor')
            iso = pg.IsocurveItem(data=z, level=level, pen=pg.mkPen(c))
            iso.setTransform(tr)
            p.addItem(iso)

    # ------------------------------------------------------------------ view
    def set_range_mode(self, mode: str):
        """'tight' or 'auto' (MATLAB axis tight / axis auto)."""
        pad = 0.0 if mode == 'tight' else 0.05
        for p in (self.real, self.imag):
            p.getViewBox().autoRange(padding=pad)

    def set_grid(self, on: bool):
        for p in (self.real, self.imag):
            p.showGrid(x=on, y=on, alpha=0.25)

    def set_zoom_mode(self, on: bool):
        mode = pg.ViewBox.RectMode if on else pg.ViewBox.PanMode
        for p in (self.real, self.imag):
            p.getViewBox().setMouseMode(mode)

    def scale(self, sx: float = 1.0, sy: float = 1.0):
        for p in (self.real, self.imag):
            p.getViewBox().scaleBy((sx, sy))

    def _on_scene_click(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        vb = self.real.getViewBox()
        if vb.sceneBoundingRect().contains(ev.scenePos()):
            pt = vb.mapSceneToView(ev.scenePos())
            self.clicked.emit(pt.x(), pt.y())
