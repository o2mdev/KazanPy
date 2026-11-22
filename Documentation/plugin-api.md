# Writing a plugin

Plugins run in the viewer's process. Drop a `.py` file in `plugins/`. Every
`KazanPlugin` subclass in it appears in the Plugins menu; *Plugins > Reload plugins*
picks up changes.

```python
from kazan.core import KazanPlugin

class MyPlugin(KazanPlugin):
    menu_name = 'MYPLUGIN'

    def __init__(self, host, guid):
        super().__init__(host, guid)
        ...                                  # build the UI

    def file_update(self):                   # MATLAB FileUpdate: new source loaded
        ...

    def compute(self):
        d = self.host.get_data('source')     # always a copy
        out = d.copy(); out.y = ...; out.ax.Color = 'r'; out.title = 'result'
        self.host.set_data('output', [out])
```

`plugins/symmetrize.py` is a small complete example.

## Host API

| MATLAB (`app.KazanViewer.`) | Python (`self.host.`) |
|---|---|
| `GetData('source' / 'psource' / 'output')` | `get_data(...)` - returns copies |
| `SetData('output', out)` / `SetData('source', s)` | `set_data('output', [..])` / `set_data('source', s)` |
| `Get('font' / 'slice')` | `get(...)` - **slice is 0-based** |
| `Set('message' / 'log' / 'slice' / 'cursor' / 'font', v)` | `set(...)` |
| `Ginput(n)` | `ginput(n)` - blocking, returns a `(k, 2)` array |
| `MakePlugins('close', app)` | automatic when the window closes |

`file_update` goes to the **active plugin only**. Other open plugins are not called,
so they do not all recompute and overwrite each other's output.

* A plugin with an *Update* checkbox registers it in `__init__` with
  `self.set_update_checkbox(cb)`. Checking that box makes the plugin active and clears
  the *Update* box in every other plugin. A box that starts checked makes the plugin
  active when it launches. Clicking the window of a plugin like this does not change
  which plugin is active.
* If no *Update* box is checked, the active plugin is the most recently activated
  window among the plugins without an *Update* box. A newly launched plugin of that
  kind starts active.

If `file_update` itself calls `set_data('source', ...)`, the host does not call
`file_update` again.

Signals: `host.sourceChanged` (a new source; emitted to everyone, connect to it only
if a background plugin really must see every file) and `host.sliceChanged(int)`.

## Data conventions

* `y` is 2-D `(n1, n2)`; a 1-D trace is `(n, 1)`.
* `ax.x` and `ax.y` are 1-D arrays.
* `ax` and `dsc` are open-ended `Struct`s: `d.ax.Color = 'r'` works, and missing fields
  read as `None`.
* Output traces can carry `ax.Color` (RGB 0..1 or a letter), `ax.LineStyle`,
  `ax.Marker`, `ax.s` (Y shift) and `ax.dx` / `ax.dy` (axis shifts applied when
  plotting).
* Python objects are shared, not copied: call `.copy()` before changing data you did
  not create.

Keep the host API to plain data (arrays, `KzData`, strings, numbers), so an
out-of-process (TCP) bridge can be added later without changing plugins.

Shared helpers: `kazan/math/` (EasySpin-convention line shapes, `kv_autofit`, rapid-scan
deconvolution) and `kazan/viewer/widgets.py` (`SciSpinBox`, a full-precision spinner).
