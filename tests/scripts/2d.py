import sys
from pathlib import Path
import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
v = KazanViewer(ini=KazanIni(S/'test_2d.ini')); v.show(); app.processEvents()
v.ddExt.setCurrentText('*.dsc'); v.ddDataType.setCurrentText('XEPR')
v.load_file(r'C:\Temp\Jens\110122\x122091301.DSC'); app.processEvents()
print('src', v.src.y.shape, v.src.ax.xlabel, '|', v.src.ax.ylabel)
print('slider visible', v.slice_col.isVisible(), 'geom', v.sl2Dplot.geometry().getRect(), 'range', v.sl2Dplot.maximum(), 'tick', v.sl2Dplot.tickInterval(), 'b2D', v.b2D.text())
print('label', v.lSlice.text())
v.sl2Dplot.setValue(50); app.processEvents(); print('slider->50: position', v.view.position, '|', v.lSlice.text())
ev = QWheelEvent(QPointF(300, 300), QPointF(300, 300), QPoint(0, 0), QPoint(0, -240), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
QApplication.sendEvent(v.plot.viewport(), ev); print('wheel -2 notches -> position', v.view.position, 'slider', v.sl2Dplot.value())
v.b2D.click(); app.processEvents()
d = v._datasets()[0][0]; t = v.get_slice(d, v.view.abscissa, v.view.position)
print('b2D ->', v.b2D.text(), 'range', v.sl2Dplot.maximum(), 'trace len', len(t.ax.x), 'xlabel', v.plot.real.getAxis('bottom').labelText, '|', v.lSlice.text())
v.sl2Dplot.setValue(1000); app.processEvents()
v._menu_cut_slice(); print('cut slice (Y) -> src', v.src.y.shape, v.src.ax.xlabel, 'slider visible', v.slice_col.isVisible(), 'b2D', v.b2D.text())
v.load_file(r'C:\Temp\Jens\110122\x122091301.DSC'); v.src.ax.filt = 'mvgaver'; v.src.ax.tc = 5
v._menu_fix_processing(); print('fix processing filt', repr(v.src.ax.filt), v.src.y.shape)
v.grab().save(str(S/'v2d.png')); v.close(); print('OK')
