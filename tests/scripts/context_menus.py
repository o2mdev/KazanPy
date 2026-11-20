"""Results box (Clear) and file list (Reload Data / Folder, Convert, Select Source)
context menus."""
import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core import KzData, Struct
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer


def run(menu, text):
    """The menu's item texts; triggers the item ``text``."""
    items = [a for a in menu.actions() if a.text()]
    for a in items:
        if a.text() == text:
            a.toggle() if a.isCheckable() else a.trigger()
    return [a.text() for a in items]


w = KazanViewer(ini=KazanIni(S / 'cm.ini')); w.show(); app.processEvents()
d = S / 'files'; d.mkdir(exist_ok=True)
x = np.linspace(0, 1, 20)
for k in range(2):
    np.savetxt(d / f'f{k}.dat', np.c_[x, x * (k + 1)])
w.ddExt.setCurrentText('*.dat'); w.ddDataType.setCurrentText('ASCII'); w.load_directory(str(d))
w.set('log', 'hello results')
items = run(w._build_results_menu(), 'Clear')
print('results menu', items, '| text after Clear:', repr(w.TextArea.toPlainText()))
assert 'Clear' in items and w.TextArea.toPlainText() == ''
names = [e[0] for e in w._dir_entries]; w.lbDirlist.setCurrentRow(names.index('f1.dat')); app.processEvents()
w.set_data('output', KzData(y=x[:, None], ax=Struct(x=x), title='o'))
print('output shown', w.view.data_src_out)
items = run(w._build_dirlist_menu(), 'Reload Data')
print('file menu', items, '| after Reload Data shows', 'Source' if w.view.data_src_out == 1 else 'Output', w.src.y.max())
assert items == ['Reload Data', 'Reload Folder', 'Convert', 'Select Source', 'Copy Full Path'] and w.view.data_src_out == 1
run(w._build_dirlist_menu(), 'Copy Full Path'); clip = QApplication.clipboard().text(); print('copied', clip)
assert Path(clip).is_absolute() and Path(clip).name == 'f1.dat' and Path(clip).exists()
run(w._build_dirlist_menu(), 'Select Source'); print('select source', w._select_source)
w.set_data('output', KzData(y=x[:, None], ax=Struct(x=x), title='o'))
w.lbDirlist.setCurrentRow(names.index('f0.dat')); app.processEvents()
print('select source off: still shows', 'Source' if w.view.data_src_out == 1 else 'Output')
assert not w._select_source and w.view.data_src_out == 2
w.close(); print('OK')
