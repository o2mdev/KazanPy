# KazanPy

KazanPy is a Python port of **Kazan3**, the MATLAB GUI for EPR data processing, with its
plugins. Goal: stay close to the original in controls and appearance.

Kazan3 is the successor of the first version, Kazan Viewer:

> Kazan Viewer is a MATLAB GUI for data processing written by Boris Epel and Alexey
> Silakov. KV is a stand-alone interface but can exchange data with the Matlab shell and
> number of plug-ins that enhance its basic capabilities. KV is an open-source freeware.
> We just ask to leave our credits and comments in the text and inform us about useful
> additions.

The same applies to KazanPy.

### Related projects

| Project | Language | Repository |
|---|---|---|
| Kazan Viewer (KV), the first version | MATLAB | [o2mdev/kazan](https://github.com/o2mdev/kazan) |
| Kazan Viewer, Silakov lab version | MATLAB | [AlexeySilakov/KazanViewer](https://github.com/AlexeySilakov/KazanViewer) ([Silakov lab software page](https://sites.psu.edu/silakovlab/software)) |
| Kazan3, the MATLAB App Designer version this port follows | MATLAB | [o2mdev/kazan3](https://github.com/o2mdev/kazan3) |
| KazanPy, this port | Python | [o2mdev/KazanPy](https://github.com/o2mdev/KazanPy) |

## Run

```
kazan3.bat
```

or `.venv\Scripts\python -m kazan`.

Setup from scratch: `py -3.12 -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`.

Settings are stored in `%USERPROFILE%\.kazanpy\kazan3.ini` (same format as the MATLAB
`kazan3.ini`, kept separate). `[KazanViewer] plugin_path` overrides the plugin folder
(default: `plugins\`).

## Tests

```
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest tests
```

Each script in `tests/scripts` drives the viewer or a plugin in its own process and
checks the results (fits recover known values, files load and save back, ...). Scripts
that need the sample data in `C:\Temp` are skipped when it is not there.

## Layout

| Path | MATLAB counterpart |
|---|---|
| `kazan/core/data.py` | `src` / `out{k}` struct, `Verify()` |
| `kazan/core/plugin.py` | plugin contract, `MakePlugins('search')` discovery |
| `kazan/core/processing.py` | `Process()` (filt / diff) |
| `kazan/core/ini.py` | `kv3_inimanage` |
| `kazan/io/loaders.py` | `kv3_ScriptLoad` and the `kv3_*read` loaders |
| `kazan/io/writers.py` | `kv3_asciiwrite`, `kv3_d01write`, `kv_brukerwrite`, `kv_LMBwrite` |
| `kazan/viewer/main_window.py` | `kazan3.mlapp` (also implements the host API) |
| `kazan/viewer/plot.py` | `haReal` / `haImag` axes, MATLAB-styled pyqtgraph |
| `kazan/math/` | `kv_autofit`, line shapes, `sinDecoBG` (rapid scan), `fminsearch` / `fminsearchbnd` |
| `plugins/*.py` | `*.mlapp` plugins |

## Documentation

See [Documentation](Documentation/README.md):

* [Viewer](Documentation/viewer.md)
* [Plugins](Documentation/plugins.md): usage, and differences from MATLAB
* [File formats](Documentation/loaders.md)
* [Writing a plugin](Documentation/plugin-api.md)
* [Port status](Documentation/status.md)
