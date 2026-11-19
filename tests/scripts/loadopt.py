import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
S = Path(sys.argv[1]); app = QApplication(sys.argv)
from kazan.core.ini import KazanIni
from kazan.viewer import KazanViewer
w = KazanViewer(ini=KazanIni(S/'test_opt.ini')); w.show(); app.processEvents()
w.ddExt.setCurrentText('*.dat'); w.ddDataType.setCurrentText('ASCII'); app.processEvents()
print('visible', w.eLoadOption.isVisible(), w.ddLoadOption1.isVisible(), w.ddLoadOption2.isVisible(),
      w.ddLoadOption1.currentText(), '|', w.ddLoadOption2.currentText(), '|', w.eLoadOption.text())
w.ddLoadOption1.setCurrentText('space'); w.ddLoadOption2.setCurrentText('rY, iY'); w.eLoadOption.setText('Field, G'); w.eLoadOption.editingFinished.emit()
print('values', w.load_option_values())
w.load_file(r'C:\Temp\Jens\031208\e3120801.dat'); print('loaded', w.src.y.shape, w.src.y.dtype, w.src.script[-60:])
w.ddDataType.setCurrentText('XEPR'); print('XEPR opts visible', w.eLoadOption.isVisible(), w.ddLoadOption1.isVisible())
w.ddDataType.setCurrentText('ASCII'); print('restored', w.ddLoadOption1.currentText(), '|', w.ddLoadOption2.currentText(), '|', w.eLoadOption.text())
w.ddExt.setCurrentText('*.rmn'); w.ddDataType.setCurrentText('RMN_2D'); print('RMN_2D', w.ddLoadOption1.currentText(), w.ddLoadOption2.isVisible(), w.load_option_values())
w.ddExt.setCurrentText('*.jpg'); w.load_directory('C:/Temp'); names = [e[0] for e in w._dir_entries]
w.lbDirlist.setCurrentRow(names.index('2026-05-20_103310.jpg')); app.processEvents(); print('image', w.src.y.shape, w.src.ax.xlabel)
w.grab().save(str(S/'viewer_opts.png')); w.close(); print('OK')
