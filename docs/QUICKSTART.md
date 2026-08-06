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

Use the plot selector for focused views:

- `phase`: unwrapped phase plus phase spectrum.
- `magnitude`: raw magnitude plus magnitude spectrum.
- `spectra`: phase and magnitude spectra only.
- `phase debug`: wrapped phase, unwrapped phase, detrended/windowed phase, and PSD.

Use `Freq` to switch spectrum x axes and tune/peak listings between `kHz`, `Hz`, and fractional tune `Q=f/f_rev`.

Use `Refresh s` to control live update speed. The default is 3 seconds. Watch the `Load:` line in the plot window or the global `Performance:` line in the main window; if it says `LAGGING`, increase the interval, reduce active BPM overlays, or disable signals you do not need.

If the window is short, use the left-pane tabs: `BPMs`, `Signals`, `Analysis`, and `FFT / perf`. The BPM overlay list scrolls independently.

## Tunes And Peaks

In a plot window, enable `Tunes` to read the configured tune PVs. Bad or out-of-range values are shown as errors in the side pane and are not drawn as plot markers. Enable `Harmonics` to draw valid harmonic markers.

The `Tune status / spectrum peaks` pane lists:

- tune PV read status and marker frequencies
- automatically detected phase/magnitude spectrum peaks
- the signal/BPM that produced each peak

## TBT Raw Logging

In normal mode, TBT write buttons are blocked. Use `Check TBT status` to read:

```text
{bpm}:signals:ddc_raw.SCAN
{bpm}:signals:ddc_synth.SCAN
```

Only with explicit operator agreement:

```bash
python3 bpm_iq_viewer.py --live --allow-writes
```

Start writes `"1 second"` and stop writes `"Passive"` to both raw and synth `.SCAN` PVs.

## If It Looks Blank

1. Select one known BPM, for example `BPMZ1L2RP`.
2. Click `Check TBT status`.
3. If `.SCAN` is `Passive`, raw arrays may not be updating.
4. Open `PV probe / edit IDs` and probe `BPMZ1L2RP:signals:ddc_raw.Ia`.
5. Check `.mls_bpm_local/logs/session_.../events.jsonl`.
