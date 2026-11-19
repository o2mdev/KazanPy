import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1])
app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
w = KazanViewer(ini=KazanIni(S/'test.ini')); w.show()
def launch(name):
    info = [i for i in w.plugin_infos if i.name == name][0]
    w.launch_plugin(info); app.processEvents(); return w.plugins[-1]
# synthetic transient: rows time (800 x 20 ns), columns field (100)
t = np.arange(800) * 20e-9; B = np.linspace(3300, 3400, 100)
line = 1 / (1 + ((B - 3350) / 5) ** 2)
sig = np.where(t[:, None] > 4e-6, np.exp(-(t[:, None] - 4e-6) / 3e-6), 0) * line[None, :]
y = 0.7 + sig + 0.002 * (B - 3300)[None, :] + 0.01 * np.random.default_rng(0).standard_normal((800, 100))
w.set_data('source', KzData(y=y, ax=Struct(x=t, xlabel='Time, s', y=B, ylabel='Field, G'), dsc=Struct(), title='tr'))
tr = launch('TRANSIENT3')
print('info', tr.eInfo.toPlainText().replace('\n', ' |'), '|', tr.text2.text(), '|', tr.text1.text())
o = w.out[0]; print('field out', o.title, o.y.shape, 'peak at', o.ax.x[np.argmax(o.y.real)], 'edge level', round(float(o.y.real[:5].mean()), 4))
tr.tbF1.click(); o = w.out[0]; print('BL1 edge level', round(float(o.y.real[:10].mean()), 4), 'titles', [d.title for d in w.out])
tr.tbS2.click(); tr.cbShowFit.setChecked(True); print('showfit', [d.title for d in w.out], tr.ShowFitHint.isVisible())
tr.cbShowFit.setChecked(False); tr.cbShowSrc.setChecked(True)
tr.show_field_position = 50; tr.pbTimeField.click()
print('time', tr.windowTitle(), [(d.title, d.y.shape, d.ax.xlabel) for d in w.out])
sm = w.out[1]; print('time trace max', round(float(sm.y.real.max()), 3), 'at', sm.ax.x[np.argmax(sm.y.real)])
tr.eSstart.setText('1'); tr.eSend.setText('0'); tr.pbTimeField.click(); print('empty sig', [d.title for d in w.out])
tr.eSstart.setText('200'); tr.eSend.setText('600'); tr.pbCalculate.click()
tr.grab().save(str(S/'transient_plugin.png')); tr.close(); app.processEvents()
# rapid scan, real file
w.ddExt.setCurrentText('*.d01'); w.ddDataType.setCurrentText('SpecMan'); w.load_directory(r'C:\Temp\BE\2025\02\250206')
names = [e[0] for e in w._dir_entries]; w.lbDirlist.setCurrentRow(names.index('1775RSCAN_file.d01')); app.processEvents()
print('src', w.src.y.shape, w.src.ax.xlabel)
rs = launch('RAPIDSCAN3')
for b in (rs.rb3, rs.rb1, rs.rb2, rs.rb4):
    b.click(); app.processEvents()
    print(b.text(), [(d.title, d.y.shape, round(float(d.ax.x[0]), 4), round(float(d.ax.x[-1]), 4)) for d in w.out], '| msg:', w.plot.real.titleLabel.text[:60])
print('baseline text', rs.TextArea.toPlainText())
rs.rb3.click(); rs.VisualMode.setCurrentText('A and B'); print('A and B', [d.title for d in w.out])
rs.VisualMode.setCurrentText('Interleave-1'); print('I1', [(d.title, d.y.shape) for d in w.out])
rs.VisualMode.setCurrentText('Sum'); rs.cbAutoPhase.setChecked(True); rs.pbDeconvolute.click(); print('auto scan phase', rs.spinScanPhase.value())
rs.cbFieldMapping.setChecked(True); rs.rb1.click(); print('B map', w.out[0].y.shape, round(w.out[0].ax.x[0], 3), round(w.out[0].ax.x[-1], 3))
rs.pbFilter.setChecked(True); print('filter ok', w.out[0].y.shape)
rs.factor_buttons[0.01].click(); print('step', rs.spinPhase.singleStep())
rs.show_script(); print(rs.TextArea.toPlainText())
rs.grab().save(str(S/'rapidscan_plugin.png')); w.grab().save(str(S/'rapidscan_viewer.png'))
rs.close(); app.processEvents(); w.close(); print('OK')
