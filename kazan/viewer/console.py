"""The workspace: a Python namespace and console that stand in for the MATLAB base
workspace and command window (*File > Export Src to Workspace* and friends).

The console is a pyqtgraph :class:`~pyqtgraph.console.ConsoleWidget` in its own window
(multi-line input, command history kept between sessions, exception viewer). It runs in
the viewer's process and GUI thread: it works on the live viewer, and a long
computation blocks the viewer until it finishes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QMainWindow
from pyqtgraph.console import ConsoleWidget

from ..core.data import KzData, Struct, verify

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


def _viewer():
    v = WORKSPACE.get('viewer')
    if v is None:
        raise RuntimeError('no viewer: open the console from a Kazan window')
    return v


def _show(*data):
    items = list(data[0]) if len(data) == 1 and isinstance(data[0], (list, tuple)) else list(data)
    _viewer().set_data('output', items)


# helpers on the viewer the console was last opened from (WORKSPACE['viewer'])
WORKSPACE.update({
    'src': lambda: _viewer().get_data('source'),
    'psrc': lambda: _viewer().get_data('psource'),
    'out': lambda: _viewer().get_data('output'),
    'show': _show,
    'plugins': lambda: list(_viewer().plugins),
    'active': lambda: _viewer().active_plugin,
    'KzData': KzData, 'Struct': Struct, 'verify': verify,
})

INTRO = """Kazan workspace (Python). Names:
  viewer         the Kazan window (plugin host API: get_data, set_data, get, set, ...)
  src() psrc()   copies of the source / processed source
  out()          copies of the output traces;  show(d, ...)  put KzData into the output
  plugins()      open plugin windows;  active()  the plugin that gets file_update
  exp_src exp_out  data from File > Export Src / Out to Workspace
  np KzData Struct verify
Example:  d = src(); d.y = d.y ** 2; show(d)
"""


class WorkspaceConsole(QMainWindow):
    """Python console on :data:`WORKSPACE`, one window shared by all viewers."""

    _instance: WorkspaceConsole | None = None

    @classmethod
    def instance(cls, history_file: Path | None = None) -> WorkspaceConsole:
        """The console window; ``history_file`` is used when it is first made."""
        if cls._instance is None:
            cls._instance = cls(history_file)
        return cls._instance

    def __init__(self, history_file: Path | None = None):
        super().__init__()
        self.setWindowTitle('Kazan Workspace')
        self.resize(720, 460)
        self.console = ConsoleWidget(namespace=WORKSPACE, text=INTRO,
                                     historyFile=str(history_file) if history_file else None)
        self.setCentralWidget(self.console)
        #: the output pane (QPlainTextEdit)
        self.out = self.console.output

    def write(self, text: str):
        """Print a message in the console."""
        # not repl.write: in pyqtgraph 0.14 it fails before the first command
        self.out.moveCursor(self.out.textCursor().MoveOperation.End)
        self.out.insertPlainText(text)
        self.out.ensureCursorVisible()

    def run(self, line: str):
        """Run a line as if typed (multi-line blocks: one line per call)."""
        self.console.repl.handleCommand(line)
