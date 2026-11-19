r"""CWMH3 rework: source layouts (Auto / Harmonics / Pairs / Blocks / source columns),
phase fit, MH reconstruction, joint fit, power saturation; real 10- and 20-harmonic files
(C:\Temp\Jens\pTAM_pH-6p6_Power_Test, C:\Temp\Jens\Three-pH-HOPE71-CWMH-Test)."""
import sys
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QApplication

S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.math import multiharmonic as mh
from kazan.viewer import KazanViewer

w = KazanViewer(ini=KazanIni(S / 'mh.ini')); w.show(); app.processEvents()
info = [i for i in w.plugin_infos if i.name == 'CWMH3'][0]

# ---- synthetic: Lorentzian HWHM 50 mG, Bm 0.2 G, 10 harmonics, 6 G sweep
N, A, BM, W, HS = 2048, 6.0, 0.2, 0.05, list(range(1, 11))
B = -A / 2 + (np.arange(N) + 0.5) * A / N
s_true, H = mh.simulate(B, BM, HS, b0=0.3, w=W, amp=1e-3, sigma=2e-6, seed=1)
ph = 40.0 + 25.0 * (np.arange(1, 11) - 1)                       # phase of harmonic h
HC = H * np.exp(1j * np.radians(ph))[:, None]                    # I + jQ as recorded
dsc = Struct(LIN_ScanAmplitude='6 G', LIN_ModAmplitude=f'{BM * 1e3:g} mG', LIN_LinMode='CH1-IQ5')


def source(raw, names=None):
    ax = Struct(x=np.arange(N) * 1e-3, xlabel='Time, s', raw=raw)
    if names is not None:
        ax.raw_names = names
    w.set_data('source', KzData(y=raw[:, :, 0], ax=ax, dsc=dsc, filename='synthetic'))
    w._on_src_out(1)


def launch():
    w.launch_plugin(info); app.processEvents()
    return w.plugins[-1]


pairs = np.stack([x for h in HC for x in (h.real, h.imag)], axis=1)[:, None, :]
names = [f'{c}: C1_H{h}{iq}' for c, (h, iq) in zip('abcdefghijklmnopqrst',
                                                   [(h, iq) for h in HS for iq in 'IQ'])]
source(pairs, names)
p = launch()
print('auto info:', p.lInfo.text().splitlines()[0])
assert p.has_q and p.hs == HS
p.fit_phase(); print('phase fit (axis):', p.PhaseSpinner.value(), p.SlopeSpinner.value())
assert abs((p.PhaseSpinner.value() - 40 + 90) % 180 - 90) < 2 and abs(p.SlopeSpinner.value() - 25) < 1
p.ddPhaseFit.setCurrentIndex(1); p.fit_phase(); print('phase fit (min imag):', p.PhaseSpinner.value(), p.SlopeSpinner.value())
assert abs((p.PhaseSpinner.value() - 40 + 90) % 180 - 90) < 3 and abs(p.SlopeSpinner.value() - 25) < 2
p.ddPhaseFit.setCurrentIndex(0); p.fit_phase()

p.DropDown2.setCurrentText('MH reconstruction'); p.sbBmOut.setValue(0.05)
p.ddShow.setCurrentIndex(0); p.calculate()
S_rec = np.ravel(w.out[0].y.real)
corr = np.corrcoef(S_rec, s_true - s_true.mean())[0, 1]
print('reconstruction: absorption corr', round(corr, 4), '| peak at', round(float(B[np.argmax(S_rec)]), 3),
      '| x label', w.out[0].ax.xlabel)
assert corr > 0.99 and abs(B[np.argmax(S_rec)] - 0.3) < 0.01
print(p.Reports.toPlainText().splitlines()[0])
p.DropDown2.setCurrentText('MH joint fit'); p.sbBm.setValue(0.15); w._message = ''; p.calculate(); print('message:', w._message)
print('joint fit:', p.Reports.toPlainText().splitlines()[:3])
r = mh.fit_harmonics(H, B, HS, 0.15, gauss=False)
assert abs(r['Bm'] / BM - 1) < 0.01 and abs(r['gamma'] / W - 1) < 0.03

# blocks and I-only layouts give the same harmonics
blocks = np.concatenate([HC.real.T, HC.imag.T], axis=1)[:, None, :]
source(blocks)
p.SourceDropDown.setCurrentIndex(3); p._read_source()
print('blocks:', p.lInfo.text().splitlines()[0]); assert np.allclose(p.hh[:, :, 0], HC)
source(blocks)
p.SourceDropDown.setCurrentIndex(0); p._read_source()
print('auto without names:', p.lInfo.text().splitlines()[0]); assert np.allclose(p.hh[:, :, 0], HC)
source(H.T[:, None, :])
p.SourceDropDown.setCurrentIndex(1); p._read_source(); p.btnUsePhase.setChecked(False)
p.DropDown2.setCurrentText('MH reconstruction'); p.calculate()
print('I-only:', p.lInfo.text().splitlines()[0], '| fit phase enabled', p.btnFitPhase.isEnabled())
assert not p.has_q and np.corrcoef(np.ravel(w.out[0].y.real), s_true)[0, 1] > 0.99

# other files: harmonics as source columns (no ax.raw), field axis in G
w.set_data('source', KzData(y=H.T, ax=Struct(x=B + 3350, xlabel='Magnetic Field, G'), filename='cols'))
w._on_src_out(1); p._read_source(); p.calculate()
print('source columns:', p.lInfo.text().splitlines()[0], '| out x', round(float(w.out[0].ax.x[0]), 2))
assert p.hh.shape == (10, N, 1) and abs(w.out[0].ax.x[0] - (B[0] + 3350)) < 1e-6

# power saturation: slices at attenuations 30..0 dB
att = np.arange(30, -1, -3.0)
pw = 10 ** ((20 - att - 30) / 10)
amp = np.sqrt(pw) / (1 + pw / 0.02) ** 0.75
raw = (H[0][:, None] * amp[None, :])[:, :, None]
w.set_data('source', KzData(y=raw[:, :, 0], ax=Struct(x=B, xlabel='Field, G', y=att, raw=raw), filename='sat'))
w._on_src_out(1); p.SourceDropDown.setCurrentIndex(1); p._read_source()
p.DropDown2.setCurrentText('Power saturation'); p.calculate()
print('power saturation:', p.Reports.toPlainText().replace('\n', ' | '))
assert 'Ps=20.0mW' in p.Reports.toPlainText()
p.close(); app.processEvents()

# ---- real files
for f, sub in ((r'C:\Temp\Jens\pTAM_pH-6p6_Power_Test\13264_CWFD.tdms', 'CH1:I10, 10 harmonics'),
               (r'C:\Temp\Jens\Three-pH-HOPE71-CWMH-Test\13875_CWFDfile.tdms', 'RS, 20 harmonics')):
    w.ddExt.setCurrentText('*.tdms'); w.ddDataType.setCurrentText('SpecMan'); w.ddLoadOption1.setCurrentIndex(0)
    w.load_file(f); app.processEvents()
    p = launch()
    print(f'{sub}:', p.lInfo.text().replace('\n', ' | '))
    p.DropDown2.setCurrentText('MH reconstruction'); p.sbBmOut.setValue(0.05); p.calculate()
    print('   ', p.Reports.toPlainText().splitlines()[0])
    assert w.out and np.all(np.isfinite(w.out[0].y))
    p.DropDown2.setCurrentText('MH joint fit'); p.calculate()
    print('   ', ' / '.join(p.Reports.toPlainText().splitlines()[:3]))
    p.DropDown2.setCurrentText('MH reconstruction'); p.ddShow.setCurrentIndex(2); p.calculate()
    w.grab().save(str(S / f"mh_{sub.split(',')[0].replace(':', '')}.png"))
    p.grab().save(str(S / f"mh_plugin_{sub.split(',')[0].replace(':', '')}.png"))
    p.close(); app.processEvents()
w.close(); print('OK')
