# MLS BPM I/Q Viewer

Control-room safe viewer for MLS BPM turn-by-turn raw DDC data. It reads each BPM as four complex button signals `A`, `B`, `C`, and `D`, then lets you inspect raw traces, phase/amplitude, spectra, tune markers, and BPM overlays.

## Start Here

Normal control-room read-only start:

```bash
git pull
python3 bpm_iq_viewer.py
```

No plot opens automatically. Click a BPM marker in the top lattice strip or double-click a BPM row to open a viewer. Machine writes are blocked unless you explicitly run `python3 bpm_iq_viewer.py --live --allow-writes`.

For offline development with synthetic data:

```bash
python3 bpm_iq_viewer.py --demo
```

## What Is In This Repo

- `bpm_iq_viewer.py`: Tkinter GUI, EPICS Channel Access backend, logging, and app entry point.
- `bpm_core.py`: GUI-free data model, PV naming, signal combinations, phase/spectrum math, and demo backend.
- `bpm_config.json`: BPM list, PV templates, tune/status PVs, and TBT start/stop values.
- `scripts/starttbt`, `scripts/stoptbt`: copies of the old control-room TBT scripts.
- `test_bpm_iq_viewer.py`: offline unit tests, including a real control-room raw snapshot regression.
- `FEATURE_TRACKER.md`: implemented, partial, and pending feature tracker.
- `docs/QUICKSTART.md`: operator-oriented GUI workflow.
- `docs/THEORY.md`: signal, phase, spectrum, and phase-space notes.
- `docs/REFERENCE.md`: PVs, CLI flags, logging, testing, and extension notes.

## Current Safe Defaults

- `python3 bpm_iq_viewer.py` uses live EPICS reads and blocks all writes.
- TBT start/stop buttons only write in `--live --allow-writes`, after a confirmation dialog.
- Optional tune/noise/status PVs are not read on startup.
- Plot windows default to the `all` view with `A+B+C+D` first, then `A`; this shows raw magnitude, phase, phase spectrum, and magnitude spectrum.
- Spectrum traces are normalized and visually stacked by default so multiple BPMs/signals can be compared without one trace hiding the rest.
- The plot side pane lists tune PV status, valid tune/harmonic markers, and automatically detected spectrum peaks in the selected frequency units.
- Live plots default to a 3 second refresh and show a load/performance line with PV count, sample count, processed bytes, elapsed time, and lag status.
- Recent raw BPM reads are cached briefly inside each plot window to avoid repeated EPICS reads during UI-only redraws.
- Plot controls are grouped into left-pane tabs; raw time traces are display-decimated while FFTs still use full-resolution data.

## Tests

```bash
MPLCONFIGDIR=/tmp/mls-bpm-tools-mpl python3 -m unittest discover -v -p 'test_*.py'
```

The tests cover PV command generation, expression parsing, phase unwrap, MATLAB-style phase spectrum, FFT settings, tune markers, and a real `BPMZ1L2RP` control-room snapshot.
