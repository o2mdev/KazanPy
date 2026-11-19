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
* **1D / Stack / Contour / Density** - 2D data as the current slice, a stack of traces,
  a contour or a density map. The slider selects the slice.
* Toolbar: **Measure** (cross: read off coordinates), **Zoom**, zoom/expand X and Y.
* *View* menu: font, view area, zoom, grid and minor grid, aspect ratio.

Toggle buttons that are "on" are shown in kazan3's orange.

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

*File > Save Source* (with or without processing), *Convert Folder to ASCII* (`.dat` /
`.txt`).

## Plugins

The *Plugins* menu lists every plugin in the `plugins` folder. Each plugin opens in its
own window and works on the current source; most of them update when you load another
file. *Plugins > Reload plugins* picks up changed plugin files, *Arrange plugins* tiles
the windows, and plugins can be added to the menu's favourites. See [plugins.md](plugins.md).

## Settings

Settings are stored in `%USERPROFILE%\.kazanpy\kazan3.ini`. It has the same format as the
MATLAB `kazan3.ini` but is a separate file. `[KazanViewer] plugin_path` overrides the
plugin folder (default `plugins\`).
