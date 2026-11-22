"""file_update (MATLAB FileUpdate) goes to the active plugin only."""
import sys
from pathlib import Path

import numpy as np

S = Path(sys.argv[1])
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer

w = KazanViewer(ini=KazanIni(S / 'test.ini')); w.show(); app.processEvents()
infos = {i.name: i for i in w.plugin_infos}
calls = []


def launch(tag, name='SYMMETRIZE'):
    w.launch_plugin(infos[name]); app.processEvents()
    p = w.plugins[-1]
    p.file_update = lambda t=tag: calls.append(t)
    return p


def load():
    x = np.linspace(0, 1, 11)
    w.set_data('source', KzData(y=x[:, None], ax=Struct(x=x), dsc=Struct()))


a = launch('a'); b = launch('b')
assert w.active_plugin is b, 'new plugin must start active'
calls.clear(); load(); assert calls == ['b'], calls

QApplication.sendEvent(a, QEvent(QEvent.Type.WindowActivate))   # user clicks plugin a
assert w.active_plugin is a
calls.clear(); load(); assert calls == ['a'], calls

a.close(); app.processEvents()
assert w.active_plugin is b, 'closing the active plugin falls back to the previous one'
calls.clear(); load(); assert calls == ['b'], calls

# a source set from inside file_update does not re-enter it
b.file_update = lambda: (calls.append('b'), load())
calls.clear(); load(); assert calls == ['b'], calls

# a failing file_update does not break loading
b.file_update = lambda: 1 / 0
load(); assert w.src.y.shape == (11, 1)
b.file_update = lambda: calls.append('b')

# --- Update checkboxes: checking one makes that plugin active and clears the others
n = launch('n', 'NOISE3')                  # its Update box starts unchecked
assert not n.cbFileUpdate.isChecked() and w.active_plugin is b, 'unchecked box: stays out'
t = launch('t', 'TRANSIENT3')              # its Update box starts checked
assert t.cbFileUpdate.isChecked() and w.active_plugin is t
calls.clear(); load(); assert calls == ['t'], calls

n.cbFileUpdate.setChecked(True)
assert w.active_plugin is n and not t.cbFileUpdate.isChecked(), 'others are cleared'
QApplication.sendEvent(b, QEvent(QEvent.Type.WindowActivate))
assert w.active_plugin is n, 'a checked Update box is not taken over by window clicks'
calls.clear(); load(); assert calls == ['n'], calls

n.cbFileUpdate.setChecked(False)
assert w.active_plugin is b, 'no box checked: back to the last activated plain plugin'
t.cbFileUpdate.setChecked(True); t.close(); app.processEvents()
assert w.active_plugin is b

for p in list(w.plugins):
    p.close()
app.processEvents()
assert w.active_plugin is None
load()
w.close(); print('OK')
