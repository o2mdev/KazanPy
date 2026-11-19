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

The parameter row under the plot shows data parameters. **=** sets the selected value.

## Processing

The processing context menu on the plot applies to the source as you view it (the
"processed source" that plugins can ask for):

* Derivative: *Normal*, *Integrate*.
* Filter: *Not Filtered*, *M.aver.* (moving average), *Sav.gol.* (Savitzky-Golay), with
  *Apply to* *Auto* / *First Dim* / *Second Dim* / *Both* and the filter time constant.

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
