"""Plugin contract between the Kazan viewer (host) and its plugins.

This is the Python counterpart of the MATLAB calls ``app.KazanViewer.GetData`` /
``SetData`` / ``Get`` / ``Set`` / ``Ginput`` / ``MakePlugins('close', app)`` and of
the plugin's ``FileUpdate`` method.

Rule: the host API passes only plain data (numpy arrays, :class:`KzData`, strings,
numbers) - never Qt objects. That keeps a later out-of-process (TCP) bridge possible
without changing any plugin.
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, Union

import numpy as np
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QMainWindow

if TYPE_CHECKING:
    from PySide6.QtCore import SignalInstance

    from .data import KzData

GetMode = Literal['source', 'psource', 'output']
SetMode = Literal['source', 'output']
GetKey = Literal['font', 'slice']
SetKey = Literal['font', 'slice', 'cursor', 'message', 'log', 'log_clear', 'log_all']


class KazanHost(Protocol):
    """Everything a plugin may use from the viewer."""

    #: emitted to everyone after a new source is loaded or set. ``file_update``
    #: (MATLAB FileUpdate) is not driven by it: the host calls that on the active
    #: plugin only.
    sourceChanged: SignalInstance
    #: emitted with the new 0-based slice index
    sliceChanged: SignalInstance

    def get_data(self, mode: GetMode) -> Union[KzData, list[KzData]]:
        """'source' raw data, 'psource' processed (filter/diff), 'output' list.

        Always returns copies.
        """

    def set_data(self, mode: SetMode, data: Union[KzData, list[KzData]]) -> None:
        """'output': show a list of data sets; 'source': replace the source."""

    def get(self, key: GetKey) -> Any:
        """'font' point size; 'slice' current 0-based slice (MATLAB was 1-based)."""

    def set(self, key: SetKey, value: Any = None) -> None:
        """'message' / 'cursor' plot title, 'log' / 'log_all' / 'log_clear' results
        box, 'slice' select slice, 'font' point size."""

    def ginput(self, n: int) -> np.ndarray:
        """Blocking pick of ``n`` points on the viewer plot; returns ``(k, 2)``,
        ``k < n`` if the user cancels with right-click or Esc."""

    def plugin_closed(self, plugin: KazanPlugin) -> None:
        """Called by the plugin when it closes (MATLAB ``MakePlugins('close', app)``)."""

    def plugin_activated(self, plugin: KazanPlugin) -> None:
        """Called by the plugin when its window is activated (see
        :class:`KazanPlugin` for who receives ``file_update``)."""

    def plugin_update(self, plugin: KazanPlugin, on: bool) -> None:
        """Called when the plugin's *Update* checkbox is toggled. Checked: the plugin
        becomes active and the other plugins' *Update* boxes are cleared."""


class KazanPlugin(QMainWindow):
    """Base class of all plugins (one window per running instance).

    Subclass, build the UI in ``__init__`` (after ``super().__init__``), override
    :meth:`file_update` if the plugin should react to a newly loaded file.
    Windows are independent top-level windows, as in MATLAB.

    Only the *active* plugin gets :meth:`file_update`, so open plugins do not all
    recompute and fight over the output:

    * a plugin with a checked *Update* checkbox (registered with
      :meth:`set_update_checkbox`) is active. Checking one clears all the others;
    * otherwise the active plugin is the most recently activated window among the
      plugins that have no *Update* checkbox (a new one starts active).
    """

    #: label in the Plugins menu; defaults to the file name in upper case
    menu_name: str = ''

    def __init__(self, host: KazanHost, guid: str):
        super().__init__()
        self.host = host
        self.guid = guid
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        #: the plugin's "Update when file changes" box, see set_update_checkbox
        self.update_checkbox = None
        if self.menu_name:
            self.setWindowTitle(self.menu_name)

    def set_update_checkbox(self, cb) -> None:
        """Register the plugin's *Update* checkbox. Checking it makes this plugin the
        active one and clears the box in every other plugin; the host keeps it in sync
        via :meth:`set_update`. Call it in ``__init__``; the box's initial state is
        honored when the plugin launches."""
        self.update_checkbox = cb
        cb.toggled.connect(lambda on: self.host.plugin_update(self, bool(on)))

    def set_update(self, on: bool) -> None:
        """Host side: show whether this plugin follows new files (no signal)."""
        cb = self.update_checkbox
        if cb is not None and cb.isChecked() != on:
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)

    def file_update(self) -> None:
        """Called on the active plugin when a new source is loaded (MATLAB
        ``FileUpdate``)."""

    def event(self, e):
        if e.type() == QEvent.Type.WindowActivate:
            self.host.plugin_activated(self)
        return super().event(e)

    def closeEvent(self, event):
        self.host.plugin_closed(self)
        super().closeEvent(event)


@dataclass
class PluginInfo:
    name: str            # MATLAB-style key, also the ini section name (e.g. 'SYMMETRIZE')
    label: str           # menu label
    cls: type
    path: Path


def discover_plugins(folder: Path) -> tuple[list[PluginInfo], list[str]]:
    """Import every ``*.py`` in ``folder`` and collect :class:`KazanPlugin` subclasses.

    A plugin that fails to import is reported in the error list and skipped, so it
    cannot take the viewer down. Calling this again re-imports the files (reload).
    """
    found: list[PluginInfo] = []
    errors: list[str] = []
    folder = Path(folder)
    if not folder.is_dir():
        return found, [f'Plugin folder not found: {folder}']

    for f in sorted(folder.glob('*.py'), key=lambda p: p.name.lower()):
        if f.name.startswith('_'):
            continue
        mod_name = f'kazan_plugins.{f.stem}'
        try:
            spec = importlib.util.spec_from_file_location(mod_name, f)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(mod_name, None)
            errors.append(f'{f.name}: {traceback.format_exc(limit=3)}')
            continue
        classes = [c for c in vars(module).values()
                   if isinstance(c, type) and issubclass(c, KazanPlugin)
                   and c is not KazanPlugin and c.__module__ == mod_name]
        for c in classes:
            name = (c.__name__ if len(classes) > 1 else f.stem).upper()
            found.append(PluginInfo(name=name, label=c.menu_name or name, cls=c, path=f))
    return found, errors
