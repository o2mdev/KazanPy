import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1])
app = QApplication(sys.argv); f = app.font(); f.setPointSize(10); app.setFont(f)
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
w = KazanViewer(ini=KazanIni(S/'test.ini')); w.show()
w.ddExt.setCurrentText('*.dsc'); w.ddDataType.setCurrentText('XEPR'); w.load_directory(r'C:\Temp\Denver')
w.lbDirlist.setCurrentRow([e[0] for e in w._dir_entries].index('mytest.DSC')); app.processEvents()
info = [i for i in w.plugin_infos if i.name == 'CWPLUGIN3'][0]
w.launch_plugin(info); p = w.plugins[-1]; app.processEvents()
p.tbSrcDerivative.click(); p.tbDestDerivative.click(); app.processEvents()
print('outputs:', [(d.title, d.y.shape) for d in w.out])
for k in ('LWpp', 'LW-L', 'LW-G', 'LW-V'):
    p.fit_line(k); print(k, '->', p.eResInt.toPlainText().replace('\n', ' | '))
# central line only: evaluation range picked via (simulated) ginput
w.ginput = lambda n: np.array([[3367.5, 0], [3370.5, 0]])
p._pick_range('evaluate'); p.cbFullIntRange.setChecked(False); p.cbShowIntRange.setChecked(True)
for k in ('LWpp', 'LW-L', 'LW-V'):
    p.fit_line(k); print('range', k, '->', p.eResInt.toPlainText().replace('\n', ' | '))
app.processEvents(); w.grab().save(str(S/'cw_viewer_fit.png'))
# absorption output + LWhh + integral
p.cbFullIntRange.setChecked(True); p.tbDestAbsorption.click(); p.fit_line('LWhh'); print('LWhh ->', p.eResInt.toPlainText().replace('\n',' | '))
p._on_integral(); print('Integral ->', p.eResInt.toPlainText())
# baseline: linear fit on outer points
p.base_buttons['2'].click(); p.pbBaseline.click(); p.cbBaselineShow.setChecked(True); p._on_fit_baseline()
print('baseline script:', [p.lbPars.item(i).text() for i in range(p.lbPars.count())])
p.base_buttons['3'].click(); p._on_fit_baseline(); print('poly3:', [p.lbPars.item(i).text() for i in range(p.lbPars.count())])
p.pbPhase.click(); p.cbUseDispersion.setChecked(False); p.ePhase.setValue(30); p.tbFilterOn.click(); app.processEvents()
print('phase/filter outputs:', [(d.title, d.y.dtype, d.ax.get('LineStyle'), d.ax.get('Marker')) for d in w.out])
app.processEvents(); w.grab().save(str(S/'cw_viewer_base.png')); p.grab().save(str(S/'cw_plugin.png'))
p.close(); w.close(); print('OK')
