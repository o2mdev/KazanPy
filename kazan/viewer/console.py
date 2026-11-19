"""The workspace: a Python namespace and console that stand in for the MATLAB base
workspace and command window (*File > Export Src to Workspace* and friends).
"""
from __future__ import annotations

import code
import contextlib
import io
import sys

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QMainWindow, QPlainTextEdit, QVBoxLayout, QWidget

#: the "base workspace" shared by all viewers and the console
WORKSPACE: dict = {'np': np}


def assign(name: str, value):
    """MATLAB ``assignin('base', name, value)``; also into ``__main__`` when Python runs
    interactively (``python -i``)."""
    WORKSPACE[name] = value
    main = sys.modules.get('__main__')
    if main is not None and (hasattr(sys, 'ps1') or sys.flags.interactive):
        setattr(main, name, value)


def lookup(name: str):
    """MATLAB ``evalin('base', name)``; None when the variable does not exist."""
    if name in WORKSPACE:
        return WORKSPACE[name]
    return getattr(sys.modules.get('__main__'), name, None)


class _Input(QLineEdit):
    """Command line with Up / Down history."""

    def __init__(self, run):
        super().__init__()
        self._run, self._history, self._pos = run, [], 0
        self.returnPressed.connect(self._enter)

    def _enter(self):
        text = self.text()
        if text.strip():
            self._history.append(text)
        self._pos = len(self._history)
        self.clear()
        self._run(text)

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self._history:
            self._pos = max(0, min(len(self._history), self._pos + (-1 if e.key() == Qt.Key.Key_Up else 1)))
            self.setText(self._history[self._pos] if self._pos < len(self._history) else '')
            return
        super().keyPressEvent(e)


class WorkspaceConsole(QMainWindow):
    """A small Python console on :data:`WORKSPACE`."""

    _instance: WorkspaceConsole | None = None

    @classmethod
    def instance(cls) -> WorkspaceConsole:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Kazan Workspace')
        self.resize(640, 400)
        w = QWidget()
        v = QVBoxLayout(w)
        self.out = QPlainTextEdit(readOnly=True)
        self.out.setFont(QFont('Consolas'))
        self.inp = _Input(self.run)
        self.inp.setFont(QFont('Consolas'))
        v.addWidget(self.out, 1)
        v.addWidget(self.inp)
        self.setCentralWidget(w)
        self._console = code.InteractiveConsole(WORKSPACE)
        self.write('Python workspace. exp_src / exp_out hold exported data; '
                   'viewer is the Kazan window.\n')

    def write(self, text: str):
        self.out.moveCursor(self.out.textCursor().MoveOperation.End)
        self.out.insertPlainText(text)
        self.out.ensureCursorVisible()

    def run(self, line: str):
        prompt = '... ' if getattr(self, '_more', False) else '>>> '
        self.write(prompt + line + '\n')
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            self._more = self._console.push(line)
        self.write(buf.getvalue())
