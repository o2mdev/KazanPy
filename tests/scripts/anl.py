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
rng = np.random.default_rng(2)
t = np.linspace(0, 200e-6, 2001); tu = t * 1e6
def setsrc(y):
    w.set_data('source', KzData(y=(y + 0.002 * rng.standard_normal(len(t)) + 0.05)[:, None], ax=Struct(x=t, xlabel='Time, s'), dsc=Struct(), title='d'))
se = np.where(tu > 20, np.exp(-(tu - 20) / 12.0), 0)
setsrc(se)
a = launch('ANLPLG3')
tabs = a.TabGroupFittingMethods
def run(tab, bound=False):
    tabs.setCurrentIndex([tabs.tabText(i) for i in range(tabs.count())].index(tab))
    a.reset_range(tab); a.cbBoundfit.setChecked(bound)
    if tab == 'SE': a.tabs_w['SE']['first'].setValue(a.tabs_w['SE']['offset'].value())
    a.ComputeButton.click()
    print(f'[{tab}{" bound" if bound else ""}]', a.tOutput.toPlainText().replace('\n', ' | '), '| out', [d.title for d in w.out])
a.baseline = tu < 15   # baseline on the pre-trigger part
run('SE'); run('SE', True)
irf = 0.5 * np.exp(-(tu - 20) / 12.0) * 0  # placeholder
from plugins.anlplg3 import exp_irf
setsrc(0.8 * exp_irf(tu - 20, 12.0, 2.0)); a.baseline = tu < 10
run('SE + IRF'); run('SE + IRF', True)
de = np.where(tu > 20, 0.6 * np.exp(-(tu - 20) / 5.0) + 0.4 * np.exp(-(tu - 20) / 60.0), 0)
setsrc(de); a.baseline = tu < 15
c = a.tabs_w['DE']; tabs.setCurrentIndex(2); a.reset_range('DE'); c['t1'].setValue(10); c['t2'].setValue(50); a.ComputeButton.click()
print('[DE]', a.tOutput.toPlainText().replace('\n', ' | '), [d.title for d in w.out])
setsrc(0.6 * exp_irf(tu - 20, 5.0, 2.0) + 0.4 * exp_irf(tu - 20, 60.0, 2.0)); a.baseline = tu < 10
tabs.setCurrentIndex(3); a.reset_range('DE + IRF'); c = a.tabs_w['DE + IRF']; c['t1'].setValue(10); c['t2'].setValue(50); c['offset'].setValue(18); c['irf'].setValue(1.5); a.ComputeButton.click()
print('[DE + IRF]', a.tOutput.toPlainText().replace('\n', ' | '))
# light-dark: 2 rows
ld = np.vstack([np.ones(50) * (1 + 1j), np.ones(50) * (0.2 + 0.1j)])
w.set_data('source', KzData(y=ld, ax=Struct(x=np.array([0., 1.]), y=np.arange(50.), ylabel='Time, s'), dsc=Struct()))
tabs.setCurrentIndex(4); a.LDPhaseSpinner.setValue(10); print('LD', w.out[0].title, w.out[0].y.shape, np.round(w.out[0].y[0, 0], 3), a.windowTitle(), a.FittingparametersPanel.isEnabled())
tabs.setCurrentIndex(5); a.PhaseSpinner.setValue(90); print('Phase', w.out[0].title, np.round(w.out[0].y[0, 0], 3))
a.grab().save(str(S/'anl_plugin.png')); a.close(); app.processEvents(); w.close(); print('OK')
