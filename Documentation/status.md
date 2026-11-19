# Port status

## Done

**Viewer**:

* Main window layout, directory browser, favourite directories and plugins.
* Source / Output / transfer.
* Real / Re-Im / Magn; 1D / Stack / Contour / Density; slice slider.
* Parameter row; zoom, measure and axis buttons.
* Processing context menu: M.aver., Sav.gol., Integrate.
* Font and grid.
* Trace styles: Color / LineStyle / LineWidth / Marker, as in SuperPlot.
* Kazan3's orange "on" state for all toggle buttons (`UpdateStateButtons`, [1 0.65 0.2]).
* `ax.dx` / `ax.dy` axis corrections applied when plotting, as in MATLAB `getplotaxis`.

**Plugins**: SYMMETRIZE, CWPLUGIN3, FITPLUGIN3, MATHPLUGIN3, COMPBOX3, MINUSBOX3,
DESCRIPTION3, TRANSIENT3, RAPIDSCAN3, NOISE3, CWMH3, ANLPLG3. See [plugins.md](plugins.md).

**Loaders**: all Kazan3 loaders with MATLAB source, plus loader options. See
[loaders.md](loaders.md).

## Not ported yet

* **Viewer**: RC filter, pseudo-modulation, parameter locking, X/Y axis representation
  menus, ESP pulse (JSS 32) axes.
* **Loaders**: UofC_bin, UofC_img, WEBMOSS, transient, RMNdat2D (no MATLAB source or
  helpers). See [loaders.md](loaders.md).
* **Plugins**: SIMPLUGIN3 (needs EasySpin); CWPLUGIN3 LW-Md (unfinished in
  MATLAB).
