# The viewer

Start with `kazan3.bat` (or `.venv\Scripts\python -m kazan`).

## Browsing and loading

The left panel is a directory browser. Pick the file extension and the data type (loader)
in the two lists above it, then click a file to load it. **Up** goes to the parent folder.
*File > Open Directory* opens another folder. *File > Favorite Directories* keeps a list
of folders (*Add Current* / *Remove Current* / *Remove All*).

Some data types have options (delimiter and column layout for ASCII, axis types for
RMN 2D, ...), shown under the file list. Supported formats and their options are listed
in [loaders.md](loaders.md).

## Source and Output

The viewer holds two data sets:

* **Source** - the loaded file. Plugins read it.
* **Output** - what plugins produce (one or more traces, each with its own colour, line
  style and marker).

The **Source** / **Output** buttons switch which one is shown. A plugin that writes
results switches the view to Output. **<<** transfers an output trace back to the source,
so you can chain processing steps.

## Plot

* **Real / Re/Im / Magn** - real part, real and imaginary parts on two axes, or magnitude.
* **1D / Stack / Contour / Density** - 2D data as one slice, a stack of traces, a
  contour or a density map.
* **2D data**: the vertical slider right of the plot selects the slice. The label under
  the plot shows the slice value and number. To step through slices, use the mouse
  wheel over the plot (when Zoom and Measure are off), *View > Next Slice* (Ctrl+U or
  Ctrl+Right) or *Previous Slice* (Ctrl+D or Ctrl+Left). The **X / Y** button under
  the slider switches the direction: *X* shows traces along the first axis (one per
  column), *Y* traces along the second axis (one per row). *Tools > Cut Slice* keeps
  the current slice as the new source.
* Toolbar: **Measure** (cross: read off coordinates), **Zoom**, zoom/expand X and Y.
* **Full scale**: double-click the plot, or *View > Full Scale* (Ctrl+A).
* *View* menu:
  * **Font** - Default or -4 ... +4 points. All controls, menus and plugin windows follow,
    and button and panel sizes grow with the font. The choice is kept in the ini file.
  * **Axis Tight / Auto / Manual** - how the range is set when data are plotted.
    *Select View Area* takes typed limits (`xmin xmax ymin ymax`) and switches to
    Manual.
  * **Show Grid**, **Show Minor Grid** (minor lines along X, as in Kazan3).
  * **Aspect Normal**, **Aspect Square** (square plot boxes), **Axis Equal** (equal
    units on both axes).

Toggle buttons that are "on" are shown in kazan3's orange.

## Window menu

These draw the current view in separate figures with matplotlib (`pip install matplotlib`).
Figures have a toolbar to zoom and to save images (PNG, PDF, SVG, ...).

* **New Window** - another viewer.
* **Show in Window** - the current plot in a new figure.
* **Plot 1D**:
  * *Open figure* - a new figure; Re/Im mode gives two axes.
  * *Empty figure*.
  * *Axis k / [r,c]* - the plot goes into subplot *k* of an *r* x *c* grid of the current
    figure (the last one used), so plots can be put side by side.
* **Plot 2D** - the 2D source as a 3D view: *Surf*, *Scatter3* (points), *Surface* (one
  coloured line per slice).

## Parameters

The parameter row under the plot shows one parameter at a time: pick it in the list,
type a value, press Enter or **=**.

* **View parameters** are kept from file to file, and follow a file that has them:
  * `xlabel`, `ylabel`
  * `Color`, `LineStyle`, `LineWidth`, `Marker`
  * `dx` - X axis correction
  * `s` - Y shift
  * `ps_mod` - pseudo-modulation amplitude, points
  * `tc` - filter time constant, points
  * `contour` - contour levels as fractions of the maximum, e.g. `.2:.1:.6`
  * `yslicelabel`
* **Data parameters** are read from each file: title, sample, comment, formula, `freq1`
  (EPR frequency), `reference`, `cf`, units.

**Locking**: right-click the parameter list or the value field and choose *Lock*. A
locked parameter keeps its value when another file is loaded. It is shown as `* name`
with a yellow value field. *Unlock all* releases all of them.

## Processing

The plot context menu (right-click) applies to the source, or to the first output trace
when Output is shown:

* **Derivative**:
  * *Normal*
  * *PS,mod* - pseudo-modulation: the first harmonic of a field modulation with
    peak-to-peak amplitude `ps_mod` points
  * *Integrate*
* **Filter** (time constant `tc`, points):
  * *Not Filtered*
  * *RC* - RC low-pass
  * *M.aver.* - moving average
  * *Sav.gol.* - Savitzky-Golay

  *Apply to* chooses the dimension: *Auto*, *First Dim*, *Second Dim* or *Both*.
* **Axis representation**:
  * *x-y* - both axes as they are.
  * *X* - as is, points, reverse, log, g-factor (from `freq1`), ppm of `reference`, or
    ppm - 1.
  * *Y* - as is, points, reverse, log.

  Log and reverse change how the plot axis is drawn. Points, g-factor and ppm change
  the axis values; the g-factor axis is drawn reversed, as in Kazan3.
* **Reload Data** loads the current file again.

*Tools > Fix Source Processing* makes the processing permanent. *Tools > Cut Slice*
takes the current slice as the new source. *Tools > Show Load Script* shows how the data
were loaded.

## Saving and export

* *File > Save Source* (with or without processing): pick the format in the file type
  list of the dialog. Each is read back by the matching data type:

  | Format | Files | Notes |
  |---|---|---|
  | ASCII (`.txt`, `.dat`) | one file | columns `x, real(y) [, imag(y)]` and a footer (`;--- created by Kazan Viewer 3.0 ---`) with the axis labels, the 2D axis, processing and data parameters |
  | SpecMan (`.d01`) | `.d01` + `.exp` | 1D or 2D, complex as a second stream |
  | Bruker new (`.dsc`) | `.DSC` + `.DTA` | 1D or 2D, big-endian double; a time axis in s is stored in ns |
  | Bruker old (`.par`) | `.par` + `.spc` | 1D only, WinEPR float format, field axis |
  | WinSIM (`.lmb`) | `.LMB` | 1D only |

  Differences from MATLAB: `.par` / `.spc` are no longer swapped and hold the real field
  axis and float data (MATLAB rounded to integers); `.dsc` keeps real data real; `.lmb`
  holds the data's own field, frequency and date instead of fixed example values.
* *Convert Folder to ASCII (dat / txt)* loads every file of the selected extension with
  the selected data type and writes `name.dat` / `name.txt` next to it. *Only missing*
  skips files already converted.
* *Export Src to Workspace* / *Export Out to Workspace* put the source (`exp_src`) or the
  output traces (`exp_out`, a list) into the workspace. *Load Src from Workspace* makes
  `exp_src` the source. In place of MATLAB's base workspace, the workspace is a Python
  namespace with its own console (*File > Workspace Console*). There `exp_src.y`,
  `exp_src.ax.x`, `np` and `viewer` are available.

## Plugins

The *Plugins* menu lists every plugin in the `plugins` folder. Each plugin opens in its
own window and works on the current source; most of them update when you load another
file. *Plugins > Reload plugins* picks up changed plugin files, *Arrange plugins* tiles
the windows, and plugins can be added to the menu's favourites. See [plugins.md](plugins.md).

## Help

*Help* has Kazan3's *How to Start*, *Data Load Routines*, *Axis Data Structure*,
*Plugins* and *How to Print* notes, adapted to KazanPy. *Documentation* opens this
folder.

## Settings

Settings are stored in `%USERPROFILE%\.kazanpy\kazan3.ini`. It has the same format as the
MATLAB `kazan3.ini` but is a separate file. `[KazanViewer] plugin_path` overrides the
plugin folder (default `plugins\`).
