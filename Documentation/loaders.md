# File formats

Pick the file extension and the data type (loader) above the file list. Some loaders
have options. Kazan3 shows them under the file list: up to two drop-downs and a text
field. Option choices are remembered per data type, and the load script (*Tools > Show
Load Script*) records them.

| Data type | Files | Code | Tested on |
|---|---|---|---|
| ASCII | text columns | `kazan/io/ascii.py` | real files |
| ASCII2D | one value per line, reshaped to 2D | `kazan/io/ascii.py` | synthetic file |
| XEPR | Bruker `.DSC` / `.DTA`, ESP / WinEPR `.par` / `.spc` | `kazan/io/bruker.py` | real files |
| XEPR_JSS | old ESP `.par` / `.spc` with JSS axes | `kazan/io/bruker.py` | synthetic files |
| ASTASHKIN | `.par` + `.dat` | `kazan/io/other.py` | real files |
| SpecMan | `.tdms`, `.d01` / `.exp` (+ `.bip`) | `kazan/io/specman.py` | real files |
| SpecManNIST | `.d01` / `.exp`, NIST field-meter variant | `kazan/io/specman.py` | real file, no field meter |
| SpecManFLD | `.d01` / `.exp`, measured field axis | `kazan/io/specman.py` | real file, no field meter |
| SpecManRAW | `.d02` (every scan) + `.exp` | `kazan/io/specman.py` | not tested |
| RMN_1D / RMN_2D | `.rmn` binary | `kazan/io/nmr.py` | synthetic files |
| RMNdat | `.dat` text, re / im interleaved | `kazan/io/nmr.py` | synthetic file |
| XWINNMR | Bruker NMR folder (`fid`, `ser` or `procs`) | `kazan/io/nmr.py` | synthetic `fid` |
| WINNMR | `.aqs` + `.1r` / `.1i` | `kazan/io/nmr.py` | synthetic files |
| TecMag | TecMag binary | `kazan/io/nmr.py` | synthetic file |
| Spinsight | Spinsight folder (`acq`, `data`) | `kazan/io/nmr.py` | synthetic files |
| OPUS_FTIR | Bruker OPUS FT-IR | `kazan/io/other.py` | not tested |
| image | `.jpg` and other images (grey levels) | `kazan/io/other.py` | real files |

"Synthetic" means a file written by the test following the MATLAB reader. That checks
the port reads what the MATLAB code read, but not that the MATLAB code matched every
real instrument file.

Common parameters such as the microwave frequency, title, sample and comment are read
from the description by `kazan/io/params.py`. Field names in `ax` and `dsc` match MATLAB,
because plugins read them (`ax.raw`, `ax.data`, `dsc.RS_Frequency`, ...).

## Loader options

* **ASCII**
  * Delimiter: tab, space, `,` or `;`.
  * Column layout:
    * `Y`, `rY, iY`
    * `X,Y`, `X,Y1,Y2,Y3..`
    * `X,(rY,iY)n` - pairs
    * `X,(rY)n,(iY)n` - first half real, second half imaginary
    * `idx, X, Y`, `idx, X, rY, iY`
  * Text field: the X axis label, used when the file has none.

  Lines that are not data go to the description (`c1`, `c2`, ...). The footer that
  Kazan Viewer 3.0 writes when saving ASCII restores the axis fields.
* **ASCII2D** - complex (re, im interleaved) or real values. Text field: `xsize ysize
  [xdwell ydwell cfreq]`. Odd sizes give centred frequency axes, even sizes time axes.
* **SpecMan** (`.tdms`, `.d01`) - *Streams*:
  * *Re + i Im* (default, as in Kazan3): the first two streams form one complex signal.
  * *All streams (2D)*: every stream is a real trace, so the slider steps through them;
    the label under the plot names the stream and its channel (e.g. `c: C1_H3I`).
    Use it for files with more than two streams, such as the 10-harmonic CW files,
    where the second stream is the second harmonic, not the imaginary part.

  All streams are also in `ax.raw` (points x slices x streams) for plugins (CWMH3).
* **RMN_2D** - axis types: D1 / D2 time or frequency.
* **OPUS_FTIR** - interferogram, baseline (fft) or data - baseline (fft).

## Differences from the MATLAB loaders

General:

* Repeated TDMS scans average all columns. MATLAB divided only the last one.
* Incomplete TDMS scans load, padded with zeros, and a message goes to the log. MATLAB
  failed.
* A `.d01` file whose header size does not match the data is read as 1D.
* TDMS: the time axis is labelled `Time, s` (MATLAB took the first stream name, giving
  `a, s`), and `ax.raw` is an array in the `.d01` layout (MATLAB: a cell array, which
  CWMH3 could not read).
* A scan count of 0 leaves the data unscaled.
* `to` and `step` in parameter values are not taken as units.

ASCII:

* The option text field starts with its default (`Time, s`) instead of empty.
* ASCII2D has real options. MATLAB's script referred to option controls that did not
  exist and to an undefined variable, so it failed.

Other formats:

* **RMN_2D**: the second axis uses its own type (MATLAB used the first axis's type for
  both), and its label no longer overwrites the first axis's label.
* **ASTASHKIN**: the data are reshaped to the X x Y sizes from the parameter file.
  MATLAB returned one long vector.
* **SpecManFLD**: works when the field stream differs in size from the data. MATLAB
  indexed stream 0 and failed.
* **TecMag**: all records are read (MATLAB failed for more than one record).
* **Spinsight**: dwell times like `2u` are read as 2 us, and the time axis is in
  seconds.
* **ESP pulse (JSS 32) axes** (XEPR and XEPR_JSS): the `Psd5` / `XPD9` pulse tables are
  read as number lists (MATLAB converted them with `str2double`, which gave NaN, so
  the time axes failed), and the *Time* axis uses the step it finds (MATLAB stored it in
  the wrong field).

## Not ported

These have no MATLAB source, or need helpers that are not available:

* **UofC_bin** - needs `read_bin_spectrum`.
* **UofC_img** - needs `epr_ReadCWImageHeader` and more.
* **WEBMOSS** (`kv3_moss_webbin`), **transient** (`kv3_ESPtransreadsdsfi`).
* **RMNdat2D** - no loader in the MATLAB script.
* XWINNMR folders with only `acqp` - MATLAB's `readAcqp` is missing.
