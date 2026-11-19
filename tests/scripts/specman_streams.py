r"""SpecMan files with more than two streams (10 harmonics, C:\Temp\Jens\pTAM...):
'Re + i Im' (MATLAB) and 'All streams (2D)'; ax.raw layout for CWMH3."""
import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core.ini import KazanIni
from kazan.io import loaders
from kazan.viewer import KazanViewer
F = r'C:\Temp\Jens\pTAM_pH-6p6_Power_Test\13264_CWFD.tdms'
ax, y, dsc = loaders.load(F, '*.tdms', 'SpecMan', ['complex'])
y = np.squeeze(np.asarray(y))
print('complex:', y.shape, y.dtype, ax.xlabel, '| raw', np.shape(ax.raw))
assert np.iscomplexobj(y) and ax.xlabel == 'Time, s' and np.shape(ax.raw) == (2048, 1, 10)
assert np.allclose(y.real, ax.raw[:, 0, 0]) and np.allclose(y.imag, ax.raw[:, 0, 1])
ax, y, dsc = loaders.load(F, '*.tdms', 'SpecMan', ['all'])
print('all:', np.shape(y), ax.ylabel, ax.streams[:3], '...')
assert np.shape(y) == (2048, 10) and not np.iscomplexobj(y) and ax.streams[2] == 'c: C1_H3I'
w = KazanViewer(ini=KazanIni(S / 'st.ini')); w.show(); app.processEvents()
w.ddExt.setCurrentText('*.tdms'); w.ddDataType.setCurrentText('SpecMan')
w.ddLoadOption1.setCurrentIndex(1)
print('option', w.ddLoadOption1.isVisible(), w.ddLoadOption1.currentText(), w.load_option_values())
w.load_file(F); app.processEvents()
w.set('slice', 2); app.processEvents()
print('viewer:', w.src.y.shape, 'slider', w.slice_col.isVisible(), '|', w.lSlice.text())
assert w.src.y.shape == (2048, 10) and w.slice_col.isVisible() and 'C1_H3I' in w.lSlice.text()
w.grab().save(str(S / 'streams.png'))
w.close(); print('OK')
