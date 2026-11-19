import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.core.processing import process, rcfilt, fieldmod
from kazan.viewer import KazanViewer
# processing
x = np.arange(1, 1001.); L = 1 / (1 + ((x - 500) / 20) ** 2)
d, w = process(KzData(y=L[:, None], ax=Struct(x=x, diff='psmod', ps_mod=2.0)))
print('psmod vs derivative', np.round(np.corrcoef(d.y[:, 0], np.gradient(L))[0, 1], 4), 'ratio', np.round(d.y.max() / np.gradient(L).max(), 3), w)
step = np.r_[np.zeros(10), np.ones(40)][:, None]
r = rcfilt(step, 1, 5.0)[:, 0]; print('rc step at tc', np.round(r[10 + 4], 3), '(1-e^-1 =', np.round(1 - np.exp(-1), 3), ')')
d, w = process(KzData(y=step + 0j, ax=Struct(x=np.arange(50.), filt='rc', tc=5))); print('rc complex ok', d.y.dtype, w)
# viewer
v = KazanViewer(ini=KazanIni(S/'test_vi.ini')); v.show(); app.processEvents()
B = np.linspace(3300, 3400, 201)
v.set_data('source', KzData(y=np.gradient(1 / (1 + ((B - 3350) / 3) ** 2))[:, None], ax=Struct(x=B, xlabel='Field, G', freq1=9.4e9), dsc=Struct(), filename='a.dat'))
pars = [v.ddSelParameter.itemData(i) for i in range(v.ddSelParameter.count())]; print('params', pars[:12], '...', len(pars))
v.ddSelParameter.setCurrentIndex(v.ddSelParameter.findData('tc')); print('tc shown', v.eParameter.text())
v.eParameter.setText('7'); v._on_parameter_set(); print('src tc', v.src.ax.tc)
v.ddSelParameter.setCurrentIndex(v.ddSelParameter.findData('freq1')); v._lock_parameter('freq1', True)
print('locked label', v.ddSelParameter.currentText(), 'style', v.eParameter.styleSheet())
v.set_data('source', KzData(y=np.ones((5, 1)), ax=Struct(x=np.arange(5.), freq1=1e9, tc=3), dsc=Struct(), filename='b.dat'))
print('after load: freq1 (locked)', v.src.ax.freq1, '| tc from file', v._par_value('tc'))
v._lock_parameter(None, False); print('unlocked', v.view.locked)
# representations
v.set_data('source', KzData(y=np.gradient(1 / (1 + ((B - 3350) / 3) ** 2))[:, None], ax=Struct(x=B, xlabel='Field, G', freq1=9.4e9, reference=9.4e9), dsc=Struct(), filename='a.dat'))
v.view.data_src_out = 1
for t in ('gspace', 'pnt', 'ppm', 'ppm-1', 'semilog', 'reverse'):
    v.view.xtype = t; v.plot_data(); d = v._datasets()[0][0]
    print(f'x {t:8s}', np.round(d.ax.x[[0, -1]], 4), d.ax.xlabel, '| invertX', v.plot.real.getViewBox().xInverted(), 'log', v.plot.real.ctrl.logXCheck.isChecked())
v.view.xtype = 'plot'; v.view.ytype = 'reverse'; v.plot_data(); print('invertY', v.plot.real.getViewBox().yInverted())
v.view.ytype = 'plot'; v.plot_data()
# contour levels
z = np.outer(np.hanning(40), np.hanning(30))
v.set_data('source', KzData(y=z, ax=Struct(x=np.arange(40.), y=np.arange(30.), contour='.2:.2:.8'), dsc=Struct(), filename='c'))
v.view.data_src_out = 1; v.view.plot_type = 'Contour'; v.plot_data()
import pyqtgraph as pg
lv = sorted(round(i.level, 3) for i in v.plot.real.items if isinstance(i, pg.IsocurveItem)); print('contour levels', lv)
v.view.plot_type = 'Density'; v.plot_data()
img = [i for i in v.plot.real.items if isinstance(i, pg.ImageItem)][0]; print('density levels', np.round(img.getLevels(), 3))
v.view.plot_type = '1D'; v.plot_data()
v.close(); print('OK')
