import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication, QInputDialog
S = Path(sys.argv[1])
app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
sys.path.insert(0, 'D:/KazanPy')
from plugins.mathplugin3 import matlab_index
print('idx', matlab_index('[5,8,9]', 10), matlab_index('1:3:end', 10), matlab_index('2:4 end', 10), matlab_index('10:-2:5', 10))
w = KazanViewer(ini=KazanIni(S/'test.ini')); w.show()
x = np.linspace(-5, 5, 101)
y = np.stack([np.exp(-x**2/(1+k))*np.exp(1j*np.deg2rad(30)) for k in range(6)], 1)
w.set_data('source', KzData(y=y, ax=Struct(x=x, y=np.arange(6.)*10, xlabel='field, G', ylabel='angle, deg'), dsc=Struct(), title='set'))
def launch(name):
    info = [i for i in w.plugin_infos if i.name == name][0]
    w.launch_plugin(info); app.processEvents(); return w.plugins[-1]
m = launch('MATHPLUGIN3')
print('limits', m.e1DLast.maximum(), m.e1DLast.value(), m.e2DLast.value())
m.bReal.click(); print('real', w.out[0].y.dtype)
m.bAsIs.click(); m.pbPhase.setChecked(True); m.ePhase.setValue(30); print('phased imag max', np.abs(w.out[0].y.imag).max())
m.pbPhase.setChecked(False)
m.e1DFirst.setValue(11); m.e1DLast.setValue(91); m.e2DFirst.setValue(2); m.e2DLast.setValue(4); m.bCutData.setChecked(True)
print('cut', w.out[0].y.shape, w.out[0].ax.x[[0,-1]], w.out[0].ax.y)
m.eCut2Dim.setText('1:2:end'); m.cbExpression2Dim.setChecked(True); print('eval cut', w.out[0].y.shape, w.out[0].ax.y)
m.pbTranspose.setChecked(True); print('transpose', w.out[0].y.shape, w.out[0].ax.xlabel, w.out[0].ax.x)
m.pbTranspose.setChecked(False); m.tbSum.setChecked(True); print('sum', w.out[0].y.shape)
m._reset_cut(); print('reset', m.e1DLast.value(), m.e2DLast.value())
m.close()
c = launch('COMPBOX3')
c.add()
d2 = KzData(y=(2*np.exp(-(x-1)**2)+0.5).reshape(-1,1), ax=Struct(x=x, xlabel='field, G'), dsc=Struct(), filename=r'C:\data\b.dat')
w.set_data('source', d2); c.add()
print('traces', [c.ddTraces.itemText(i) for i in range(c.ddTraces.count())], [o.ax.Color for o in w.out])
c.spin['shift_x'].setValue(1.5); print('dx in out', w.out[1].ax.dx)
pl = [it for it in w.plot.real.listDataItems()]; print('plotted x0 of trace2', pl[-1].xData[0])
c.to_first(); t = c.traces[1]; print('to first zoom/shift', round(t['zoom_y'],4), round(t['shift_y'],4))
c.traces[0]['zoom_y'] = 3.0; c.fit_all_to_first(); assert c.traces[0]['zoom_y'] == 1.0
c.ddUnits.setCurrentText('dB'); c.traces[0]['zoom_y'] = 6.0; c.fit_all_to_first()
assert c.traces[0]['zoom_y'] == 0.0; c.ddUnits.setCurrentText('linear')
for t in c.traces: t['shift_y'], t['zoom_y'] = 2.0, 3.0
acts = {a.text(): a for a in c.menuBar().actions()[0].menu().actions()}; acts['Clear Y All'].trigger()
assert all(t['shift_y'] == 0 and t['zoom_y'] == 1 for t in c.traces)
c.to_first(); c.ddUnits.setCurrentText('dB'); print('dB zoom', round(c.traces[1]['zoom_y'],4)); c.ddUnits.setCurrentText('linear')
c.normalize_all(); print('norm', [(round(t['zoom_y'],3), round(t['shift_y'],3)) for t in c.traces])
c.ddTraces.setCurrentIndex(0); c.normalize_slices(); print('norm2d out range', np.round([np.real(w.out[0].y).min(axis=0).max(), np.real(w.out[0].y).max(axis=0).min()],3), c.mDisChanges.isVisible())
c.discard_2d()
QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.5, True)); c.waterfall(False); print('waterfall', [t['shift_y'] for t in c.traces])
c.add_all(); print('add all', w.out[0].y.shape, np.isnan(w.out[0].y).sum())
c.ddTraces.setCurrentIndex(0); c.ungroup(); print('ungroup', len(c.traces), [c.ddTraces.itemText(i) for i in range(c.ddTraces.count())][:3])
c.sort_by_y(); print('sorted y', [float(np.ravel(t['data'].ax.y)[0]) for t in c.traces])
for t in c.traces: t['shift_x']=0
c.join_traces(); print('join', c.traces[0]['data'].y.shape, c.ddTraces.itemText(0), c.traces[0]['data'].ax.y)
c.add_current_to_output(); print('cur to out', len(w.out))
n0 = len(c.traces); fit = w.out[0].copy(); fit.ax.s = 0.25; fit.ax.dx = -0.5; fit.title = 'fit'
w.set_data('output', [fit, fit]); c.bAddOutput.click()
t = c.traces[-1]; assert len(c.traces) == n0 + 2 and t['shift_y'] == 0.25 and t['shift_x'] == -0.5, t
assert c.ddTraces.itemText(len(c.traces) - 1).endswith(':fit') and len(w.out) == n0 + 2
w.set_data('output', []); c.add_output(); assert len(c.traces) == n0 + 2
print('add output', len(c.traces), c.bAdd.text(), '|', c.bAddOutput.text())
# Change from Output: current trace replaced, colour kept, shifts from the output
c.ddTraces.setCurrentIndex(0); col0 = c.traces[0]['data'].ax.Color
f2 = fit.copy(); f2.y = f2.y * 3; f2.ax.s = 0.75; f2.title = 'fit2'
w.set_data('output', [f2]); c.bChangeOutput.click(); t = c.traces[0]
assert t['shift_y'] == 0.75 and t['data'].ax.Color == col0 and c.ddTraces.itemText(0) == '1:fit2'
assert np.allclose(np.real(t['data'].y), np.real(f2.y)) and len(c.traces) == n0 + 2
# Options menu: Inverse Y, Combine All Traces to 2D, Delete All
acts = {a.text(): a for a in c.bOptions.menu().actions() if a.text()}
assert set(acts) == {'Inverse Y', 'Combine All Traces to 2D', 'Source processing', 'Delete All'}, set(acts)
assert [m.title() for m in c.menuBar().findChildren(type(c.mOptions)) if m.title()] == ['Processing']
acts['Inverse Y'].trigger(); assert c.traces[0]['ysign'] == -1
for t in c.traces: t['shift_x'] = 0
acts['Combine All Traces to 2D'].trigger()          # check box: output only
assert acts['Combine All Traces to 2D'].isChecked() and len(c.traces) == n0 + 2
ncol = sum(t['data'].y.shape[1] for t in c.traces)   # every column of every trace
assert len(w.out) == 1 and w.out[0].y.shape[1] == ncol, [o.y.shape for o in w.out]
c.spin['shift_y'].setValue(5.0); assert len(w.out) == 1      # stays combined on edits
acts['Combine All Traces to 2D'].trigger(); assert len(w.out) == n0 + 2
acts['Delete All'].trigger(); assert not c.traces
c.add(); c.change_output(); assert len(c.traces) == 1
print('options ok')
app.processEvents(); w.grab().save(str(S/'comp_viewer.png')); c.grab().save(str(S/'comp_plugin.png'))
c.delete_all(); print('after delete', len(w.out), c.ddTraces.itemText(0))
c.close(); m = launch('MATHPLUGIN3'); m.grab().save(str(S/'math_plugin.png')); m.close(); w.close(); print('OK')
