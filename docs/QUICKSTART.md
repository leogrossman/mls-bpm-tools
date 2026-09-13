# Quickstart

## Read-Only Control-Room Use

```bash
git pull
python3 bpm_iq_viewer.py
```

The main window is a BPM picker:

1. Click a BPM marker in the top lattice strip, or double-click a BPM row.
2. A plot window opens and paints before the first EPICS read starts.
3. Use `Refresh now` to force a fresh read.
4. Use `Live` to keep reading periodically.
5. Use `BPM overlays` to add or toggle BPMs in that plot.

The top lattice strip can overlay basic beta-x/beta-y and Dx/Dy curves for standard user, low-alpha, and SSMB optics modes. Use it as the normal first navigation surface: click a BPM marker to open that BPM.

Use `Open lattice viewer` for the larger clickable lattice plot. It has the same optics modes with separate beta-x, beta-y, Dx, and Dy toggles.

## First Plot To Trust

The normal first plot is `all`. It opens raw magnitude, unwrapped phase, phase spectrum, and magnitude spectrum for:

1. `A+B+C+D`
2. `A`

This is the fastest way to see whether the BPM is returning useful raw complex data. Switch to `phase debug` only when you want to inspect the calculation steps:

1. `angle(z)`
2. unwrapped phase
3. detrended/windowed phase
4. PSD

## Signals

The default signals are:

- `A+B+C+D`
- `A`

Use the `Signals to plot` panel to add B/C/D, difference candidates, mean, or a custom expression. `Normalize spectra` and `Stack spectra` are on by default so overlaid spectra stay visible instead of covering each other.

Plot windows open on the `Signals` tab by default. Use the `Spectrum display` controls there to make overlaid spectra thinner, more transparent, or more separated. You can also drag a visible spectrum curve up/down to give that trace a manual log-scale offset. `Reset dragged offsets` clears those manual shifts.

The `BPMs` tab can add BPMs from the main-window selection or from other open plot windows, so two separate BPM views can be combined into one overlay plot.

Use the plot selector for focused views:

- `phase`: unwrapped phase plus phase spectrum.
- `magnitude`: raw magnitude plus magnitude spectrum.
- `spectra`: phase and magnitude spectra only.
- `phase debug`: wrapped phase, unwrapped phase, detrended/windowed phase, and PSD.

Use `Freq` to switch spectrum x axes and tune/peak listings between `kHz`, `Hz`, and fractional tune `Q=f/f_rev`.

Use `Refresh s` to control live update speed. The default is 3 seconds. Watch the `Load:` line in the plot window or the global `Performance:` line in the main window; if it says `LAGGING`, increase the interval, reduce active BPM overlays, or disable signals you do not need.

If the window is short, use the left-pane tabs: `BPMs`, `Signals`, `Analysis`, and `FFT / perf`. The BPM overlay list scrolls independently.

The `FFT / perf` tab explains the calculation from complex raw I/Q to phase and magnitude spectra, including `unwrap`, detrending, windowing, PSD, `df Hz`, and `max time points`. The tiny plots show the same pipeline visually. Keep these settings the same inside one plot window when comparing BPMs or signals; open another plot window if you want to compare a different FFT assumption.

## Tunes And Peaks

In a plot window, enable `Tunes` to read the configured tune PVs. Bad or out-of-range values are shown as errors in the side pane and are not drawn as plot markers. Harmonics are off by default; enable `Harmonics` and set `max harmonics` in the `Analysis` tab when you want them.

Enable sidebands in the `Analysis` tab to mark simple synchrotron/betatron mixing candidates `Qx +/- m Qz` and `Qy +/- m Qz`. These are guide markers, not fitted peaks.

The `Tune status / spectrum peaks` pane lists:

- tune PV read status and marker frequencies
- automatically detected phase/magnitude spectrum peaks
- the signal/BPM that produced each peak

## TBT Raw Logging

In normal mode, TBT write buttons are blocked. Use `TBT raw logging control...` for the safer workflow:

1. Load the current BPM selection, or click `Suggest burst BPMs` for a small SSMB-oriented high/low dispersion set.
2. Keep `max BPMs` small, usually 2-4 BPMs while other experiments are running.
3. Click `Check selected status` before changing anything.
4. Click `Preview start writes` and review every PV/value.
5. Use `Capture raw arrays now` or `Start capture series` to save read-only raw BPM data. This works in normal read-only mode.
6. Only in write-capable mode, turn on `Arm write mode`; the indicator turns red.
7. Click `Start selected with auto-stop`.
8. Confirm the EPICS writes in the warning dialog.
9. Verify that the auto-stop setting is short enough for the study.

The panel writes only the selected BPMs, unlike the original shell scripts which used `caput_many` broadly. The start command writes:

```text
{bpm}:signals:ddc_raw.SCAN
{bpm}:signals:ddc_synth.SCAN
```

Only with explicit operator agreement:

```bash
python3 bpm_iq_viewer.py --live --allow-writes
```

Start writes `"1 second"` and stop writes `"Passive"` to both raw and synth `.SCAN` PVs.

The `Suggest burst BPMs` button currently uses the built-in SSMB optics guide to choose a tiny mix of high-`|Dx|` BPMs and low-`|Dx|` reference BPMs. Treat it as a practical starting set for burst/longitudinal-phase studies, not a machine-approved optics table.

Read-only raw captures are saved here:

```text
.mls_bpm_local/logs/session_YYYYMMDD_HHMMSS/raw_bpm_logs/*.npz
```

Each file contains complex arrays, separate I/Q arrays, a sum phasor per BPM, and `metadata_json`.

## CSR / THz Bursting Analysis

Use `Bursting analysis...` after saving one or more raw captures. The analysis window is read-only and can load the latest `.npz` capture automatically.

Useful first pass:

1. Select `Sum phase` and compare two BPMs with coherence enabled by choosing BPM A and BPM B.
2. Look at the `1-200 kHz` spectrogram and band-power trace for intermittent activity.
3. Switch to `Horizontal diff/sum` and compare high-`Dx` and low-`Dx` BPMs.
4. Treat built-in dispersion checks as guides only until real low-alpha optics are imported.
5. Remember that BPMs measure centroids/moments; a null BPM result can still be compatible with internal microbunching seen by THz diagnostics.

More detail is in `docs/BURSTING_ANALYSIS.md`.

## If It Looks Blank

1. Select one known BPM, for example `BPMZ1L2RP`.
2. Click `Check TBT status`.
3. If `.SCAN` is `Passive`, raw arrays may not be updating.
4. Open `PV probe / edit IDs` and probe `BPMZ1L2RP:signals:ddc_raw.Ia`.
5. Check `.mls_bpm_local/logs/session_.../events.jsonl`.
