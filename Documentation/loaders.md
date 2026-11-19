# File formats

| Data type | Files | Code |
|---|---|---|
| ASCII | text columns (first column x) | `kazan/io/loaders.py` |
| SpecMan | `.tdms` (also interleaved TDMS) | `kazan/io/specman.py` |
| SpecMan | `.d01` / `.exp`, with a `.bip` sidecar | `kazan/io/specman.py` |
| XEPR | Bruker `.DSC` / `.DTA` | `kazan/io/bruker.py` |
| ESP / WinEPR | `.par` / `.spc` | `kazan/io/bruker.py` |

Common parameters such as the microwave frequency, title, sample and comment are read
from the description by `kazan/io/params.py`. Field names in `ax` and `dsc` match MATLAB,
because plugins read them (`ax.raw`, `ax.data`, `dsc.RS_Frequency`, ...).

## Differences from the MATLAB loaders

* Repeated TDMS scans average all columns. MATLAB divided only the last one.
* Incomplete TDMS scans load, padded with zeros, and a message goes to the log. MATLAB
  failed.
* A `.d01` file whose header size does not match the data is read as 1D.
* A scan count of 0 leaves the data unscaled.
* `to` and `step` in parameter values are not taken as units.

## Not ported yet

ASCII2D, RMN, NIST, SpecManFLD / RAW and the other loaders; loader options.
