# Port status

## Done

**Viewer**:

* Main window layout, directory browser, favourite directories and plugins.
* Source / Output / transfer.
* Real / Re-Im / Magn; 1D / Stack / Contour / Density.
* 2D data: vertical slice slider, X / Y slice direction, mouse wheel and Ctrl+U / Ctrl+D
  slice stepping, Cut Slice, Fix Source Processing.
* Parameter row; zoom, measure and axis buttons.
* Font: every control, menu and plugin window follows *View > Font*; in the viewer window
  it also scales with the window size.
* Grid, minor grid, Aspect Normal / Square / Axis Equal, Select View Area.
* File: Save Source (ASCII, SpecMan `.d01`, Bruker `.dsc` / `.par`, WinSIM `.lmb`),
  Convert Folder to ASCII, Export / Load Workspace (a Python console).
* Help menu.
* Window: New Window, Show in Window, Plot 1D (figures, subplots), Plot 2D (Surf,
  Scatter3, Surface), drawn with matplotlib.
* Trace styles: Color / LineStyle / LineWidth / Marker, as in SuperPlot.
* Kazan3's orange "on" state for all toggle buttons (`UpdateStateButtons`, [1 0.65 0.2]).
* `ax.dx` / `ax.dy` axis corrections applied when plotting, as in MATLAB `getplotaxis`.
* Processing: RC filter and pseudo-modulation (PS,mod), besides M.aver., Sav.gol. and
  Integrate.
* View parameters (`ps_mod`, `tc`, `contour`, styles, ...) and parameter locking.
* X / Y axis representations: points, reverse, log, g-factor, ppm.
* ESP pulse (JSS 32) axes.

**Plugins**: SYMMETRIZE, CWPLUGIN3, FITPLUGIN3, MATHPLUGIN3, COMPBOX3, MINUSBOX3,
DESCRIPTION3, TRANSIENT3, RAPIDSCAN3, NOISE3, CWMH3, ANLPLG3. See [plugins.md](plugins.md).

**Loaders**: all Kazan3 loaders with MATLAB source, plus loader options. See
[loaders.md](loaders.md).

## Not ported yet

* **Loaders**: UofC_bin, UofC_img, WEBMOSS, transient, RMNdat2D (no MATLAB source or
  helpers). See [loaders.md](loaders.md).
* **Plugins**: SIMPLUGIN3 (needs EasySpin); CWPLUGIN3 LW-Md (unfinished in
  MATLAB).
