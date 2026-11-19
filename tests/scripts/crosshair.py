import sys
from pathlib import Path
import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
w = KazanViewer(ini=KazanIni(S/'cross.ini')); w.show(); app.processEvents()
x = np.linspace(3300, 3400, 501); y = -(x - 3350) / ((x - 3350) ** 2 + 25)
w.set_data('source', KzData(y=y[:, None], ax=Struct(x=x, xlabel='Magnetic Field, G', freq1=9.4e9), title='line'))
w.bSource.click(); app.processEvents()
vp = w.plot.viewport()
def at(fx, fy):
    vb = w.plot.real.getViewBox(); r = vb.sceneBoundingRect()
    sp = QPointF(r.left() + fx * r.width(), r.top() + fy * r.height())
    return w.plot.mapFromScene(sp)
def mouse(t, p, b=Qt.MouseButton.NoButton, bs=Qt.MouseButton.NoButton):
    QApplication.sendEvent(vp, QMouseEvent(t, QPointF(p), QPointF(vp.mapToGlobal(p)), b, bs, Qt.KeyboardModifier.NoModifier))
def click(p):
    L = Qt.MouseButton.LeftButton
    mouse(QEvent.Type.MouseButtonPress, p, L, L); mouse(QEvent.Type.MouseButtonRelease, p, L, Qt.MouseButton.NoButton)
state = {}
def during():
    mouse(QEvent.Type.MouseMove, at(0.3, 0.4)); app.processEvents()
    state['lines'] = (w.plot._vline.isVisible(), round(w.plot._vline.value(), 1), w.plot.real.titleLabel.text)
    click(at(0.3, 0.4)); app.processEvents()
    mouse(QEvent.Type.MouseMove, at(0.6, 0.7)); app.processEvents()
    w.grab().save(str(S/'cross_ginput.png'))
    click(at(0.6, 0.7))
QTimer.singleShot(200, during)
pts = w.ginput(2)
print('during ginput: vline visible, x, title', state['lines'])
print('picked', np.round(pts, 2).tolist(), '| crosshair after', w.plot._crosshair, w.plot._vline.scene() is None)
w.bMeasure.setChecked(True); mouse(QEvent.Type.MouseMove, at(0.5, 0.5)); app.processEvents()
print('measure: crosshair', w.plot._crosshair, w.plot._vline.isVisible(), '| title', w.plot.real.titleLabel.text)
click(at(0.25, 0.5)); click(at(0.75, 0.5)); app.processEvents()
print('measure log:', w.TextArea.toPlainText().splitlines()[:2])
w.plot_data(); print('after replot crosshair kept', w.plot._vline.scene() is not None)
w.bMeasure.setChecked(False); print('measure off', w.plot._crosshair, w.plot._vline.scene() is None)
w.close(); print('OK')
