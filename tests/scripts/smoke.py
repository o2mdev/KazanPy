import sys, numpy as np
from pathlib import Path
S = Path(sys.argv[1])
# test data: asymmetric 1D derivative-like line and a 2D set
x = np.linspace(3300, 3400, 501)
y = -(x-3350)/((x-3350)**2+25)**1 + 0.3*np.exp(-((x-3365)/4)**2)
(S/'data').mkdir(exist_ok=True)
np.savetxt(S/'data'/'line1d.dat', np.c_[x, y], header='test EPR line\nfield, G')
np.savetxt(S/'data'/'set2d.txt', np.c_[x, np.array([y*(1-0.1*k) for k in range(8)]).T])

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv); f = app.font(); f.setPointSize(10); app.setFont(f)
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
w = KazanViewer(ini=KazanIni(S/'test.ini')); w.show(); app.processEvents()
w.grab().save(str(S/'shot_welcome.png'))
print('plugins found:', [i.name for i in w.plugin_infos])
w.ddExt.setCurrentText('*'); w.load_directory(str(S/'data'))
print('list:', [w.lbDirlist.item(i).text() for i in range(w.lbDirlist.count())])
w.lbDirlist.setCurrentRow([w.lbDirlist.item(i).text() for i in range(w.lbDirlist.count())].index('line1d.dat'))
src = w.get_data('source'); print('src', src.y.shape, src.ax.x[:2], src.filename[-10:], sorted(src.dsc)[:3])
# value semantics check
src.y[:] = 0; assert np.abs(w.src.y).max() > 0, 'host data was modified!'
info = [i for i in w.plugin_infos if i.name == 'SYMMETRIZE'][0]
w.launch_plugin(info); p = w.plugins[0]
p.eCenter.setValue(3352.0); p.pbCalculate.click(); app.processEvents()
print('view', w.view.data_src_out, 'out', [(d.title, d.ax.Color, d.y.shape) for d in w.out])
print('get slice', w.get('slice'), 'font', w.get('font'))
w.grab().save(str(S/'shot_output.png')); p.grab().save(str(S/'shot_plugin.png'))
# file_update via signal: load the 2D file -> plugin recomputes
w.lbDirlist.setCurrentRow([w.lbDirlist.item(i).text() for i in range(w.lbDirlist.count())].index('set2d.txt'))
print('after 2D load out shapes', [d.y.shape for d in w.out])
w.set('slice', 3); w.type_buttons['Stack'].click(); app.processEvents(); w.grab().save(str(S/'shot_stack.png'))
w.type_buttons['Density'].click(); w.type_buttons['Contour'].click(); w.part_buttons['reim'].click(); w.type_buttons['1D'].click(); app.processEvents()
w.bSource.click(); app.processEvents()
p.close(); app.processEvents(); print('plugins left', len(w.plugins))
w.close(); print('OK')
