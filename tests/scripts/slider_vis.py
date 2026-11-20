"""The slice slider and X / Y button show only when the displayed data are 2D."""
import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
w = KazanViewer(ini=KazanIni(S / 'sv.ini')); w.show(); app.processEvents()
vis = lambda: w.slice_col.isVisible()
x = np.linspace(0, 1, 50)
print('empty', vis()); assert not vis()
w.set_data('source', KzData(y=x[:, None], ax=Struct(x=x), title='1d')); w._on_src_out(1)
print('1D source', vis()); assert not vis()
t = np.arange(800) * 20e-9; B = np.linspace(3300, 3400, 100)
y = np.where(t[:, None] > 4e-6, np.exp(-(t[:, None] - 4e-6) / 3e-6), 0) / (1 + ((B[None, :] - 3350) / 5) ** 2)
w.set_data('source', KzData(y=y, ax=Struct(x=t, xlabel='Time, s', y=B, ylabel='Field, G'), title='tr')); w._on_src_out(1)
print('2D source', vis()); assert vis()
w.b2D.click(); print('Y direction', w.b2D.text(), w._n_slices()); assert w.view.abscissa == 2
info = [i for i in w.plugin_infos if i.name == 'TRANSIENT3'][0]
w.launch_plugin(info); app.processEvents(); tr = w.plugins[-1]
print('field-domain output (1D)', vis(), 'abscissa', w.view.abscissa); assert not vis() and w.view.abscissa == 1
tr.pbTimeField.click(); app.processEvents()
print('time-domain output (2D)', vis()); assert vis()
w.bSource.click(); app.processEvents(); print('back to 2D source', vis()); assert vis()
for pt in ('Stack', 'Contour', 'Density'):          # all slices at once: no slider
    w._on_plot_type(pt); app.processEvents(); print(pt, vis()); assert not vis()
w._on_plot_type('1D'); app.processEvents(); print('1D again', vis()); assert vis()
tr.close(); w.close(); print('OK')
