# KazanPy

Python port of the MATLAB **Kazan3** EPR data viewer with plugins (`D:\epri\Kazan3`).
Goal: stay close to the original in controls and appearance.

## Run

```
.venv\Scripts\python -m kazan
```

Setup from scratch: `py -3.12 -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`.

Settings are stored in `%USERPROFILE%\.kazanpy\kazan3.ini` (same format as the MATLAB
`kazan3.ini`, kept separate). `[KazanViewer] plugin_path` overrides the plugin folder
(default: `plugins\`).

## Layout

| Path | MATLAB counterpart |
|---|---|
| `kazan/core/data.py` | `src` / `out{k}` struct, `Verify()` |
| `kazan/core/plugin.py` | plugin contract, `MakePlugins('search')` discovery |
| `kazan/core/processing.py` | `Process()` (filt / diff) |
| `kazan/core/ini.py` | `kv3_inimanage` |
| `kazan/io/loaders.py` | `kv3_ScriptLoad` and the `kv3_*read` loaders |
| `kazan/viewer/main_window.py` | `kazan3.mlapp` (also implements the host API) |
| `kazan/viewer/plot.py` | `haReal` / `haImag` axes, MATLAB-styled pyqtgraph |
| `plugins/*.py` | `*.mlapp` plugins |

## Writing a plugin

Plugins run in the viewer's process. Drop a `.py` file in `plugins/`; every
`KazanPlugin` subclass in it appears in the Plugins menu (Plugins > Reload plugins
picks up changes).

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

| MATLAB (`app.KazanViewer.`) | Python (`self.host.`) |
|---|---|
| `GetData('source' / 'psource' / 'output')` | `get_data(...)` - returns copies |
| `SetData('output', out)` / `SetData('source', s)` | `set_data('output', [..])` / `set_data('source', s)` |
| `Get('font' / 'slice')` | `get(...)` - **slice is 0-based** |
| `Set('message' / 'log' / 'slice' / 'cursor' / 'font', v)` | `set(...)` |
| `Ginput(n)` | `ginput(n)` - blocking, returns `(k, 2)` array |
| `MakePlugins('close', app)` | automatic when the window closes |

Data conventions: `y` is 2-D `(n1, n2)` (a 1-D trace is `(n, 1)`), `ax.x` / `ax.y`
are 1-D arrays, `ax` and `dsc` are open-ended `Struct`s (`d.ax.Color = 'r'` works;
missing fields read as `None`). Python objects are shared, not copied: call
`.copy()` before changing data you did not create.

Keep the host API to plain data (arrays, `KzData`, strings, numbers), so an
out-of-process (TCP) bridge can be added later without changing plugins.

## Port status

Done: main window layout, directory browser, Source/Output/transfer, Real/Re-Im/Magn,
1D/Stack/Contour/Density, slice slider, parameter row (data parameters), zoom/measure/axis
buttons, processing context menu (M.aver., Sav.gol., Integrate), font, grid, favorites
(plugins and directories), Symmetrize plugin.

Loaders: ASCII; SpecMan `.tdms` (`kazan/io/specman.py`, also reads interleaved TDMS);
SpecMan `.d01`/`.exp` with `.bip` sidecar; Bruker XEPR `.DSC`/`.DTA` and ESP/WinEPR
`.par`/`.spc` (`kazan/io/bruker.py`); common parameters (`kazan/io/params.py`).
Field names in `ax`/`dsc` match MATLAB because plugins read them (`ax.raw`, `ax.data`,
`dsc.RS_Frequency`, ...).

Deliberate differences from the MATLAB loaders: repeated TDMS scans average all columns
(MATLAB divided only the last); incomplete TDMS scans load with zeros plus a log message
(MATLAB failed); a `.d01` header whose declared size does not match is read as 1D; a
scan count of 0 leaves the data unscaled; `to`/`step` are not taken as units.

Not ported yet: RC filter, pseudo-modulation, loaders other than those above (ASCII2D,
RMN, NIST, SpecManFLD/RAW, ...), loader options, parameter locking, X/Y axis
representation menus, ESP pulse (JSS 32) axes, the other 12 plugins.
