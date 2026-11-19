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
x = np.linspace(0, 10, 201)
ref = KzData(y=(np.sin(x) + 1).reshape(-1, 1), ax=Struct(x=x, xlabel='t, s'), dsc=Struct(), title='ref')
w.set_data('source', ref)
m = launch('MINUSBOX3')
m.plot_this(); print('no ref msg:', w.plot.real.titleLabel.text)
m.set_reference()
x2 = np.linspace(0.5, 9.5, 150)
cur = KzData(y=(2*np.sin(x2) + 2 + 0.5*x2).reshape(-1, 1), ax=Struct(x=x2, xlabel='t, s'), dsc=Struct(), title='cur')
w.set_data('source', cur); m.plot_this()
print('titles', [d.title for d in w.out])
m.spin['zoom_y'].setValue(0.5); m.spin['shift_y'].setValue(-1.0)
r = w.out[-1]; print('result max |res - 0.25x|', np.abs(r.y[:,0] + 0.25*r.ax.x).max(), 'x range', r.ax.x[[0,-1]])
m.cbPlus.click(); print('op', m.operator, round(float(w.out[-1].y[0,0]),3))
m.cbSimpleMath.click(); print('simple', [d.title for d in w.out])
m.cbMinus.click(); m.reset_shift(); m.reset_zoom(); m.to_ref(); print('to ref', {k: round(s.value(),4) for k,s in m.spin.items()})
m.cbInverseResult.setChecked(True); m.cbShiftResult.setChecked(True); m.eShiftResult.setValue(2); print('res s', w.out[-1].ax.s)
# 2D current vs 1D ref, per-slice zoom
y2 = np.stack([np.sin(x)+1]*3, 1) * np.array([1,2,3])
w.set_data('source', KzData(y=y2, ax=Struct(x=x), dsc=Struct(), title='2d'))
m.set_reference(); print('slices', [m.pmSlice.itemText(i) for i in range(m.pmSlice.count())])
m.cbInverseResult.setChecked(False); m.cbShiftResult.setChecked(False); m.reset_shift(); m.reset_zoom()
for k in (1,2,3): m.pmSlice.setCurrentIndex(k); m.spin['zoom_y'].setValue(1.0/k)
w.set_data('source', KzData(y=np.stack([np.sin(x)+1]*3,1), ax=Struct(x=x), dsc=Struct(), title='flat')); m.plot_this()
print('ref - cur/k residual per slice', np.round(np.abs(w.out[-1].y - (y2 - np.stack([np.sin(x)+1]*3,1)*np.array([1,1/2,1/3]))).max(),6))
m.grab().save(str(S/'minus_plugin.png')); m.close()
# Description
w.ddExt.setCurrentText('*.dsc'); w.ddDataType.setCurrentText('XEPR'); w.load_directory(r'C:\Temp\Jens\Pulse')
names = [e[0] for e in w._dir_entries]; w.lbDirlist.setCurrentRow(names.index('x123013002.DSC')); app.processEvents()
d = launch('DESCRIPTION3'); print('title', d.windowTitle()[-20:]); print(d.txtDescription.toPlainText().splitlines()[:3])
from plugins.description3 import psd_sequence
print('Psd5', psd_sequence(w.src.dsc, 5)[:3].tolist())
d.show_sequence(); app.processEvents(); win = d.sequence_windows[-1]; win.grab().save(str(S/'sequence.png'))
w.set_data('source', ref); d.file_update(); d.show_sequence(); print('msg', w.plot.real.titleLabel.text)
d.grab().save(str(S/"desc_plugin.png")); d.close(); app.processEvents(); w.close(); print('OK')
