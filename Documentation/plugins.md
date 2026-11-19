# Plugins

Each plugin opens from the *Plugins* menu in its own window. It works on the viewer's
source and writes its results to the viewer's Output. Indices shown to the user are
1-based, as in MATLAB.

Each section ends with the differences from MATLAB Kazan3. Most of them are MATLAB bugs
that were fixed.

- [SYMMETRIZE](#symmetrize)
- [CWPLUGIN3](#cwplugin3) - CW spectra
- [FITPLUGIN3](#fitplugin3) - script fitting
- [MATHPLUGIN3](#mathplugin3) - data manipulation
- [COMPBOX3](#compbox3) - comparison box
- [MINUSBOX3](#minusbox3) - reference arithmetic
- [DESCRIPTION3](#description3) - file description and pulse sequence
- [TRANSIENT3](#transient3) - 2D transients
- [RAPIDSCAN3](#rapidscan3) - rapid scan

---

## SYMMETRIZE

Mirrors the source around a symmetry centre. Output: source (red), flipped (blue) and
their average (green).

## CWPLUGIN3

Processing of a CW trace in three steps, plus line-width analysis:

1. **Baseline** - none, constant, linear, or a polynomial of order 3/4/5, fitted to the
   selected range.
2. **Phase** - zero-order phase.
3. **Filter**.

Then:

* **Conversion** between absorption, derivative and integral.
* **Integration** of the processed spectrum.
* **Line-width fits**: LW-L (Lorentzian), LW-G (Gaussian), LW-V (Voigtian) over the
  selected range, plus LWhh (half-height width) and LWpp (peak-to-peak width).

Differences from MATLAB:

* 2D data: the current viewer slice is processed. MATLAB assumed 1D data.
* LW-L and LW-G report the integral of the fitted line. MATLAB printed the start value.
* LW-V fits the selected range only. LWhh uses range indices consistently.
* The start widths for the fits come from the measured peak-to-peak or half-height
  width. MATLAB used range/5, which diverges for narrow lines.
* Baseline buttons 3/4/5 select polynomial baselines of that order. In MATLAB they did
  nothing.
* LW-Md (spin-probe model fit) is unfinished in MATLAB and disabled here.

## FITPLUGIN3

Fits a user script to the current slice. A script looks like this:

```
f = a*exp(-x/t)
a = 1
t = 2e-6
```

With *Fit > Fit All*, every slice gets its own script. Output shows the source (blue or
a chosen colour), ignored points (grey dots), the fit (red) and the difference (green).

* *Simulation > Fit Function ...* edits the model. Presets: EPR/MRI, line shapes,
  polynomials.
* The fit range is built with the add / remove / clear range buttons, picking two points
  on the viewer plot.
* Values and functions can be edited in the script list; the context menu has more
  options.
* *Source processing* fits the processed source. *Show Difference* and *Show Range*
  control the output.

Differences from MATLAB:

* *Fit Function ...* opens a plain script editor. MATLAB used the external
  `fittingbox_func` dialog, which is not part of Kazan3.
* Single-slice mode plots the current viewer slice with its fit. MATLAB fitted the
  viewer slice but plotted all slices, and their difference against that one fit.
* *Enter Expression* asks for an expression. MATLAB inserted the constant 125.
* The source shown honours *Source processing*. MATLAB always plotted the raw source.
* After a coefficient of an `exppolyfit` result is edited by hand, the curve is
  re-evaluated without the fitted shift, so it is slightly off.

## MATHPLUGIN3

Simple manipulation of the source, applied in this order:

1. **Part** - as is / real / imag / abs.
2. **Cut Data** - point ranges in both dimensions, or (*eval*) a MATLAB index expression
   for the second dimension (`[5,8,9]`, `1:2:end`). *Reset* restores the full ranges.
3. **Transpose**.
4. **sum(y,2)** - sum over the second dimension.
5. **Phase** - zero order, first order around a pivot point, and *dt*, a first-order
   phase that changes from slice to slice. The x0.1 / x1 / x10 buttons set the spinner
   step.

Differences from MATLAB:

* The point ranges start as the full data. MATLAB set them to 1..1, so *Cut Data* first
  showed a single point.
* The second-dimension expression accepts MATLAB index syntax only, not a general `eval`.

## COMPBOX3

Comparison box. It collects snapshots of the viewer source as traces and shows them
together in Output. Each trace has its own colour, X/Y shift, X/Y zoom (linear or dB)
and sign.

*Processing* menu:

* Normalize the current trace, all traces, or the slices of 2D data.
* Fit traces to the first one.
* Waterfall.
* Add Current To Output; Add All (sum of all traces).
* Join Traces into a 2D set (spline onto a common axis); Ungroup 2D data.
* Sort By Y Value.

Differences from MATLAB:

* *Join Traces*, *Ungroup Data*, *Add Current To Output* and *Normalize Current 2D*
  work. In MATLAB they called undefined functions or fields and failed.
* *Add All* and *Join Traces* also apply Zoom X and dB zoom, as the plot does.
* *Change* keeps the colour of the trace. *Delete* / *Delete All* refresh the Output.
* The second-dimension field is editable. It sets the trace's Y axis value, which *Sort
  By Y Value* and *Join Traces* use.
* The trace list shows the file name without the folder.

## MINUSBOX3

Arithmetic between a reference and the current data:

```
Result = Reference (+ - .* ./) CurData(x*ZoomX + ShiftX)*ZoomY + ShiftY
Result = CurData(x*ZoomX + ShiftX)*ZoomY + ShiftY        ("Res = Zoom*Src+Shift")
```

* **Set as reference** stores the current source. The button turns lilac when a
  reference is set.
* Shift X/Y and Zoom X/Y have step selectors and Reset buttons. **-> Ref.** copies the
  current settings to the reference.
* With 2D data, the slice selector sets Zoom Y / Shift Y per slice (*All* sets them for
  every slice).
* When the X axes differ, both traces are spline-interpolated onto their common range.
* *Shift result* and *Inverse result* shift and invert the result.
* *View* menu: show the reference, trace 2 and the result.

Differences from MATLAB:

* Shift Y is applied per slice. MATLAB used the first slice's shift for all slices.
* *Reset* of the shift sets it to 0. MATLAB set 1.
* The current data is always the raw source. MATLAB switched to the processed source
  when *Show Reference* was checked.
* A 1-slice reference with 2D current data works for every slice. In MATLAB the
  per-slice settings only covered the reference's slices.

## DESCRIPTION3

Lists every field of the source description as `name   value`; nested groups show as
`group-field`. The window title is the file name, and the list refreshes when another
file is loaded.

**Sequence** draws the pulse sequence in a separate window: Bruker XEPR files from
`Psd1..36`, ESP files from `XPD1..16`. Each channel gets a row with its name, and each
pulse is labelled with its length.

Differences from MATLAB:

* Values are printed correctly. MATLAB's formatting turned numeric values into odd
  characters.
* Each channel of the sequence plot has one colour. MATLAB changed colour on every
  segment.
* Channels without pulses get no (empty) row.

## TRANSIENT3

For 2D transient data (field x time). *Transpose* (on by default) puts the field on the
first dimension. The *field / time pts* box shows the data size.

Processing, in order:

1. The **dark signal** (mean over the *Dark signal* time points) is subtracted from every
   transient.
2. **Smooth** (No / 3 / 5 / 10) applies Savitzky-Golay smoothing in time.
3. **Inv** inverts the data.

The point ranges are typed as *Start* / *End* point numbers; the labels show them in
time units. Changes apply with **Calculate**. The smoothing, baseline and *Show Fit*
buttons apply at once.

**Field domain** (default):

* Output is the mean over the *Signal* time points, plotted against field.
* A baseline of order No / 0 / 1 / 2 / 3 is fitted to the field **Range** (black
  circles in the plot) and subtracted. The range starts as the first 10 and last 11
  points; *Add* / *Remv* change it by picking two points on the viewer plot.
* **Show Fit** draws the baseline (green) instead of subtracting it; a red hint says so.
* **Show src** adds the unsmoothed data (red).

**Time domain** (click *Switch to Time*):

* Mark a field first, with the cross next to *Switch to Time*, while in the field domain.
* Output is the transient at the marked field, minus the mean transient of the baseline
  range (the off-resonance fields). The signal (green) and dark (black) regions are
  marked.
* The crosses next to the *Signal* and *Dark signal* fields pick those ranges on the
  plot.

*Update when file changes* recalculates when a new file is loaded.

Differences from MATLAB:

* The baseline is fitted only when the range has more than 3 points. MATLAB tested the
  length of the mask, so a near-empty range gave NaN.
* All time-domain outputs are labelled with the time axis. MATLAB kept the field label on
  two of them.
* The cross buttons are enabled for the current domain from the start.

## RAPIDSCAN3

Sinusoidal rapid-scan EPR. The scan frequency, scan width and sampling are read from the
file description. Supported sources: SpecMan JIVA25 (`SCAN_Frequency1`,
`SCAN_AmplitudePP1`, `DG_Sampling`), Eclypse FPGA (`RS_Frequency` / `RS_RSFrequency`),
`aliases_RS*`, and Denver files.

Pick a mode in *Processing* and press **Go!**. Any change of a setting also reprocesses.

* **As is** - one scan cycle of every trace, circularly shifted by the *Scan phase*.
  Output is the sum of the cycle and its time-reversed copy; *A and B* in the visual
  list also shows both halves. *Use filter* applies a Butterworth low-pass filter with
  the given cutoff. *B mapping* plots against the sinusoidal field.
* **Find Time** - the data against a cosine at the scan frequency. Use it to adjust the
  *Scan phase* and the *Time factor*.
* **Deconvolve (new)** - deconvolution with background removal (`sinDecoBG`, M.
  Tseytlin, University of Denver). It gives the up-scan (A) and down-scan (B) spectra
  against field. The visual list selects *Sum* (A+B), *A and B*, or the interleaved cycle
  before (*Interleave-1*) or after (*Interleave-2*) the RF phase. Check **auto** to
  estimate the scan phase; the result goes into *Scan phase*.
* **Baseline** - fits a sinusoidal background `a cos + i b sin + offset` to the first
  trace and shows the amplitude and offsets on the *Tab* page.

Other controls:

* *Use phase* / *Phase* - RF phase.
* */\ or \/* - direction of the first half-scan.
* *Factor* x0.001 ... x10 - spinner step.
* *Compensation* tab - *Scan factor* and *Time factor* correct the scan width and the
  sampling.
* **Script** shows Python code for the current deconvolution on the *Tab* page.
* *Update* reprocesses when a new file is loaded.

Differences from MATLAB:

* The Filter, BL, Nharm and dB controls failed in MATLAB (their callbacks passed too
  many arguments); they reprocess now. The *Linear* tab controls have no effect; the
  linear-scan code was unreachable in MATLAB too.
* *auto* stores the scan phase it actually applied. MATLAB stored it with the opposite
  sign, so switching *auto* off reprocessed with the wrong phase.
* *Update* works. MATLAB's `FileUpdate` was empty.
* *Script* shows a Python script instead of printing a MATLAB one. Outputs get a field
  label.
* The `aliases_RS*` and Denver parameter branches referred to an undefined variable and
  failed; they work now.
