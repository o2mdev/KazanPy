import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QApplication

S = Path(sys.argv[1])
app = QApplication(sys.argv)
f = app.font(); f.setPointSize(10); app.setFont(f)
from kazan.core.ini import KazanIni
from kazan.io.ascii import ascii_read
from kazan.viewer import KazanViewer
from kazan.viewer import console, main_window

ini = S / 'test_menus.ini'
ini.unlink(missing_ok=True)
v = KazanViewer(ini=KazanIni(ini)); v.show(); app.processEvents()
v.ddExt.setCurrentText('*.dsc'); v.ddDataType.setCurrentText('XEPR')
v.load_file(r'C:\Temp\Jens\110122\x122091301.DSC'); app.processEvents()
print('disabled menu items:', [a.text() for m in v.menuBar().actions() for a in m.menu().actions()
                               if not a.isEnabled()])

# ---- font
w0 = v.bUp.width(); fs0 = v.bUp.font().pointSize()
v.set('font', v.view.default_font + 4); app.processEvents()
print('font +4: bUp width', w0, '->', v.bUp.width(), '| button font', fs0, '->', v.bUp.font().pointSize(),
      '| list font', v.lbDirlist.font().pointSize(), '| ini Font', v.ini.get('KazanViewer', 'Font', ''))
v.grab().save(str(S / 'font_after_4.png'))
v.set('font', v.view.default_font - 4); app.processEvents()
print('font -4: bUp width', v.bUp.width(), 'font', v.bUp.font().pointSize())
v.grab().save(str(S / 'font_after_-4.png'))
v.set('font', v.view.default_font); app.processEvents()

# ---- save with footer, read back
d = v._save_data(False)
out = S / 'save_test.txt'
main_window.ascii_write(str(out), d, origin=d.filename, parameters=[n for n, _, _ in v.DATA_PARAMETERS])
ax, y, dsc = ascii_read(str(out))
print('save/read: y', y.shape, 'ax.y restored', np.allclose(ax.y, np.ravel(d.ax.y)), 'max err',
      float(np.max(np.abs(y - np.real(d.y)))), 'xlabel', ax.xlabel)

# ---- convert folder
tmp = S / 'conv'
shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
for ext in ('.DSC', '.DTA', '.YGF'):
    shutil.copy(r'C:\Temp\Jens\110122\x122091301' + ext, tmp)
v.load_directory(str(tmp)); app.processEvents()
n = v.convert_folder('.dat'); print('convert folder:', n, sorted(p.name for p in tmp.iterdir()))
print('only missing:', v.convert_folder('.dat', only_missing=True))

# ---- workspace
v._menu_workspace('export_src')
print('workspace exp_src', console.WORKSPACE['exp_src'].y.shape)
con = console.WorkspaceConsole.instance()
con.run('exp_src.y = exp_src.y[:, :3] * 2')
con.run('print(exp_src.y.shape)')
v._menu_workspace('load_src')
print('loaded back', v.src.y.shape, '| console tail:', con.out.toPlainText().strip().splitlines()[-1])

# ---- view items
v._set_aspect('square'); app.processEvents()
r = v.plot.real.getViewBox().sceneBoundingRect()
print('square: viewbox', round(r.width()), 'x', round(r.height()))
v._set_aspect('equal'); print('equal locked', v.plot.real.getViewBox().state['aspectLocked'])
v._set_aspect('normal')
v._set_grid(True); v._set_minor_grid(True)
print('grid', v.plot.real.getAxis('bottom').grid, v.plot.real.getAxis('left').grid,
      'levels', v.plot.real.getAxis('bottom').style['maxTickLevel'])
v._set_range('manual'); v.plot.set_view_area(0, 1e-5, 20, 40); app.processEvents()
print('view area', [round(x, 8) for x in v.plot.view_area()])
v._set_range('tight')

# ---- figures
v.load_file(r'C:\Temp\Jens\110122\x122091301.DSC'); v.view.part = 'reim'
plt = main_window.figures.pyplot()
v._menu_figure('open'); fig = plt.gcf(); print('open figure axes', len(fig.axes), fig.axes[0].get_title())
v._menu_figure((1, 2, 2)); print('subplot axes', len(plt.gcf().axes))
v._menu_figure('show'); plt.gcf().savefig(S / 'fig_show.png')
v.view.part = 'real'
v.view.plot_type = 'Contour'; v._menu_figure('show'); plt.gcf().savefig(S / 'fig_contour.png')
v.view.plot_type = '1D'
for k in ('surf', 'scatter3', 'surface'):
    v._menu_plot_2d(k); plt.gcf().savefig(S / f'fig_{k}.png')
print('figures', plt.get_fignums())
plt.close('all')

# ---- new window
v._menu_new_window(); app.processEvents()
print('viewers', len(main_window.VIEWERS))
for w in list(main_window.VIEWERS):
    w.close()
print('OK')
