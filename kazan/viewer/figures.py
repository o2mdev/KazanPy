"""Window menu: the viewer plot in separate matplotlib figures (MATLAB ``figure`` /
``subplot`` / ``surf``), ports of kazan3 ``WindowsMenuSelected``.

matplotlib is imported on first use, so the viewer starts without it.
"""
from __future__ import annotations

import os

import numpy as np

from .plot import to_qcolor

_LINESTYLE = {'-': '-', '--': '--', ':': ':', '-.': '-.', 'none': 'None'}
_MARKER = {'o': 'o', '+': '+', '*': '*', '.': '.', 'x': 'x', 's': 's', 'square': 's',
           'd': 'd', 'diamond': 'd', '^': '^', 'v': 'v', '>': '>', '<': '<', 'p': 'p',
           'pentagram': 'p', 'h': 'h', 'hexagram': 'h'}


def pyplot():
    """matplotlib.pyplot on the Qt backend of the running application."""
    os.environ.setdefault('QT_API', 'pyside6')
    import matplotlib
    matplotlib.use('QtAgg')
    import matplotlib.pyplot as plt
    plt.ion()
    return plt


class MplPlot:
    """matplotlib axes with the drawing interface of :class:`KazanPlot`, so the viewer's
    plot code draws into a figure (MATLAB ``PlotData(rAxis, iAxis)``)."""

    def __init__(self, real, imag=None, font_size: int = 10):
        self.real, self.imag = real, imag
        self.font_size = font_size

    def clear_plots(self):
        for a in (self.real, self.imag):
            if a is not None:
                a.cla()

    def show_imag(self, show: bool):
        pass

    def set_title(self, text: str):
        self.real.set_title(text, fontsize=self.font_size, fontweight='bold')

    def set_labels(self, xlabel: str, ylabel: str, imag_ylabel: str | None = None):
        bottom = self.imag if self.imag is not None else self.real
        bottom.set_xlabel(xlabel, fontsize=self.font_size)
        self.real.set_ylabel(ylabel, fontsize=self.font_size)
        if self.imag is not None:
            self.imag.set_ylabel(imag_ylabel or ylabel, fontsize=self.font_size)

    @staticmethod
    def line(item, x, y, color='b', width=1.0, style='-', marker='none'):
        if item is None:
            return
        item.plot(np.asarray(x), np.asarray(y), color=to_qcolor(color).name(),
                  linewidth=float(width), linestyle=_LINESTYLE.get(style, '-'),
                  marker=_MARKER.get(marker), markerfacecolor='none')

    @staticmethod
    def density(item, x, y, z, clim=None):
        if item is None:
            return
        kw = dict(vmin=clim[0], vmax=clim[1]) if clim is not None and clim[1] > clim[0] else {}
        item.imshow(np.asarray(z, float).T, origin='lower', aspect='auto', cmap='viridis',
                    extent=[float(x[0]), float(x[-1]), float(y[0]), float(y[-1])], **kw)

    @staticmethod
    def contour(item, x, y, z, nlevels: int = 10, levels=None):
        if item is None:
            return
        z = np.asarray(z, float)
        if levels is None:
            levels = np.linspace(np.nanmin(z), np.nanmax(z), nlevels + 2)[1:-1]
        levels = np.unique(np.asarray(levels, float))
        item.contour(np.ravel(x), np.ravel(y), z.T, levels=levels, cmap='viridis')

    def axis_modes(self, item, logx=False, logy=False, invx=False, invy=False):
        if item is None:
            return
        item.set_xscale('log' if logx else 'linear')
        item.set_yscale('log' if logy else 'linear')
        if item.xaxis_inverted() != invx:
            item.invert_xaxis()
        if item.yaxis_inverted() != invy:
            item.invert_yaxis()

    def set_range_mode(self, mode: str):
        for a in (self.real, self.imag):
            if a is not None:
                a.margins(0.0 if mode == 'tight' else 0.05)
                a.autoscale(True)

    def set_grid(self, on: bool, minor: bool = False):
        for a in (self.real, self.imag):
            if a is not None:
                a.grid(on, which='major')
                if minor:
                    a.minorticks_on()
                    a.grid(True, which='minor', axis='x', alpha=0.3)

    def set_aspect(self, mode: str):
        for a in (self.real, self.imag):
            if a is not None:
                if mode == 'equal':
                    a.set_aspect('equal', adjustable='datalim')
                elif mode == 'square':
                    a.set_box_aspect(1)


def plot_2d(kind: str, d):
    """MATLAB Plot 2D menu: ``surf``, ``scatter3`` (one coloured point per sample) or
    ``surface`` (one line per slice, coloured by its value); colormap jet."""
    plt = pyplot()
    y = np.real(np.asarray(d.y))
    x = np.ravel(d.ax.x)
    ys = np.ravel(d.ax.get('y')) if d.ax.get('y') is not None else np.arange(1.0, y.shape[1] + 1)
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    if kind == 'surf':
        X, Y = np.meshgrid(ys, x)
        ax.plot_surface(X, Y, y, cmap='jet', edgecolor='none')
        ax.set_xlabel(d.ax.get('ylabel') or '')
        ax.set_ylabel(d.ax.get('xlabel') or '')
        ax.view_init(14, 30 - 90)
    else:
        if kind == 'scatter3':
            X = np.repeat(x[:, None], y.shape[1], axis=1)
            Z = np.repeat(ys[None, :], y.shape[0], axis=0)
            ax.scatter(X.ravel(), Z.ravel(), y.ravel(), c=y.ravel(), cmap='jet', s=1)
        else:
            from mpl_toolkits.mplot3d.art3d import Line3DCollection
            norm = plt.Normalize(np.nanmin(y), np.nanmax(y))
            for k in range(y.shape[1]):
                pts = np.column_stack([x, np.full_like(x, ys[k], dtype=float), y[:, k]])
                seg = np.stack([pts[:-1], pts[1:]], axis=1)
                lc = Line3DCollection(seg, cmap='jet', norm=norm)
                lc.set_array(0.5 * (y[:-1, k] + y[1:, k]))
                ax.add_collection3d(lc)
            ax.set_xlim(np.nanmin(x), np.nanmax(x))
            ax.set_ylim(np.nanmin(ys), np.nanmax(ys))
            ax.set_zlim(np.nanmin(y), np.nanmax(y))
        ax.set_xlabel(d.ax.get('xlabel') or '')
        ax.set_ylabel(d.ax.get('ylabel') or '')
        ax.view_init(14, -55 - 90)
    fig.show()
    return fig
