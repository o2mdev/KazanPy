"""File > Workspace Console: pyqtgraph console in a separate window, on the live viewer."""
import sys
from pathlib import Path

import numpy as np

S = Path(sys.argv[1])
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer

w = KazanViewer(ini=KazanIni(S / 'test.ini')); w.show(); app.processEvents()
x = np.linspace(0, 1, 11)
w.set_data('source', KzData(y=x[:, None], ax=Struct(x=x), dsc=Struct(), title='lin'))

from kazan.viewer import console
act = [a for m in w.menuBar().actions() if m.text() == 'File'
       for a in m.menu().actions() if a.text() == 'Workspace Console'][0]
act.trigger(); app.processEvents()
c = console.WorkspaceConsole.instance()
assert c.isVisible() and c.isWindow() and c.parent() is None
act.trigger(); assert console.WorkspaceConsole.instance() is c, 'one console'

c.run("d = src(); d.y = d.y ** 2; d.title = 'sq'; show(d)")
assert len(w.out) == 1 and np.allclose(w.out[0].y[:, 0], x ** 2) and w.out[0].title == 'sq'
c.run("print('n_out', len(out()), active())")
text = c.out.toPlainText()
assert 'n_out 1 None' in text, text[-300:]
c.run("1/0")                                     # an error is shown, not raised
assert 'ZeroDivisionError' in c.out.toPlainText()
c.run('for k in range(2):'); c.run('    print("loop", k)'); c.run('')   # multi-line block
assert 'loop 1' in c.out.toPlainText()
c.run("viewer.set('message', 'from console')")
assert 'from console' in w.plot.real.titleLabel.text, w.plot.real.titleLabel.text
assert (S / 'kazan_console_history.pkl').exists(), 'history saved next to the ini'

w.close(); app.processEvents()
print('OK')
