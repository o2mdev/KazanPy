import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1])
app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
from kazan.math.autofit import tokens, evaluate_script
print(tokens('f = a*exp(-x/t).*cos(x*2*pi*F+Ph)'), tokens('f = 1e-5*a + b2*x'))
w = KazanViewer(ini=KazanIni(S/'test.ini')); w.show()
x = np.linspace(0, 10e-6, 200); taus = [1e-6, 2e-6, 3e-6, 4e-6]
rng = np.random.default_rng(0)
y = np.stack([2*np.exp(-x/t) + 0.01*rng.standard_normal(len(x)) for t in taus], 1)
w.set_data('source', KzData(y=y, ax=Struct(x=x, y=np.arange(4.), xlabel='time, s'), dsc=Struct(), title='decays'))
info = [i for i in w.plugin_infos if i.name == 'FITPLUGIN3'][0]
w.launch_plugin(info); p = w.plugins[-1]; app.processEvents()
w.set('slice', 2); p.fit_once(); print('single slice 2:', p.fits[0]['script'], [d.title for d in w.out], [d.y.shape for d in w.out])
p.mFitAll.trigger(); print('fit all items', p.ddSliceSelector.count(), 'sel', p.ddSliceSelector.currentIndex())
p.fit_all(); print('all:', [f['script'][2] for f in p.fits])
p.ddSliceSelector.setCurrentIndex(1); print('viewer slice ->', w.get('slice'))
w.set('slice', 3); print('selector <-', p.ddSliceSelector.currentIndex())
# range: drop the first 2 us
w.ginput = lambda n: np.array([[-1e-6, 0], [2e-6, 0]]); p.range_changed('remove'); print('ignored pts', (~p.area_fit).sum(), [d.title for d in w.out])
p.fit_once(); print('ranged slice 4', p.fits[3]['script'])
# editing: change t of current set
p.lScript.setCurrentRow(2); print('mode', p.editor_mode, p.eNumValue.value()); p.eNumValue.setValue(5e-6); print('edited', p.fits[3]['script'])
p.lScript.setCurrentRow(0); p.eStringValue.setText('a*exp(-x/t) + c'); p.eStringValue.setModified(True); p._on_string_edited(); print('fn edited', p.fits[3]['script'])
p.fit_once(); print('with c', p.fits[3]['script'])
p.select_function([s for s in __import__('plugins.fitplugin3', fromlist=['x']).FUNCTIONS['Polynomial'][2][1]] if False else ['f = polyfit(x,y,n)','n = 2']); p.fit_once(); print('poly', p.fits[3]['script'])
print(evaluate_script(p.fits[3]['script'], x[:3]), w.out[1].y.shape)
app.processEvents(); w.grab().save(str(S/'fit_viewer.png')); p.grab().save(str(S/'fit_plugin.png'))
p.close(); w.close(); print('OK')
