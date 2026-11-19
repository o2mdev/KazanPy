import sys
from pathlib import Path
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
v = KazanViewer(ini=KazanIni(S/'mb.ini')); v.show(); app.processEvents()
v.ddExt.setCurrentText('*.dsc'); v.ddDataType.setCurrentText('XEPR')
v.load_file(r'C:\Temp\Jens\110122\x122091301.DSC'); app.processEvents()
full = [round(x, 9) for x in v.plot.view_area()]
v.plot.scale(0.3, 0.3); app.processEvents(); print('zoomed', [round(x, 9) for x in v.plot.view_area()])
c = v.plot.real.getViewBox().sceneBoundingRect().center()
pos = v.plot.mapFromScene(c)
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QMouseEvent
pf = QPointF(pos.x(), pos.y()); vp = v.plot.viewport(); gp = QPointF(vp.mapToGlobal(pos))
L, N = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
for t, b, bs in ((QEvent.Type.MouseButtonPress, L, L), (QEvent.Type.MouseButtonRelease, L, N),
                 (QEvent.Type.MouseButtonDblClick, L, L), (QEvent.Type.MouseButtonRelease, L, N)):
    QApplication.sendEvent(vp, QMouseEvent(t, pf, gp, b, bs, Qt.KeyboardModifier.NoModifier))
app.processEvents(); print('double-click', [round(x, 9) for x in v.plot.view_area()] == full)
v.plot.scale(0.3, 0.3); v._set_range('manual'); v.full_scale(); app.processEvents()
print('manual -> full scale', [round(x, 9) for x in v.plot.view_area()] == full, v.view.range)
v.close(); print('OK')
