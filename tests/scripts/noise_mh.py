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
rng = np.random.default_rng(1)
x = np.linspace(0, 1, 1000)
clean = 1e-3 * np.exp(-((x - 0.5) / 0.05) ** 2)          # 1 mV peak
noise = 10e-6 * rng.standard_normal(1000)                  # 10 uV
y = (clean + noise + 1j * 0.5 * clean)[:, None]
w.set_data('source', KzData(y=y, ax=Struct(x=x, xlabel='t, s'), dsc=Struct(), title='n'))
n = launch('NOISE3')
n.pbCalculate.click(); print(n.TextArea.toPlainText())
print('outputs', [(d.title, d.y.shape) for d in w.out])
# reference = clean signal -> noise is exactly the added noise
w.set_data('source', KzData(y=(clean + 1j * 0.5 * clean)[:, None], ax=Struct(x=x), dsc=Struct()))
n.set_reference()
w.set_data('source', KzData(y=y, ax=Struct(x=x), dsc=Struct())); n.pbCalculate.click()
print('with ref:', n.TextArea.toPlainText().replace('\n', ' || '))
n.clear_reference()
for i in range(n.ddFitOptions.count()):
    n.ddFitOptions.setCurrentIndex(i); n.pbCalculate.click(); print(' sig', n.ddFitOptions.currentText(), n.TextArea.toPlainText().splitlines()[0])
n.ddFitOptions.setCurrentIndex(0)
sine = (2e-3 * np.sin(2 * np.pi * 7 * x + 0.3))[:, None]
w.set_data('source', KzData(y=np.hstack([sine, sine]) + 10e-6 * rng.standard_normal((1000, 2)), ax=Struct(x=x), dsc=Struct()))
for i in range(n.ddNoiseOptions.count()):
    n.ddNoiseOptions.setCurrentIndex(i); n.pbCalculate.click(); print(' noise', n.ddNoiseOptions.currentText(), '|', n.TextArea.toPlainText().splitlines()[1][:40], '| msg', w.plot.real.titleLabel.text[:30])
n.ddNoiseOptions.setCurrentIndex(0); n.ddRangeOptions.setCurrentIndex(4); n.pbCalculate.click(); print('last20 noise pts', w.out[1].y.shape)
# real CW file with ax.data channels
w.ddExt.setCurrentText('*.d01'); w.ddDataType.setCurrentText('SpecMan'); w.load_directory(r'C:\Temp\BE\2025\02\250217')
names = [e[0] for e in w._dir_entries]; w.lbDirlist.setCurrentRow(names.index('2064file.d01')); app.processEvents()
n.ddRangeOptions.setCurrentIndex(0); n.pbCalculate.click(); print('real file:', n.TextArea.toPlainText().replace('\n', ' || '))
n.grab().save(str(S/'noise_plugin.png')); n.close(); app.processEvents()
# CWMH synthetic: 10 channels, harmonic k has phase 20 + 15*(k-1) deg
B = np.linspace(-5, 5, 1024); att = np.arange(0, 30, 3.0)
line = 1 / (1 + B ** 2)
raw = np.zeros((1024, len(att), 10))
P = 10 ** ((20 - att - 30) / 10)
amp = 1.0 * np.sqrt(P) / (1 + P / 0.02) ** 1.0
for k in range(5):
    ph = np.deg2rad(20 + 15 * k)
    sig = np.gradient(line, k + 1)[:, None] * amp[None, :] * np.exp(1j * ph) + 1e-6 * k
    raw[:, :, k], raw[:, :, k + 5] = sig.real, sig.imag
src = KzData(y=raw[:, :, 0], ax=Struct(x=B + 3350, xlabel='Field, G', y=att, ylabel='Att, dB', raw=raw), dsc=Struct())
w.set_data('source', src)
m = launch('CWMH3')
for mode in ('As Is', 'MH', 'Phases', 'Power saturation'):
    m.DropDown2.setCurrentText(mode); m.CalculateButton.click()
    print(mode, [(d.title, d.y.shape) for d in w.out], '| msg', w.plot.real.titleLabel.text[:40], '|', m.Reports.toPlainText().replace('\n', ' '))
m.DropDown2.setCurrentText('Phases'); m.btnUsePhase.setChecked(True)
print('lin phase', m.Reports.toPlainText(), 'max |imag|/|real|', round(float(np.abs(w.out[0].y.imag).max() / np.abs(w.out[0].y.real).max()), 4))
m.DropDown2.setCurrentText('As Is')
for s in ('I Channel 7', 'IQ all'):
    m.SourceDropDown.setCurrentText(s); print(s, [(d.title, d.y.shape) for d in w.out])
w.set_data('source', KzData(y=np.ones((10, 1)), ax=Struct(), dsc=Struct())); m.CalculateButton.click(); print('no raw msg:', w.plot.real.titleLabel.text)
m.grab().save(str(S/'cwmh_plugin.png')); m.close(); app.processEvents(); w.close(); print('OK')
